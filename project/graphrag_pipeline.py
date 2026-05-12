import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


INDEX_VERSION = "1.0"
MAX_CHUNKS_PER_RECORD = 20


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def graphrag_index_path(base_dir, case_id):
    return Path(base_dir) / "runtime" / "graphrag" / str(case_id) / "index.json"


def load_graphrag_index(base_dir, case_id):
    path = graphrag_index_path(base_dir, case_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("version") != INDEX_VERSION:
        return None
    return data


def build_graphrag_index(case_id, case_data, base_dir, save=True):
    builder = _GraphRAGBuilder(case_id, case_data, base_dir)
    index = builder.build()
    if save:
        path = graphrag_index_path(base_dir, case_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
        tmp.replace(path)
    return index


def retrieve_graphrag(case_id, case_data, base_dir, query, limit=8):
    index = load_graphrag_index(base_dir, case_id)
    if index is None:
        index = build_graphrag_index(case_id, case_data, base_dir, save=True)

    query = (query or "").strip()
    tokens = _tokenize(query)
    people = [n for n in index.get("nodes", []) if n.get("type") == "person"]
    mentioned_people = [
        n for n in people
        if n.get("label") and n.get("label") in query
    ]
    entrusted = set(index.get("metadata", {}).get("entrusted_parties", []))

    scored = []
    for chunk in index.get("chunks", []):
        score = _score_chunk(chunk, query, tokens, mentioned_people, entrusted)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (item[0], item[1].get("created_order", 0)), reverse=True)
    top_chunks = [chunk for _, chunk in scored[:limit]]

    matched_node_ids = set()
    for chunk in top_chunks:
        matched_node_ids.update(chunk.get("node_ids", []))
        if chunk.get("source_node_id"):
            matched_node_ids.add(chunk["source_node_id"])
    for person in mentioned_people:
        matched_node_ids.add(person["id"])

    relevant_edges = []
    for edge in index.get("edges", []):
        if edge.get("source") in matched_node_ids or edge.get("target") in matched_node_ids:
            relevant_edges.append(edge)
            matched_node_ids.add(edge.get("source", ""))
            matched_node_ids.add(edge.get("target", ""))

    nodes_by_id = {node["id"]: node for node in index.get("nodes", [])}
    relevant_nodes = [
        nodes_by_id[node_id]
        for node_id in matched_node_ids
        if node_id in nodes_by_id
    ]

    citations = []
    seen_citations = set()
    for chunk in top_chunks:
        citation = chunk.get("citation") or chunk.get("source_title") or chunk["id"]
        if citation not in seen_citations:
            citations.append({
                "id": f"E{len(citations) + 1}",
                "citation": citation,
                "source_type": chunk.get("source_type", ""),
                "record_id": chunk.get("record_id", ""),
            })
            seen_citations.add(citation)

    return {
        "case": case_id,
        "query": query,
        "chunks": top_chunks,
        "nodes": relevant_nodes,
        "edges": relevant_edges[:12],
        "citations": citations,
        "index_summary": index.get("summary", {}),
    }


def format_graphrag_context(retrieval, max_chars=16000):
    lines = [
        "GraphRAG 检索证据：",
        f"问题：{retrieval.get('query', '')}",
        "",
        "【证据片段】",
    ]
    for idx, chunk in enumerate(retrieval.get("chunks", []), start=1):
        text = _compact_text(chunk.get("text", ""), 2400)
        citation = chunk.get("citation") or chunk.get("source_title") or chunk.get("id")
        lines.append(f"[E{idx}] {citation}")
        lines.append(text)
    if retrieval.get("edges"):
        lines.extend(["", "【相关关系】"])
        for edge in retrieval["edges"][:8]:
            label = edge.get("label", "")
            evidence = _compact_text(edge.get("evidence", ""), 180)
            flow = edge.get("flow", "")
            lines.append(
                f"- {edge.get('source_label', edge.get('source'))} -> "
                f"{edge.get('target_label', edge.get('target'))}: {label}"
                f"{f'（{flow}）' if flow else ''}"
                f"{f'；依据：{evidence}' if evidence else ''}"
            )
    if retrieval.get("nodes"):
        lines.extend(["", "【相关节点】"])
        for node in retrieval["nodes"][:10]:
            description = _compact_text(node.get("description", ""), 300)
            lines.append(
                f"- {node.get('label', '')}：{node.get('subtype', '')}"
                f"{f'；{description}' if description else ''}"
            )

    context = "\n".join(lines)
    if len(context) <= max_chars:
        return context
    return context[:max_chars].rstrip() + "\n...[证据上下文已截断]"


def run_graphrag_job(store, job_id, load_case_data_fn, save_case_data_fn):
    job = next((item for item in store.get_jobs() if item.get("id") == job_id), None)
    if not job:
        return

    case_id = job.get("case", "")
    store.update_job(job_id, status="running", progress=8, message="开始构建 GraphRAG 索引", log="读取案件数据")
    case_data = load_case_data_fn(case_id)
    if case_data is None:
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message=f"案件 {case_id} 不存在",
            finished_at=now_iso(),
        )
        return

    index = build_graphrag_index(case_id, case_data, store.base_dir, save=True)
    index_path = graphrag_index_path(store.base_dir, case_id)
    store.update_job(
        job_id,
        progress=45,
        message="基础证据图谱索引已生成",
        log=f"索引: {index_path}",
        graphrag_index=str(index_path),
    )

    ai_graph = _try_ai_graph_extraction(store, case_data, index, job_id)
    if ai_graph:
        case_data["案情图谱"] = ai_graph
        store.update_job(job_id, progress=82, message="AI 图谱抽取已写入案件数据", log="AI 图谱抽取完成")
    elif not case_data.get("案情图谱"):
        case_data["案情图谱"] = build_basic_case_graph(case_data, index)
        store.update_job(job_id, progress=82, message="已生成基础案情图谱", log="未配置可用 AI 时使用基础图谱")
    else:
        store.update_job(job_id, progress=82, message="保留已有案情图谱", log="案件已有案情图谱，未覆盖")

    reviewed_graph = _try_strong_graph_review(store, case_data, index, case_data.get("案情图谱"), job_id)
    if reviewed_graph:
        case_data["案情图谱"] = reviewed_graph
        store.update_job(job_id, progress=88, message="强 AI 图谱复核已完成", log="strong AI 已复核图谱结构")

    save_case_data_fn(case_id, case_data)
    rebuilt_index = build_graphrag_index(case_id, case_data, store.base_dir, save=True)
    store.update_job(
        job_id,
        status="completed",
        progress=100,
        message=(
            "GraphRAG 完成："
            f"{rebuilt_index['summary']['chunk_count']} 个证据片段，"
            f"{rebuilt_index['summary']['node_count']} 个节点，"
            f"{rebuilt_index['summary']['edge_count']} 条关系"
        ),
        log="GraphRAG 索引和图谱已更新",
        finished_at=now_iso(),
        graphrag_index=str(index_path),
    )


def build_basic_case_graph(case_data, index):
    people = [node for node in index.get("nodes", []) if node.get("type") == "person"]
    focus = _extract_focus_people(case_data)
    person_id_map = {}
    nodes = []
    for idx, person in enumerate(people[:20], start=1):
        graph_id = f"node{idx}"
        person_id_map[person["id"]] = graph_id
        nodes.append({
            "id": graph_id,
            "label": person.get("label", ""),
            "type": "person",
            "subtype": "委托人" if person.get("label") in focus["entrusted_parties"] else "涉案人员",
            "description": person.get("description", ""),
            "importance": "primary" if person.get("label") in focus["focus_people"] else "secondary",
            "members": [],
            "records": person.get("records", []),
        })

    edges = []
    seen_pairs = set()
    for edge in index.get("edges", []):
        source = person_id_map.get(edge.get("source"))
        target = person_id_map.get(edge.get("target"))
        if not source or not target or source == target:
            continue
        pair = (source, target, edge.get("label", ""))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        edges.append({
            "id": f"edge{len(edges) + 1}",
            "source": source,
            "target": target,
            "label": edge.get("label", "关联"),
            "type": edge.get("type", "indirect"),
            "style": edge.get("style", "dashed"),
            "flow": edge.get("flow", "证据关系"),
            "evidence": edge.get("evidence", ""),
        })
        if len(edges) >= 30:
            break

    return {
        "version": "1.0",
        "generated_at": now_iso(),
        "selected_parties": focus["focus_people"],
        "nodes": nodes,
        "edges": edges,
    }


class _GraphRAGBuilder:
    def __init__(self, case_id, case_data, base_dir):
        self.case_id = case_id
        self.case_data = case_data or {}
        self.base_dir = Path(base_dir)
        self.documents = []
        self.chunks = []
        self.nodes = []
        self.edges = []
        self._node_by_key = {}
        self._node_counter = 0
        self._edge_counter = 0
        self._chunk_counter = 0
        self._document_counter = 0

    def build(self):
        focus = _extract_focus_people(self.case_data)
        self._add_indictment(focus)
        self._add_records(focus)
        self._add_record_summaries()
        self._add_person_summaries(focus)
        self._add_existing_graph()
        self._add_people_mentions()
        summary = {
            "document_count": len(self.documents),
            "chunk_count": len(self.chunks),
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }
        return {
            "version": INDEX_VERSION,
            "case": self.case_id,
            "case_name": self.case_data.get("案件名称", self.case_id),
            "generated_at": now_iso(),
            "metadata": {
                "entrusted_parties": focus["entrusted_parties"],
                "related_people": focus["related_people"],
                "focus_people": focus["focus_people"],
            },
            "summary": summary,
            "documents": self.documents,
            "nodes": self.nodes,
            "edges": self.edges,
            "chunks": self.chunks,
        }

    def _add_indictment(self, focus):
        raw = self.case_data.get("起诉书") or self.case_data.get("起诉意见书") or {}
        if not isinstance(raw, dict):
            return
        structured = raw.get("structured") if isinstance(raw.get("structured"), dict) else raw
        content_parts = []
        content = raw.get("content") or raw.get("原文") or ""
        if content:
            content_parts.append(content)
        for key in ("案件事实", "犯罪事实", "罪名", "指控罪名", "涉案金额", "其他关键信息"):
            value = structured.get(key, "")
            if isinstance(value, list):
                value = "；".join(str(item) for item in value if item)
            if value:
                content_parts.append(f"{key}：{value}")
        text = "\n".join(content_parts).strip()
        if not text:
            return
        doc_id = self._add_document("起诉书/起诉意见书", "indictment", text, {})
        node_id = self._add_node(
            "doc:indictment",
            "起诉书/起诉意见书",
            "document",
            "指控文书",
            "案件指控主线和证据目录来源",
            "primary",
        )
        self._add_chunks(doc_id, node_id, text, "indictment", "起诉书/起诉意见书", focus, {})

    def _add_records(self, focus):
        records = self.case_data.get("笔录列表", [])
        all_names = [r.get("姓名", "") for r in records if r.get("姓名")]
        for record in records:
            record_id = str(record.get("id", ""))
            name = record.get("姓名", "") or "未知人员"
            person_node = self._add_person(name, focus, record_id)
            record_title = _record_title(record)
            record_node = self._add_node(
                f"record:{record_id}",
                record_title,
                "document",
                record.get("笔录类型", "笔录"),
                record.get("引用格式", ""),
                "secondary",
                records=[record_id] if record_id else [],
            )
            self._add_edge(
                person_node,
                record_node,
                "形成笔录",
                "direct",
                "solid",
                "证据关系",
                record.get("引用格式", record_title),
            )
            content = _get_record_content(record, self.case_data, self.base_dir)
            if content:
                doc_id = self._add_document(record_title, "record", content, {"record_id": record_id})
                self._add_chunks(
                    doc_id,
                    record_node,
                    content,
                    "record",
                    record.get("引用格式") or record_title,
                    focus,
                    {
                        "record_id": record_id,
                        "name": name,
                        "date": record.get("日期", ""),
                        "record_type": record.get("笔录类型", ""),
                    },
                )
            for other_name in all_names:
                if other_name and other_name != name and content and other_name in content:
                    other_node = self._add_person(other_name, focus, "")
                    self._add_edge(
                        person_node,
                        other_node,
                        "笔录提及",
                        "indirect",
                        "dashed",
                        "证据关系",
                        record.get("引用格式", record_title),
                    )

    def _add_record_summaries(self):
        summaries = self.case_data.get("笔录摘要", {})
        if not isinstance(summaries, dict):
            return
        records_by_id = {str(r.get("id", "")): r for r in self.case_data.get("笔录列表", [])}
        for record_id, summary in summaries.items():
            text = summary.get("content", "") if isinstance(summary, dict) else str(summary or "")
            if not text:
                continue
            record = records_by_id.get(str(record_id), {})
            title = f"{_record_title(record) if record else f'笔录{record_id}'} 摘要"
            doc_id = self._add_document(title, "record_summary", text, {"record_id": str(record_id)})
            node_id = self._node_by_key.get(f"record:{record_id}", "")
            self._add_chunks(
                doc_id,
                node_id,
                text,
                "record_summary",
                title,
                _extract_focus_people(self.case_data),
                {"record_id": str(record_id), "name": record.get("姓名", "")},
            )

    def _add_person_summaries(self, focus):
        summaries = self.case_data.get("人物摘要", {})
        if not isinstance(summaries, dict):
            return
        for name, summary in summaries.items():
            text = summary.get("content", "") if isinstance(summary, dict) else str(summary or "")
            if not text:
                continue
            person_node = self._add_person(name, focus, "")
            doc_id = self._add_document(f"{name} 人物摘要", "person_summary", text, {"name": name})
            self._add_chunks(doc_id, person_node, text, "person_summary", f"{name} 人物摘要", focus, {"name": name})

    def _add_existing_graph(self):
        graph = self.case_data.get("案情图谱", {})
        if not isinstance(graph, dict):
            return
        graph_node_map = {}
        for raw_node in graph.get("nodes", []):
            label = raw_node.get("label", "")
            if not label:
                continue
            node_id = self._add_node(
                f"graph:{raw_node.get('id', label)}",
                label,
                raw_node.get("type", "other"),
                raw_node.get("subtype", ""),
                raw_node.get("description", ""),
                raw_node.get("importance", "secondary"),
                raw_node.get("records", []),
                raw_node.get("members", []),
            )
            graph_node_map[raw_node.get("id", label)] = node_id
            if raw_node.get("description"):
                doc_id = self._add_document(f"{label} 图谱说明", "graph_node", raw_node["description"], {"graph_node": label})
                self._add_chunks(doc_id, node_id, raw_node["description"], "graph_node", f"图谱节点：{label}", _extract_focus_people(self.case_data), {})
        for raw_edge in graph.get("edges", []):
            source = graph_node_map.get(raw_edge.get("source"))
            target = graph_node_map.get(raw_edge.get("target"))
            if not source or not target:
                continue
            self._add_edge(
                source,
                target,
                raw_edge.get("label", "关联"),
                raw_edge.get("type", "indirect"),
                raw_edge.get("style", "dashed"),
                raw_edge.get("flow", "事实关系"),
                raw_edge.get("evidence", ""),
            )

    def _add_people_mentions(self):
        people = [node for node in self.nodes if node.get("type") == "person"]
        people_by_label = {node["label"]: node["id"] for node in people if node.get("label")}
        for chunk in self.chunks:
            text = chunk.get("text", "")
            mentioned = [label for label in people_by_label if label and label in text]
            node_ids = set(chunk.get("node_ids", []))
            for label in mentioned:
                node_ids.add(people_by_label[label])
            chunk["node_ids"] = sorted(node_ids)

    def _add_person(self, name, focus, record_id):
        if not name:
            name = "未知人员"
        subtype = "委托人" if name in focus["entrusted_parties"] else "涉案人员"
        importance = "primary" if name in focus["focus_people"] else "secondary"
        records = [record_id] if record_id else []
        return self._add_node(
            f"person:{name}",
            name,
            "person",
            subtype,
            f"{name}，{subtype}",
            importance,
            records=records,
        )

    def _add_document(self, title, source_type, text, metadata):
        self._document_counter += 1
        doc = {
            "id": f"doc{self._document_counter}",
            "title": title,
            "source_type": source_type,
            "text_length": len(text or ""),
            "metadata": metadata or {},
        }
        self.documents.append(doc)
        return doc["id"]

    def _add_node(self, key, label, node_type, subtype="", description="", importance="secondary", records=None, members=None):
        if key in self._node_by_key:
            node_id = self._node_by_key[key]
            node = next(n for n in self.nodes if n["id"] == node_id)
            for record_id in records or []:
                if record_id and record_id not in node.setdefault("records", []):
                    node["records"].append(record_id)
            return node_id
        self._node_counter += 1
        node_id = f"n{self._node_counter}"
        self._node_by_key[key] = node_id
        self.nodes.append({
            "id": node_id,
            "label": label,
            "type": node_type,
            "subtype": subtype,
            "description": description or "",
            "importance": importance,
            "records": [r for r in (records or []) if r],
            "members": members or [],
        })
        return node_id

    def _add_edge(self, source, target, label, edge_type, style, flow, evidence):
        if not source or not target:
            return
        source_node = self._node_label(source)
        target_node = self._node_label(target)
        self._edge_counter += 1
        self.edges.append({
            "id": f"e{self._edge_counter}",
            "source": source,
            "target": target,
            "source_label": source_node,
            "target_label": target_node,
            "label": label,
            "type": edge_type or "indirect",
            "style": style or "dashed",
            "flow": flow or "事实关系",
            "evidence": evidence or "",
        })

    def _add_chunks(self, doc_id, source_node_id, text, source_type, citation, focus, metadata):
        for part_index, part in enumerate(_split_text(text), start=1):
            self._chunk_counter += 1
            chunk_id = f"c{self._chunk_counter}"
            self.chunks.append({
                "id": chunk_id,
                "document_id": doc_id,
                "source_node_id": source_node_id,
                "node_ids": [source_node_id] if source_node_id else [],
                "source_type": source_type,
                "source_title": citation,
                "citation": _chunk_citation(citation, metadata, part_index),
                "text": part,
                "tokens": sorted(_tokenize(part)),
                "created_order": self._chunk_counter,
                **(metadata or {}),
            })

    def _node_label(self, node_id):
        for node in self.nodes:
            if node["id"] == node_id:
                return node.get("label", node_id)
        return node_id


def _try_ai_graph_extraction(store, case_data, index, job_id):
    settings = store.get_settings(masked=False)
    cheap = settings.get("cheap", {})
    if not cheap.get("base_url") or not cheap.get("api_key") or not cheap.get("model"):
        store.update_job(job_id, progress=60, message="AI 图谱抽取跳过", log="cheap AI 未配置完整")
        return None
    try:
        from ai_services import AIClient, AIServiceError
    except ImportError:
        return None

    evidence = "\n\n".join(
        f"[{idx}] {chunk.get('citation')}\n{_compact_text(chunk.get('text', ''), 500)}"
        for idx, chunk in enumerate(index.get("chunks", [])[:18], start=1)
    )
    focus = _extract_focus_people(case_data)
    prompt = (
        "请基于以下证据抽取案情图谱 JSON。只输出 JSON，不要解释。\n"
        f"委托当事人：{'、'.join(focus['entrusted_parties']) or '未确认'}\n"
        f"涉案核心人物：{'、'.join(focus['related_people']) or '未提取'}\n"
        "节点总数控制在20个以内。禁止直接写主犯、从犯等法律评价。"
        "关系必须包含 source、target、label、type、style、flow、evidence。\n\n"
        f"{evidence}"
    )
    schema_hint = (
        "输出格式：{\"version\":\"1.0\",\"generated_at\":\"ISO时间\","
        "\"selected_parties\":[],\"nodes\":[{\"id\":\"node1\",\"label\":\"姓名\","
        "\"type\":\"person|organization|account|event\",\"subtype\":\"事实作用\","
        "\"description\":\"含证据来源提示\",\"importance\":\"primary|secondary\","
        "\"members\":[],\"records\":[]}],\"edges\":[{\"id\":\"edge1\","
        "\"source\":\"node1\",\"target\":\"node2\",\"label\":\"关系\","
        "\"type\":\"direct|indirect\",\"style\":\"solid|dashed\","
        "\"flow\":\"货物流|资金流|指挥联络|证据关系|事实关系\","
        "\"evidence\":\"证据来源\"}]}"
    )
    store.update_job(job_id, progress=62, message="正在调用 AI 抽取图谱", log="调用 cheap AI 抽取节点关系")
    try:
        content = AIClient(settings).chat(
            "cheap",
            [{"role": "user", "content": f"{prompt}\n\n{schema_hint}"}],
            system="你是刑事案件证据图谱抽取助手。只输出严格 JSON。",
            max_tokens=2600,
        )
        graph = _parse_json_object(content)
    except (AIServiceError, ValueError, TypeError) as exc:
        store.update_job(job_id, progress=70, message="AI 图谱抽取失败，改用基础图谱", log=str(exc))
        return None
    if not _is_valid_case_graph(graph):
        store.update_job(job_id, progress=70, message="AI 图谱格式无效，改用基础图谱", log="AI 返回 JSON 缺少 nodes/edges")
        return None
    graph.setdefault("version", "1.0")
    graph.setdefault("generated_at", now_iso())
    graph.setdefault("selected_parties", focus["entrusted_parties"] or focus["focus_people"])
    return graph


def _try_strong_graph_review(store, case_data, index, graph, job_id, ai_client_cls=None):
    if not _is_valid_case_graph(graph):
        return None
    settings = store.get_settings(masked=False)
    strong = settings.get("strong", {})
    if not strong.get("base_url") or not strong.get("api_key") or not strong.get("model"):
        store.update_job(job_id, progress=84, message="强 AI 图谱复核跳过", log="strong AI 未配置完整")
        return None
    if ai_client_cls is None:
        try:
            from ai_services import AIClient as ai_client_cls, AIServiceError
        except ImportError:
            return None
    else:
        try:
            from ai_services import AIServiceError
        except ImportError:
            AIServiceError = Exception

    evidence = "\n\n".join(
        f"[{idx}] {chunk.get('citation')}\n{_compact_text(chunk.get('text', ''), 420)}"
        for idx, chunk in enumerate(index.get("chunks", [])[:14], start=1)
    )
    focus = _extract_focus_people(case_data)
    prompt = (
        "请复核并规范化以下案情图谱 JSON。只输出修订后的 JSON，不要解释。\n"
        "要求：\n"
        "1. 以委托当事人为中心；\n"
        "2. nodes 只保留真实人物，车辆、账户、地点、犯罪团伙、下游买家、事件等不得作为节点；\n"
        "3. 非人物信息可放入 edge.label、edge.evidence 或 node.description；\n"
        "4. 不新增证据中没有的人物关系，不作主犯/从犯法评价；\n"
        "5. 必须保留 nodes/edges 数组，关系 source/target 必须指向存在的人物节点。\n\n"
        f"委托当事人：{'、'.join(focus['entrusted_parties']) or '未确认'}\n"
        f"涉案核心人物：{'、'.join(focus['related_people']) or '未提取'}\n\n"
        f"【待复核图谱 JSON】\n{json.dumps(graph, ensure_ascii=False)}\n\n"
        f"【证据摘录】\n{evidence}"
    )
    store.update_job(job_id, progress=84, message="正在调用强 AI 复核图谱", log="调用 strong AI 复核图谱")
    try:
        content = ai_client_cls(settings).chat(
            "strong",
            [{"role": "user", "content": prompt}],
            system="你是刑事案件图谱质检助手。只输出严格 JSON，禁止解释。",
            max_tokens=3000,
        )
        reviewed = _parse_json_object(content)
    except (AIServiceError, ValueError, TypeError) as exc:
        store.update_job(job_id, progress=86, message="强 AI 图谱复核失败，保留原图", log=str(exc))
        return None
    if not _is_valid_case_graph(reviewed):
        store.update_job(job_id, progress=86, message="强 AI 图谱复核格式无效，保留原图", log="strong AI 返回 JSON 缺少 nodes/edges")
        return None
    reviewed.setdefault("version", graph.get("version", "1.0"))
    reviewed.setdefault("generated_at", now_iso())
    reviewed.setdefault("selected_parties", focus["entrusted_parties"] or focus["focus_people"])
    return reviewed


def _parse_json_object(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise ValueError("AI 返回内容不是 JSON")


def _is_valid_case_graph(graph):
    return isinstance(graph, dict) and isinstance(graph.get("nodes"), list) and isinstance(graph.get("edges"), list)


def _score_chunk(chunk, query, tokens, mentioned_people, entrusted):
    text = (chunk.get("text", "") + " " + chunk.get("citation", "")).lower()
    raw_text = chunk.get("text", "") + " " + chunk.get("citation", "")
    score = 0.0
    if query and query.lower() in text:
        score += 30
    for token in tokens:
        if not token:
            continue
        if token.lower() in text:
            score += 4 + min(6, text.count(token.lower()))
    for person in mentioned_people:
        label = person.get("label", "")
        if label and (label in raw_text or label == chunk.get("name")):
            score += 14
    for party in entrusted:
        if party and party in raw_text:
            score += 3
    source_type = chunk.get("source_type", "")
    if source_type in ("record_summary", "person_summary") and len(tokens) <= 3:
        score += 2
    if source_type == "indictment" and any(token in text for token in ("起诉", "指控", "罪名", "事实", "金额")):
        score += 3
    return score


def _extract_focus_people(case_data):
    entrusted = _normalize_list(case_data.get("委托当事人", []))
    if not entrusted:
        entrusted = _normalize_list(case_data.get("当事人清单", []))
    related = _normalize_list(case_data.get("涉案核心人物", []))
    if not related:
        indictment = case_data.get("起诉书") or case_data.get("起诉意见书") or {}
        structured = indictment.get("structured", {}) if isinstance(indictment, dict) else {}
        related = [name for name in _normalize_list(structured.get("当事人", [])) if name not in entrusted]
    if not related:
        related = sorted(set(r.get("姓名", "") for r in case_data.get("笔录列表", []) if r.get("姓名") not in entrusted))
    focus = []
    seen = set()
    for name in entrusted + related:
        if name and name not in seen:
            focus.append(name)
            seen.add(name)
    return {
        "entrusted_parties": entrusted,
        "related_people": related,
        "focus_people": focus,
    }


def _normalize_list(value):
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


def _record_title(record):
    if not record:
        return "未知笔录"
    parts = [
        record.get("姓名", ""),
        record.get("日期", ""),
        record.get("笔录类型", ""),
    ]
    return " ".join(part for part in parts if part) or f"笔录{record.get('id', '')}"


def _get_record_content(record, case_data, base_dir):
    if record.get("全文内容"):
        return record.get("全文内容", "")
    file_path = record.get("文件路径", "")
    if not file_path:
        return ""
    path = Path(file_path)
    if not path.is_absolute():
        base = case_data.get("笔录目录", "")
        base_path = Path(base) if base else Path("data")
        if not base_path.is_absolute():
            base_path = Path(base_dir) / base_path
        path = base_path / path
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _split_text(text, size=2000, overlap=200):
    text = _compact_whitespace(text)
    if not text:
        return []
    if len(text) <= size:
        return [text]
    parts = []
    start = 0
    while start < len(text) and len(parts) < MAX_CHUNKS_PER_RECORD:
        end = min(len(text), start + size)
        if end < len(text):
            punctuation = max(text.rfind("。", start, end), text.rfind("\n", start, end), text.rfind("；", start, end))
            if punctuation > start + math.floor(size * 0.55):
                end = punctuation + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [part for part in parts if part]


def _tokenize(text):
    text = (text or "").lower()
    words = set(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", text))
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{3,}", text)
    for run in cjk_runs:
        for size in (2, 3, 4):
            for idx in range(0, max(0, len(run) - size + 1)):
                words.add(run[idx:idx + size])
    return {word for word in words if len(word) >= 2}


def _chunk_citation(citation, metadata, part_index):
    pieces = [citation]
    if metadata.get("record_id"):
        pieces.append(f"笔录ID {metadata['record_id']}")
    if metadata.get("date"):
        pieces.append(metadata["date"])
    if part_index > 1:
        pieces.append(f"片段{part_index}")
    return "，".join(piece for piece in pieces if piece)


def _compact_whitespace(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _compact_text(text, limit):
    text = _compact_whitespace(text)
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
