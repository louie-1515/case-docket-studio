import csv
import html
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
SAFE_FILENAME_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RECORD_TYPE_PATTERN = re.compile(r"(讯问笔录|询问笔录|辨认笔录|检查笔录|搜查笔录|提取笔录|扣押笔录|询问|讯问|笔录)")
DIRECTORY_KEYWORDS = ("目录", "讯问笔录", "询问笔录", "辨认笔录", "证据卷", "页码")
TARGET_RECORD_TYPES = ("讯问笔录", "询问笔录")

# ── 证据类型分类规则引擎 ──
# 按优先级排列，条目匹配到即停止。关键词对条目文本做子串匹配。
EVIDENCE_CLASSIFICATION_RULES = [
    # (优先级, 类别名, [关键词列表])
    (1, "讯问/询问笔录", ["讯问笔录", "询问笔录"]),
    (2, "辨认/指认", ["辨认笔录", "指认笔录", "辨认照片"]),
    (3, "电子数据类", ["电子数据", "电子证据", "数据检查", "关键截图",
                         "硬盘镜像", "手机取证", "微信记录", "支付宝记录",
                         "电子勘验", "电子物证", "电子提取"]),
    (4, "搜查/扣押类", ["搜查证", "搜查笔录", "搜查记录", "扣押清单", "扣押证据",
                         "扣押笔录", "扣押决定书", "扣押款物", "查封", "封存",
                         "扣押物品", "扣押决定"]),
    (5, "勘验/检查类", ["勘验笔录", "现场勘验", "现场照片", "现场示意图",
                         "勘查笔录", "勘验检查", "人身检查"]),
    (6, "鉴定意见类", ["鉴定意见", "鉴定书", "鉴定聘请书", "检验报告", "司法鉴定",
                         "鉴定报告"]),
    (7, "价格认定类", ["价格认定", "价格证明", "价格鉴定", "价格评估", "货值认定",
                         "价格结论书"]),
    (8, "检查/提取笔录", ["检查笔录", "提取笔录", "提取清单", "调取证据"]),
    (9, "程序文书类", ["传唤证", "拘留证", "逮捕证", "取保候审", "监视居住",
                         "权利义务告知", "询问通知书", "讯问通知书", "到案经过",
                         "抓获经过", "破案经过", "立案决定书", "立案告知书",
                         "回避", "调取证据通知书", "接受证据清单", "发还清单",
                         "认罪认罚承诺书", "认罪认罚"]),
    (10, "犯罪嫌疑人信息", ["犯罪嫌疑人基本情况", "户籍证明", "前科", "违法犯罪记录",
                              "刑事判决书", "释放证明", "身份信息"]),
    (11, "证人相关", ["证人权利义务", "证人资格", "询问通知书"]),
    (12, "情况说明", ["情况说明", "办案说明", "工作说明"]),
    (13, "其他", []),  # 兜底
]


def classify_evidence_type(entry_text: str) -> str:
    """对证据目录条目的文本做分类，返回类别名。"""
    if not entry_text:
        return "其他"
    text = str(entry_text)
    for _priority, category, keywords in EVIDENCE_CLASSIFICATION_RULES:
        if not keywords:
            continue
        for kw in keywords:
            if kw in text:
                return category
    return "其他"


# ── 完整目录解析（含非笔录条目） ──

def parse_full_directory(text, pdf_page_count=None, page_offset=0):
    """解析证据卷目录的全部条目（不仅限于讯问/询问笔录）。

    返回列表，每项包含：序号、条目名称、证据类型、页码范围、日期等。
    与 parse_directory_text_to_split_plan 不同，不过滤笔录类型。
    """
    # 复用已有的行解析和 HTML/表格解析逻辑
    raw_entries = _parse_all_directory_entries(text)
    if not raw_entries:
        return []

    items = []
    for index, entry in enumerate(raw_entries, start=1):
        evidence_start = entry["evidence_start"]
        evidence_end = entry.get("evidence_end") or evidence_start
        if evidence_end < evidence_start:
            evidence_end = evidence_start

        pdf_start = evidence_start + page_offset
        pdf_end = evidence_end + page_offset

        # 校验页码范围
        warnings = []
        if pdf_start < 1 or pdf_end < 1:
            warnings.append("换算后的 PDF 页码小于 1")
        if pdf_page_count and pdf_end > pdf_page_count:
            warnings.append(f"PDF 页码超出总页数 {pdf_page_count}")

        entry_text = entry.get("source_text", "")
        evidence_type = classify_evidence_type(entry_text)

        items.append({
            "index": index,
            "名称": entry.get("name", entry_text[:60]),
            "证据类型": evidence_type,
            "证据卷页码": [evidence_start, evidence_end],
            "pdf页码": [pdf_start, pdf_end],
            "页数": evidence_end - evidence_start + 1,
            "日期": entry.get("directory_date", ""),
            "涉及人员": entry.get("persons", []),
            "目录原始文本": entry_text,
            "warnings": warnings,
        })

    return items


def _parse_all_directory_entries(text):
    """解析目录文本中的所有条目，返回 raw entry 列表。"""
    text = str(text or "")

    # 尝试三种解析方式，取条目数最多的
    results = []
    for parser in [_parse_dir_lines_generic, _parse_dir_html_table, _parse_dir_flat_table]:
        try:
            entries = parser(text)
            if entries:
                results.append(entries)
        except Exception:
            pass

    if not results:
        return []
    # 取条目数最多的结果
    return max(results, key=len)


def _parse_dir_lines_generic(text):
    """通用逐行解析：匹配"数字-数字"页码范围模式，要求行有足够的上下文。"""
    entries = []
    for line_no, line in enumerate(str(text).splitlines(), start=1):
        line = line.strip()
        if not line or len(line) < 20:  # 目录行至少 20 字符
            continue
        # 必须匹配页码范围（多页或单页），页码范围必须在行尾
        page_match = re.search(
            r"(\d{2,5})\s*(?:[-—~至到])\s*(\d{2,5})\s*(?:页|P)?\s*$",
            line, re.IGNORECASE
        )
        if not page_match:
            continue
        evidence_start = int(page_match.group(1))
        evidence_end = int(page_match.group(2))
        if evidence_end < evidence_start or evidence_end > 5000:
            continue

        # 页码范围不能是单页单号（太容易误匹配）
        if evidence_start == evidence_end:
            continue

        # 提取日期（可选，没有也不拒绝）
        date_match = re.search(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", line)
        directory_date = date_match.group(1) if date_match else ""

        # 提取条目名称
        before_page = line[:page_match.start()].strip()
        before_page = re.sub(r"^[（(]?\d{1,4}[）)、.．\s-]*", "", before_page).strip()

        # 尝试提取人名
        persons = []
        person_matches = re.findall(r"([一-鿿]{2,4})(?=[）)]|$|\s|[（(])", before_page)
        if person_matches:
            persons = [p for p in person_matches if len(p) >= 2]

        name = before_page[:80] if before_page else line[:80]

        entries.append({
            "line_no": line_no,
            "name": name.strip(),
            "directory_date": directory_date,
            "evidence_start": evidence_start,
            "evidence_end": evidence_end,
            "persons": persons,
            "source_text": line,
        })
    return entries


def _parse_dir_html_table(text):
    """从 HTML 表格解析目录条目（MinerU 输出常见格式）。

    支持多种列布局：
    - 6列：序号 | 办案单位 | 文号 | 名称 | 日期 | 页码
    - 5列：序号 | 办案人 | 名称（含文号） | 日期 | 页码
    - 自动识别"名称"和"页码"所在的列
    """
    entries = []
    rows = re.findall(r"<tr>(.*?)</tr>", str(text), re.IGNORECASE | re.DOTALL)
    for row_index, row in enumerate(rows, start=1):
        cells = [html.unescape(re.sub(r"<.*?>", "", cell)).strip()
                 for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)]
        if len(cells) < 4 or cells[0] == "序号":
            continue
        try:
            seq = int(cells[0])
        except (ValueError, TypeError):
            seq = row_index

        # 合并所有单元格文本，从中提取关键字段
        full_text = " ".join(cells)

        # 提取页码范围（最后出现的 "数字-数字" 模式，支持1-5位页码）
        page_range_match = re.search(
            r"(\d{1,5})\s*(?:[-—~至到])\s*(\d{1,5})\s*$", full_text
        )
        if not page_range_match:
            # 尝试在最后两个单元格中查找
            for cell in reversed(cells[-2:]):
                pm = re.search(r"(\d{2,5})\s*(?:[-—~至到])\s*(\d{2,5})", cell)
                if pm:
                    page_range_match = pm
                    break
        if not page_range_match:
            continue

        evidence_start = int(page_range_match.group(1))
        evidence_end = int(page_range_match.group(2))
        if evidence_end < evidence_start or evidence_end > 5000:
            continue

        # 提取日期
        date_match = re.search(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", full_text)
        directory_date = date_match.group(1) if date_match else ""

        # 提取条目名称：页码范围之前、序号之后的内容
        before_page = full_text[:page_range_match.start()].strip()
        before_page = re.sub(r"^\d{1,4}\s*", "", before_page).strip()

        # 从名称中提取人名
        persons = []
        # 匹配括号内的人名列表
        bracket_match = re.search(r"[（(]([^）)]{2,60})[）)]", before_page)
        if bracket_match:
            person_text = bracket_match.group(1).replace("、", " ").replace("，", " ")
            person_matches = re.findall(r"([一-鿿]{2,4})", person_text)
            persons = [p for p in person_matches if len(p) >= 2 and p not in
                       ("讯问笔录", "询问笔录", "辨认笔录", "检查笔录", "搜查笔录",
                        "扣押清单", "权利义务", "告知书", "通知书")]

        # 清理条目名称
        name = before_page[:120].strip() if before_page else full_text[:120]

        entries.append({
            "line_no": seq,
            "name": name,
            "directory_date": directory_date,
            "evidence_start": evidence_start,
            "evidence_end": evidence_end,
            "persons": persons,
            "source_text": full_text,
        })
    return entries


def _parse_dir_flat_table(text):
    """从扁平表格文本解析目录条目。"""
    # 尝试匹配 tab 或 | 分隔的表格行
    entries = []
    for line_no, line in enumerate(str(text).splitlines(), start=1):
        line = line.strip()
        if not line or len(line) < 10:
            continue
        # 匹配行末页码范围
        page_match = re.search(r"(\d{2,5})\s*(?:[-—~至到])\s*(\d{2,5})\s*$", line)
        if not page_match:
            continue
        evidence_start = int(page_match.group(1))
        evidence_end = int(page_match.group(2))
        if evidence_end < evidence_start or evidence_end > 2000:
            continue

        date_match = re.search(r"(\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日)", line)
        directory_date = date_match.group(1) if date_match else ""

        before_page = line[:page_match.start()].strip()
        before_page = re.sub(r"^[（(]?\d{1,4}[）)、.．\s-]*", "", before_page).strip()

        persons = re.findall(r"([一-鿿]{2,4})(?=[）)]|$|\s|[（(])", before_page)
        persons = [p for p in persons if len(p) >= 2]

        entries.append({
            "line_no": line_no,
            "name": before_page[:80] if before_page else line[:80],
            "directory_date": directory_date,
            "evidence_start": evidence_start,
            "evidence_end": evidence_end,
            "persons": persons,
            "source_text": line,
        })
    return entries


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def plan_blank_insertions(title_pages):
    insertion_indices = []
    offset = 0
    for sys_page in sorted(int(page) for page in title_pages if int(page) > 0):
        if (sys_page + offset) % 2 == 0:
            insertion_indices.append(sys_page - 1)
            offset += 1
    return insertion_indices


def extract_title_pages_from_content_list(pages):
    title_pages = []
    for page_index, blocks in enumerate(pages):
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "title":
                continue
            content = block.get("content", {})
            if isinstance(content, dict) and content.get("level") == 1:
                title_pages.append(page_index + 1)
                break
    return title_pages


def parse_manual_split_items(raw_items):
    if raw_items in (None, ""):
        return []
    if isinstance(raw_items, str):
        try:
            data = json.loads(raw_items)
        except json.JSONDecodeError as exc:
            raise ValueError(f"人工页码清单不是有效 JSON: {exc}") from exc
    else:
        data = raw_items
    if not isinstance(data, list):
        raise ValueError("人工页码清单必须是数组")

    items = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条页码清单必须是对象")
        name = str(item.get("name") or item.get("姓名") or "").strip()
        if not name:
            raise ValueError(f"第 {index} 条页码清单缺少 name")
        ranges_data = item.get("ranges") or item.get("页码范围")
        if ranges_data is None:
            ranges_data = [{"start": item.get("start"), "end": item.get("end")}]
        if not isinstance(ranges_data, list) or not ranges_data:
            raise ValueError(f"第 {index} 条页码清单缺少 ranges")
        ranges = []
        for range_index, range_item in enumerate(ranges_data, start=1):
            if not isinstance(range_item, dict):
                raise ValueError(f"第 {index} 条第 {range_index} 个页码范围必须是对象")
            try:
                start = int(range_item.get("start"))
                end = int(range_item.get("end"))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"第 {index} 条第 {range_index} 个页码范围必须包含数字 start/end") from exc
            if start < 1 or end < start:
                raise ValueError(f"第 {index} 条第 {range_index} 个页码范围无效")
            ranges.append({"start": start, "end": end})
        items.append({"name": name, "ranges": ranges})
    return items


def safe_pdf_name(name):
    safe_name = SAFE_FILENAME_PATTERN.sub("_", str(name or "").strip()).strip(" .")
    if not safe_name:
        safe_name = "未命名"
    return f"{safe_name}.pdf"


def safe_split_pdf_name(index, item):
    name = safe_path_component(item.get("name"), "未命名")
    record_type = safe_path_component(item.get("record_type", "笔录"), "笔录")
    ranges = item.get("ranges") or []
    if ranges:
        start = ranges[0].get("start", "")
        end = ranges[-1].get("end", "")
        try:
            suffix = f"P{int(start):03d}-P{int(end):03d}"
        except (TypeError, ValueError):
            suffix = "P未知"
    else:
        suffix = "P未知"
    return f"{int(index):03d}_{name}_{record_type}_{suffix}.pdf"


def safe_path_component(name, fallback="未命名"):
    safe_name = SAFE_FILENAME_PATTERN.sub("_", str(name or "").strip()).strip(" .")
    return safe_name or fallback


def parse_positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def parse_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_directory_text_to_split_plan(text, pdf_page_count=None, page_offset=0):
    raw_entries = []
    for line_no, line in enumerate(str(text or "").splitlines(), start=1):
        entry = parse_directory_line(line, line_no)
        if entry:
            raw_entries.append(entry)
    html_entries = parse_html_directory_table_text(text)
    flat_entries = parse_flat_directory_table_text(text)
    if html_entries and len(html_entries) >= max(len(raw_entries), len(flat_entries)):
        raw_entries = html_entries
    elif flat_entries and len(flat_entries) >= len(raw_entries):
        raw_entries = flat_entries

    items = []
    for index, entry in enumerate(raw_entries, start=1):
        next_entry = raw_entries[index] if index < len(raw_entries) else None
        evidence_start = entry["evidence_start"]
        evidence_end = entry.get("evidence_end")
        inferred_end = False
        if evidence_end is None:
            if next_entry and next_entry["evidence_start"] > evidence_start:
                evidence_end = next_entry["evidence_start"] - 1
                inferred_end = True
            else:
                evidence_end = evidence_start
                inferred_end = True
        pdf_start = evidence_start + page_offset
        pdf_end = evidence_end + page_offset
        warnings = []
        if evidence_end < evidence_start:
            warnings.append("结束页小于起始页")
        if pdf_start < 1 or pdf_end < 1:
            warnings.append("换算后的 PDF 页码小于 1")
        if pdf_page_count and pdf_end > pdf_page_count:
            warnings.append(f"换算后的 PDF 页码超出总页数 {pdf_page_count}")
        confidence = 0.9
        if inferred_end:
            confidence -= 0.18
            warnings.append("结束页由下一条目录推断")
        if entry.get("record_type") in ("询问", "讯问", "笔录"):
            confidence -= 0.08
        if entry.get("record_type") not in TARGET_RECORD_TYPES:
            continue
        items.append(
            {
                "index": index,
                "name": entry["name"],
                "record_type": entry.get("record_type", ""),
                "directory_date": entry.get("directory_date", ""),
                "evidence_start": evidence_start,
                "evidence_end": evidence_end,
                "pdf_start": pdf_start,
                "pdf_end": pdf_end,
                "ranges": [{"start": pdf_start, "end": pdf_end}],
                "confidence": round(max(0.1, confidence), 2),
                "source_text": entry["source_text"],
                "warnings": warnings,
            }
        )

    for earlier, later in zip(items, items[1:]):
        if earlier["pdf_end"] >= later["pdf_start"]:
            earlier["warnings"].append(f"与第 {later['index']} 条页码重叠")
            later["warnings"].append(f"与第 {earlier['index']} 条页码重叠")
            earlier["confidence"] = min(earlier["confidence"], 0.55)
            later["confidence"] = min(later["confidence"], 0.55)
    return items


def parse_html_directory_table_text(text):
    entries = []
    rows = re.findall(r"<tr>(.*?)</tr>", str(text or ""), re.IGNORECASE | re.DOTALL)
    for row_index, row in enumerate(rows, start=1):
        cells = [
            html.unescape(re.sub(r"<.*?>", "", cell)).strip()
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)
        ]
        if len(cells) < 6 or cells[0] == "序号":
            continue
        seq, _author, _docno, title, date, pages = cells[:6]
        title_match = re.search(r"(?:刑事)?(讯问|询问)笔录[（(]([^）)]{1,200})[）)]", title)
        if not title_match:
            continue
        page_match = re.search(r"(\d{1,5})\s*[-—~至到]\s*(\d{1,5})", pages)
        if not page_match:
            continue
        name = extract_name_from_directory_title(title_match.group(2))
        if not name:
            continue
        try:
            line_no = int(seq)
        except (TypeError, ValueError):
            line_no = row_index
        entries.append(
            {
                "line_no": line_no,
                "name": name,
                "record_type": f"{title_match.group(1)}笔录",
                "directory_date": date,
                "evidence_start": int(page_match.group(1)),
                "evidence_end": int(page_match.group(2)),
                "source_text": " | ".join(cells),
            }
        )
    return entries


def parse_flat_directory_table_text(text):
    flattened = str(text or "").replace("\r", "\n")
    flattened = re.sub(r"律师阅卷：\S+\s+执业证号：\d+", " ", flattened)
    flattened = re.sub(r"\s*\n\s*", " | ", flattened)
    flattened = re.sub(r"\s+", " ", flattened)
    if not flattened.strip():
        return []

    type_options = "讯问|询问|辨认|检查|搜查|提取|扣押"
    entry_pattern = re.compile(
        rf"(?:^|\|\s*)"
        rf"(?P<prefix>.{{0,240}}?)"
        rf"(?P<record_type>(?:刑事)?(?:{type_options})笔录)"
        rf"（(?P<title>.{{1,180}}?)）\s*\|\s*"
        rf"(?P<date>\d{{4}}年\d{{1,2}}月\d{{1,2}}日)\s*\|\s*"
        rf"(?P<start>\d{{1,5}})\s*[-—~至到]\s*(?P<end>\d{{1,5}})",
    )
    entries = []
    for index, match in enumerate(entry_pattern.finditer(flattened), start=1):
        title = re.sub(r"\s*\|\s*", "", match.group("title")).strip()
        name = extract_name_from_directory_title(title)
        if not name:
            prefix = re.sub(r"\s*\|\s*", "", match.group("prefix")).strip()
            name_match = re.search(r"([\u4e00-\u9fff·]{2,10})$", prefix)
            name = name_match.group(1) if name_match else ""
        if not name:
            continue
        record_type = match.group("record_type")
        if record_type.startswith("刑事"):
            record_type = record_type[2:]
        entries.append(
            {
                "line_no": index,
                "name": name,
                "record_type": record_type,
                "directory_date": match.group("date"),
                "evidence_start": int(match.group("start")),
                "evidence_end": int(match.group("end")),
                "source_text": re.sub(r"\s+", " ", match.group(0)).strip(),
            }
        )
    return entries


def extract_name_from_directory_title(title):
    cleaned = re.sub(r"\s+", "", str(title or "")).replace("，", ",")
    cleaned = re.sub(r"^\W+", "", cleaned)
    candidate = re.split(r"[,、;；]", cleaned, maxsplit=1)[0]
    candidate = re.sub(r"[^A-Za-z0-9\u4e00-\u9fff·]", "", candidate)
    return candidate if re.search(r"[\u4e00-\u9fff]", candidate) else ""


def parse_directory_line(line, line_no):
    original = str(line or "").strip()
    if not original:
        return None
    normalized = re.sub(r"[.·•…⋯。．]{2,}", " ", original)
    normalized = re.sub(r"\s+", " ", normalized)
    if not RECORD_TYPE_PATTERN.search(normalized):
        return None
    page_match = re.search(
        r"(?:P|第\s*)?(\d{1,5})\s*(?:[-—~至到]\s*(?:P|第\s*)?(\d{1,5}))?\s*(?:页|P)?\s*$",
        normalized,
        re.IGNORECASE,
    )
    if not page_match:
        return None
    evidence_start = int(page_match.group(1))
    evidence_end = int(page_match.group(2)) if page_match.group(2) else None
    before_page = normalized[: page_match.start()].strip(" -—~至到\t")
    type_match = RECORD_TYPE_PATTERN.search(before_page)
    if not type_match:
        return None
    record_type = type_match.group(1)
    if record_type in ("询问", "讯问"):
        record_type = f"{record_type}笔录"
    before_type = before_page[: type_match.start()].strip()
    before_type = re.sub(r"^[（(]?\d{1,4}[）)、.．\s-]*", "", before_type).strip()
    name_match = re.search(r"([\u4e00-\u9fff·]{2,10})$", before_type)
    if not name_match:
        return None
    name = name_match.group(1)
    date_match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日)", before_page)
    return {
        "line_no": line_no,
        "name": name,
        "record_type": record_type,
        "directory_date": date_match.group(1) if date_match else "",
        "evidence_start": evidence_start,
        "evidence_end": evidence_end,
        "source_text": original,
    }


def import_pymupdf():
    try:
        import pymupdf

        return pymupdf
    except ImportError:
        try:
            import fitz

            return fitz
        except ImportError as exc:
            raise RuntimeError("缺少 PyMuPDF 依赖，请先安装 pymupdf") from exc


def find_job(store, job_id):
    for job in store.get_jobs():
        if job.get("id") == job_id:
            return job
    return None


def material_status_to_job_status(status):
    if status in ("completed", "needs_mineru_or_splitter", "needs_directory_ocr"):
        return "completed"
    if status == "partial":
        return "partial"
    return "failed"


def run_material_job(store, job_id):
    job = find_job(store, job_id)
    if not job:
        return None

    try:
        store.update_job(
            job_id,
            status="running",
            progress=5,
            message="材料处理任务启动",
            log="材料处理任务启动",
        )
        pipeline = MaterialPipeline(store.base_dir)
        job_type = job.get("type", "")
        case_id = job.get("case", "")
        params = job.get("params", {})

        if job_type == "material_coarse_split":
            manifest = pipeline.run_coarse_split(job_id, case_id, params)
        elif job_type == "material_refine_export":
            manifest = pipeline.run_refine_export(job_id, case_id, params)
        else:
            manifest = pipeline.create_manifest(job_id, case_id, job_type, params)
            manifest = pipeline.fail_manifest(manifest, f"未知材料任务类型: {job_type}")

        manifest_status = manifest.get("status", "failed")
        job_status = material_status_to_job_status(manifest_status)
        message = manifest.get("message", "") or "材料处理任务完成"
        store.update_job(
            job_id,
            status=job_status,
            progress=100,
            message=message,
            manifest=manifest.get("manifest_path", ""),
            log=message,
            finished_at=now_iso(),
        )
    except Exception as exc:
        message = f"材料处理任务失败: {exc}"
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message=message,
            log=message,
            finished_at=now_iso(),
        )
    return find_job(store, job_id)


class MaterialPipeline:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.runtime_dir = self.base_dir / "runtime" / "material_jobs"

    def job_dir(self, job_id):
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("Invalid material job_id")
        return self.runtime_dir / job_id

    def create_manifest(self, job_id, case_id, job_type, params):
        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "job_id": job_id,
            "case": case_id,
            "type": job_type,
            "params": params or {},
            "status": "created",
            "message": "",
            "files": [],
            "errors": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "manifest_path": str(job_dir / "manifest.json"),
        }
        self.write_manifest(manifest)
        return manifest

    def create_output_package(self, manifest, raw_pdf_path):
        job_dir = Path(manifest["manifest_path"]).parent
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        case_name = safe_path_component(manifest.get("case") or Path(raw_pdf_path).stem, "案件")
        package_dir = job_dir / f"{case_name}_目录解析粗分_{timestamp}"
        dirs = {
            "package_dir": package_dir,
            "directory_ocr_dir": package_dir / "01_目录页待OCR",
            "directory_result_dir": package_dir / "02_目录解析结果",
            "coarse_split_dir": package_dir / "03_coarse_split_粗分PDF",
        }
        for path in dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        manifest["root_manifest_path"] = manifest["manifest_path"]
        manifest["manifest_path"] = str(package_dir / "manifest.json")
        manifest["output_package"] = {key: str(value) for key, value in dirs.items()}
        return dirs

    def write_manifest(self, manifest):
        manifest["updated_at"] = now_iso()
        path = Path(manifest["manifest_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    def fail_manifest(self, manifest, message):
        manifest["status"] = "failed"
        manifest["message"] = message
        manifest.setdefault("errors", []).append(
            {
                "message": message,
                "time": now_iso(),
            }
        )
        self.write_manifest(manifest)
        return manifest

    def load_title_pages(self, content_list_path):
        content_list_path = Path(content_list_path)
        pages = json.loads(content_list_path.read_text(encoding="utf-8"))
        return extract_title_pages_from_content_list(pages)

    def discover_mineru_items(self, mineru_dir):
        root = Path(mineru_dir)
        items = []
        for content_list_path in sorted(root.rglob("content_list_v2.json")):
            parent_name = content_list_path.parent.name
            pdf_name = parent_name
            marker = ".pdf-"
            if marker in parent_name.lower():
                pdf_name = parent_name[: parent_name.lower().find(marker) + len(".pdf")]

            pdf_candidates = [
                content_list_path.parent / pdf_name,
                content_list_path.parent.parent / pdf_name,
                root / pdf_name,
            ]
            pdf_path = next((candidate for candidate in pdf_candidates if candidate.exists()), None)

            items.append(
                {
                    "name": Path(pdf_name).stem,
                    "pdf_path": pdf_path,
                    "content_list_path": content_list_path,
                }
            )
        return items

    def read_pdf_text_pages(self, pdf_path, scan_pages=30):
        pymupdf = import_pymupdf()
        pages = []
        doc = pymupdf.open(str(pdf_path))
        try:
            limit = min(parse_positive_int(scan_pages, 30), doc.page_count)
            for index in range(limit):
                try:
                    text = doc[index].get_text("text") or ""
                except Exception:
                    text = ""
                pages.append({"page": index + 1, "text": text})
        finally:
            doc.close()
        return pages

    def export_directory_pages_for_ocr(self, source_pdf, output_pdf, scan_pages=30):
        pymupdf = import_pymupdf()
        source_pdf = Path(source_pdf)
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open(str(source_pdf))
        out_doc = pymupdf.open()
        tmp_path = output_pdf.with_name(f"{output_pdf.name}.{uuid.uuid4().hex}.tmp.pdf")
        try:
            page_count = min(parse_positive_int(scan_pages, 30), doc.page_count)
            if page_count <= 0:
                raise ValueError("PDF 没有可导出的页面")
            out_doc.insert_pdf(doc, from_page=0, to_page=page_count - 1)
            out_doc.save(str(tmp_path))
            tmp_path.replace(output_pdf)
            return {"output_pdf": str(output_pdf), "start_page": 1, "end_page": page_count, "page_count": page_count}
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        finally:
            out_doc.close()
            doc.close()

    def read_directory_text_from_mineru(self, mineru_dir):
        root = Path(mineru_dir)
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"目录 MinerU 输出目录不存在: {root}")
        text_parts = []
        for name in ("full.md", "content.md", "middle.md"):
            for path in sorted(root.rglob(name)):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if text.strip():
                    text_parts.append(text)
        if text_parts:
            return "\n".join(text_parts)
        for content_list in sorted(root.rglob("content_list_v2.json")):
            pages = json.loads(content_list.read_text(encoding="utf-8"))
            text = self.text_from_content_list(pages)
            if text.strip():
                text_parts.append(text)
        return "\n".join(text_parts)

    def text_from_content_list(self, pages):
        lines = []
        if not isinstance(pages, list):
            return ""
        for blocks in pages:
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                content = block.get("content", "")
                if isinstance(content, dict):
                    value = content.get("text") or content.get("content") or ""
                else:
                    value = content
                if value:
                    lines.append(str(value))
        return "\n".join(lines)

    def has_directory_text_signal(self, pages):
        text = "\n".join(page.get("text", "") for page in pages)
        if len(text.strip()) < 20:
            return False
        return sum(1 for keyword in DIRECTORY_KEYWORDS if keyword in text) >= 1 and bool(RECORD_TYPE_PATTERN.search(text))

    def write_split_plan_outputs(self, dirs, split_items, source_text):
        result_dir = dirs["directory_result_dir"]
        result_dir.mkdir(parents=True, exist_ok=True)
        text_path = result_dir / "directory_text.txt"
        json_path = result_dir / "split_plan.json"
        csv_path = result_dir / "split_plan_preview.csv"
        text_path.write_text(source_text or "", encoding="utf-8")
        json_path.write_text(json.dumps(split_items, ensure_ascii=False, indent=2), encoding="utf-8")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["index", "name", "record_type", "evidence_start", "evidence_end", "pdf_start", "pdf_end", "confidence", "warnings"],
            )
            writer.writeheader()
            for item in split_items:
                writer.writerow(
                    {
                        "index": item.get("index", ""),
                        "name": item.get("name", ""),
                        "record_type": item.get("record_type", ""),
                        "evidence_start": item.get("evidence_start", ""),
                        "evidence_end": item.get("evidence_end", ""),
                        "pdf_start": item.get("pdf_start", ""),
                        "pdf_end": item.get("pdf_end", ""),
                        "confidence": item.get("confidence", ""),
                        "warnings": "；".join(item.get("warnings", [])),
                    }
                )
        return {"directory_text": str(text_path), "split_plan": str(json_path), "split_plan_preview": str(csv_path)}

    def insert_blanks_for_double_sided(self, source_pdf, output_pdf, title_pages):
        pymupdf = import_pymupdf()
        source_pdf = Path(source_pdf)
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        insertion_indices = plan_blank_insertions(title_pages)
        tmp_path = output_pdf.with_name(f"{output_pdf.name}.{uuid.uuid4().hex}.tmp.pdf")

        try:
            doc = pymupdf.open(str(source_pdf))
            try:
                original_page_count = doc.page_count
                for index in sorted(insertion_indices, reverse=True):
                    page_kwargs = {}
                    if doc.page_count:
                        reference_index = max(0, min(index - 1, doc.page_count - 1))
                        try:
                            rect = doc[reference_index].rect
                            page_kwargs = {"width": rect.width, "height": rect.height}
                        except (AttributeError, IndexError, TypeError):
                            page_kwargs = {}
                    doc.insert_page(index, **page_kwargs)
                doc.save(str(tmp_path))
                output_page_count = doc.page_count
            finally:
                doc.close()

            tmp_path.replace(output_pdf)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return {
            "original_page_count": original_page_count,
            "output_page_count": output_page_count,
            "inserted_blank_pages": len(insertion_indices),
            "insertion_indices": insertion_indices,
        }

    def run_refine_export(self, job_id, case_id, params):
        params = dict(params or {})
        mineru_dir = params.get("mineru_dir", "")
        output_dir = params.get("output_dir", "")
        mineru_dir_is_path_value = isinstance(mineru_dir, (str, Path))
        output_dir_is_path_value = isinstance(output_dir, (str, Path))
        mineru_dir_text = str(mineru_dir) if mineru_dir_is_path_value else ""
        output_dir_text = str(output_dir) if output_dir_is_path_value else ""
        params["mineru_dir"] = mineru_dir_text if mineru_dir_is_path_value else ""
        params["output_dir"] = output_dir_text if output_dir_is_path_value else ""
        manifest = self.create_manifest(
            job_id=job_id,
            case_id=case_id,
            job_type="material_refine_export",
            params=params,
        )

        if not mineru_dir_is_path_value or not mineru_dir_text.strip():
            return self.fail_manifest(manifest, "缺少或无效 MinerU 输出目录")
        if not output_dir_is_path_value or not output_dir_text.strip():
            return self.fail_manifest(manifest, "缺少或无效输出目录")

        mineru_dir_path = Path(mineru_dir_text)
        output_dir_path = Path(output_dir_text)
        try:
            if not mineru_dir_path.exists() or not mineru_dir_path.is_dir():
                return self.fail_manifest(manifest, f"MinerU 输出目录不存在: {mineru_dir_text}")
            if output_dir_path.exists() and not output_dir_path.is_dir():
                return self.fail_manifest(manifest, f"输出路径不是目录: {output_dir_text}")

            output_dir_path.mkdir(parents=True, exist_ok=True)
            manifest["outputs"] = {**manifest.get("outputs", {}), "output_dir": str(output_dir_path)}
            items = self.discover_mineru_items(mineru_dir_path)
        except OSError as exc:
            return self.fail_manifest(manifest, f"细分插页准备失败: {exc}")
        if not items:
            return self.fail_manifest(
                manifest,
                f"未找到 content_list_v2.json: {mineru_dir_text}",
            )

        success_count = 0
        failure_count = 0
        for item in items:
            result = {
                "name": item.get("name", ""),
                "pdf_path": str(item.get("pdf_path") or ""),
                "content_list_path": str(item.get("content_list_path") or ""),
                "status": "created",
            }
            try:
                pdf_path = item.get("pdf_path")
                if not pdf_path:
                    raise FileNotFoundError("未找到 content_list 对应的 PDF")

                title_pages = self.load_title_pages(item["content_list_path"])
                if not title_pages:
                    raise ValueError("未发现一级标题页")

                output_pdf = output_dir_path / Path(pdf_path).name
                stats = self.insert_blanks_for_double_sided(pdf_path, output_pdf, title_pages)
                result.update(stats)
                result["title_pages"] = title_pages
                result["output_pdf"] = str(output_pdf)
                result["status"] = "completed"
                success_count += 1
            except json.JSONDecodeError as exc:
                result["status"] = "failed"
                result["error"] = f"content_list JSON 读取失败: {exc}"
                failure_count += 1
            except Exception as exc:
                result["status"] = "failed"
                result["error"] = str(exc)
                failure_count += 1
            manifest["files"].append(result)

        if success_count and failure_count:
            manifest["status"] = "partial"
        elif success_count:
            manifest["status"] = "completed"
        else:
            manifest["status"] = "failed"
        manifest["message"] = f"细分插页完成：成功 {success_count} 个，失败 {failure_count} 个。"
        self.write_manifest(manifest)
        return manifest

    def run_coarse_split(self, job_id, case_id, params):
        params = dict(params or {})
        raw_pdf = params.get("raw_pdf", "")
        manual_ranges = params.get("manual_ranges", "")
        directory_mineru_dir = params.get("directory_mineru_dir", "")
        directory_scan_pages = parse_positive_int(params.get("directory_scan_pages"), 30)
        page_offset = parse_int(params.get("page_offset"), 0)
        raw_pdf_is_path_value = isinstance(raw_pdf, (str, Path))
        raw_pdf_text = str(raw_pdf) if raw_pdf_is_path_value else ""
        params["raw_pdf"] = raw_pdf_text if raw_pdf_is_path_value else ""
        params["directory_scan_pages"] = directory_scan_pages
        params["page_offset"] = page_offset
        params["directory_mineru_dir"] = str(directory_mineru_dir) if isinstance(directory_mineru_dir, (str, Path)) else ""
        manifest = self.create_manifest(
            job_id=job_id,
            case_id=case_id,
            job_type="material_coarse_split",
            params=params,
        )
        manifest["inputs"] = {
            "raw_pdf": raw_pdf_text,
            "note": params.get("note", ""),
            "mode": params.get("mode", "coarse_split"),
            "manual_ranges": manual_ranges if isinstance(manual_ranges, str) else "",
            "directory_scan_pages": directory_scan_pages,
            "directory_mineru_dir": params["directory_mineru_dir"],
            "page_offset": page_offset,
        }

        if not raw_pdf_is_path_value or not raw_pdf_text.strip():
            return self.fail_manifest(manifest, "缺少或无效原始 PDF 路径")

        raw_pdf_path = Path(raw_pdf_text)
        if not raw_pdf_path.exists():
            return self.fail_manifest(manifest, f"原始案卷 PDF 不存在: {raw_pdf_text}")
        if not raw_pdf_path.is_file():
            return self.fail_manifest(manifest, f"原始案卷路径不是文件: {raw_pdf_text}")
        if raw_pdf_path.suffix.lower() != ".pdf":
            return self.fail_manifest(manifest, f"原始案卷文件必须是 PDF: {raw_pdf_text}")

        try:
            dirs = self.create_output_package(manifest, raw_pdf_path)
        except OSError as exc:
            return self.fail_manifest(manifest, f"创建粗分输出包失败: {exc}")

        try:
            split_items = parse_manual_split_items(manual_ranges)
        except ValueError as exc:
            return self.fail_manifest(manifest, str(exc))

        if split_items:
            normalized_items = []
            for index, item in enumerate(split_items, start=1):
                normalized_items.append({**item, "index": index, "record_type": item.get("record_type", "笔录")})
            plan_outputs = self.write_split_plan_outputs(dirs, normalized_items, "人工页码清单")
            manifest["outputs"] = {**manifest.get("output_package", {}), **plan_outputs}
            return self.run_manual_coarse_split(manifest, raw_pdf_path, normalized_items, dirs["coarse_split_dir"])

        try:
            pdf_page_count = self.get_pdf_page_count(raw_pdf_path)
            directory_text = ""
            source_mode = ""
            if params["directory_mineru_dir"].strip():
                directory_text = self.read_directory_text_from_mineru(params["directory_mineru_dir"])
                source_mode = "mineru_directory_text"
            else:
                pages = self.read_pdf_text_pages(raw_pdf_path, directory_scan_pages)
                if self.has_directory_text_signal(pages):
                    directory_text = "\n".join(page.get("text", "") for page in pages)
                    source_mode = "pdf_text_layer"
            if directory_text.strip():
                split_plan = parse_directory_text_to_split_plan(
                    directory_text,
                    pdf_page_count=pdf_page_count,
                    page_offset=page_offset,
                )
                if split_plan:
                    plan_outputs = self.write_split_plan_outputs(dirs, split_plan, directory_text)
                    manifest["outputs"] = {**manifest.get("output_package", {}), **plan_outputs}
                    manifest["directory_parse"] = {
                        "source": source_mode,
                        "item_count": len(split_plan),
                        "page_offset": page_offset,
                    }
                    return self.run_manual_coarse_split(manifest, raw_pdf_path, split_plan, dirs["coarse_split_dir"])
                if params["directory_mineru_dir"].strip():
                    return self.fail_manifest(manifest, "已读取 MinerU 目录文本，但未解析出可用目录条目")

            ocr_pdf = dirs["directory_ocr_dir"] / f"{safe_path_component(raw_pdf_path.stem, '案卷')}_疑似目录页_第001-{directory_scan_pages:03d}页.pdf"
            export_stats = self.export_directory_pages_for_ocr(raw_pdf_path, ocr_pdf, directory_scan_pages)
            hint = {
                "raw_pdf": str(raw_pdf_path),
                "directory_pages_pdf": str(ocr_pdf),
                "scan_pages": directory_scan_pages,
                "page_offset": page_offset,
                "next_step": "请将 directory_pages_pdf 交给 MinerU 解析，再把 MinerU 输出目录填入“目录页 MinerU 结果目录”后重新启动粗分任务。",
            }
            hint_path = dirs["directory_ocr_dir"] / "directory_hint.json"
            hint_path.write_text(json.dumps(hint, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest["status"] = "needs_directory_ocr"
            manifest["message"] = f"未检测到可解析目录文本层，已导出疑似目录页 PDF: {ocr_pdf}"
            manifest["outputs"] = {
                **manifest.get("output_package", {}),
                "directory_pages_pdf": str(ocr_pdf),
                "directory_hint": str(hint_path),
            }
            manifest["files"].append({"name": "疑似目录页", "status": "completed", **export_stats})
            manifest["next_step"] = hint["next_step"]
            self.write_manifest(manifest)
            return manifest
        except Exception as exc:
            return self.fail_manifest(manifest, f"自动目录解析粗分失败: {exc}")

    def get_pdf_page_count(self, pdf_path):
        pymupdf = import_pymupdf()
        doc = pymupdf.open(str(pdf_path))
        try:
            return doc.page_count
        finally:
            doc.close()

    def run_manual_coarse_split(self, manifest, raw_pdf_path, split_items, output_dir=None):
        pymupdf = import_pymupdf()
        output_dir = Path(output_dir) if output_dir else Path(manifest["manifest_path"]).parent / "coarse_split"
        if output_dir.exists() and not output_dir.is_dir():
            return self.fail_manifest(manifest, f"粗分输出路径不是目录: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)

        source_doc = pymupdf.open(str(raw_pdf_path))
        try:
            total_pages = source_doc.page_count
            completed = 0
            failed = 0
            for item in split_items:
                file_result = {
                    "name": item["name"],
                    "record_type": item.get("record_type", "笔录"),
                    "ranges": item["ranges"],
                    "confidence": item.get("confidence"),
                    "warnings": item.get("warnings", []),
                    "status": "created",
                }
                try:
                    output_pdf = output_dir / safe_split_pdf_name(item.get("index", completed + failed + 1), item)
                    out_doc = pymupdf.open()
                    try:
                        for page_range in item["ranges"]:
                            start = page_range["start"]
                            end = page_range["end"]
                            if end > total_pages:
                                raise ValueError(f"页码范围超出 PDF 总页数 {total_pages}: {start}-{end}")
                            out_doc.insert_pdf(
                                source_doc,
                                from_page=start - 1,
                                to_page=end - 1,
                            )
                        if out_doc.page_count == 0:
                            raise ValueError("没有可导出的页面")
                        tmp_path = output_pdf.with_name(f"{output_pdf.name}.{uuid.uuid4().hex}.tmp.pdf")
                        try:
                            out_doc.save(str(tmp_path))
                            tmp_path.replace(output_pdf)
                        except Exception:
                            if tmp_path.exists():
                                tmp_path.unlink()
                            raise
                    finally:
                        out_doc.close()
                    file_result.update(
                        {
                            "status": "completed",
                            "output_pdf": str(output_pdf),
                            "page_count": sum(page_range["end"] - page_range["start"] + 1 for page_range in item["ranges"]),
                        }
                    )
                    completed += 1
                except Exception as exc:
                    file_result["status"] = "failed"
                    file_result["error"] = str(exc)
                    failed += 1
                manifest["files"].append(file_result)
        finally:
            source_doc.close()

        if completed and failed:
            manifest["status"] = "partial"
        elif completed:
            manifest["status"] = "completed"
        else:
            manifest["status"] = "failed"
        manifest["message"] = f"粗分完成：成功 {completed} 个，失败 {failed} 个。输出目录: {output_dir}"
        manifest["outputs"] = {**manifest.get("outputs", {}), "coarse_split_dir": str(output_dir)}
        manifest["next_step"] = f"请将粗分输出目录交给 MinerU 解析：{output_dir}"
        self.write_manifest(manifest)
        return manifest
