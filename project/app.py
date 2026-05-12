"""案件智能分析台 Web 应用 - Flask 后端（v2: 模糊搜索 + 页码定位）"""

import csv
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from flask import Flask, Response, jsonify, request, render_template, send_file, stream_with_context
from ai_services import (
    AIClient,
    AIServiceError,
    AIStore,
    now_iso,
    run_job_background,
    simulate_analysis_job,
)
from graphrag_pipeline import (
    build_graphrag_index,
    format_graphrag_context,
    graphrag_index_path,
    load_graphrag_index,
    retrieve_graphrag,
    run_graphrag_job,
)
from analysis_pipeline import run_analysis_job
from material_pipeline import run_material_job, parse_full_directory, classify_evidence_type
from mineru_client import MinerUClient
from auto_material_pipeline import AutoMaterialPipeline

app = Flask(__name__)
app.json.ensure_ascii = False  # 禁止 Unicode 转义，确保中文可读

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 请求编码修复：Windows 终端（GBK）中文参数 → UTF-8
# ---------------------------------------------------------------------------
from urllib.parse import parse_qs as _parse_qs, unquote_plus as _unquote_plus
from flask import g as _g

def _query_string_contains_non_ascii(qs_bytes: bytes) -> bool:
    """检测原始 query string 是否包含非 ASCII 字节（可能有中文）。"""
    return any(b > 127 for b in qs_bytes)

def _bytes_looks_like_gbk(qs_bytes: bytes) -> bool:
    """粗糙判断：是否可能是 GBK 而非 UTF-8（以 GBK 双字节序列为特征）。"""
    try:
        text = qs_bytes.decode("gbk")
        return any("一" <= c <= "鿿" or "㐀" <= c <= "䶿" for c in text)
    except (UnicodeDecodeError, ValueError):
        return False


def _string_has_cjk(text: str) -> bool:
    """字符串是否包含 CJK 统一汉字（U+4E00–U+9FFF）。"""
    return any("一" <= c <= "鿿" for c in text)

def _try_fix_query_string(qs_bytes: bytes) -> dict | None:
    """尝试将 GBK 编码的查询字符串修复为 UTF-8 键值对。"""
    try:
        fixed_text = qs_bytes.decode("gbk")
        # 用 parse_qs 解析，返回 {key: [value1, ...]} → {key: value}
        parsed = _parse_qs(fixed_text, keep_blank_values=True)
        return {k: v[0] if v else "" for k, v in parsed.items()}
    except Exception:
        return None

@app.before_request
def _fix_request_encoding():
    """检测并修复因 Windows 终端 GBK 编码导致的中文查询参数乱码。
    同时修复 POST JSON body 中的 GBK 编码（curl on Windows bash 常见问题）。"""
    # ---- GET query string ----
    qs = request.query_string
    if qs and isinstance(qs, bytes) and _query_string_contains_non_ascii(qs):
        try:
            qs.decode("utf-8")
        except UnicodeDecodeError:
            if _bytes_looks_like_gbk(qs):
                fixed = _try_fix_query_string(qs)
                if fixed:
                    _g._fixed_args = fixed

    # ---- POST JSON body ----
    if request.method in ("POST", "PUT") and request.content_type and "application/json" in request.content_type:
        body = request.get_data()
        if not body or not _query_string_contains_non_ascii(body):
            return
        # 关键难点：GBK 中文字节序列可能是合法的 UTF-8（只是解出错误字符）。
        # 例如"张三" GBK=D6 EC CF BC CF BC，UTF-8 不会报错而是解出 Ƭϼϼ。
        # 策略：对比 UTF-8 和 GBK 两种解码，GBK 产出中文且 UTF-8 没有中文 → 判定为 GBK。
        utf8_text = None
        try:
            utf8_text = body.decode("utf-8")
        except UnicodeDecodeError:
            pass  # UTF-8 直接拒绝 → 继续尝试 GBK
        if utf8_text is not None and _string_has_cjk(utf8_text):
            return  # UTF-8 解码已含中文 → 正常
        # UTF-8 没有中文（或解不了）→ 尝试 GBK
        if _bytes_looks_like_gbk(body):
            try:
                fixed_text = body.decode("gbk")
                request._cached_data = fixed_text.encode("utf-8")
                request.environ["CONTENT_LENGTH"] = str(len(request._cached_data))
            except Exception:
                pass

def _get_arg_fixed(key: str, default: str = "") -> str:
    """获取查询参数，优先从 request.args，若乱码则回退到 GBK 修复版本。"""
    val = request.args.get(key, default)
    if val and val != default:
        # 检测乱码特征：值中含有 U+FFFD 或孤立的高位 Latin-1 字节
        if "�" in val or any(
            0x80 <= ord(c) <= 0xA0 and c != "\xa0" for c in val
        ):
            fixed_args = getattr(_g, "_fixed_args", None)
            if fixed_args:
                fixed_val = fixed_args.get(key)
                if fixed_val:
                    return fixed_val
    return val


def _env_path(name, default=None):
    """读取目录环境变量；相对路径按当前项目目录解析。"""
    raw_value = os.environ.get(name, "")
    if raw_value:
        path = Path(raw_value)
    elif default is not None:
        path = Path(default)
    else:
        return ""
    if not path.is_absolute():
        path = (BASE_DIR / path).resolve()
    return str(path)


DATA_DIR = _env_path("DATA_DIR", BASE_DIR / "data")
RECORDS_ROOT = _env_path("RECORDS_ROOT")
AI_STORE = AIStore(BASE_DIR)
TRASH_DIR = BASE_DIR / "runtime" / "trash"
TRASH_RETENTION_DAYS = 7
WORKSPACE_DIR = Path.home() / "Desktop" / "案件笔录工作区"
WORKSPACE_SUBDIRS = ["外置Agent结果", "双面打印PDF"]


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------

def _run_tk_dialog(dialog_fn):
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        root.update()
        return dialog_fn(root) or ""
    finally:
        root.destroy()


def pick_local_file(title="选择文件", filetypes=None):
    from tkinter import filedialog

    return _run_tk_dialog(
        lambda root: filedialog.askopenfilename(
            parent=root,
            title=title,
            filetypes=filetypes or [("所有文件", "*.*")],
        )
    )


def pick_local_directory(title="选择文件夹"):
    from tkinter import filedialog

    return _run_tk_dialog(
        lambda root: filedialog.askdirectory(
            parent=root,
            title=title,
            mustexist=False,
        )
    )


def open_local_path(path):
    os.startfile(str(path))


@app.route("/api/system/pick-file", methods=["POST"])
def api_pick_file():
    payload = request.get_json(silent=True) or {}
    kind = payload.get("kind", "")
    filetypes = [("所有文件", "*.*")]
    if kind == "pdf":
        filetypes = [("PDF 文件", "*.pdf"), ("所有文件", "*.*")]
    try:
        path = pick_local_file(title=payload.get("title") or "选择文件", filetypes=filetypes)
    except Exception as exc:
        return jsonify({"error": f"打开文件选择窗口失败: {exc}"}), 500
    return jsonify({"path": path, "cancelled": not bool(path)})


@app.route("/api/system/pick-directory", methods=["POST"])
def api_pick_directory():
    payload = request.get_json(silent=True) or {}
    try:
        path = pick_local_directory(title=payload.get("title") or "选择文件夹")
    except Exception as exc:
        return jsonify({"error": f"打开文件夹选择窗口失败: {exc}"}), 500
    return jsonify({"path": path, "cancelled": not bool(path)})

def _resolve_file_path(record, case_data):
    """根据笔录记录和案件数据，解析出实际文件的绝对路径。"""
    file_path = record.get("文件路径", "")
    if not file_path:
        return None

    file_path_obj = Path(file_path)
    if not file_path_obj.is_absolute():
        base_dir = case_data.get("笔录目录", "")
        base_dir_obj = Path(base_dir) if base_dir else Path(DATA_DIR)
        if not base_dir_obj.is_absolute():
            base_dir_obj = (BASE_DIR / base_dir_obj).resolve()
        file_path_obj = base_dir_obj / file_path_obj

    if RECORDS_ROOT:
        file_path_obj = Path(RECORDS_ROOT) / file_path_obj.parent.name / "full.md"
    return str(file_path_obj)


def _get_record_content(record, case_data):
    """优先返回 JSON 内嵌全文，其次读取外部全文文件。"""
    content = record.get("全文内容", "")
    if content:
        return content
    return _read_content(_resolve_file_path(record, case_data)) or ""


def _load_page_source_content(record, case_data):
    """分页读取优先使用磁盘原文，缺失时退回 JSON 内嵌全文。"""
    file_content = _read_content(_resolve_file_path(record, case_data))
    if file_content:
        return file_content
    return record.get("全文内容", "")


def _normalize_indictment_data(case_data):
    """兼容新版与旧版起诉书数据结构，统一为前端可直接使用的格式。"""
    raw = case_data.get("起诉书") or case_data.get("起诉意见书") or {}
    if not isinstance(raw, dict):
        raw = {}

    # 新版格式：{"has_content": true, "content": "...", "structured": {...}}
    if "content" in raw or "structured" in raw or "has_content" in raw:
        content = raw.get("content", "") or raw.get("原文", "")
        structured = raw.get("structured", {}) if isinstance(raw.get("structured"), dict) else {}
        merged = {
            "案件编号": structured.get("案件编号") or raw.get("案件编号", ""),
            "案件名称": structured.get("案件名称") or raw.get("案件名称", ""),
            "当事人": structured.get("当事人") or structured.get("犯罪嫌疑人") or [],
            "罪名": structured.get("罪名") or structured.get("指控罪名") or "",
            "案件事实": structured.get("案件事实") or structured.get("犯罪事实") or raw.get("案件事实", ""),
            "涉案金额": structured.get("涉案金额") or raw.get("涉案金额", ""),
            "其他关键信息": structured.get("其他关键信息") or raw.get("其他关键信息", ""),
            "证据列表": structured.get("证据列表") or raw.get("证据列表", []),
            "适用法律": structured.get("适用法律") or raw.get("适用法律", []),
            "文书类型": structured.get("文书类型") or raw.get("文书类型", ""),
        }
        has_content = bool(raw.get("has_content")) or bool(content) or any(merged.values())
        return {
            "has_content": has_content,
            "content": content,
            "structured": merged,
        }

    # 旧版技能格式：{"原文": "...", "案件编号": "...", "犯罪嫌疑人": [...], ...}
    suspects = raw.get("犯罪嫌疑人", [])
    parties = []
    if isinstance(suspects, list):
        for item in suspects:
            if isinstance(item, dict):
                name = item.get("姓名", "")
                if name:
                    parties.append(name)
            elif item:
                parties.append(str(item))

    charges = raw.get("指控罪名", [])
    if isinstance(charges, list):
        charges_text = "；".join(str(item) for item in charges if item)
    else:
        charges_text = str(charges or "")

    evidences = raw.get("证据列表", [])
    laws = raw.get("适用法律", [])
    content = raw.get("content", "") or raw.get("原文", "")
    structured = {
        "案件编号": raw.get("案件编号", ""),
        "案件名称": raw.get("案件名称", "") or case_data.get("案件名称", ""),
        "当事人": parties,
        "罪名": charges_text,
        "案件事实": raw.get("案件事实", ""),
        "涉案金额": raw.get("涉案金额", ""),
        "其他关键信息": "",
        "证据列表": evidences if isinstance(evidences, list) else [str(evidences)],
        "适用法律": laws if isinstance(laws, list) else [str(laws)],
        "文书类型": "起诉意见书" if "起诉意见书" in content else "起诉书",
    }
    has_content = bool(content) or any(structured.values())
    return {
        "has_content": has_content,
        "content": content,
        "structured": structured,
    }


def _extract_case_parties(case_data):
    """从案件 JSON 中提取辩护视角上下文。"""
    indictment = _normalize_indictment_data(case_data)
    structured = indictment.get("structured", {})

    def _normalize_list(value):
        seen = set()
        deduped = []
        if not isinstance(value, list):
            return deduped
        for item in value:
            if item and item not in seen:
                deduped.append(item)
                seen.add(item)
        return deduped

    entrusted_parties = _normalize_list(case_data.get("委托当事人", []))
    if not entrusted_parties:
        entrusted_parties = _normalize_list(case_data.get("当事人清单", []))

    indictment_parties = structured.get("当事人", [])
    if not isinstance(indictment_parties, list):
        indictment_parties = []

    related_people = _normalize_list(case_data.get("涉案核心人物", []))
    if not related_people:
        related_people = _normalize_list(case_data.get("核心当事人", []))
    if not related_people:
        related_people = [name for name in indictment_parties if name not in entrusted_parties]

    all_focus_people = []
    seen_focus = set()
    for name in entrusted_parties + related_people:
        if name and name not in seen_focus:
            all_focus_people.append(name)
            seen_focus.add(name)

    if not all_focus_people:
        all_focus_people = sorted(set(
            r.get("姓名", "") for r in case_data.get("笔录列表", []) if r.get("姓名")
        ))

    indictment_summary = structured.get("案件事实", "")
    if not indictment_summary:
        # fallback: 直接拿起诉书全文内容
        indictment_summary = indictment.get("content", "") if isinstance(indictment, dict) else ""

    return {
        "entrusted_parties": entrusted_parties,
        "related_people": related_people,
        "focus_people": all_focus_people,
        "indictment_summary": indictment_summary,
        "has_indictment": indictment.get("has_content", False),
    }


def _extract_party_candidates(case_data, q=""):
    """从案件 JSON 中提取“委托人候选”列表，用于新建/选择委托当事人。

    返回：[{name, sources, score}, ...]
    """
    q = (q or "").strip()

    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        return []

    def _iter_party_names(value):
        """兼容 ['张三'] / [{'姓名':'张三'}] / [{'name':'张三'}] 等结构。"""
        for item in _as_list(value):
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(
                    item.get("姓名")
                    or item.get("name")
                    or item.get("名称")
                    or item.get("当事人")
                    or ""
                ).strip()
            else:
                name = ""
            if name:
                yield name

    def _normalize_name(name):
        # 常见格式噪声：引号、括号等
        name = (name or "").strip()
        name = name.strip(" \t\r\n\"'“”‘’()（）【】[]<>《》")
        return name.strip()

    def _is_obviously_not_person(name):
        if not name:
            return True
        if any(ch.isdigit() for ch in name):
            return True
        if len(name) <= 1 or len(name) > 18:
            return True

        bad_keywords = [
            # 抽象/群体
            "犯罪团伙", "团伙", "团伙成员", "同案人员", "其他人员", "多人", "一伙人",
            # 交易角色/泛称
            "下游买家", "上游卖家", "买家", "卖家", "客户", "老板", "司机", "同伙",
            # 非人物实体
            "车辆", "车牌", "账号", "账户", "银行卡", "支付宝", "微信", "QQ", "手机号", "电话",
            "住址", "地址", "地点", "现场", "仓库", "宾馆", "酒店",
            # 机构/单位（明显不是个人名）
            "有限公司", "有限责任公司", "公司", "银行", "医院", "学校", "派出所", "公安局", "法院", "检察院",
        ]
        if any(k in name for k in bad_keywords):
            return True

        # 纯角色词（更像标签，不像名字）
        role_only = {"被告人", "被害人", "嫌疑人", "证人", "民警", "法官", "检察官", "律师"}
        if name in role_only:
            return True

        return False

    source_weights = {
        "委托当事人": 100,
        "起诉书.structured.当事人": 85,
        "涉案核心人物": 75,
        "当事人清单": 65,
        "笔录列表": 55,
    }

    agg = {}

    def _add(name, source):
        name = _normalize_name(name)
        if _is_obviously_not_person(name):
            return
        item = agg.get(name)
        if item is None:
            item = {"name": name, "sources": set(), "_weights": []}
            agg[name] = item
        item["sources"].add(source)
        item["_weights"].append(source_weights.get(source, 10))

    # 1) 委托当事人（优先）
    for name in _iter_party_names(case_data.get("委托当事人")):
        _add(name, "委托当事人")

    # 2) 起诉书 structured 当事人
    indictment = _normalize_indictment_data(case_data)
    structured = indictment.get("structured", {}) if isinstance(indictment, dict) else {}
    for name in _iter_party_names(structured.get("当事人")):
        _add(name, "起诉书.structured.当事人")

    # 3) 当事人清单[].姓名
    for name in _iter_party_names(case_data.get("当事人清单")):
        _add(name, "当事人清单")

    # 4) 笔录列表[].姓名
    for record in _as_list(case_data.get("笔录列表")):
        if isinstance(record, dict):
            name = record.get("姓名", "")
            if name:
                _add(name, "笔录列表")

    # 5) 涉案核心人物
    for name in _iter_party_names(case_data.get("涉案核心人物")):
        _add(name, "涉案核心人物")

    candidates = []
    for item in agg.values():
        sources = sorted(item["sources"])
        max_weight = max(item["_weights"]) if item["_weights"] else 0
        score = max_weight + max(0, len(sources) - 1) * 5
        candidates.append({"name": item["name"], "sources": sources, "score": score})

    if q:
        def _match(candidate_name):
            return q in candidate_name or q.lower() in candidate_name.lower()

        candidates = [c for c in candidates if _match(c["name"])]
        for c in candidates:
            # q 命中轻微加分，避免同分时“看起来更相关”的排前面
            c["score"] += 3

    candidates.sort(key=lambda x: (-x["score"], x["name"]))
    return candidates


def _standardize_graph_payload(case_data, case_id):
    """将案件图谱统一为前端和 drawio 导出共用的数据结构。"""
    graph = case_data.get("案情图谱", {})
    has_graph = bool(graph) and bool(graph.get("nodes", []))

    raw_nodes = graph.get("nodes", []) if has_graph else []
    nodes = []
    for n in raw_nodes:
        if not _is_real_person_graph_node(n):
            continue
        nodes.append({
            "id": n.get("id", ""),
            "label": n.get("label", ""),
            "type": n.get("type", "other"),
            "subtype": n.get("subtype", ""),
            "description": n.get("description", ""),
            "importance": n.get("importance", "secondary"),
            "members": n.get("members", []),
            "records": n.get("records", []),
        })

    visible_node_ids = {node["id"] for node in nodes}
    raw_edges = graph.get("edges", []) if has_graph else []
    edges = []
    for e in raw_edges:
        source = e.get("source", "")
        target = e.get("target", "")
        if source not in visible_node_ids or target not in visible_node_ids:
            continue
        edges.append({
            "id": e.get("id", ""),
            "source": source,
            "target": target,
            "label": e.get("label", ""),
            "type": e.get("type", "indirect"),
            "style": e.get("style", "dashed"),
            "flow": e.get("flow", "") or _infer_flow_type(e.get("label", "")),
            "evidence": e.get("evidence", ""),
        })

    node_labels = {node["label"] for node in nodes}
    case_parties = _extract_case_parties(case_data)
    center_parties = [name for name in case_parties["entrusted_parties"] if name in node_labels]
    if not center_parties:
        selected = graph.get("selected_parties", []) if has_graph else []
        center_parties = [name for name in selected if name in node_labels]
    if not center_parties:
        center_parties = [
            node["label"]
            for node in nodes
            if node.get("importance") == "primary"
        ][:1]
    if not center_parties and nodes:
        center_parties = [nodes[0]["label"]]

    return {
        "case_name": case_data.get("案件名称", case_id),
        "has_graph": has_graph and bool(nodes),
        "nodes": nodes,
        "edges": edges,
        "parties": center_parties,
        "center_parties": center_parties,
    }


def _is_real_person_graph_node(node):
    """图谱只展示真实人物，排除组织、车辆、账户、事件和抽象群体。"""
    if not isinstance(node, dict):
        return False
    if node.get("type") != "person":
        return False

    label = str(node.get("label", "")).strip()
    if not label:
        return False

    # 有 members 的“人物”节点通常是大模型总结出的集合概念，比如“下游买家”。
    if node.get("members"):
        return False

    abstract_patterns = [
        "团伙",
        "买家",
        "客户",
        "对象",
        "群体",
        "人员组",
        "公司",
        "犯罪组织",
        "车辆",
        "货车",
        "轿车",
        "账户",
        "仓库",
        "山庄",
        "酒店",
        "工地",
    ]
    if any(pattern in label for pattern in abstract_patterns):
        return False

    # 兜底排除车牌号样式，避免被错误标成 person 后进入关系网。
    if re.search(r"^[\u4e00-\u9fa5][A-Z][A-Z0-9]{4,7}", label):
        return False

    return True


def _drawio_value(label, subtitle=""):
    label_text = html_escape(_safe_graph_text(label), quote=True)
    subtitle_text = html_escape(_safe_graph_text(subtitle), quote=True)
    if not subtitle_text:
        return label_text
    return (
        f"{label_text}&lt;br&gt;"
        f"&lt;font style=&quot;font-size:11px;font-weight:normal&quot;&gt;"
        f"{subtitle_text}&lt;/font&gt;"
    )


def _drawio_node_style(node):
    fill = {
        "person": "#f5f5f5",
        "organization": "#e8f5e9",
        "account": "#fff7ed",
        "event": "#eff6ff",
        "other": "#f8fafc",
    }.get(node.get("type", "other"), "#f8fafc")
    stroke_width = "3" if node.get("importance") == "primary" else "2"
    return (
        "rounded=1;whiteSpace=wrap;html=1;"
        f"fillColor={fill};strokeColor=#333333;strokeWidth={stroke_width};"
        "fontSize=14;fontStyle=1;fontColor=#333333;align=center;"
        "verticalAlign=middle;textShadow=1;"
    )


def _safe_graph_text(text):
    """图谱展示层避免直接使用主从犯结论，改成作用表述。"""
    value = str(text or "")
    replacements = {
        "主犯": "核心作用",
        "从犯": "辅助作用",
        "首要分子": "组织作用",
        "共犯": "共同参与",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _infer_flow_type(label):
    text = str(label or "")
    if any(word in text for word in ["付款", "收款", "转账", "资金", "定金", "打款", "账户", "支付"]):
        return "资金流"
    if any(word in text for word in ["采购", "销售", "运输", "转运", "接驳", "发货", "收货", "仓库", "货"]):
        return "货物流"
    if any(word in text for word in ["指派", "安排", "联系", "介绍", "通知", "沟通", "控制", "管理"]):
        return "指挥联络"
    if any(word in text for word in ["证明", "供述", "辨认", "证实", "印证"]):
        return "证据关系"
    return "事实关系"


def _drawio_edge_color(flow):
    return "#64748b" if flow == "证据关系" else "#333333"


def _build_drawio_xml(case_id, graph_payload):
    case_name = graph_payload.get("case_name", case_id)
    nodes = [node for node in graph_payload.get("nodes", []) if node.get("type") != "event"]
    edges = graph_payload.get("edges", [])
    parties = set(graph_payload.get("parties", []))

    node_id_map = {}
    cells = [
        '<mxCell id="0" />',
        '<mxCell id="1" parent="0" />',
        (
            '<mxCell id="title" parent="1" '
            'style="text;html=1;strokeColor=none;fillColor=none;'
            'align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;'
            'fontStyle=1;fontSize=20;fontColor=#333333;textShadow=1;" '
            f'value="{html_escape(case_name, quote=True)}" vertex="1">'
            '<mxGeometry height="40" width="1100" x="250" y="40" as="geometry" />'
            '</mxCell>'
        ),
    ]

    center, direct, indirect = [], [], []
    center_labels = set(parties)
    for node in nodes:
        label = node.get("label", "")
        if label in center_labels:
            center.append(node)
        else:
            indirect.append(node)

    center_ids = {node.get("id") for node in center}
    direct_ids = set()
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in center_ids and target not in center_ids:
            direct_ids.add(target)
        if target in center_ids and source not in center_ids:
            direct_ids.add(source)
    direct, indirect = [], []
    for node in nodes:
        if node in center:
            continue
        if node.get("id") in direct_ids:
            direct.append(node)
        else:
            indirect.append(node)

    side_map = {}
    for node in direct:
        labels = " ".join(
            edge.get("label", "")
            for edge in edges
            if (
                (edge.get("source") in center_ids and edge.get("target") == node.get("id"))
                or (edge.get("target") in center_ids and edge.get("source") == node.get("id"))
            )
        )
        side_map[node.get("id")] = (
            "right"
            if re.search(r"接驳|押运|转运|驾驶|等待|参与|被抓获|辅助", labels)
            else "left"
        )

    pending = {node.get("id") for node in indirect}
    changed = True
    while changed and pending:
        changed = False
        for node_id in list(pending):
            linked_sides = []
            for edge in edges:
                source = edge.get("source")
                target = edge.get("target")
                if source == node_id and target in side_map:
                    linked_sides.append(side_map[target])
                if target == node_id and source in side_map:
                    linked_sides.append(side_map[source])
            if linked_sides:
                side_map[node_id] = linked_sides[0]
                pending.remove(node_id)
                changed = True
    for index, node_id in enumerate(sorted(pending)):
        side_map[node_id] = "left" if index % 2 == 0 else "right"

    direct_left = [node for node in direct if side_map.get(node.get("id")) != "right"]
    direct_right = [node for node in direct if side_map.get(node.get("id")) == "right"]
    indirect_left = [node for node in indirect if side_map.get(node.get("id")) != "right"]
    indirect_right = [node for node in indirect if side_map.get(node.get("id")) == "right"]

    layout_rows = [
        (indirect_left, 60, 170, 220),
        (direct_left, 340, 150, 230),
        (center, 650, 130, 240),
        (direct_right, 980, 150, 230),
        (indirect_right, 1260, 170, 220),
    ]

    order = 1
    for group, x, y_start, width in layout_rows:
        for index, node in enumerate(group):
            drawio_id = f"node{order}"
            order += 1
            node_id_map[node.get("id")] = drawio_id
            subtitle = node.get("subtype") or node.get("description", "")
            if len(subtitle) > 32:
                subtitle = subtitle[:32].rstrip() + "..."
            height = 72 if subtitle else 56
            y = y_start + index * 122
            cells.append(
                f'<mxCell id="{drawio_id}" parent="1" '
                f'style="{_drawio_node_style(node)}" '
                f'value="{_drawio_value(node.get("label"), subtitle)}" vertex="1">'
                f'<mxGeometry height="{height}" width="{width}" x="{x}" y="{y}" as="geometry" />'
                '</mxCell>'
            )

    edge_order = 1
    for edge in edges:
        source = node_id_map.get(edge.get("source"))
        target = node_id_map.get(edge.get("target"))
        if not source or not target:
            continue
        dashed = edge.get("style") == "dashed" or edge.get("type") == "indirect"
        stroke_width = "2" if dashed else "3"
        dashed_style = "dashed=1;dashPattern=8 4 1 4;" if dashed else ""
        stroke_color = _drawio_edge_color(edge.get("flow", ""))
        label = html_escape(_safe_graph_text(edge.get("label", "")), quote=True)
        cells.append(
            f'<mxCell id="edge{edge_order}" edge="1" parent="1" source="{source}" target="{target}" '
            f'style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;'
            f'jettySize=auto;html=1;{dashed_style}strokeColor={stroke_color};'
            f'strokeWidth={stroke_width};align=center;verticalAlign=middle;'
            f'fontSize=11;fontColor={stroke_color};labelBackgroundColor=#ffffff;'
            f'endArrow=classic;textShadow=1;" value="{label}">'
            '<mxGeometry relative="1" as="geometry" />'
            '</mxCell>'
        )
        edge_order += 1

    content = "\n        ".join(cells)
    return (
        '<mxfile host="app.diagrams.net">\n'
        f'  <diagram name="{html_escape(case_name, quote=True)}" id="case-graph">\n'
        '    <mxGraphModel dx="1600" dy="1200" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        'pageWidth="1600" pageHeight="1000" math="0" shadow="0">\n'
        '      <root>\n'
        f'        {content}\n'
        '      </root>\n'
        '    </mxGraphModel>\n'
        '  </diagram>\n'
        '</mxfile>\n'
    )


def _read_content(file_path):
    """读取文件内容，失败时返回 None。"""
    if not file_path:
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (FileNotFoundError, OSError):
        return None


import re as _re

def _clean_record_content(text):
    """清洗笔录原文，去除OCR噪声和无关内容。"""
    if not text:
        return text
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        s = line.strip()
        # 跳过页码标记
        if _re.match(r"^第\s*\d+\s*页\s*共\s*\d+\s*页$", s):
            continue
        # 跳过图片引用
        if s.startswith("![](") or s.startswith("!["):
            continue
        # 跳过纯数字行（OCR残留页码）
        if s.isdigit() and len(s) <= 3:
            continue
        # 跳过空行连续重复（保留单个）
        if not s:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        # 跳过纯标点/符号行
        if _re.match(r"^[^\w一-鿿]+$", s) and len(s) < 5:
            continue
        cleaned.append(line)
    # 去除首尾空行
    while cleaned and cleaned[0] == "":
        cleaned.pop(0)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)


def _content_lines(content):
    """将全文按行拆分，返回列表。"""
    return content.split("\n") if content else []


def _line_number_of_offset(content, offset):
    """计算 offset（字符偏移）对应的行号（从 0 开始）。"""
    return content[:offset].count("\n")


def _find_page_for_line(line_num, page_mapping):
    """根据行号查页码映射，返回 evidence_page 或 None。
    page_mapping 格式: [{"md_page": 1, "evidence_page": 108, "start_line": 0, "end_line": 150}, ...]
    """
    if not page_mapping:
        return None
    for entry in page_mapping:
        start = entry.get("start_line", 0)
        end = entry.get("end_line", float("inf"))
        if start <= line_num <= end:
            return entry.get("evidence_page")
    return None


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_cases():
    cases = []
    data_path = Path(DATA_DIR)
    if not data_path.exists():
        return cases
    for f in sorted(data_path.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                cases.append({
                    "id": f.stem,
                    "name": data.get("案件名称", f.stem),
                    "filename": f.name,
                    "record_count": len(data.get("笔录列表", [])),
                })
        except (json.JSONDecodeError, KeyError):
            continue
    return cases


CASE_PINYIN_MAP = {
    "朱": "zhu",
    "霞": "xia",
    "新": "xin",
    "案": "an",
    "重": "zhong",
    "复": "fu",
    "件": "jian",
}


def slugify_case_id(case_name):
    parts = []
    for char in str(case_name or "").strip().lower():
        if char.isascii() and char.isalnum():
            parts.append(char)
        elif char in CASE_PINYIN_MAP:
            parts.append("_" + CASE_PINYIN_MAP[char] + "_")
        elif char in (" ", "-", "_", "　"):
            parts.append("_")
    slug = re.sub(r"_+", "_", "".join(parts)).strip("_")
    return slug[:64] or "case"


def unique_case_id(case_name):
    base = slugify_case_id(case_name)
    data_path = Path(DATA_DIR)
    candidate = base
    index = 2
    while (data_path / f"{candidate}.json").exists():
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def create_empty_case_data(case_name, case_id):
    return {
        "案件名称": case_name,
        "案件编号": case_id,
        "笔录目录": [],
        "笔录总数": 0,
        "笔录列表": [],
        "起诉书": {"has_content": False, "content": "", "structured": {}},
        "笔录摘要": {},
        "人物摘要": {},
        "案情图谱": {"nodes": [], "edges": []},
        "当事人清单": [],
        "核心当事人": [],
        "委托当事人": [],
        "涉案核心人物": [],
        "全文内容": "",
    }


def load_case_data(case_id):
    data_path = Path(DATA_DIR)
    fp = data_path / f"{case_id}.json"
    if not fp.exists():
        return None
    with open(fp, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_case_data(case_id, case_data):
    """保存案件 JSON 数据。"""
    data_path = Path(DATA_DIR)
    data_path.mkdir(parents=True, exist_ok=True)
    fp = data_path / f"{case_id}.json"
    with open(fp, "w", encoding="utf-8") as fh:
        json.dump(case_data, fh, ensure_ascii=False, indent=2)
    return fp


def _clean_trash_expired():
    """清理废纸篓中超过 7 天的案件。"""
    now = datetime.now(timezone.utc).astimezone()
    if not TRASH_DIR.exists():
        return
    for case_dir in list(TRASH_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        meta_path = case_dir / "_trash_meta.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                deleted_at = datetime.fromisoformat(meta.get("deleted_at", ""))
                if (now - deleted_at).days < TRASH_RETENTION_DAYS:
                    continue
            except (ValueError, json.JSONDecodeError):
                pass
        shutil.rmtree(case_dir, ignore_errors=True)


def move_case_to_trash(case_id):
    """将案件及其关联数据移入废纸篓。"""
    _clean_trash_expired()
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    trash_case_dir = TRASH_DIR / case_id
    # 防止覆盖已有的废纸篓条目
    if trash_case_dir.exists():
        shutil.rmtree(trash_case_dir, ignore_errors=True)
    trash_case_dir.mkdir(parents=True, exist_ok=True)

    moved = []

    # 案件 JSON（核心，必须成功）
    case_json = Path(DATA_DIR) / f"{case_id}.json"
    if not case_json.exists():
        raise FileNotFoundError(f"案件文件不存在: {case_json}")
    shutil.move(str(case_json), str(trash_case_dir / case_json.name))
    moved.append("case_json")

    # GraphRAG 索引（非关键，失败不影响）
    try:
        graphrag_dir = BASE_DIR / "runtime" / "graphrag" / case_id
        if graphrag_dir.exists():
            shutil.move(str(graphrag_dir), str(trash_case_dir / "graphrag"))
            moved.append("graphrag")
    except Exception:
        pass

    # Agent 输出（非关键，失败不影响）
    try:
        agent_dir = _agent_output_dir(case_id)
        if agent_dir.exists():
            shutil.move(str(agent_dir), str(trash_case_dir / "agent_outputs"))
            moved.append("agent_outputs")
    except Exception:
        pass

    # 写入废纸篓元数据
    meta = {
        "case_id": case_id,
        "deleted_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "retention_days": TRASH_RETENTION_DAYS,
        "moved_items": moved,
    }
    (trash_case_dir / "_trash_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def restore_case_from_trash(case_id):
    """从废纸篓恢复案件。"""
    trash_case_dir = TRASH_DIR / case_id
    if not trash_case_dir.exists():
        return False

    restored = []

    # 恢复案件 JSON
    for f in trash_case_dir.glob("*.json"):
        if f.name == "_trash_meta.json":
            continue
        target = Path(DATA_DIR) / f.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(target))
        restored.append("case_json")

    # 恢复 GraphRAG（非关键）
    try:
        graphrag_src = trash_case_dir / "graphrag"
        if graphrag_src.exists():
            graphrag_dst = BASE_DIR / "runtime" / "graphrag" / case_id
            graphrag_dst.parent.mkdir(parents=True, exist_ok=True)
            if graphrag_dst.exists():
                shutil.rmtree(str(graphrag_dst), ignore_errors=True)
            shutil.move(str(graphrag_src), str(graphrag_dst))
            restored.append("graphrag")
    except Exception:
        pass

    # 恢复 Agent 输出（非关键）
    try:
        agent_src = trash_case_dir / "agent_outputs"
        if agent_src.exists():
            agent_dst = _agent_output_dir(case_id)
            agent_dst.parent.mkdir(parents=True, exist_ok=True)
            if agent_dst.exists():
                shutil.rmtree(str(agent_dst), ignore_errors=True)
            shutil.move(str(agent_src), str(agent_dst))
            restored.append("agent_outputs")
    except Exception:
        pass
        restored.append("agent_outputs")

    # 清理废纸篓目录
    shutil.rmtree(str(trash_case_dir), ignore_errors=True)
    return True


def list_trash():
    """列出废纸篓内容。"""
    _clean_trash_expired()
    if not TRASH_DIR.exists():
        return []
    now = datetime.now(timezone.utc).astimezone()
    items = []
    for case_dir in sorted(TRASH_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        meta_path = case_dir / "_trash_meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            deleted_at = datetime.fromisoformat(meta.get("deleted_at", ""))
            days_left = max(0, TRASH_RETENTION_DAYS - (now - deleted_at).days)
            case_name = ""
            for f in case_dir.glob("*.json"):
                if f.name == "_trash_meta.json":
                    continue
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    case_name = data.get("案件名称", "")
                except json.JSONDecodeError:
                    pass
                break
            items.append({
                "case_id": meta["case_id"],
                "case_name": case_name or meta["case_id"],
                "deleted_at": meta["deleted_at"],
                "days_left": days_left,
                "moved_items": meta.get("moved_items", []),
            })
        except (ValueError, json.JSONDecodeError, KeyError):
            pass
    return items


# ---------------------------------------------------------------------------
# 页面路由
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/cases")
def api_cases():
    return jsonify(load_cases())


@app.route("/api/cases", methods=["POST"])
def api_cases_create():
    payload = request.get_json(silent=True) or {}
    case_name = str(payload.get("case_name") or payload.get("name") or "").strip()
    if not case_name:
        return jsonify({"error": "案件名称不能为空"}), 400
    case_id = unique_case_id(case_name)
    case_data = create_empty_case_data(case_name, case_id)
    save_case_data(case_id, case_data)
    return jsonify(
        {
            "case": {
                "id": case_id,
                "name": case_name,
                "record_count": 0,
                "filename": f"{case_id}.json",
            }
        }
    )


@app.route("/api/cases/<case_id>/update-field", methods=["POST"])
def api_cases_update_field(case_id):
    payload = request.get_json(silent=True) or {}
    field = (payload.get("field") or "").strip()
    key = (payload.get("key") or "").strip()
    content = payload.get("content", "")
    if not field or not content:
        return jsonify({"error": "缺少 field 或 content"}), 400
    case_data = load_case_data(case_id)
    if case_data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    if field in ("笔录摘要", "人物摘要"):
        existing = case_data.get(field, {})
        if not isinstance(existing, dict):
            existing = {}
        if key:
            existing[key] = {"content": str(content).strip(), "generated_at": now_iso(), "source": "小扣聊天更新"}
        elif isinstance(content, dict):
            existing.update(content)
        case_data[field] = existing
    elif field == "案情图谱":
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return jsonify({"error": "图谱内容不是有效 JSON"}), 400
        case_data["案情图谱"] = content
    else:
        return jsonify({"error": f"不支持的字段: {field}"}), 400

    save_case_data(case_id, case_data)
    return jsonify({"ok": True, "field": field, "key": key})


@app.route("/api/cases/<case_id>", methods=["DELETE"])
def api_cases_delete(case_id):
    if load_case_data(case_id) is None:
        return jsonify({"error": f"案件不存在: {case_id}"}), 404
    try:
        meta = move_case_to_trash(case_id)
        return jsonify({"ok": True, "trash": meta})
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


@app.route("/api/cases/<case_id>/restore", methods=["POST"])
def api_cases_restore(case_id):
    restored = restore_case_from_trash(case_id)
    if not restored:
        return jsonify({"error": f"废纸篓中未找到案件: {case_id}"}), 404
    return jsonify({"ok": True, "case_id": case_id})


@app.route("/api/trash")
def api_trash():
    return jsonify({"trash": list_trash()})


@app.route("/api/workspace/open", methods=["POST"])
def api_open_workspace():
    # 确保目录存在
    for sub in WORKSPACE_SUBDIRS:
        (WORKSPACE_DIR / sub).mkdir(parents=True, exist_ok=True)
    # 打开工作区
    if os.name == "nt":
        os.startfile(str(WORKSPACE_DIR))
    return jsonify({"ok": True, "path": str(WORKSPACE_DIR)})


@app.route("/api/agent/capabilities")
def api_agent_capabilities():
    settings = AI_STORE.get_settings(masked=True)
    mineru_configured = bool((settings.get("mineru") or {}).get("has_api_token"))
    return jsonify(
        {
            "capabilities": [
                "material_auto_build",
                "graphrag_retrieve",
                "record_detail",
                "agent_save_result",
                "evidence_directory",
                "evidence_parse",
                "agent_memories",
            ],
            "cases": load_cases(),
            "sensitive_fields": ["api_key", "api_token"],
            "mineru": {"configured": mineru_configured},
        }
    )


@app.route("/api/records")
def api_records():
    case_id = _get_arg_fixed("case")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    records = data.get("笔录列表", [])

    name_filter = _get_arg_fixed("name").strip()
    date_filter = _get_arg_fixed("date").strip()
    type_filter = _get_arg_fixed("type").strip()

    if name_filter:
        records = [r for r in records if name_filter in r.get("姓名", "")]
    if date_filter:
        records = [r for r in records if date_filter in r.get("日期", "")]
    if type_filter:
        records = [r for r in records if type_filter in r.get("笔录类型", "")]

    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "total": len(records),
        "records": records,
    })


@app.route("/api/record/<record_id>")
def api_record_detail(record_id):
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    for r in data.get("笔录列表", []):
        if str(r.get("id")) == str(record_id):
            # 优先使用JSON中已拆分的全文内容（同一人的多份笔录各自独立）
            content = _get_record_content(r, data)
            if not content and r.get("文件路径"):
                content = f"[文件未找到: {r.get('文件路径')}]"
            content = _clean_record_content(content)
            return jsonify({**r, "原文内容": content})

    return jsonify({"error": f"笔录 {record_id} 不存在"}), 404


# ---------------------------------------------------------------------------
# 新增 API：按页码返回内容
# ---------------------------------------------------------------------------

@app.route("/api/record/<record_id>/page/<int:page_num>")
def api_record_page(record_id, page_num):
    """返回某份笔录指定页的内容。
    优先使用笔录中的 页码映射 字段进行精确定位；
    若无映射，尝试按 MinerU 输出的 <!-- page N --> 标记分页；
    都没有时，返回全文并提示无法精确分页。
    """
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    for r in data.get("笔录列表", []):
        if str(r.get("id")) == str(record_id):
            content = _load_page_source_content(r, data)
            if not content:
                return jsonify({"error": "笔录原文未找到"}), 404

            # 策略 1：有 页码映射 字段，精确切片
            page_mapping = r.get("页码映射", [])
            if page_mapping:
                lines = _content_lines(content)
                page_lines = []
                for entry in page_mapping:
                    if entry.get("evidence_page") == page_num:
                        start = entry.get("start_line", 0)
                        end = entry.get("end_line", len(lines))
                        page_lines = lines[start:end + 1]
                        break
                if page_lines:
                    return jsonify({
                        "record_id": record_id,
                        "page": page_num,
                        "content": "\n".join(page_lines),
                        "source": "页码映射",
                    })
                return jsonify({"error": f"页码 {page_num} 在映射中未找到"}), 404

            # 策略 2：按 MinerU 的 <!-- page N --> 标记分页
            page_pattern = re.compile(r"<!--\s*page\s+(\d+)\s*-->", re.IGNORECASE)
            pages = {}
            current_page = None
            buf = []
            for line in content.split("\n"):
                m = page_pattern.match(line.strip())
                if m:
                    if current_page is not None:
                        pages[current_page] = "\n".join(buf)
                    current_page = int(m.group(1))
                    buf = []
                else:
                    buf.append(line)
            if current_page is not None:
                pages[current_page] = "\n".join(buf)

            if pages:
                if page_num in pages:
                    return jsonify({
                        "record_id": record_id,
                        "page": page_num,
                        "content": pages[page_num],
                        "source": "page标记",
                    })
                return jsonify({
                    "error": f"页码 {page_num} 未找到",
                    "available_pages": sorted(pages.keys()),
                }), 404

            # 策略 3：无法分页，返回全文
            return jsonify({
                "record_id": record_id,
                "page": page_num,
                "content": content,
                "source": "全文（无分页信息）",
                "warning": "该笔录无分页映射，返回全文内容",
            })

    return jsonify({"error": f"笔录 {record_id} 不存在"}), 404


# ---------------------------------------------------------------------------
# 核心：模糊多关键词搜索
# ---------------------------------------------------------------------------

def _get_all_names(records):
    """提取数据集中所有人员姓名。"""
    return sorted(set(r.get("姓名", "") for r in records if r.get("姓名")))


def _split_keywords_by_name(keywords, all_names):
    """将关键词分为人名关键词和内容关键词。

    返回 (name_keywords, content_keywords)。
    人名匹配规则：关键词是某人姓名的子串，或某人姓名是关键词的子串。
    """
    name_kws = []
    content_kws = []
    matched_names = set()

    for kw in keywords:
        kw_strip = kw.strip()
        if not kw_strip:
            continue
        found = False
        for name in all_names:
            # 双向子串匹配：关键词包含姓名，或姓名包含关键词
            if kw_strip in name or name in kw_strip:
                if name not in matched_names:
                    name_kws.append(name)
                    matched_names.add(name)
                found = True
                break
        if not found:
            content_kws.append(kw_strip)

    return name_kws, content_kws


def _fuzzy_search_records(records, case_data, keywords):
    """对笔录列表执行多关键词模糊搜索。

    智能分流：如果关键词中包含人名，先按人名锁定该人的笔录，
    再在该人笔录范围内对剩余关键词做模糊匹配。
    如果没有人名关键词，则对所有笔录做全量模糊搜索。

    返回按匹配度降序排列的列表，每项包含:
      - 笔录原始字段
      - 匹配分数、匹配关键词列表、匹配片段、匹配页码
    """
    all_names = _get_all_names(records)
    name_kws, content_kws = _split_keywords_by_name(keywords, all_names)

    # 确定搜索范围和实际要搜的内容关键词
    if name_kws:
        # 有人名 → 锁定该人笔录，只搜内容关键词
        target_records = [r for r in records if r.get("姓名", "") in name_kws]
        search_kws = content_kws if content_kws else name_kws
        # 如果只有人名没有内容关键词，直接返回该人所有笔录
        if not content_kws:
            results = []
            for r in target_records:
                entry = {k: v for k, v in r.items() if k not in ("全文内容", "页码映射")}
                entry["匹配分数"] = 1
                entry["匹配关键词"] = name_kws
                entry["匹配关键词数"] = len(name_kws)
                entry["总关键词数"] = len(keywords)
                if r.get("印刷页码"):
                    entry["匹配页码"] = f"证据卷P{r.get('印刷页码')}"
                if r.get("内容摘要"):
                    entry["匹配片段"] = f"...{r['内容摘要'][:120]}..."
                results.append(entry)
            return results
    else:
        # 无人名 → 全量搜索
        target_records = records
        search_kws = keywords

    results = []

    for r in target_records:
        # --- 元数据文本 ---
        meta_text = " ".join([
            r.get("姓名", ""),
            r.get("笔录类型", ""),
            r.get("次数", ""),
            r.get("日期", ""),
            r.get("印刷页码", ""),
            r.get("引用格式", ""),
            r.get("内容摘要", ""),
        ])
        meta_lower = meta_text.lower()

        # --- 读取全文 ---
        content = _get_record_content(r, case_data)
        content_lower = content.lower() if content else ""

        # --- 逐关键词打分 ---
        matched_keywords = []
        total_hits = 0
        best_snippet = ""
        match_page = None
        page_mapping = r.get("页码映射", [])

        for kw in search_kws:
            kw_lower = kw.lower()

            # 在元数据中匹配
            meta_hits = meta_lower.count(kw_lower)

            # 在全文中匹配
            content_hits = content_lower.count(kw_lower) if content_lower else 0

            if meta_hits == 0 and content_hits == 0:
                continue

            matched_keywords.append(kw)
            total_hits += meta_hits + content_hits

            # 生成最佳片段（取第一次出现的上下文）
            if content and content_hits > 0 and not best_snippet:
                idx = content_lower.find(kw_lower)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(kw) + 80)
                best_snippet = content[start:end].replace("\n", " ")

                # 计算匹配所在行 → 查页码
                if page_mapping:
                    line_num = _line_number_of_offset(content, idx)
                    match_page = _find_page_for_line(line_num, page_mapping)

        if not matched_keywords:
            continue

        # --- 构造结果条目（排除大字段，避免响应臃肿） ---
        entry = {k: v for k, v in r.items() if k not in ("全文内容", "页码映射")}
        entry["匹配分数"] = total_hits
        entry["匹配关键词"] = matched_keywords
        entry["匹配关键词数"] = len(matched_keywords)
        entry["总关键词数"] = len(keywords)
        if best_snippet:
            entry["匹配片段"] = f"...{best_snippet}..."
        if match_page is not None:
            entry["匹配页码"] = f"P{match_page}"
        elif r.get("印刷页码"):
            entry["匹配页码"] = f"证据卷P{r.get('印刷页码')}"

        results.append(entry)

    # 排序：匹配关键词数降序 → 总命中次数降序
    results.sort(key=lambda x: (x["匹配关键词数"], x["匹配分数"]), reverse=True)
    return results


@app.route("/api/search", methods=["GET", "POST"])
def api_search():
    """多关键词模糊搜索。GET 支持查询参数 ?case=xxx&keyword=关键词；
    POST 支持 JSON body {"case": "xxx", "keyword": "关键词"}（推荐，避免中文编码问题）。"""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        case_id = data.get("case", "")
        keyword = data.get("keyword", "").strip()
    else:
        case_id = _get_arg_fixed("case")
        keyword = _get_arg_fixed("keyword").strip()

    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if not keyword:
        return jsonify({"error": "缺少 keyword 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    # 拆分多个关键词（空格分隔）
    keywords = [kw.strip() for kw in keyword.split() if kw.strip()]
    if not keywords:
        return jsonify({"error": "缺少 keyword 参数"}), 400

    records = data.get("笔录列表", [])

    # 智能分流：识别人名关键词
    all_names = _get_all_names(records)
    name_kws, content_kws = _split_keywords_by_name(keywords, all_names)

    results = _fuzzy_search_records(records, data, keywords)

    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "keyword": keyword,
        "keywords": keywords,
        "name_filter": name_kws,  # 锁定的人名
        "content_keywords": content_kws,  # 实际搜索的内容关键词
        "total": len(results),
        "results": results,
    })


@app.route("/api/names")
def api_names():
    """返回案件中所有人员姓名列表。"""
    case_id = _get_arg_fixed("case")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    records = data.get("笔录列表", [])
    names = _get_all_names(records)
    return jsonify({"names": names})


@app.route("/api/filters")
def api_filters():
    case_id = _get_arg_fixed("case")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    records = data.get("笔录列表", [])

    # 联动筛选：根据已选条件过滤后，再提取各维度的可选值
    name_filter = _get_arg_fixed("name").strip()
    type_filter = _get_arg_fixed("type").strip()
    date_filter = _get_arg_fixed("date").strip()

    filtered = records
    if name_filter:
        filtered = [r for r in filtered if name_filter == r.get("姓名", "")]
    if type_filter:
        filtered = [r for r in filtered if type_filter == r.get("笔录类型", "")]
    if date_filter:
        filtered = [r for r in filtered if date_filter == r.get("日期", "")]

    names = sorted(set(r.get("姓名", "") for r in filtered if r.get("姓名")))
    dates = sorted(set(r.get("日期", "") for r in filtered if r.get("日期")))
    types = sorted(set(r.get("笔录类型", "") for r in filtered if r.get("笔录类型")))

    return jsonify({"names": names, "dates": dates, "types": types})


# ---------------------------------------------------------------------------
# 新增 API：笔录摘要
# ---------------------------------------------------------------------------

@app.route("/api/summaries")
def api_summaries():
    """返回案件中所有笔录的 AI 摘要。"""
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    summaries = data.get("笔录摘要", {})
    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "summaries": summaries,
    })


# ---------------------------------------------------------------------------
# 新增 API：人物摘要
# ---------------------------------------------------------------------------

@app.route("/api/person-summaries")
def api_person_summaries():
    """返回案件中所有人物的综合摘要。
    若案件数据中已存在 人物摘要 字段，直接返回；
    否则按现有笔录列表中的人物姓名聚合，返回空 content 占位。
    """
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    person_summaries = data.get("人物摘要")
    if person_summaries is not None:
        return jsonify({
            "case_name": data.get("案件名称", case_id),
            "person_summaries": person_summaries,
        })

    # 按笔录列表中的人物姓名聚合，生成空 content 占位
    records = data.get("笔录列表", [])
    agg = {}
    for r in records:
        name = r.get("姓名", "")
        if not name:
            continue
        if name not in agg:
            agg[name] = {"content": "", "record_count": 0}
        agg[name]["record_count"] += 1

    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "person_summaries": agg,
    })


@app.route("/api/parties", methods=["GET", "POST"])
def api_parties():
    """读取或更新案件的辩护视角上下文。"""
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        case_id = str(payload.get("case", "")).strip()
    else:
        case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    if request.method == "POST":
        entrusted_parties = payload.get("entrusted_parties", [])
        related_people = payload.get("related_people")

        if not isinstance(entrusted_parties, list):
            return jsonify({"error": "entrusted_parties 必须为列表"}), 400

        normalized_entrusted = []
        for item in entrusted_parties:
            if isinstance(item, str):
                name = item.strip()
                if name and name not in normalized_entrusted:
                    normalized_entrusted.append(name)

        current_context = _extract_case_parties(data)
        if related_people is None:
            related_people = current_context["related_people"]
        elif not isinstance(related_people, list):
            return jsonify({"error": "related_people 必须为列表"}), 400

        normalized_related = []
        for item in related_people:
            if isinstance(item, str):
                name = item.strip()
                if (
                    name
                    and name not in normalized_entrusted
                    and name not in normalized_related
                ):
                    normalized_related.append(name)

        data["委托当事人"] = normalized_entrusted
        data["涉案核心人物"] = normalized_related
        save_case_data(case_id, data)
        data = load_case_data(case_id)

    context = _extract_case_parties(data)
    response_payload = {
        "case_name": data.get("案件名称", case_id),
        **context,
    }

    # 向后兼容：新增字段不改变既有字段含义
    response_payload["candidates"] = _extract_party_candidates(data, q="")
    return jsonify(response_payload)


@app.route("/api/parties/candidates")
def api_party_candidates():
    """返回案件的委托人候选列表（支持关键词过滤）。"""
    case_id = _get_arg_fixed("case")
    q = _get_arg_fixed("q")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    candidates = _extract_party_candidates(data, q=q)
    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "candidates": candidates,
    })


# ---------------------------------------------------------------------------
# 新增 API：起诉书 / 起诉意见书
# ---------------------------------------------------------------------------

@app.route("/api/indictment")
def api_indictment():
    """返回案件的起诉书或起诉意见书内容。"""
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    indictment = _normalize_indictment_data(data)
    structured = indictment.get("structured", {})

    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "has_indictment": indictment.get("has_content", False),
        "content": indictment.get("content", ""),
        "structured": {
            "案件编号": structured.get("案件编号", ""),
            "案件名称": structured.get("案件名称", ""),
            "文书类型": structured.get("文书类型", ""),
            "当事人": structured.get("当事人", []),
            "罪名": structured.get("罪名", ""),
            "案件事实": structured.get("案件事实", ""),
            "涉案金额": structured.get("涉案金额", ""),
            "其他关键信息": structured.get("其他关键信息", ""),
            "证据列表": structured.get("证据列表", []),
            "适用法律": structured.get("适用法律", []),
        },
    })


# ---------------------------------------------------------------------------
# 新增 API：案情图谱
# ---------------------------------------------------------------------------

@app.route("/api/graph")
def api_graph():
    """返回案件的案情图谱数据（节点、边、关注人物列表）。"""
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    return jsonify(_standardize_graph_payload(data, case_id))


@app.route("/api/graph/drawio")
def api_graph_drawio():
    """导出 diagrams.net/drawio 可编辑案情导图。"""
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    graph_payload = _standardize_graph_payload(data, case_id)
    if not graph_payload.get("has_graph"):
        return jsonify({"error": "当前案件暂无案情图谱数据"}), 404

    xml = _build_drawio_xml(case_id, graph_payload)
    filename = f"{case_id}_case_graph.drawio"
    return Response(
        xml,
        mimetype="application/xml; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# GraphRAG 检索增强
# ---------------------------------------------------------------------------

@app.route("/api/graphrag/index")
def api_graphrag_index():
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    index = load_graphrag_index(BASE_DIR, case_id)
    if index is None:
        index = build_graphrag_index(case_id, data, BASE_DIR, save=True)
    return jsonify({
        "case": case_id,
        "path": str(graphrag_index_path(BASE_DIR, case_id)),
        "summary": index.get("summary", {}),
        "metadata": index.get("metadata", {}),
    })


@app.route("/api/graphrag/rebuild", methods=["POST"])
def api_graphrag_rebuild():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    index = build_graphrag_index(case_id, data, BASE_DIR, save=True)
    return jsonify({
        "case": case_id,
        "path": str(graphrag_index_path(BASE_DIR, case_id)),
        "summary": index.get("summary", {}),
    })


@app.route("/api/graphrag/retrieve", methods=["POST"])
def api_graphrag_retrieve():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    query = (payload.get("query") or "").strip()
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if not query:
        return jsonify({"error": "检索问题不能为空"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    retrieval = retrieve_graphrag(
        case_id,
        data,
        BASE_DIR,
        query,
        limit=int(payload.get("limit") or 8),
    )
    return jsonify({"retrieval": retrieval})


# ---------------------------------------------------------------------------
# 临时分析 / 外接 Agent 工作台
# ---------------------------------------------------------------------------

@app.route("/api/agent/brief", methods=["POST"])
def api_agent_brief():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    task = (payload.get("task") or "").strip()
    output_format = (payload.get("output_format") or "markdown").strip()
    include_full_text = bool(payload.get("include_full_text"))
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if not task:
        return jsonify({"error": "临时任务不能为空"}), 400
    case_data = load_case_data(case_id)
    if case_data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    retrieval = retrieve_graphrag(case_id, case_data, BASE_DIR, task, limit=10)
    brief = _build_agent_brief(case_id, case_data, task, output_format, retrieval, include_full_text)
    return jsonify({
        "case": case_id,
        "brief": brief,
        "retrieval": retrieval,
        "suggested_dir": str(_agent_output_dir(case_id)),
    })


@app.route("/api/agent/save-result", methods=["POST"])
def api_agent_save_result():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    title = (payload.get("title") or "临时分析结果").strip()
    content = payload.get("content") or ""
    fmt = (payload.get("format") or "md").strip().lower()
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if load_case_data(case_id) is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404
    if not str(content).strip():
        return jsonify({"error": "结果内容不能为空"}), 400
    suffix = {"markdown": "md", "md": "md", "csv": "csv", "txt": "txt"}.get(fmt, "md")
    output_dir = _agent_output_dir(case_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{_safe_filename(title)}.{suffix}"
    output_path = output_dir / filename
    counter = 2
    while output_path.exists():
        output_path = output_dir / f"{_safe_filename(title)}_{counter}.{suffix}"
        counter += 1
    encoding = "utf-8-sig" if suffix == "csv" else "utf-8"
    output_path.write_text(str(content), encoding=encoding)
    return jsonify({"ok": True, "path": str(output_path), "filename": output_path.name})


def _build_agent_brief(case_id, case_data, task, output_format, retrieval, include_full_text=False):
    entrusted = _as_text_list(case_data.get("委托当事人") or case_data.get("当事人清单"))
    related = _as_text_list(case_data.get("涉案核心人物"))
    records = case_data.get("笔录列表", [])
    summaries = case_data.get("笔录摘要", {}) if isinstance(case_data.get("笔录摘要"), dict) else {}
    person_summaries = case_data.get("人物摘要", {}) if isinstance(case_data.get("人物摘要"), dict) else {}
    graph = case_data.get("案情图谱", {}) if isinstance(case_data.get("案情图谱"), dict) else {}
    indictment = case_data.get("起诉书") or case_data.get("起诉意见书") or {}
    indictment_text = indictment.get("content", "") if isinstance(indictment, dict) else str(indictment or "")
    record_lines = []
    for record in records[:80]:
        record_id = str(record.get("id", ""))
        summary = summaries.get(record_id, {})
        summary_text = summary.get("content", "") if isinstance(summary, dict) else str(summary or "")
        line = f"- {record_id or '?'}｜{record.get('姓名', '未知')}｜{record.get('笔录类型', '')}｜{record.get('日期', '')}｜{record.get('引用格式', '') or record.get('印刷页码', '')}"
        if summary_text:
            line += f"\n  摘要：{_agent_compact(summary_text, 180)}"
        if include_full_text:
            full_text = record.get("全文内容") or record.get("内容摘要") or ""
            line += f"\n  原文节选：{_agent_compact(full_text, 900)}"
        record_lines.append(line)
    person_lines = []
    for name, value in list(person_summaries.items())[:30]:
        content = value.get("content", "") if isinstance(value, dict) else str(value or "")
        person_lines.append(f"- {name}：{_agent_compact(content, 220)}")
    graph_lines = [
        f"节点数：{len(graph.get('nodes', []))}",
        f"关系数：{len(graph.get('edges', []))}",
        f"中心/委托人：{'、'.join(graph.get('selected_parties', []) or entrusted) or '未确认'}",
    ]
    retrieval_context = format_graphrag_context(retrieval, max_chars=5000)
    return "\n".join([
        "# Agent Brief",
        "",
        "你是外接强 Agent，请基于下列案件上下文完成临时分析任务。必须区分证据、推断和未明确事项；输出中尽量保留证据来源。",
        "",
        "## 临时任务",
        task,
        "",
        "## 输出要求",
        f"- 输出格式：{output_format}",
        "- 如生成表格，请优先使用 Markdown 表格；需要给用户二次处理时同时给 CSV 字段建议。",
        "- 对材料未明确的字段写“未明确/待核对”，不要补造事实。",
        "- 每条关键结论尽量附证据来源，如笔录人名、日期、证据卷页码或引用格式。",
        "",
        "## 当前案件",
        f"- 案件 ID：{case_id}",
        f"- 案件名称：{case_data.get('案件名称', case_id)}",
        f"- 委托当事人：{'、'.join(entrusted) or '未确认'}",
        f"- 涉案核心人物：{'、'.join(related) or '未提取'}",
        f"- 笔录数量：{len(records)}",
        "",
        "## 起诉书/起诉意见书节选",
        _agent_compact(indictment_text, 1200) or "未提供",
        "",
        "## 人物摘要",
        "\n".join(person_lines) or "暂无人物摘要",
        "",
        "## 案情图谱概况",
        "\n".join(graph_lines),
        "",
        "## 笔录目录与摘要",
        "\n".join(record_lines) or "暂无笔录",
        "",
        "## GraphRAG 检索证据",
        retrieval_context,
        "",
        "## 可保存位置",
        f"建议将最终结果保存到：{_agent_output_dir(case_id)}",
    ])


def _agent_output_dir(case_id):
    """外置Agent / 小扣输出目录 → 桌面工作区。"""
    for sub in WORKSPACE_SUBDIRS:
        (WORKSPACE_DIR / sub).mkdir(parents=True, exist_ok=True)
    return WORKSPACE_DIR / "外置Agent结果" / _safe_filename(case_id)


def _safe_filename(value):
    text = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", "_", str(value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:80] or "untitled"


def _agent_compact(text, limit=1000):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _as_text_list(value):
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, dict):
                name = item.get("姓名") or item.get("name") or item.get("label")
                if name:
                    result.append(str(name))
            elif item:
                result.append(str(item))
        return result
    if value:
        return [str(value)]
    return []


# ---------------------------------------------------------------------------
# AI 设置、任务中心、案件聊天
# ---------------------------------------------------------------------------

@app.route("/api/ai/settings", methods=["GET", "POST"])
def api_ai_settings():
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        return jsonify(AI_STORE.save_settings(payload))
    return jsonify(AI_STORE.get_settings(masked=True))


@app.route("/api/ai/test", methods=["POST"])
def api_ai_test():
    payload = request.get_json(silent=True) or {}
    profile = payload.get("profile", "strong")
    settings = AI_STORE.get_settings(masked=False)
    form_config = payload.get("config", {})
    if isinstance(form_config, dict) and profile in ("strong", "cheap"):
        target = settings.setdefault(profile, {})
        for field in ("protocol", "base_url", "model", "temperature", "max_tokens"):
            if field in form_config:
                target[field] = form_config[field]
        api_key = form_config.get("api_key")
        if api_key and api_key != "********":
            target["api_key"] = api_key
    client = AIClient(settings)
    try:
        content = client.chat(
            profile,
            [{"role": "user", "content": "请回复：连接正常"}],
            system="你是接口连通性测试助手，只需简短回复。",
            max_tokens=30,
        )
        return jsonify({"ok": True, "message": content.strip()})
    except AIServiceError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/jobs")
def api_jobs():
    case_id = request.args.get("case", "")
    jobs = AI_STORE.get_jobs()
    if case_id:
        jobs = [job for job in jobs if job.get("case") == case_id]
    return jsonify({"jobs": jobs})


@app.route("/api/jobs/<job_id>")
def api_job_detail(job_id):
    job = next((item for item in AI_STORE.get_jobs() if item.get("id") == job_id), None)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify({"job": job})


@app.route("/api/jobs/<job_id>/manifest")
def api_job_manifest(job_id):
    case_id = request.args.get("case", "")
    result = _load_material_job_manifest(job_id, case_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    _, manifest = result
    return jsonify({"manifest": manifest})


@app.route("/api/jobs/<job_id>/manifest/download")
def api_job_manifest_download(job_id):
    case_id = request.args.get("case", "")
    result = _load_material_job_manifest(job_id, case_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    manifest_path, _ = result
    return send_file(
        manifest_path,
        mimetype="application/json",
        as_attachment=True,
        download_name=f"{job_id}_manifest.json",
    )


@app.route("/api/jobs/<job_id>/artifact")
def api_job_artifact(job_id):
    case_id = request.args.get("case", "")
    kind = request.args.get("kind", "")
    result = _load_material_job_manifest(job_id, case_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    manifest_path, manifest = result
    artifact_path = _resolve_material_artifact_path(manifest_path, manifest, kind)
    if artifact_path is None:
        return jsonify({"error": "清单中没有对应文件"}), 404
    return send_file(artifact_path, as_attachment=True, download_name=artifact_path.name)


@app.route("/api/jobs/<job_id>/artifact/preview")
def api_job_artifact_preview(job_id):
    case_id = request.args.get("case", "")
    kind = request.args.get("kind", "")
    result = _load_material_job_manifest(job_id, case_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    manifest_path, manifest = result
    artifact_path = _resolve_material_artifact_path(manifest_path, manifest, kind)
    if artifact_path is None:
        return jsonify({"error": "清单中没有对应文件"}), 404
    if kind != "split_plan_preview":
        return jsonify({"error": "暂不支持预览该文件"}), 400
    with open(artifact_path, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        columns = reader.fieldnames or []
        rows = [{column: row.get(column, "") for column in columns} for row in reader]
    return jsonify({"columns": columns, "rows": rows})


@app.route("/api/jobs/<job_id>/open-output", methods=["POST"])
def api_job_open_output(job_id):
    case_id = request.args.get("case", "")
    result = _load_material_job_manifest(job_id, case_id)
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    manifest_path, manifest = result
    target = _resolve_material_output_dir(manifest_path, manifest)
    if target is None:
        return jsonify({"error": "没有可打开的输出目录"}), 404
    try:
        open_local_path(target)
    except OSError as exc:
        return jsonify({"error": f"打开输出目录失败: {exc}"}), 500
    return jsonify({"ok": True, "path": str(target)})


@app.route("/api/jobs/<job_id>/review-items")
def api_job_review_items(job_id):
    result = _load_material_job_manifest(job_id, "")
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[1], int):
        return result
    manifest_path, manifest = result
    outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
    candidate = outputs.get("review_items")
    if not candidate:
        return jsonify({"error": "review_items 不存在"}), 404

    # 只允许读取 material_jobs 目录内的 review_items.json
    material_jobs_dir = (AI_STORE.base_dir / "runtime" / "material_jobs").resolve()
    try:
        review_items_path = Path(candidate).resolve(strict=True)
        review_items_path.relative_to(material_jobs_dir)
    except ValueError:
        return jsonify({"error": "review_items 路径不在材料任务目录内"}), 403
    except OSError:
        return jsonify({"error": "review_items 文件不存在"}), 404

    if review_items_path.name != "review_items.json":
        return jsonify({"error": "review_items 文件名无效"}), 403
    try:
        with open(review_items_path, "r", encoding="utf-8") as fh:
            items = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"review_items 读取失败: {exc}"}), 500
    return jsonify({"review_items": items})


def _load_material_job_manifest(job_id, case_id=""):
    job = next((item for item in AI_STORE.get_jobs() if item.get("id") == job_id), None)
    if not job or (case_id and job.get("case") != case_id):
        return jsonify({"error": "任务不存在"}), 404

    manifest_value = job.get("manifest", "")
    if not manifest_value:
        return jsonify({"error": "任务清单不存在"}), 404

    material_jobs_dir = (AI_STORE.base_dir / "runtime" / "material_jobs").resolve()
    try:
        manifest_path = Path(manifest_value).resolve(strict=True)
        manifest_path.relative_to(material_jobs_dir)
    except ValueError:
        return jsonify({"error": "任务清单路径不在材料任务目录内"}), 403
    except OSError:
        return jsonify({"error": "任务清单文件不存在"}), 404

    if manifest_path.name != "manifest.json":
        return jsonify({"error": "任务清单文件名无效"}), 403

    try:
        with open(manifest_path, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"error": f"任务清单读取失败: {exc}"}), 500
    return manifest_path, manifest


def _resolve_material_artifact_path(manifest_path, manifest, kind):
    outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
    key_map = {
        "manifest": "manifest",
        "split_plan": "split_plan",
        "split_plan_preview": "split_plan_preview",
        "directory_text": "directory_text",
    }
    if kind == "manifest":
        return manifest_path
    output_key = key_map.get(kind)
    if not output_key or output_key not in outputs:
        return None
    return _safe_material_path(manifest_path, outputs.get(output_key), require_file=True)


def _resolve_material_output_dir(manifest_path, manifest):
    outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
    candidates = [
        outputs.get("coarse_split_dir"),
        outputs.get("output_dir"),
        (manifest.get("output_package") or {}).get("coarse_split_dir") if isinstance(manifest.get("output_package"), dict) else None,
    ]
    for item in manifest.get("files", []) if isinstance(manifest, dict) else []:
        output_pdf = item.get("output_pdf") or item.get("output_path")
        if output_pdf:
            candidates.append(str(Path(output_pdf).parent))
    candidates.append(str(manifest_path.parent))
    for candidate in candidates:
        target = _safe_material_path(manifest_path, candidate, require_file=False, allow_external=True)
        if target and target.is_dir():
            return target
    return None


def _safe_material_path(manifest_path, value, require_file=False, allow_external=False):
    if not value:
        return None
    try:
        path = Path(value).resolve(strict=True)
        if not allow_external:
            path.relative_to(manifest_path.parent)
    except (OSError, ValueError):
        return None
    if require_file and not path.is_file():
        return None
    return path


def run_auto_material_job(store, job_id):
    job = next((item for item in store.get_jobs() if item.get("id") == job_id), None)
    if not job:
        return

    store.update_job(job_id, status="running", progress=1, message="自动建库执行中")
    settings = store.get_settings(masked=False)
    mineru_settings = settings.get("mineru") or {}
    api_token = (mineru_settings.get("api_token") or "").strip()
    if not api_token:
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message="MinerU 未配置：api_token 未配置",
            finished_at=now_iso(),
        )
        return

    case_id = job.get("case") or ""
    params = job.get("params") or {}
    manifest_path = store.base_dir / "runtime" / "material_jobs" / job_id / "manifest.json"
    try:
        client = MinerUClient(mineru_settings)
        pipeline = AutoMaterialPipeline(store.base_dir, client, graph_builder=build_graphrag_index)
        manifest = pipeline.run(job_id=job_id, case_id=case_id, params=params)
        status = manifest.get("status") or "failed"
        message = manifest.get("message") or ("自动建库完成" if status == "completed" else "自动建库失败")
        outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
        graphrag_index = outputs.get("graphrag_index")
        changes = {
            "status": status,
            "progress": 100,
            "message": message,
            "finished_at": now_iso(),
        }
        if manifest_path.exists():
            changes["manifest"] = str(manifest_path)
        if graphrag_index:
            changes["graphrag_index"] = graphrag_index
        store.update_job(job_id, **changes)

        case_json = outputs.get("case_json")
        if status == "completed" and case_json:
            try:
                with open(case_json, "r", encoding="utf-8") as fh:
                    case_data = json.load(fh)
                # 若 params 里带了委托人，补齐到案件 JSON（不覆盖已有列表）
                entrusted_from_params = (params.get("entrusted_party") or "").strip()
                if entrusted_from_params:
                    entrusted_list = case_data.get("委托当事人")
                    if not isinstance(entrusted_list, list):
                        entrusted_list = []
                    if entrusted_from_params not in entrusted_list:
                        entrusted_list.append(entrusted_from_params)
                    case_data["委托当事人"] = entrusted_list
                save_case_data(case_id, case_data)
                _auto_enqueue_material_postprocess_jobs(store, job_id, case_id, params, case_data)
            except (OSError, json.JSONDecodeError):
                # 案件 JSON 保存失败不应覆盖主任务状态，只记录日志
                store.update_job(job_id, log=f"案件 JSON 保存失败: {case_json}")
    except Exception as exc:
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message=f"自动建库失败: {exc}",
            finished_at=now_iso(),
        )


def enqueue_analysis_chain(store, case_id, entrusted_party, marker_value=None):
    """创建并启动分析任务链。

    Args:
        store: AIStore 实例
        case_id: 案件 ID
        entrusted_party: 委托人姓名
        marker_value: 可选标记值，用于去重（如 material_job_id）

    Returns:
        创建的任务列表 [{"id": ..., "type": ..., "title": ...}, ...]
    """
    if not entrusted_party:
        raise ValueError("未提供委托人，无法启动分析任务链")

    settings = store.get_settings(masked=False)
    routing = settings.get("routing", {}) if isinstance(settings.get("routing"), dict) else {}

    def profile_for(job_type):
        if job_type in ("record_summaries", "person_summaries"):
            return routing.get("extract_default", "cheap")
        if job_type in ("case_context", "graph", "review"):
            return routing.get("review_default", "strong")
        return "cheap"

    def handler_for(job_type):
        if job_type == "graph":
            return lambda s, jid: run_graphrag_job(s, jid, load_case_data, save_case_data)
        if job_type in ("case_context", "record_summaries", "person_summaries", "review"):
            return lambda s, jid: run_analysis_job(s, jid, load_case_data, save_case_data, AIClient)
        return simulate_analysis_job

    titles = {
        "case_context": "生成委托人上下文",
        "record_summaries": "批量生成笔录摘要",
        "person_summaries": "生成人物摘要",
        "graph": "生成案情图谱",
    }
    chain = ["case_context", "record_summaries", "person_summaries", "graph"]

    marker_key = "__auto_from_material_job"
    already = set()
    if marker_value:
        for item in store.get_jobs():
            if item.get("case") != case_id:
                continue
            params = item.get("params") or {}
            if isinstance(params, dict) and params.get(marker_key) == marker_value:
                already.add(item.get("type"))

    created = []
    for job_type in chain:
        if job_type in already:
            continue
        job_params = {"entrusted_party": entrusted_party}
        if marker_value:
            job_params[marker_key] = marker_value
        new_job = store.create_job(
            case_id,
            job_type,
            titles[job_type],
            params=job_params,
            profile=profile_for(job_type),
        )
        run_job_background(store, new_job["id"], handler_for(job_type))
        created.append({"id": new_job["id"], "type": job_type, "title": titles[job_type]})

    return created


def _auto_enqueue_material_postprocess_jobs(store, material_job_id, case_id, material_params, case_data):
    material_params = material_params or {}
    if material_params.get("__postprocess_enqueued") or material_params.get("__postprocess_skipped"):
        store.update_job(material_job_id, log="后处理任务链已处理过，本次跳过重复创建")
        return

    entrusted = case_data.get("委托当事人")
    if not isinstance(entrusted, list):
        entrusted = []
    entrusted = [str(x).strip() for x in entrusted if str(x).strip()]
    entrusted_from_params = (material_params.get("entrusted_party") or "").strip()
    if entrusted_from_params and entrusted_from_params not in entrusted:
        entrusted.append(entrusted_from_params)

    if not entrusted:
        raise ValueError("未发现委托当事人，无法启动后处理任务链。请先确认委托人。")

    created = enqueue_analysis_chain(store, case_id, entrusted[0], marker_value=material_job_id)

    updated_params = dict(material_params)
    updated_params["__postprocess_enqueued"] = True
    updated_params["__postprocess_enqueued_jobs"] = [c["id"] for c in created]
    store.update_job(material_job_id, params=updated_params, log=f"已自动创建后处理任务：{len(created)} 个")


@app.route("/api/material/auto-build", methods=["POST"])
def api_material_auto_build():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    params = {}
    for key in ("raw_pdf", "case_name", "document_pdf", "document_type"):
        if key in payload:
            params[key] = payload.get(key)
    job = AI_STORE.create_job(
        case_id,
        "material_auto_build",
        "自动 MinerU 建库",
        params=params,
        profile="cheap",
    )
    run_job_background(AI_STORE, job["id"], run_auto_material_job)
    return jsonify({"job": job})


@app.route("/api/cases/<case_id>/confirm-client", methods=["POST"])
def api_confirm_client(case_id):
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "请提供委托人姓名"}), 400

    case_data = load_case_data(case_id)
    if not case_data:
        return jsonify({"error": f"案件不存在: {case_id}"}), 404

    entrusted = case_data.get("委托当事人")
    if not isinstance(entrusted, list):
        entrusted = []
    entrusted = [str(x).strip() for x in entrusted if str(x).strip()]
    if name not in entrusted:
        entrusted.append(name)
    case_data["委托当事人"] = entrusted
    save_case_data(case_id, case_data)

    created = enqueue_analysis_chain(AI_STORE, case_id, name)
    return jsonify({"entrusted_parties": entrusted, "jobs": created})


@app.route("/api/jobs/start", methods=["POST"])
def api_jobs_start():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    job_type = payload.get("type", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    titles = {
        "material_coarse_split": "粗分笔录",
        "material_refine_export": "细分插页并导出双面打印 PDF",
        "material_auto_build": "自动 MinerU 建库",
        "case_context": "生成委托人上下文",
        "record_summaries": "批量生成笔录摘要",
        "person_summaries": "生成人物摘要",
        "graph": "生成案情图谱",
        "review": "复核分析结果",
    }
    if job_type not in titles:
        return jsonify({"error": "未知任务类型"}), 400
    # 分析类任务需要委托人
    analysis_types = ("case_context", "record_summaries", "person_summaries", "graph", "review")
    if job_type in analysis_types:
        case_data = load_case_data(case_id)
        entrusted = case_data.get("委托当事人") if case_data else []
        if not isinstance(entrusted, list):
            entrusted = []
        entrusted = [str(x).strip() for x in entrusted if str(x).strip()]
        params_entrusted = (payload.get("params", {}).get("entrusted_party") or "").strip()
        if params_entrusted and params_entrusted not in entrusted:
            entrusted.append(params_entrusted)
        if not entrusted:
            return jsonify({"error": "请先确认委托人；委托人是摘要和图谱的中心"}), 400
    settings = AI_STORE.get_settings(masked=False)
    routing = settings.get("routing", {})
    if job_type.startswith("material"):
        profile = "cheap"
    elif job_type in ("record_summaries", "person_summaries"):
        profile = routing.get("extract_default", "cheap")
    elif job_type in ("case_context", "review", "graph"):
        profile = routing.get("review_default", "strong")
    else:
        profile = "cheap"
    job = AI_STORE.create_job(
        case_id,
        job_type,
        titles[job_type],
        params=payload.get("params", {}),
        profile=profile,
    )
    if job_type == "material_auto_build":
        handler = run_auto_material_job
    elif job_type.startswith("material"):
        handler = run_material_job
    elif job_type == "graph":
        handler = lambda store, job_id: run_graphrag_job(store, job_id, load_case_data, save_case_data)
    elif job_type in ("case_context", "record_summaries", "person_summaries", "review"):
        handler = lambda store, job_id: run_analysis_job(store, job_id, load_case_data, save_case_data, AIClient)
    else:
        handler = simulate_analysis_job
    run_job_background(AI_STORE, job["id"], handler)
    return jsonify({"job": job})


@app.route("/api/chat/history")
def api_chat_history():
    case_id = request.args.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    return jsonify({"messages": AI_STORE.get_chat(case_id)})


# ── Agent 通用经验记忆系统 ──

AGENT_MEMORY_PATH = BASE_DIR / "runtime" / "agent_memory.json"


def _load_agent_memories():
    """加载 Agent 积累的通用办案经验。"""
    try:
        if AGENT_MEMORY_PATH.is_file():
            with open(AGENT_MEMORY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


def _save_agent_memory(rule: str):
    """保存一条通用办案经验。去重：相同规则不重复存储。"""
    memories = _load_agent_memories()
    rule_clean = rule.strip()
    if not rule_clean or len(rule_clean) < 10:
        return False
    # 去重
    existing = {m.get("rule", "").strip() for m in memories}
    if rule_clean in existing:
        return False
    memories.append({
        "rule": rule_clean,
        "added_at": now_iso(),
    })
    AGENT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AGENT_MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)
    return True


@app.route("/api/agent/memories", methods=["GET", "POST", "DELETE"])
def api_agent_memories():
    """管理 Agent 通用经验记忆。"""
    if request.method == "GET":
        return jsonify({"memories": _load_agent_memories()})
    elif request.method == "POST":
        payload = request.get_json(silent=True) or {}
        rule = payload.get("rule", "").strip()
        if not rule:
            return jsonify({"error": "缺少 rule 参数"}), 400
        saved = _save_agent_memory(rule)
        return jsonify({"saved": saved, "total": len(_load_agent_memories())})
    elif request.method == "DELETE":
        payload = request.get_json(silent=True) or {}
        index = payload.get("index")
        memories = _load_agent_memories()
        if index is not None and 0 <= index < len(memories):
            removed = memories.pop(index)
            AGENT_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(AGENT_MEMORY_PATH, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
            return jsonify({"removed": removed, "total": len(memories)})
        return jsonify({"error": "无效的索引"}), 400


def _build_evidence_context(data: dict) -> str:
    """构建证据目录摘要上下文，供小扣了解有哪些非笔录证据可用。"""
    directory = data.get("证据目录")
    if not directory:
        # 尝试从建库 manifest 中读取并解析
        case_name = data.get("案件名称", "")
        for job in reversed(AI_STORE.get_jobs()):
            if job.get("case") == case_name and job.get("type") == "material_auto_build":
                try:
                    _, manifest = _load_material_job_manifest(job["id"], "")
                    outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
                    toc_text = ""
                    for key, val in outputs.items():
                        if "directory" in str(key).lower() or "toc" in str(key).lower():
                            out_dir = val.get("output_dir") if isinstance(val, dict) else str(val)
                            md = os.path.join(str(BASE_DIR), out_dir, "full.md")
                            if os.path.isfile(md):
                                toc_text = open(md, encoding="utf-8").read()
                                break
                    if toc_text:
                        page_offset = manifest.get("page_offset", 0)
                        directory = parse_full_directory(toc_text, page_offset=page_offset)
                        if directory:
                            data["证据目录"] = directory
                            save_case_data(case_name, data)
                except Exception:
                    pass
                break

    if not directory:
        return ""

    # 已有解析结果的证据
    other_evidence = data.get("其他证据") or []
    parsed_indices = {e.get("条目索引") for e in other_evidence if e.get("条目索引")}

    # 按类型分组摘要
    by_type = {}
    for d in directory:
        t = d.get("证据类型", "其他")
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(d)

    lines = ["【证据卷目录摘要 — 小扣可调取的非笔录证据】"]
    lines.append("格式：条目索引. 名称 (页码范围, 页数) [已解析/未解析]")
    lines.append("")

    # 只展示非笔录类型
    skip_types = {"讯问/询问笔录"}
    for t in sorted(by_type):
        if t in skip_types:
            continue
        items = by_type[t]
        lines.append(f"## {t} ({len(items)}条)")
        for d in items[:20]:  # 每种最多20条，避免上下文过长
            status = "已解析" if d["index"] in parsed_indices else "未解析"
            pages = f"P{d.get('证据卷页码', [0,0])[0]}-{d.get('证据卷页码', [0,0])[1]}"
            name = (d.get("名称") or "")[:60]
            lines.append(f"  {d['index']}. {name} ({pages}, {d.get('页数',0)}页) [{status}]")
        if len(items) > 20:
            lines.append(f"  ... 还有 {len(items) - 20} 条")
        lines.append("")

    # 追加已解析证据内容
    if other_evidence:
        lines.append("")
        lines.append("【已解析证据内容 — 可直接引用】")
        for ev in other_evidence[-10:]:  # 最近10份
            idx = ev.get("条目索引", "")
            name = (ev.get("名称") or ev.get("标题") or "")[:80]
            text = (ev.get("内容") or ev.get("全文") or "")[:2000]
            if text:
                lines.append(f"## 条目{idx}：{name}")
                lines.append(text)
                lines.append("")

    return "\n".join(lines)


@app.route("/api/chat", methods=["POST"])
def api_chat():
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    message = (payload.get("message") or "").strip()
    settings = AI_STORE.get_settings(masked=False)
    profile = payload.get("profile") or settings.get("routing", {}).get("chat_default", "strong")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    context = _extract_case_parties(data)
    evidence_summary = _build_evidence_context(data)
    # 加载 Agent 积累的通用办案经验
    agent_memories = _load_agent_memories()
    memory_text = ""
    if agent_memories:
        memory_text = "【已积累的办案经验】\n"
        for m in agent_memories[-10:]:  # 最近10条
            memory_text += f"- {m.get('rule', '')}\n"
        memory_text += "\n"

    system = (
        "你是刑事辩护阅卷助手。回答必须围绕委托当事人，避免直接下主犯/从犯等结论性评价；"
        "如涉及事实，请尽量说明证据来源或提示需要核对具体笔录。\n\n"
        "你有能力调取证据卷中的非笔录材料（搜查扣押清单、鉴定意见、价格认定书、勘验笔录等）。"
        "当你认为需要查看某份证据才能回答用户问题时，在回答末尾加一行：\n"
        "[PARSE_EVIDENCE: 条目索引1, 条目索引2, ...]\n"
        "系统会自动解析这些证据并将内容提供给你做后续分析。\n"
        "条目索引来自下方「证据卷目录摘要」，请根据证据类型和名称选择可能相关的条目。\n\n"
        f"{memory_text}"
        "如果在办案过程中发现通用规律（非本案特定信息），可在回答末尾加一行：\n"
        "[MEMORY: 规律描述]\n"
        "例如：[MEMORY: 扣押物品明细通常在价格认定书附表中而非搜查笔录正文]\n"
        "系统会自动保存这些经验，供后续案件复用。\n\n"
        "输出标记规则（所有标记放在回答最后一行，标记之前为正文）：\n"
        "1. 如果用户要求保存结果，加一行 [SAVE: title=文件名, format=csv|md|txt]\n"
        "2. 如果用户要求更新某人的笔录摘要，按原有格式重新生成摘要正文，末尾加一行 [UPDATE: 笔录摘要, key=人物姓名]\n"
        "3. 如果用户要求更新某人的图片人物摘要，重新生成摘要正文，末尾加一行 [UPDATE: 人物摘要, key=人物姓名]\n"
        "4. 如果用户要求更新案情图谱，输出新的图谱JSON，末尾加一行 [UPDATE: 案情图谱]"
    )
    # 查询增强：用弱模型判断是否需合并上一轮问题
    chat_history = AI_STORE.get_chat(case_id)
    search_query = message
    prev = ""
    for item in reversed(chat_history):
        if item.get("role") == "user" and item.get("content", "").strip() != message.strip():
            prev = item["content"]
            break
    if prev:
        try:
            classifier = AIClient(settings)
            decision = classifier.chat("cheap", [
                {"role": "user", "content": (
                    f"上一轮问题：{prev}\n当前问题：{message}\n"
                    "判断当前问题是否在讨论和上一轮相同的话题（是延伸追问/确认/深入）。"
                    "只回答 YES 或 NO。"
                )}
            ], max_tokens=3)
            if "YES" in decision.upper():
                search_query = f"{message} {prev}"
        except Exception:
            pass
    retrieval = retrieve_graphrag(case_id, data, BASE_DIR, search_query, limit=12)
    graphrag_context = format_graphrag_context(retrieval)
    case_context = (
        f"\n\n【当前案件背景 — 每次对话自动更新】\n"
        f"案件名称：{data.get('案件名称', case_id)}\n"
        f"委托当事人：{'、'.join(context.get('entrusted_parties', [])) or '未确认'}\n"
        f"涉案核心人物：{'、'.join(context.get('related_people', [])) or '未提取'}\n\n"
        f"{graphrag_context}\n"
        f"起诉书主线摘要：{context.get('indictment_summary', '')}\n"
        f"{evidence_summary}"
    )
    system_full = system + case_context
    messages = []
    for item in chat_history[-8:]:
        if item.get("role") in ("user", "assistant"):
            messages.append({"role": item["role"], "content": item.get("content", "")})
    messages.append({"role": "user", "content": message})

    try:
        client = AIClient(settings)
        answer = client.chat(profile, messages, system=system_full, max_tokens=2400)
    except AIServiceError as exc:
        return jsonify({"error": str(exc)}), 400

    # 检测 [MEMORY: ...] 标记 — 保存通用经验
    memory_match = re.search(r"\[MEMORY:\s*([^\]]+)\]", answer)
    if memory_match:
        rule = memory_match.group(1).strip()
        if _save_agent_memory(rule):
            answer = answer[: memory_match.start()].strip()
            # 追加确认信息
            answer += f"\n\n> 已记录经验：{rule}"

    # 检测 [PARSE_EVIDENCE: ...] 标记
    parse_match = re.search(r"\[PARSE_EVIDENCE:\s*([^\]]+)\]", answer)
    parse_entries = []
    parse_job_id = None
    if parse_match:
        try:
            parse_entries = [int(x.strip()) for x in parse_match.group(1).split(",") if x.strip().isdigit()]
        except ValueError:
            parse_entries = []
        # 剥离标记，只保留正文
        answer = answer[: parse_match.start()].strip()
        # 自动提交解析任务
        if parse_entries:
            directory = data.get("证据目录") or []
            selected = [d for d in directory if d.get("index") in parse_entries]
            if selected:
                manifest = None
                for job in reversed(AI_STORE.get_jobs()):
                    if job.get("case") == case_id and job.get("type") == "material_auto_build":
                        try:
                            _, manifest = _load_material_job_manifest(job["id"], case_id)
                        except Exception:
                            pass
                        break
                raw_pdf = (manifest.get("params") or {}).get("raw_pdf") if manifest else ""
                if raw_pdf and os.path.isfile(raw_pdf):
                    params = {"case_id": case_id, "raw_pdf": raw_pdf, "entries": selected}
                    ev_job = AI_STORE.create_job(
                        case_id, "evidence_parse",
                        f"小扣自动解析 {len(selected)} 份证据",
                        params=params, profile="cheap",
                    )
                    run_job_background(AI_STORE, ev_job["id"], _run_evidence_parse_job)
                    parse_job_id = ev_job["id"]

    AI_STORE.append_chat(case_id, "user", message, profile=profile)
    assistant_msg = AI_STORE.append_chat(case_id, "assistant", answer, profile=profile)

    response = {"message": assistant_msg}
    if parse_job_id:
        response["action"] = "parse_evidence"
        response["parse_entries"] = parse_entries
        response["parse_job_id"] = parse_job_id
        response["parse_hint"] = (
            f"已自动提交 {len(parse_entries)} 份证据的解析任务 (job: {parse_job_id})。"
            f"解析完成后可继续向我提问。"
        )
    return jsonify(response)


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """SSE 流式聊天 — 分阶段推送检索状态、思考过程、逐字输出。"""
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    message = (payload.get("message") or "").strip()
    settings = AI_STORE.get_settings(masked=False)
    profile = payload.get("profile") or settings.get("routing", {}).get("chat_default", "strong")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400
    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    def generate():
        # 构建基础上下文（无 GraphRAG — 由模型自己驱动检索）
        context = _extract_case_parties(data)
        evidence_summary = _build_evidence_context(data)
        agent_memories = _load_agent_memories()
        memory_text = ""
        if agent_memories:
            memory_text = "【已积累的办案经验】\n"
            for m in agent_memories[-10:]:
                memory_text += f"- {m.get('rule', '')}\n"
            memory_text += "\n"

        records_lookup = {r["id"]: r for r in data.get("笔录列表", [])}
        chat_history = AI_STORE.get_chat(case_id)

        system = (
            "你是刑事辩护阅卷助手。回答必须围绕委托当事人，避免直接下主犯/从犯等结论性评价；"
            "如涉及事实，请尽量说明证据来源或提示需要核对具体笔录。\n\n"
            "【你的工具箱 — 自己决定何时用什么】\n"
            "你启动时只有案件基本信息和证据目录。要用以下工具获取具体证据：\n"
            "- [SEARCH: 关键词] → 在案卷中搜索相关证据片段（GraphRAG检索）\n"
            "- [FETCH_RECORD: 笔录ID] → 获取某份笔录的完整全文\n"
            "- [PARSE_EVIDENCE: 条目索引] → 解析证据卷中的非笔录材料（鉴定意见、勘验笔录等）\n\n"
            "工作流程：用户提问 → 你想清楚需要查什么 → 发一个工具指令 → 系统执行并把结果追加给你 → "
            "你可以继续发指令 → 证据足够后给出最终答案。\n"
            "每次只能发一个指令。不要一次性列多个指令。不要问用户\"要不要继续查\"——自己决定，自己查。\n"
            "最多使用 5 次工具。当你认为证据已足够，直接给出最终答案，不要带任何工具标记。\n"
            "- [REBUILD_INDEX: 理由] → 请求重建GraphRAG索引（需用户确认后才执行）\n\n"
            f"{memory_text}"
            "如果在办案过程中发现通用规律（非本案特定信息），可在回答末尾加一行：\n"
            "[MEMORY: 规律描述]\n"
            "例如：[MEMORY: 扣押物品明细通常在价格认定书附表中而非搜查笔录正文]\n"
            "系统会自动保存这些经验，供后续案件复用。\n\n"
            "输出标记规则（所有标记放在回答最后一行，标记之前为正文）：\n"
            "1. 如果用户要求保存结果，加一行 [SAVE: title=文件名, format=csv|md|txt]\n"
            "2. 如果用户要求更新某人的笔录摘要，按原有格式重新生成摘要正文，末尾加一行 [UPDATE: 笔录摘要, key=人物姓名]\n"
            "3. 如果用户要求更新某人的图片人物摘要，重新生成摘要正文，末尾加一行 [UPDATE: 人物摘要, key=人物姓名]\n"
            "4. 如果用户要求更新案情图谱，输出新的图谱JSON，末尾加一行 [UPDATE: 案情图谱]"
        )
        case_context = (
            f"\n\n【案件信息】\n"
            f"案件名称：{data.get('案件名称', case_id)}\n"
            f"委托当事人：{'、'.join(context.get('entrusted_parties', [])) or '未确认'}\n"
            f"涉案核心人物：{'、'.join(context.get('related_people', [])) or '未提取'}\n"
            f"起诉书主线摘要：{context.get('indictment_summary', '')}\n"
            f"{evidence_summary}"
        )
        system_full = system + case_context

        messages = []
        for item in chat_history[-8:]:
            if item.get("role") in ("user", "assistant"):
                messages.append({"role": item["role"], "content": item.get("content", "")})
        messages.append({"role": "user", "content": message})

        # 工具调用循环：模型驱动，最多 5 轮
        yield _sse_event("stage", {"stage": "thinking", "text": "模型正在分析…"})

        client = AIClient(settings)
        full_answer = ""
        parse_entries = []
        memory_note = ""
        MAX_ROUNDS = 5

        for round_num in range(MAX_ROUNDS + 1):
            is_last = (round_num == MAX_ROUNDS)
            try:
                if is_last:
                    for token in client.chat_stream(profile, messages, system=system_full, max_tokens=3200):
                        full_answer += token
                        yield _sse_event("token", {"content": token})
                    break
                # 工具轮：静默调用，检查标记
                round_answer = client.chat(profile, messages, system=system_full, max_tokens=500)
            except AIServiceError as exc:
                if round_num > 0:
                    break
                yield _sse_event("error", {"text": str(exc)})
                return

            # 检测工具标记
            search_match = re.search(r"\[SEARCH:\s*([^\]]+)\]", round_answer)
            fetch_match = re.search(r"\[FETCH_RECORD:\s*(\d+)\]", round_answer)
            parse_match = re.search(r"\[PARSE_EVIDENCE:\s*([^\]]+)\]", round_answer)
            rebuild_match = re.search(r"\[REBUILD_INDEX:\s*([^\]]*)\]", round_answer)

            if search_match:
                query = search_match.group(1).strip()
                partial = round_answer[:search_match.start()].strip()
                messages.append({"role": "assistant", "content": partial or f"正在检索：{query[:30]}…"})
                yield _sse_event("stage", {"stage": "thinking", "text": f"检索：{query[:20]}…"})
                new_retrieval = retrieve_graphrag(case_id, data, BASE_DIR, query, limit=12)
                # 自动补齐截断
                seen = set()
                for chunk in new_retrieval.get("chunks", [])[:8]:
                    meta = chunk.get("metadata") or {}
                    rid = meta.get("record_id")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    rec = records_lookup.get(rid)
                    if rec and len(rec.get("全文内容") or "") > len(chunk.get("text", "")) * 1.5:
                        chunk["text"] = (rec.get("全文内容") or "")[:6000]
                new_ctx = format_graphrag_context(new_retrieval)
                messages.append({"role": "user", "content": f"[检索结果]\n{new_ctx}"})
                continue

            if fetch_match:
                rid = int(fetch_match.group(1))
                partial = round_answer[:fetch_match.start()].strip()
                messages.append({"role": "assistant", "content": partial or f"正在调取笔录 ID={rid}…"})
                yield _sse_event("stage", {"stage": "thinking", "text": "调取笔录全文…"})
                rec = records_lookup.get(rid)
                if rec:
                    full_text = (rec.get("全文内容") or "")[:6000]
                    citation = f"{rec.get('姓名','')} {rec.get('日期','')} {rec.get('笔录类型','')} P{rec.get('印刷页码','')}"
                    messages.append({"role": "user", "content": f"[完整笔录]\n{citation}\n\n{full_text}"})
                else:
                    messages.append({"role": "user", "content": f"[系统] 未找到记录 ID={rid}"})
                continue

            if parse_match:
                try:
                    entries = [int(x.strip()) for x in parse_match.group(1).split(",") if x.strip().isdigit()]
                except ValueError:
                    entries = []
                parse_entries = entries
                partial = round_answer[:parse_match.start()].strip()
                messages.append({"role": "assistant", "content": partial or f"正在提交 {len(entries)} 份证据解析…"})
                yield _sse_event("stage", {"stage": "thinking", "text": f"提交证据解析：{len(entries)} 份…"})
                messages.append({"role": "user", "content": f"[系统] 已记录 {len(entries)} 份证据解析请求，解析完成后可继续提问。"})
                continue

            if rebuild_match:
                reason = rebuild_match.group(1).strip()
                partial = round_answer[:rebuild_match.start()].strip()
                full_answer = partial or f"建议重建GraphRAG索引：{reason}"
                # 保存聊天记录后再发 done
                AI_STORE.append_chat(case_id, "user", message, profile=profile)
                AI_STORE.append_chat(case_id, "assistant", full_answer, profile=profile)
                yield _sse_event("done", {
                    "rebuild_requested": True,
                    "rebuild_reason": reason,
                })
                return

            # 无工具标记 → 模型认为够了，流式输出最终答案
            yield _sse_event("stage", {"stage": "thinking", "text": "正在生成回复…"})
            for token in client.chat_stream(profile, messages, system=system_full, max_tokens=3200):
                full_answer += token
                yield _sse_event("token", {"content": token})
            break

        # 保存聊天记录
        AI_STORE.append_chat(case_id, "user", message, profile=profile)
        AI_STORE.append_chat(case_id, "assistant", full_answer, profile=profile)

        # 检测记忆标记
        memory_match = re.search(r"\[MEMORY:\s*([^\]]+)\]", full_answer)
        if memory_match:
            rule = memory_match.group(1).strip()
            if _save_agent_memory(rule):
                memory_note = f"\n\n> 已记录经验：{rule}"

        yield _sse_event("done", {
            "memory_note": memory_note,
            "parse_entries": parse_entries,
        })

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── 证据材料（非笔录证据按需解析） ──


@app.route("/api/evidence-directory")
def api_evidence_directory():
    """返回案件的完整证据目录（分类后），供证据材料 Tab 展示。"""
    case_id = _get_arg_fixed("case")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    # 优先从案件 JSON 读取已缓存的证据目录
    directory = data.get("证据目录")
    if directory:
        return jsonify({"case_name": data.get("案件名称", case_id), "directory": directory})

    # 尝试从建库 manifest 中读取目录文本并解析
    manifest = None
    for job in reversed(AI_STORE.get_jobs()):
        if job.get("case") == case_id and job.get("type") == "material_auto_build":
            try:
                _, manifest = _load_material_job_manifest(job["id"], case_id)
            except Exception:
                pass
            if manifest:
                break

    if not manifest:
        return jsonify({"directory": [], "message": "未找到建库记录，请先完成自动建库"})

    # 获取目录文本
    toc_text = ""
    outputs = manifest.get("outputs", {}) if isinstance(manifest, dict) else {}
    for stage_key in ("directory_mineru", "01_directory_mineru"):
        stage = outputs.get(stage_key) or {}
        if not isinstance(stage, dict):
            # manifest 的 outputs 可能是扁平的
            pass
    # 遍历 outputs 查找 MinerU 输出
    for key, val in (outputs.items() if isinstance(outputs, dict) else []):
        if "directory" in key.lower() or "toc" in key.lower():
            toc_dir = val.get("output_dir") if isinstance(val, dict) else str(val)
            md_path = os.path.join(str(BASE_DIR), toc_dir, "full.md")
            if os.path.isfile(md_path):
                try:
                    with open(md_path, "r", encoding="utf-8") as fh:
                        toc_text = fh.read()
                except Exception:
                    pass
                break

    if not toc_text:
        return jsonify({"directory": [], "message": "未找到目录解析结果，建库可能尚未完成目录 MinerU 阶段"})

    page_offset = manifest.get("page_offset") or manifest.get("params", {}).get("page_offset") or 0
    raw_pdf_param = (manifest.get("params") or {}).get("raw_pdf") or ""
    pdf_page_count = None
    if raw_pdf_param and os.path.isfile(raw_pdf_param):
        try:
            import fitz
            doc = fitz.open(raw_pdf_param)
            pdf_page_count = len(doc)
            doc.close()
        except Exception:
            pass

    directory = parse_full_directory(toc_text, pdf_page_count=pdf_page_count, page_offset=page_offset)

    # 缓存到案件 JSON
    if directory:
        data["证据目录"] = directory
        save_case_data(case_id, data)

    return jsonify({
        "case_name": data.get("案件名称", case_id),
        "page_offset": page_offset,
        "directory": directory,
    })


@app.route("/api/evidence/parse", methods=["POST"])
def api_evidence_parse():
    """按需解析选中的证据条目。"""
    payload = request.get_json(silent=True) or {}
    case_id = payload.get("case", "")
    if not case_id:
        return jsonify({"error": "缺少 case 参数"}), 400

    entries = payload.get("entries") or []
    if not entries or not isinstance(entries, list):
        return jsonify({"error": "请提供要解析的条目索引列表"}), 400

    data = load_case_data(case_id)
    if data is None:
        return jsonify({"error": f"案件 {case_id} 不存在"}), 404

    directory = data.get("证据目录")
    if not directory:
        return jsonify({"error": "未找到证据目录，请先完成建库或刷新证据目录"}), 400

    # 从 manifest 获取 raw_pdf
    manifest = None
    for job in reversed(AI_STORE.get_jobs()):
        if job.get("case") == case_id and job.get("type") == "material_auto_build":
            try:
                _, manifest = _load_material_job_manifest(job["id"], case_id)
            except Exception:
                pass
            if manifest:
                break

    if not manifest:
        return jsonify({"error": "未找到建库记录"}), 400

    raw_pdf = (manifest.get("params") or {}).get("raw_pdf") or ""
    if not raw_pdf or not os.path.isfile(raw_pdf):
        return jsonify({"error": "建库原始 PDF 不存在，无法切分证据"}), 400

    # 创建解析任务
    selected = [d for d in directory if d.get("index") in entries]
    if not selected:
        return jsonify({"error": "未匹配到选中的条目"}), 400

    params = {
        "case_id": case_id,
        "raw_pdf": raw_pdf,
        "entries": selected,
    }
    job = AI_STORE.create_job(
        case_id,
        "evidence_parse",
        f"解析 {len(selected)} 份证据材料",
        params=params,
        profile="cheap",
    )
    run_job_background(AI_STORE, job["id"], _run_evidence_parse_job)
    return jsonify({"job": job})


def _run_evidence_parse_job(store, job_id):
    """后台任务：按需解析选中的证据条目。"""
    import pymupdf

    job = store.get_job(job_id)
    if not job:
        return
    params = job.get("params", {})
    case_id = params.get("case_id", "")
    raw_pdf = params.get("raw_pdf", "")
    entries = params.get("entries", [])

    store.update_job(job_id, status="running", message="开始解析证据材料", progress=5)

    try:
        doc = pymupdf.open(raw_pdf)
    except Exception as e:
        store.update_job(job_id, status="failed", message=f"无法打开 PDF: {e}")
        return

    try:
        data = load_case_data(case_id)
        if not data:
            raise ValueError("案件不存在")
        if "其他证据" not in data:
            data["其他证据"] = []

        other = data["其他证据"]
        total = len(entries)
        parsed = 0

        for idx, entry in enumerate(entries):
            pdf_start = entry.get("pdf页码", [0, 0])[0]
            pdf_end = entry.get("pdf页码", [0, 0])[1]
            # 页码从 1 开始，PyMuPDF 从 0 开始
            start_page = max(0, pdf_start - 1)
            end_page = min(len(doc) - 1, pdf_end - 1)

            store.update_job(
                job_id,
                message=f"切分: {entry.get('名称', '')} (P{pdf_start}-{pdf_end})",
                progress=10 + int(80 * idx / total),
            )

            # 切分 PDF
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                split_pdf_path = tmp.name
            try:
                new_doc = pymupdf.open()
                new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page)
                new_doc.save(split_pdf_path)
                new_doc.close()

                # MinerU OCR
                from mineru_client import MinerUClient
                mineru_config = AI_STORE.get_settings(masked=False).get("mineru", {})
                client = MinerUClient(mineru_config)

                output_dir = (
                    BASE_DIR / "runtime" / "material_jobs" / job_id / f"other_{entry['index']}"
                )
                client.parse_pdf_to_clean_dir(split_pdf_path, str(output_dir),
                                              job_label=f"other_evidence_{entry['index']}")

                # 读取 OCR 结果
                md_path = output_dir / "full.md"
                ocr_content = md_path.read_text(encoding="utf-8") if md_path.is_file() else ""

                # 存入案件 JSON
                evidence_item = {
                    "id": f"other_{entry['index']}_{uuid.uuid4().hex[:8]}",
                    "条目索引": entry["index"],
                    "证据类型": entry.get("证据类型", ""),
                    "名称": entry.get("名称", ""),
                    "页码范围": [pdf_start, pdf_end],
                    "MinerU目录": str(output_dir),
                    "OCR状态": "completed",
                    "ocr全文": ocr_content,
                    "解析时间": now_iso(),
                }
                other.append(evidence_item)
                parsed += 1

                store.update_job(job_id,
                                 message=f"已完成 {parsed}/{total}: {entry.get('名称', '')}",
                                 progress=10 + int(80 * (idx + 1) / total),
                                 log=f"解析完成: {entry.get('名称', '')}")
            except Exception as item_error:
                store.update_job(job_id,
                                 log=f"解析失败 [{entry.get('名称', '')}]: {item_error}")
            finally:
                try:
                    os.remove(split_pdf_path)
                except OSError:
                    pass

        doc.close()
        data["其他证据"] = other
        save_case_data(case_id, data)

        store.update_job(job_id, status="completed",
                         message=f"完成：{parsed}/{total} 份证据解析成功",
                         progress=100)

    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        store.update_job(job_id, status="failed", message=f"证据解析失败: {e}")


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
