import json
import re
from datetime import datetime, timezone

from ai_services import AIClient, AIServiceError
from graphrag_pipeline import build_graphrag_index, format_graphrag_context, retrieve_graphrag


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_analysis_job(store, job_id, load_case_data_fn, save_case_data_fn, ai_client_cls=AIClient):
    job = next((item for item in store.get_jobs() if item.get("id") == job_id), None)
    if not job:
        return

    case_id = job.get("case", "")
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

    settings = store.get_settings(masked=False)
    profile = _profile_for_job(job, settings)
    missing = _missing_profile_fields(settings.get(profile, {}))
    if missing:
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message=f"{_profile_label(profile)} 未配置完整：{missing}",
            log=f"{profile} AI 未配置完整",
            finished_at=now_iso(),
        )
        return

    client = ai_client_cls(settings)
    job_type = job.get("type", "")
    store.update_job(job_id, status="running", progress=5, message="AI 分析任务启动", log="读取案件上下文")

    try:
        if job_type == "case_context":
            result = _run_case_context(store, job_id, client, profile, case_id, case_data)
            case_data["委托人上下文"] = result
            # 保存起诉书摘要
            isum = result.get("indictment_summary", "")
            if isum:
                indictment = case_data.get("起诉书") or case_data.get("起诉意见书")
                if isinstance(indictment, dict):
                    indictment.setdefault("structured", {})["案件事实"] = isum
        elif job_type == "record_summaries":
            result = _run_record_summaries(store, job_id, client, profile, case_data, job.get("params", {}))
            case_data["笔录摘要"] = result
        elif job_type == "person_summaries":
            result = _run_person_summaries(store, job_id, client, profile, case_data, job.get("params", {}))
            case_data["人物摘要"] = result
        elif job_type == "review":
            result = _run_review(store, job_id, client, profile, case_id, case_data, store.base_dir)
            case_data["分析复核"] = result
        else:
            raise ValueError(f"未知 AI 分析任务类型：{job_type}")

        save_case_data_fn(case_id, case_data)
        try:
            build_graphrag_index(case_id, case_data, store.base_dir, save=True)
        except Exception as exc:
            store.update_job(job_id, log=f"GraphRAG 索引刷新失败：{exc}")
        store.update_job(
            job_id,
            status="completed",
            progress=100,
            message=_completion_message(job_type, result),
            log="结果已写回案件 JSON",
            finished_at=now_iso(),
        )
    except (AIServiceError, ValueError, OSError) as exc:
        store.update_job(
            job_id,
            status="failed",
            progress=100,
            message=f"AI 分析失败：{exc}",
            log=str(exc),
            finished_at=now_iso(),
        )


def _run_case_context(store, job_id, client, profile, case_id, case_data):
    focus = _focus_context(case_data)
    # 起诉书全文（完整的 content，用于摘要生成）
    indictment = case_data.get("起诉书") or case_data.get("起诉意见书") or {}
    indictment_full = indictment.get("content", "") if isinstance(indictment, dict) else ""

    prompt = (
        "请为刑事辩护阅卷生成委托人上下文，要求围绕委托当事人说明案件主线、"
        "相关人物、关键风险、优先核对材料。不要直接下主犯/从犯结论。\n\n"
        f"{_case_brief(case_id, case_data)}\n\n"
        f"【委托当事人】{focus['entrusted_text']}\n"
        f"【涉案核心人物】{focus['related_text']}\n"
        f"【笔录摘要】\n{_record_summary_block(case_data, limit=12)}"
    )
    store.update_job(job_id, progress=35, message="正在生成委托人上下文", log=f"调用 {_profile_label(profile)}")
    content = client.chat(
        profile,
        [{"role": "user", "content": prompt}],
        system="你是刑事辩护阅卷助手，输出结构清晰、客观克制。",
        max_tokens=1800,
    )

    # 生成起诉书摘要（如果起诉书内容存在）
    indictment_summary = ""
    if indictment_full.strip():
        store.update_job(job_id, progress=55, message="正在生成起诉书摘要", log="起诉书摘要")
        summary_prompt = (
            "请为以下刑事起诉书/起诉意见书生成摘要。用陈述句客观概括案件事实，保持关键细节。\n"
            "案情简单时简洁，案情复杂时可详尽，但不超过10000字。\n\n"
            f"{_compact(indictment_full, 50000)}"
        )
        indictment_summary = client.chat(
            profile,
            [{"role": "user", "content": summary_prompt}],
            system="你是刑事文书摘要助手，输出客观、完整、不遗漏关键事实。",
            max_tokens=3000,
        )
        indictment_summary = indictment_summary.strip()

    return {
        "content": content.strip(),
        "indictment_summary": indictment_summary,
        "generated_at": now_iso(),
        "profile": profile,
    }


def _run_record_summaries(store, job_id, client, profile, case_data, params=None):
    params = params or {}
    records = case_data.get("笔录列表", [])
    existing = case_data.get("笔录摘要", {})
    summaries = dict(existing) if isinstance(existing, dict) else {}
    selected_records = _select_batch(records, params)
    total = len(selected_records)
    force = _truthy(params.get("force"))
    if not total:
        return summaries

    for index, record in enumerate(selected_records, start=1):
        record_id = str(record.get("id", index))
        if not force and _summary_has_content(summaries.get(record_id)):
            progress = 10 + int(index / total * 78)
            store.update_job(job_id, progress=progress, message=f"跳过已有笔录摘要 {index}/{total}", log=f"跳过：{_record_title(record)}")
            continue
        prompt = (
            "请为以下刑事笔录生成摘要。\n\n"
            "要求：\n"
            "1. 按事件分条，每件事用一段话描述始末，包含：涉及人物及关系、事情经过、"
            "交易方式/金额/数量等细节、时间地点。\n"
            "2. 用陈述句概括，不要照搬原文，不要用引号引用笔录原话。\n"
            "3. 跳过身份信息、权利告知、签字确认等程序性内容。\n"
            "4. 如果某件事与委托当事人有关，标注【委托人相关】。\n"
            "5. 如果发现矛盾或疑点，标注【待核对】。\n\n"
            f"{_case_brief('', case_data)}\n\n"
            f"【笔录信息】{_record_title(record)}\n"
            f"【笔录全文】\n{_compact(record.get('全文内容') or record.get('内容摘要') or '', 6500)}"
        )
        progress = 10 + int(index / total * 78)
        store.update_job(job_id, progress=progress, message=f"正在生成笔录摘要 {index}/{total}", log=_record_title(record))
        content = client.chat(
            profile,
            [{"role": "user", "content": prompt}],
            system="你是刑事笔录摘要助手。按事件分条输出摘要，用陈述句概括，不照搬原文。",
            max_tokens=1200,
        )
        summaries[record_id] = {
            "content": content.strip(),
            "generated_at": now_iso(),
            "profile": profile,
        }
    return summaries


def _run_person_summaries(store, job_id, client, profile, case_data, params=None):
    params = params or {}
    records_by_person = {}
    for record in case_data.get("笔录列表", []):
        name = record.get("姓名", "")
        if not name:
            continue
        records_by_person.setdefault(name, []).append(record)

    existing_record_summaries = case_data.get("笔录摘要", {})
    existing_person_summaries = case_data.get("人物摘要", {})
    result = dict(existing_person_summaries) if isinstance(existing_person_summaries, dict) else {}
    selected_items = _select_batch(list(records_by_person.items()), params)
    total = max(1, len(selected_items))
    force = _truthy(params.get("force"))
    for index, (name, records) in enumerate(selected_items, start=1):
        if not force and _summary_has_content(result.get(name)):
            progress = 10 + int(index / total * 78)
            store.update_job(job_id, progress=progress, message=f"跳过已有人物摘要 {index}/{total}", log=f"跳过：{name}")
            continue
        summaries = []
        for record in records:
            record_id = str(record.get("id", ""))
            item = existing_record_summaries.get(record_id, {}) if isinstance(existing_record_summaries, dict) else {}
            content = item.get("content", "") if isinstance(item, dict) else str(item or "")
            summaries.append(f"- {_record_title(record)}：{content or _compact(record.get('内容摘要') or record.get('全文内容') or '', 300)}")
        prompt = (
            "请为该刑事案件人物生成综合阅卷摘要。\n\n"
            "要求：\n"
            "1. 用陈述句简要概括，不要照搬笔录内容。\n"
            "2. 包含以下方面（自然段落即可，不需要编号标题）：\n"
            "   - 此人在案件中的角色和行为（如：参与了什么、负责什么、卖了什么买了什么）\n"
            "   - 与委托当事人的关系和往来（如有）\n"
            "   - 涉及的关键事实（交易次数、金额、物品数量等）\n"
            "   - 证据价值（此人的供述能证明什么、对委托人有利还是不利）\n"
            "   - 矛盾或待核对问题（如有）\n"
            "3. 不要使用【角色定位】【关系网络】【关键供述】等标签式标题。\n"
            "4. 避免直接下主犯/从犯结论，只描述具体行为和作用。\n\n"
            f"{_case_brief('', case_data)}\n\n"
            f"【人物】{name}\n"
            f"【相关笔录】\n{chr(10).join(summaries)}"
        )
        progress = 10 + int(index / total * 78)
        store.update_job(job_id, progress=progress, message=f"正在生成人物摘要 {index}/{total}", log=name)
        content = client.chat(
            profile,
            [{"role": "user", "content": prompt}],
            system="你是刑事案件人物摘要助手。用陈述句简要概括，不照搬笔录内容，不使用标签式标题。",
            max_tokens=1200,
        )
        result[name] = {
            "content": content.strip(),
            "record_count": len(records),
            "generated_at": now_iso(),
            "profile": profile,
        }
    return result


def _run_review(store, job_id, client, profile, case_id, case_data, base_dir):
    questions = [
        "现有材料中围绕委托当事人的关键不利证据是什么？",
        "现有材料中有哪些矛盾、缺口或需要优先核对的地方？",
    ]
    retrieval_blocks = []
    for question in questions:
        retrieval = retrieve_graphrag(case_id, case_data, base_dir, question, limit=6)
        retrieval_blocks.append(format_graphrag_context(retrieval, max_chars=3500))
    prompt = (
        "请复核当前案件 AI 分析结果，输出：1. 已有依据；2. 主要风险；3. 矛盾与缺口；"
        "4. 下一步阅卷清单。必须引用证据来源，证据不足要明确说明。\n\n"
        f"{_case_brief(case_id, case_data)}\n\n"
        f"【委托人上下文】\n{_compact(_field_content(case_data.get('委托人上下文')), 1800)}\n\n"
        f"【GraphRAG 证据】\n{chr(10).join(retrieval_blocks)}"
    )
    store.update_job(job_id, progress=45, message="正在复核分析结果", log=f"调用 {_profile_label(profile)}")
    content = client.chat(
        profile,
        [{"role": "user", "content": prompt}],
        system="你是刑事辩护分析复核助手，必须区分事实、证据和推断。",
        max_tokens=2200,
    )
    return {
        "content": content.strip(),
        "generated_at": now_iso(),
        "profile": profile,
    }


def _profile_for_job(job, settings):
    job_type = job.get("type", "")
    routing = settings.get("routing", {})
    if job_type in ("record_summaries", "person_summaries"):
        return job.get("profile") or routing.get("extract_default", "cheap")
    if job_type in ("case_context", "review"):
        return job.get("profile") or routing.get("review_default", "strong")
    return job.get("profile") or "cheap"


def _missing_profile_fields(config):
    missing = []
    if not config.get("base_url"):
        missing.append("Base URL")
    if not config.get("api_key"):
        missing.append("API Key")
    if not config.get("model"):
        missing.append("模型")
    return "、".join(missing)


def _profile_label(profile):
    return "强 AI" if profile == "strong" else "弱 AI"


def _select_batch(items, params):
    try:
        start = int(params.get("batch_start") or 1)
    except (TypeError, ValueError):
        start = 1
    try:
        limit = int(params.get("batch_limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    start = max(1, start)
    offset = start - 1
    if limit > 0:
        return list(items)[offset:offset + limit]
    return list(items)[offset:]


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "是"}


def _summary_has_content(value):
    if isinstance(value, dict):
        return bool(str(value.get("content", "")).strip())
    return bool(str(value or "").strip())


def _completion_message(job_type, result):
    if job_type == "record_summaries":
        return f"笔录摘要已生成：{len(result)} 份"
    if job_type == "person_summaries":
        return f"人物摘要已生成：{len(result)} 人"
    if job_type == "case_context":
        return "委托人上下文已生成"
    if job_type == "review":
        return "分析复核已完成"
    return "AI 分析已完成"


def _case_brief(case_id, case_data):
    focus = _focus_context(case_data)
    indictment = case_data.get("起诉书") or case_data.get("起诉意见书") or {}
    structured = indictment.get("structured", {}) if isinstance(indictment, dict) else {}
    fact = structured.get("案件事实") or structured.get("犯罪事实") or ""
    content = indictment.get("content", "") if isinstance(indictment, dict) else ""
    if not fact:
        fact = content
    return (
        f"案件名称：{case_data.get('案件名称', case_id)}\n"
        f"委托当事人：{focus['entrusted_text'] or '未确认'}\n"
        f"涉案核心人物：{focus['related_text'] or '未提取'}\n"
        f"起诉书主线：{_compact(fact, 900)}"
    )


def _focus_context(case_data):
    entrusted = _as_list(case_data.get("委托当事人", [])) or _as_list(case_data.get("当事人清单", []))
    related = _as_list(case_data.get("涉案核心人物", []))
    if not related:
        related = sorted(set(r.get("姓名", "") for r in case_data.get("笔录列表", []) if r.get("姓名") not in entrusted))
    return {
        "entrusted": entrusted,
        "related": related,
        "entrusted_text": "、".join(entrusted),
        "related_text": "、".join(related),
    }


def _as_list(value):
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


def _record_summary_block(case_data, limit=12):
    summaries = case_data.get("笔录摘要", {})
    records = case_data.get("笔录列表", [])
    lines = []
    for record in records[:limit]:
        record_id = str(record.get("id", ""))
        summary = summaries.get(record_id, {}) if isinstance(summaries, dict) else {}
        content = summary.get("content", "") if isinstance(summary, dict) else str(summary or "")
        lines.append(f"- {_record_title(record)}：{content or _compact(record.get('内容摘要') or record.get('全文内容') or '', 260)}")
    return "\n".join(lines)


def _record_title(record):
    parts = [record.get("姓名", ""), record.get("日期", ""), record.get("笔录类型", "")]
    return " ".join(part for part in parts if part) or f"笔录{record.get('id', '')}"


def _field_content(value):
    if isinstance(value, dict):
        return value.get("content", "")
    return str(value or "")


def _compact(text, limit=1000):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."
