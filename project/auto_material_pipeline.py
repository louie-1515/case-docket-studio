import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from material_pipeline import (
    import_pymupdf,
    parse_directory_text_to_split_plan,
    safe_path_component,
    safe_split_pdf_name,
    plan_blank_insertions,
    extract_title_pages_from_content_list,
)


JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
DATE_PATTERN = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
TOC_PAGE_RANGE_PATTERN = re.compile(r"(\d{1,4})\s*(?:[-~至]\s*(\d{1,4}))?")
PAGE_NUM_PATTERN = re.compile(r"第\s*(\d+)\s*页\s*共\s*(\d+)\s*页")

def _is_obviously_not_person(name):
    if not name:
        return True
    if any(ch.isdigit() for ch in name):
        return True
    if len(name) <= 1 or len(name) > 18:
        return True
    bad_keywords = [
        "犯罪团伙", "团伙", "同案人员", "下游买家", "上游卖家",
        "有限公司", "公司", "银行", "公安局", "法院", "检察院",
        "车辆", "车牌", "账号", "账户",
    ]
    if any(k in name for k in bad_keywords):
        return True
    role_only = {"被告人", "被害人", "嫌疑人", "证人", "民警", "法官", "检察官", "律师"}
    if name in role_only:
        return True
    return False


def _normalize_extracted_name(name):
    name = (name or "").strip()
    name = name.strip(" \t\r\n\"'""''()（）【】[]<>《》，。、；：")
    return name.strip()


def extract_party_candidates_from_document(text):
    """从文书材料 MinerU 解析文本中提取当事人姓名。

    返回：[{"name": "张三", "source": "起诉意见书.犯罪嫌疑人"}, ...]
    """
    text = str(text or "").strip()
    if not text:
        return []

    seen = set()
    candidates = []

    def _add(name, source):
        name = _normalize_extracted_name(name)
        if _is_obviously_not_person(name):
            return
        if name in seen:
            return
        seen.add(name)
        candidates.append({"name": name, "source": source})

    # 判断文书类型
    is_prosecution_opinion = "起诉意见书" in text
    is_indictment = "起诉书" in text and not is_prosecution_opinion

    if is_prosecution_opinion:
        keyword = "犯罪嫌疑人"
        source_label = "起诉意见书.犯罪嫌疑人"
    elif is_indictment:
        keyword = "被告人"
        source_label = "起诉书.被告人"
    else:
        keyword = None
        source_label = None

    # 模式1：犯罪嫌疑人姓名：A，B，C（封面结构字段）
    cover_pattern = re.compile(r"犯罪嫌疑人姓名[：:]\s*(.+)")
    for match in cover_pattern.finditer(text):
        raw = match.group(1)
        raw = raw.split("\n")[0]
        names = re.split(r"[，,、]", raw)
        for name in names:
            _add(name, "文书卷.犯罪嫌疑人姓名")

    # 模式2/3/4/5：按关键词提取
    keywords_to_try = []
    if keyword:
        keywords_to_try.append((keyword, source_label))
    else:
        keywords_to_try.append(("犯罪嫌疑人", "起诉意见书.犯罪嫌疑人"))
        keywords_to_try.append(("被告人", "起诉书.被告人"))

    for kw, src in keywords_to_try:
        # 模式2：犯罪嫌疑人A、B、C涉嫌（顿号分隔，以涉嫌结尾）
        pattern_inline = re.compile(
            re.escape(kw) + r"([一-鿿]{1,6}(?:[、][一-鿿]{1,6})*)\s*涉嫌"
        )
        for match in pattern_inline.finditer(text):
            raw = match.group(1)
            names = re.split(r"[、]", raw)
            for name in names:
                _add(name, src)

        # 模式3：犯罪嫌疑人：A，男性/女性（冒号后单人）
        pattern_colon = re.compile(
            re.escape(kw) + r"[：:]\s*([一-鿿]{2,6})\s*[，,]\s*(?:男|女)"
        )
        for match in pattern_colon.finditer(text):
            _add(match.group(1), src)

    return candidates


STAGES = [
    "upload",
    "directory_mineru",
    "document_mineru",
    "directory_parse",
    "split_pdfs",
    "record_mineru",
    "validation",
    "case_json",
    "graphrag",
    "completed",
]

STAGE_DIRS = {
    "upload": "00_upload",
    "directory_mineru": "01_directory_mineru",
    "document_mineru": "01b_document_mineru",
    "directory_parse": "02_directory_parse",
    "split_pdfs": "03_split_pdfs",
    "record_mineru": "04_record_mineru_clean",
    "validation": "05_validation",
    "case_json": "06_case_json",
    "graphrag": "07_graphrag",
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_record_date(date_text):
    match = DATE_PATTERN.search(str(date_text or ""))
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}年{int(month):02d}月{int(day):02d}日"


def format_printed_pages(ranges):
    page_ranges = []
    for page_range in ranges or []:
        try:
            start = int(page_range.get("start"))
            end = int(page_range.get("end"))
        except (TypeError, ValueError):
            continue
        if start <= 0 or end < start:
            continue
        if start == end:
            page_ranges.append(f"{start}")
        else:
            page_ranges.append(f"{start}-{end}")
    return "、".join(page_ranges)


class AutoMaterialPipeline:
    def __init__(self, base_dir, mineru_client, graph_builder=None):
        self.base_dir = Path(base_dir)
        self.runtime_dir = self.base_dir / "runtime" / "material_jobs"
        self.mineru_client = mineru_client
        self.graph_builder = graph_builder

    def job_dir(self, job_id):
        if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("Invalid material job_id")
        return self.runtime_dir / job_id

    def _stage_dir(self, job_dir, stage):
        return Path(job_dir) / STAGE_DIRS[stage]

    def write_manifest(self, manifest):
        manifest["updated_at"] = now_iso()
        path = Path(manifest["manifest_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def write_review_items(self, review_items, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{uuid.uuid4().hex}.tmp")
        tmp.write_text(json.dumps(review_items or [], ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def extract_record_dates_from_markdown(self, text):
        dates = []
        seen = set()
        for match in DATE_PATTERN.finditer(str(text or "")):
            normalized = normalize_record_date(match.group(0))
            if normalized and normalized not in seen:
                seen.add(normalized)
                dates.append(normalized)
        return dates

    def classify_review_item(self, validation):
        level = validation.get("level") or validation.get("status") or "blocking"
        item = {
            "level": level,
            "code": validation.get("code", ""),
            "name": validation.get("name", ""),
            "directory_date": validation.get("directory_date", ""),
            "ocr_dates": list(validation.get("ocr_dates") or []),
            "default_action": validation.get("default_action", ""),
        }
        record_date = validation.get("record_date")
        if record_date:
            item["record_date"] = record_date
        return item

    def check_page_completeness(self, clean_text):
        """校验笔录页码完整性：检查"第X页共Y页"标识。

        返回：{
            "has_page_marks": bool,
            "first_page": int or None,
            "last_page": int or None,
            "total_pages": int or None,
            "first_is_page_1": bool,
            "last_is_final": bool,
            "complete": bool,
            "detail": str,
        }
        """
        text = str(clean_text or "")
        matches = list(PAGE_NUM_PATTERN.finditer(text))
        if not matches:
            return {
                "has_page_marks": False,
                "first_page": None,
                "last_page": None,
                "total_pages": None,
                "first_is_page_1": False,
                "last_is_final": False,
                "complete": False,
                "detail": "未找到页码标识（第X页共Y页）",
            }

        first_match = matches[0]
        last_match = matches[-1]
        first_page = int(first_match.group(1))
        first_total = int(first_match.group(2))
        last_page = int(last_match.group(1))
        last_total = int(last_match.group(2))

        first_is_page_1 = (first_page == 1)
        last_is_final = (last_page == last_total) and (last_total > 0)

        detail_parts = []
        if not first_is_page_1:
            detail_parts.append(f"首页为第{first_page}页，不是第1页")
        if not last_is_final:
            detail_parts.append(f"末页为第{last_page}页/共{last_total}页，不匹配")
        if not detail_parts:
            detail_parts.append("页码完整")

        return {
            "has_page_marks": True,
            "first_page": first_page,
            "last_page": last_page,
            "total_pages": last_total,
            "first_is_page_1": first_is_page_1,
            "last_is_final": last_is_final,
            "complete": first_is_page_1 and last_is_final,
            "detail": "；".join(detail_parts),
            "all_marks": [
                {"page": int(m.group(1)), "total": int(m.group(2))}
                for m in matches
            ],
        }

    def validate_record_against_directory(self, split_item, clean_result_dir):
        split_item = dict(split_item or {})
        clean_result_dir = Path(clean_result_dir)
        full_md_path = clean_result_dir / "full.md"
        try:
            clean_text = full_md_path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            clean_text = ""

        directory_date = normalize_record_date(split_item.get("directory_date", ""))
        ocr_dates = self.extract_record_dates_from_markdown(clean_text)
        name = str(split_item.get("name") or "").strip()
        record_type = str(split_item.get("record_type") or "").strip()
        record_date = ""
        level = "blocking"
        code = "date_missing"
        default_action = "manual_review_required"

        if directory_date and directory_date in ocr_dates:
            record_date = directory_date
            level = "auto_fixed"
            code = "date_exact"
            default_action = "use_directory_date"
        elif directory_date and ocr_dates:
            record_date = directory_date
            level = "review"
            code = "date_conflict"
            default_action = "do_not_create_unsupported_record"
        elif directory_date and not ocr_dates:
            record_date = directory_date
            level = "auto_fixed"
            code = "date_exact"
            default_action = "use_directory_date"
        elif not directory_date and ocr_dates:
            record_date = ocr_dates[0]
            level = "auto_fixed"
            code = "ocr_date_substituted"
            default_action = "use_ocr_first_date"

        # 页码完整性校验
        page_check = self.check_page_completeness(clean_text)
        if page_check["has_page_marks"] and not page_check["complete"]:
            # 页码不完整：升级为 review，需要人工确认
            if level == "auto_fixed":
                level = "review"
                code = "page_incomplete"
                default_action = "manual_review_required"

        validation = {
            "name": name,
            "record_type": record_type,
            "directory_date": directory_date,
            "ocr_dates": ocr_dates,
            "record_date": record_date,
            "level": level,
            "status": level,
            "code": code,
            "default_action": default_action,
            "clean_full_md": str(full_md_path),
            "split_pdf": str(split_item.get("split_pdf") or ""),
            "page_ranges": list(split_item.get("ranges") or []),
            "page_status": "已按目录/OCR校验",
            "page_check": page_check,
        }
        validation["review_item"] = self.classify_review_item(validation)
        return validation

    def try_repair_incomplete_pages(self, uploaded_pdf, split_item, validation, clean_dir):
        """尝试补救页码不完整的笔录：从原始 PDF 截取缺失页并 OCR 拼接。

        返回：(repaired: bool, new_clean_text: str or None)
        """
        page_check = validation.get("page_check", {})
        if not page_check.get("has_page_marks") or page_check.get("complete"):
            return False, None

        if not self.mineru_client:
            return False, None

        first_page = page_check.get("first_page")
        last_page = page_check.get("last_page")
        total_pages = page_check.get("total_pages")
        if not all(isinstance(x, int) and x > 0 for x in [first_page, last_page, total_pages]):
            return False, None

        ranges = split_item.get("ranges") or []
        if not ranges:
            return False, None

        split_start = int(ranges[0].get("start", 0))
        split_end = int(ranges[-1].get("end", 0))
        if split_start <= 0 or split_end < split_start:
            return False, None

        head_missing = first_page - 1  # 缺前几页
        tail_missing = total_pages - last_page  # 缺后几页

        if head_missing <= 0 and tail_missing <= 0:
            return False, None

        repair_parts = []

        # 截取并 OCR 缺失的头部页
        if head_missing > 0:
            head_start = split_start - head_missing
            if head_start < 1:
                head_start = 1
            head_end = split_start - 1
            if head_end >= head_start:
                try:
                    head_pdf = Path(clean_dir) / "_repair_head.pdf"
                    self.extract_pdf_pages(uploaded_pdf, head_pdf, head_start, head_end)
                    head_clean = Path(clean_dir) / "_repair_head_clean"
                    head_clean.mkdir(parents=True, exist_ok=True)
                    self.mineru_client.parse_pdf_to_clean_dir(head_pdf, head_clean, job_label="repair_head")
                    head_md = head_clean / "full.md"
                    if head_md.exists():
                        repair_parts.append(("head", head_md.read_text(encoding="utf-8", errors="ignore")))
                except Exception:
                    pass  # 补救失败不影响原流程

        # 截取并 OCR 缺失的尾部页
        if tail_missing > 0:
            tail_start = split_end + 1
            tail_end = split_end + tail_missing
            try:
                tail_pdf = Path(clean_dir) / "_repair_tail.pdf"
                self.extract_pdf_pages(uploaded_pdf, tail_pdf, tail_start, tail_end)
                tail_clean = Path(clean_dir) / "_repair_tail_clean"
                tail_clean.mkdir(parents=True, exist_ok=True)
                self.mineru_client.parse_pdf_to_clean_dir(tail_pdf, tail_clean, job_label="repair_tail")
                tail_md = tail_clean / "full.md"
                if tail_md.exists():
                    repair_parts.append(("tail", tail_md.read_text(encoding="utf-8", errors="ignore")))
            except Exception:
                pass

        if not repair_parts:
            return False, None

        # 拼接
        full_md_path = Path(clean_dir) / "full.md"
        original_text = ""
        if full_md_path.exists():
            original_text = full_md_path.read_text(encoding="utf-8", errors="ignore")

        parts = []
        for position, text in repair_parts:
            if position == "head":
                parts.append(text)
        parts.append(original_text)
        for position, text in repair_parts:
            if position == "tail":
                parts.append(text)

        new_text = "\n\n".join(p for p in parts if p.strip())
        full_md_path.write_text(new_text, encoding="utf-8")
        return True, new_text

    def insert_blanks_for_double_sided(self, source_pdf, output_pdf, content_list_path):
        """为双面打印插入空白页：每个一级标题前如需对齐奇数页则插空白页。"""
        pymupdf = import_pymupdf()
        source_pdf = Path(source_pdf)
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        pages = json.loads(Path(content_list_path).read_text(encoding="utf-8"))
        title_pages = extract_title_pages_from_content_list(pages)
        insertion_indices = plan_blank_insertions(title_pages)

        tmp_path = output_pdf.with_name(f"{output_pdf.name}.{uuid.uuid4().hex}.tmp.pdf")
        try:
            doc = pymupdf.open(str(source_pdf))
            try:
                for index in sorted(insertion_indices, reverse=True):
                    page_kwargs = {}
                    if doc.page_count:
                        ref_idx = max(0, min(index - 1, doc.page_count - 1))
                        try:
                            rect = doc[ref_idx].rect
                            page_kwargs = {"width": rect.width, "height": rect.height}
                        except (AttributeError, IndexError, TypeError):
                            page_kwargs = {}
                    doc.insert_page(index, **page_kwargs)
                doc.save(str(tmp_path))
            finally:
                doc.close()
            tmp_path.replace(output_pdf)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise
        return {"output_pdf": str(output_pdf), "original_pages": doc.page_count if hasattr(doc, 'page_count') else None}

    def copy_or_reference_input_pdf(self, raw_pdf, upload_dir):
        raw_pdf = Path(raw_pdf).resolve()
        upload_dir = Path(upload_dir)
        upload_dir.mkdir(parents=True, exist_ok=True)
        # 共享缓存：同一份源PDF只保留一份副本，避免每次建库重复复制
        cache_dir = upload_dir.parent / "_input_pdfs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_key = hashlib.md5(str(raw_pdf).encode()).hexdigest()[:12]
        cached = cache_dir / f"{cache_key}_{raw_pdf.name}"
        if not cached.exists():
            shutil.copy2(raw_pdf, cached)
        return cached

    def run_directory_mineru(self, raw_pdf, directory_dir):
        directory_dir = Path(directory_dir)
        directory_dir.mkdir(parents=True, exist_ok=True)
        return self.mineru_client.parse_pdf_to_clean_dir(raw_pdf, directory_dir, job_label="directory_mineru")

    def run_document_mineru(self, document_pdf, document_dir, document_type=""):
        document_dir = Path(document_dir)
        document_dir.mkdir(parents=True, exist_ok=True)
        label = "document_direct_mineru" if document_type == "direct" else "document_volume_mineru"
        return self.mineru_client.parse_pdf_to_clean_dir(document_pdf, document_dir, job_label=label)

    def build_indictment_data(self, clean_result_dir, document_type="", source_pdf="", 独立PDF=""):
        clean_result_dir = Path(clean_result_dir)
        text_parts = []
        for name in ("full.md", "content_list_v2.json"):
            path = clean_result_dir / name
            if path.exists():
                text_parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        text = "\n\n".join(part for part in text_parts if part.strip())
        doc_kind = "起诉意见书" if "起诉意见书" in text else ("起诉书" if "起诉书" in text else "")
        content = self.extract_indictment_section(text, doc_kind)
        return {
            "has_content": bool(content.strip()),
            "content": content,
            "structured": {
                "文书类型": doc_kind or ("起诉书/起诉意见书" if content.strip() else ""),
                "材料类型": document_type or "",
                "来源PDF": str(source_pdf or ""),
                "独立PDF": 独立PDF or "",
                "解析目录": str(clean_result_dir),
                "提取方式": "MinerU 云 API 自动解析",
            },
        }

    def _extract_printed_page_range_from_line(self, line):
        line = str(line or "").strip()
        if not line:
            return None
        matches = list(TOC_PAGE_RANGE_PATTERN.finditer(line))
        if not matches:
            return None
        match = matches[-1]
        try:
            start = int(match.group(1))
        except (TypeError, ValueError):
            return None
        end_raw = match.group(2)
        end = None
        if end_raw:
            try:
                end = int(end_raw)
            except (TypeError, ValueError):
                end = None
        if start <= 0:
            return None
        if end is not None and end < start:
            return None
        return {"start": start, "end": end}

    def find_indictment_entry_in_text(self, text):
        text = str(text or "")
        if not text.strip():
            return None

        # TOC usually appears early; limit scan to reduce false hits in正文.
        head = text[:60000]
        lines = head.splitlines()
        keywords = ("起诉意见书", "起诉书")

        candidates = []
        for idx, raw in enumerate(lines):
            line = str(raw or "").strip()
            if not line:
                continue
            for kw in keywords:
                if kw not in line:
                    continue
                page_range = self._extract_printed_page_range_from_line(line)
                if not page_range:
                    continue
                candidates.append(
                    {
                        "keyword": kw,
                        "line_index": idx,
                        "line": line[:200],
                        "printed_start": page_range["start"],
                        "printed_end": page_range["end"],
                    }
                )

        if not candidates:
            return None

        # Prefer 起诉意见书, otherwise 起诉书; for ties, prefer earlier TOC line.
        candidates.sort(key=lambda item: (0 if item["keyword"] == "起诉意见书" else 1, item["line_index"]))
        selected = candidates[0]

        # If TOC doesn't provide an end page, try to infer by scanning next items.
        if selected.get("printed_end") is None:
            current = int(selected["printed_start"])
            for next_idx in range(int(selected["line_index"]) + 1, min(int(selected["line_index"]) + 80, len(lines))):
                page_range = self._extract_printed_page_range_from_line(lines[next_idx])
                if not page_range:
                    continue
                next_start = int(page_range["start"])
                if next_start > current:
                    selected["printed_end"] = next_start - 1
                    break

        return selected

    def infer_document_page_offset(self, document_pdf, printed_start, keyword):
        printed_start = int(printed_start or 0)
        if printed_start <= 0:
            return {"ok": False, "reason": "invalid_printed_start", "offset": 0}

        pymupdf = import_pymupdf()
        doc = pymupdf.open(str(document_pdf))
        try:
            page_count = doc.page_count
            found_page = None
            for page_no in range(1, page_count + 1):
                try:
                    text = doc[page_no - 1].get_text("text") or ""
                except Exception:
                    text = ""
                if keyword in text:
                    found_page = page_no
                    break
            if not found_page:
                return {"ok": False, "reason": "keyword_not_found_in_pdf", "offset": 0, "keyword": keyword}
            return {"ok": True, "reason": "keyword_match", "offset": int(found_page) - int(printed_start), "found_page": found_page, "keyword": keyword}
        finally:
            doc.close()

    def extract_pdf_pages(self, source_pdf, output_pdf, start_page, end_page):
        pymupdf = import_pymupdf()
        source_pdf = Path(source_pdf)
        output_pdf = Path(output_pdf)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)

        start_page = int(start_page)
        end_page = int(end_page)
        if start_page < 1 or end_page < start_page:
            raise ValueError(f"页码范围无效: {start_page}-{end_page}")

        src = pymupdf.open(str(source_pdf))
        try:
            total = src.page_count
            if end_page > total:
                raise ValueError(f"页码范围超出 PDF 总页数 {total}: {start_page}-{end_page}")
            out = pymupdf.open()
            try:
                out.insert_pdf(src, from_page=start_page - 1, to_page=end_page - 1)
                if out.page_count == 0:
                    raise ValueError("没有可导出的页面")
                tmp_path = output_pdf.with_name(f"{output_pdf.name}.{uuid.uuid4().hex}.tmp.pdf")
                try:
                    out.save(str(tmp_path))
                    tmp_path.replace(output_pdf)
                except Exception:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    raise
            finally:
                out.close()
        finally:
            src.close()

    def extract_indictment_section(self, text, doc_kind=""):
        text = str(text or "").strip()
        if not text:
            return ""
        candidates = []
        for keyword in ("起诉意见书", "起诉书"):
            index = text.find(keyword)
            if index >= 0:
                candidates.append(index)
        if not candidates:
            return text[:50000]
        start = min(candidates)
        section = text[start:]
        heading_matches = list(re.finditer(r"\n\s*#{1,4}\s+[^\n]{2,50}", section))
        for match in heading_matches[1:]:
            heading = match.group(0)
            if "起诉意见书" not in heading and "起诉书" not in heading and match.start() > 800:
                section = section[:match.start()]
                break
        return section[:50000].strip()

    def read_directory_text(self, directory_dir):
        directory_dir = Path(directory_dir)
        parts = []
        for name in ("full.md", "content_list_v2.json"):
            path = directory_dir / name
            if path.exists():
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        text = "\n\n".join(part for part in parts if part.strip())
        if not text.strip():
            raise FileNotFoundError(f"未找到目录文本: {directory_dir}")
        return text

    def infer_page_offset(self, raw_pdf, directory_dir, pdf_page_count):
        try:
            text = self.read_directory_text(directory_dir)
            probe_items = parse_directory_text_to_split_plan(text, pdf_page_count=pdf_page_count, page_offset=0)[:8]
        except Exception:
            return {"offset": 0, "score": 0, "reason": "directory_probe_failed"}
        if not probe_items:
            return {"offset": 0, "score": 0, "reason": "no_directory_items"}

        try:
            pymupdf = import_pymupdf()
            doc = pymupdf.open(str(raw_pdf))
        except Exception:
            return {"offset": 0, "score": 0, "reason": "pdf_text_probe_failed"}

        page_text_cache = {}

        def page_text(page_no):
            if page_no < 1 or page_no > pdf_page_count:
                return ""
            if page_no not in page_text_cache:
                try:
                    page_text_cache[page_no] = doc[page_no - 1].get_text("text")
                except Exception:
                    page_text_cache[page_no] = ""
            return page_text_cache[page_no]

        try:
            first_start = min(int(item.get("evidence_start") or 1) for item in probe_items)
            max_offset = min(120, max(0, pdf_page_count - first_start))
            candidates = range(-5, max_offset + 1)
            best = {"offset": 0, "score": 0, "reason": "default"}
            for offset in candidates:
                score = 0
                hits = []
                for item in probe_items:
                    start = int(item.get("evidence_start") or 0) + offset
                    combined = "\n".join([page_text(start), page_text(start + 1)])
                    if not combined.strip():
                        continue
                    name = str(item.get("name") or "").strip()
                    record_type = str(item.get("record_type") or "").strip()
                    directory_date = normalize_record_date(item.get("directory_date") or "")
                    item_score = 0
                    if name and name in combined:
                        item_score += 5
                    if record_type and record_type in combined:
                        item_score += 2
                    if directory_date:
                        raw_date = directory_date.replace("年0", "年").replace("月0", "月")
                        if directory_date in combined or raw_date in combined:
                            item_score += 2
                    if item_score:
                        hits.append({"name": name, "page": start, "score": item_score})
                    score += item_score
                if score > best["score"]:
                    best = {"offset": offset, "score": score, "reason": "pdf_text_match", "hits": hits[:5]}
            if best["score"] >= 7:
                return best
            return {"offset": 0, "score": best["score"], "reason": "low_confidence", "best_candidate": best}
        finally:
            try:
                doc.close()
            except Exception:
                pass

    def parse_directory_to_plan(self, directory_dir, pdf_page_count, page_offset):
        text = self.read_directory_text(directory_dir)
        return parse_directory_text_to_split_plan(text, pdf_page_count=pdf_page_count, page_offset=page_offset)

    def split_records(self, raw_pdf, split_plan, split_dir):
        pymupdf = import_pymupdf()
        raw_pdf = Path(raw_pdf)
        split_dir = Path(split_dir)
        split_dir.mkdir(parents=True, exist_ok=True)

        source_doc = pymupdf.open(str(raw_pdf))
        try:
            total_pages = source_doc.page_count
            results = []
            for index, item in enumerate(split_plan, start=1):
                output_pdf = split_dir / safe_split_pdf_name(index, item)
                out_doc = pymupdf.open()
                try:
                    for page_range in item.get("ranges") or []:
                        start = int(page_range["start"])
                        end = int(page_range["end"])
                        if start < 1 or end < start:
                            raise ValueError(f"页码范围无效: {start}-{end}")
                        if end > total_pages:
                            raise ValueError(f"页码范围超出 PDF 总页数 {total_pages}: {start}-{end}")
                        out_doc.insert_pdf(source_doc, from_page=start - 1, to_page=end - 1)
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

                result = dict(item)
                result.update(
                    {
                        "index": index,
                        "split_pdf": str(output_pdf),
                        "page_count": sum(int(page_range["end"]) - int(page_range["start"]) + 1 for page_range in item.get("ranges") or []),
                        "status": "completed",
                    }
                )
                results.append(result)
            return results
        finally:
            source_doc.close()

    def run_record_mineru(self, split_results, record_mineru_dir):
        record_mineru_dir = Path(record_mineru_dir)
        record_mineru_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for item in split_results:
            split_pdf = Path(item["split_pdf"])
            clean_dir = record_mineru_dir / split_pdf.stem
            clean_dir.mkdir(parents=True, exist_ok=True)
            self.mineru_client.parse_pdf_to_clean_dir(split_pdf, clean_dir, job_label=split_pdf.stem)
            result = dict(item)
            result.update(
                {
                    "clean_dir": str(clean_dir),
                    "clean_full_md": str(clean_dir / "full.md"),
                    "clean_content_list": str(clean_dir / "content_list_v2.json"),
                    "clean_layout": str(clean_dir / "layout.json"),
                    "clean_meta": str(clean_dir / "mineru_meta.json"),
                    "status": "completed",
                }
            )
            results.append(result)
        return results

    def _load_directory_full_text(self, directory_dir):
        directory_dir = Path(directory_dir)
        parts = []
        for name in ("full.md", "content_list_v2.json"):
            path = directory_dir / name
            if path.exists():
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
        return "\n\n".join(part for part in parts if part.strip())

    def _graph_index_output(self, result, case_id):
        if isinstance(result, (str, Path)):
            return str(Path(result))
        if isinstance(result, dict):
            for key in ("graphrag_index", "index_path", "path", "index"):
                value = result.get(key)
                if value:
                    return str(Path(value))
        return str(self.base_dir / "runtime" / "graphrag" / str(case_id) / "index.json")

    def _fail_manifest(self, manifest, message):
        manifest["status"] = "failed"
        manifest["stage"] = "failed"
        manifest["message"] = message
        manifest.setdefault("errors", []).append({"message": message, "time": now_iso()})
        self.write_manifest(manifest)
        return manifest

    def run(self, job_id, case_id, params):
        params = dict(params or {})
        raw_pdf_value = params.get("raw_pdf")
        manifest = {
            "job_id": job_id,
            "case_id": case_id,
            "params": params,
            "status": "running",
            "stage": "upload",
            "stages": STAGES,
            "outputs": {},
            "errors": [],
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

        job_dir = self.job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        stage_dirs = {stage: self._stage_dir(job_dir, stage) for stage in STAGE_DIRS}
        for path in stage_dirs.values():
            path.mkdir(parents=True, exist_ok=True)
        manifest["manifest_path"] = str(job_dir / "manifest.json")
        review_items_path = job_dir / "review_items.json"
        self.write_review_items([], review_items_path)
        manifest["outputs"]["review_items"] = str(review_items_path)
        self.write_manifest(manifest)

        if not isinstance(raw_pdf_value, (str, Path)) or not str(raw_pdf_value).strip():
            return self._fail_manifest(manifest, "缺少或无效原始 PDF 路径")

        raw_pdf = Path(raw_pdf_value)
        if not raw_pdf.exists():
            return self._fail_manifest(manifest, f"原始案卷 PDF 不存在: {raw_pdf}")
        if not raw_pdf.is_file():
            return self._fail_manifest(manifest, f"原始案卷路径不是文件: {raw_pdf}")
        if raw_pdf.suffix.lower() != ".pdf":
            return self._fail_manifest(manifest, f"原始案卷文件必须是 PDF: {raw_pdf}")

        document_pdf_value = params.get("document_pdf")
        document_pdf = None
        if isinstance(document_pdf_value, (str, Path)) and str(document_pdf_value).strip():
            document_pdf = Path(document_pdf_value)
            if not document_pdf.exists():
                return self._fail_manifest(manifest, f"文书材料 PDF 不存在: {document_pdf}")
            if not document_pdf.is_file():
                return self._fail_manifest(manifest, f"文书材料路径不是文件: {document_pdf}")
            if document_pdf.suffix.lower() != ".pdf":
                return self._fail_manifest(manifest, f"文书材料文件必须是 PDF: {document_pdf}")

        case_name = str(params.get("case_name") or case_id)
        case_no = str(params.get("case_no") or case_id)
        document_type = str(params.get("document_type") or ("direct" if document_pdf else "")).strip()
        manifest["inputs"] = {
            "raw_pdf": str(raw_pdf),
            "case_name": case_name,
            "case_no": case_no,
            "page_offset": "auto",
            "document_pdf": str(document_pdf or ""),
            "document_type": document_type,
            "entrusted_party": str(params.get("entrusted_party") or ""),
        }
        self.write_manifest(manifest)

        try:
            uploaded_pdf = self.copy_or_reference_input_pdf(raw_pdf, stage_dirs["upload"])
            manifest["outputs"]["uploaded_pdf"] = str(uploaded_pdf)
            manifest["stage"] = "upload"
            self.write_manifest(manifest)

            directory_clean_dir = self.run_directory_mineru(uploaded_pdf, stage_dirs["directory_mineru"])
            manifest["outputs"]["directory_mineru_dir"] = str(directory_clean_dir)
            manifest["stage"] = "directory_mineru"
            self.write_manifest(manifest)

            indictment_data = {"has_content": False, "content": "", "structured": {}}
            document_review_items = []
            if document_pdf:
                if document_type == "volume":
                    volume_dir = stage_dirs["document_mineru"] / "volume_directory"
                    document_clean_dir = self.run_document_mineru(document_pdf, volume_dir, document_type)
                    manifest["outputs"]["document_mineru_dir"] = str(document_clean_dir)

                    toc_text = ""
                    try:
                        toc_text = self.read_directory_text(document_clean_dir)
                    except Exception:
                        toc_text = ""

                    entry = self.find_indictment_entry_in_text(toc_text)
                    if not entry:
                        document_review_items.append(
                            {
                                "level": "blocking",
                                "code": "document_indictment_not_found",
                                "name": "",
                                "directory_date": "",
                                "ocr_dates": [],
                                "default_action": "manual_review_required",
                                "detail": "文书卷目录未定位到“起诉意见书/起诉书”条目，请人工确认并截取对应页段。",
                            }
                        )
                        indictment_data = {
                            "has_content": False,
                            "content": "",
                            "structured": {
                                "文书类型": "",
                                "材料类型": document_type,
                                "来源PDF": str(document_pdf or ""),
                                "解析目录": str(document_clean_dir),
                                "提取方式": "目录定位失败（需人工确认）",
                            },
                        }
                    else:
                        printed_start = int(entry["printed_start"])
                        printed_end = entry.get("printed_end")
                        keyword = entry["keyword"]

                        offset_info = self.infer_document_page_offset(document_pdf, printed_start, keyword)
                        if not offset_info.get("ok"):
                            document_review_items.append(
                                {
                                    "level": "blocking",
                                    "code": "document_page_offset_infer_failed",
                                    "name": "",
                                    "directory_date": "",
                                    "ocr_dates": [],
                                    "default_action": "manual_review_required",
                                    "detail": f"已在目录识别到“{keyword}”（印刷页{printed_start}），但无法在PDF正文中匹配关键词以推断页码偏移；请人工确认页码偏移与页段。",
                                }
                            )
                            indictment_data = {
                                "has_content": False,
                                "content": "",
                                "structured": {
                                    "文书类型": keyword,
                                    "材料类型": document_type,
                                    "来源PDF": str(document_pdf or ""),
                                    "解析目录": str(document_clean_dir),
                                    "提取方式": "页码偏移推断失败（需人工确认）",
                                    "目录命中": entry,
                                },
                            }
                        else:
                            offset = int(offset_info.get("offset") or 0)
                            pdf_start = printed_start + offset
                            if printed_end is None:
                                pdf_end = self._get_pdf_page_count(document_pdf)
                            else:
                                pdf_end = int(printed_end) + offset
                            if pdf_start < 1:
                                pdf_start = 1
                            if pdf_end < pdf_start:
                                pdf_end = pdf_start

                            selected_pdf = stage_dirs["document_mineru"] / "selected_document.pdf"
                            self.extract_pdf_pages(document_pdf, selected_pdf, pdf_start, pdf_end)
                            # Export independent indictment PDF to prominent/manifest location
                            independent_pdf_name = f"{keyword}_独立.pdf"
                            independent_pdf = stage_dirs["document_mineru"] / independent_pdf_name
                            shutil.copy2(selected_pdf, independent_pdf)
                            manifest["outputs"]["selected_document_pdf"] = str(selected_pdf)
                            manifest["outputs"]["independent_indictment_pdf"] = str(independent_pdf)

                            selected_clean_dir = stage_dirs["document_mineru"] / "selected_clean"
                            selected_clean_dir.mkdir(parents=True, exist_ok=True)
                            self.mineru_client.parse_pdf_to_clean_dir(selected_pdf, selected_clean_dir, job_label="document_selected_mineru")
                            manifest["outputs"]["selected_document_mineru_dir"] = str(selected_clean_dir)

                            indictment_data = self.build_indictment_data(selected_clean_dir, document_type, source_pdf=selected_pdf, 独立PDF=str(independent_pdf))
                            indictment_data.setdefault("structured", {})["目录命中"] = entry
                            indictment_data["structured"]["页码偏移推断"] = offset_info

                    manifest.setdefault("outputs", {})["document_review_items"] = len(document_review_items)
                    manifest["stage"] = "document_mineru"
                    self.write_manifest(manifest)
                else:
                    document_clean_dir = self.run_document_mineru(document_pdf, stage_dirs["document_mineru"], document_type)
                    indictment_data = self.build_indictment_data(document_clean_dir, document_type, source_pdf=document_pdf)
                    manifest["outputs"]["document_mineru_dir"] = str(document_clean_dir)
                    manifest["stage"] = "document_mineru"
                    self.write_manifest(manifest)
                    document_review_items = []

            # 从文书材料 MinerU 结果中提取当事人候选
            party_candidates = []
            if indictment_data.get("has_content"):
                party_candidates = extract_party_candidates_from_document(indictment_data.get("content", ""))
            elif document_pdf:
                doc_text_parts = []
                for fname in ("full.md", "content_list_v2.json"):
                    fpath = stage_dirs["document_mineru"] / fname
                    if fpath.exists():
                        doc_text_parts.append(fpath.read_text(encoding="utf-8", errors="ignore"))
                doc_text = "\n\n".join(p for p in doc_text_parts if p.strip())
                party_candidates = extract_party_candidates_from_document(doc_text)
            manifest["party_candidates"] = party_candidates
            self.write_manifest(manifest)

            page_count = self._get_pdf_page_count(uploaded_pdf)
            offset_info = self.infer_page_offset(uploaded_pdf, directory_clean_dir, page_count)
            page_offset = int(offset_info.get("offset") or 0)
            manifest["inputs"]["page_offset"] = page_offset
            manifest["inputs"]["page_offset_source"] = "auto"
            manifest["inputs"]["page_offset_confidence"] = offset_info
            self.write_manifest(manifest)
            split_plan = self.parse_directory_to_plan(directory_clean_dir, page_count, page_offset)
            split_plan_path = stage_dirs["directory_parse"] / "split_plan.json"
            self.write_review_items(split_plan, split_plan_path)
            manifest["outputs"]["split_plan"] = str(split_plan_path)
            manifest["stage"] = "directory_parse"
            self.write_manifest(manifest)

            if not split_plan:
                return self._fail_manifest(manifest, "未解析出可用目录条目，自动材料管线中止")

            split_results = self.split_records(uploaded_pdf, split_plan, stage_dirs["split_pdfs"])
            manifest["outputs"]["split_pdfs"] = str(stage_dirs["split_pdfs"])
            manifest["stage"] = "split_pdfs"
            self.write_manifest(manifest)

            record_results = self.run_record_mineru(split_results, stage_dirs["record_mineru"])
            manifest["outputs"]["record_mineru_dir"] = str(stage_dirs["record_mineru"])
            manifest["stage"] = "record_mineru"
            self.write_manifest(manifest)

            validations = []
            review_items = []
            repair_count = 0
            for idx, item in enumerate(record_results):
                validation = self.validate_record_against_directory(item, item.get("clean_dir") or "")
                # 页码不完整时尝试补救
                page_check = validation.get("page_check", {})
                if page_check.get("has_page_marks") and not page_check.get("complete"):
                    split_item = split_results[idx] if idx < len(split_results) else {}
                    repaired, new_text = self.try_repair_incomplete_pages(
                        uploaded_pdf, split_item, validation, item.get("clean_dir") or ""
                    )
                    if repaired:
                        repair_count += 1
                        # 重新校验
                        validation = self.validate_record_against_directory(item, item.get("clean_dir") or "")
                validations.append(validation)
                review_items.append(validation["review_item"])
            if repair_count:
                manifest.setdefault("log", []).append(f"页码补救成功：{repair_count} 份笔录")
            if document_review_items:
                review_items.extend(list(document_review_items))

            validation_dir = stage_dirs["validation"]
            validation_dir.mkdir(parents=True, exist_ok=True)
            validation_summary = {
                "split_pdf_count": len(split_results),
                "record_clean_count": len(record_results),
                "validation_count": len(validations),
                "validated_at": now_iso(),
            }
            validation_path = validation_dir / "validation.json"
            validation_path.write_text(
                json.dumps(
                    {
                        **validation_summary,
                        "validations": validations,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest["outputs"]["validation"] = str(validation_path)
            manifest["review_summary"] = {
                "auto_fixed": sum(1 for item in review_items if item.get("level") == "auto_fixed"),
                "review": sum(1 for item in review_items if item.get("level") == "review"),
                "blocking": sum(1 for item in review_items if item.get("level") == "blocking"),
            }
            self.write_review_items(review_items, review_items_path)
            manifest["stage"] = "validation"
            self.write_manifest(manifest)

            # 双面打印：为每份笔录插入空白页，输出到桌面工作区
            duplex_dir = Path.home() / "Desktop" / "案件笔录工作区" / "双面打印PDF" / str(case_id)
            duplex_dir.mkdir(parents=True, exist_ok=True)
            duplex_count = 0
            for ri, (split_item, record_item) in enumerate(zip(split_results, record_results)):
                source_pdf = Path(record_item.get("split_pdf") or "")
                content_list_path = Path(record_item.get("clean_dir") or "") / "content_list_v2.json"
                if not source_pdf.exists() or not content_list_path.exists():
                    continue
                try:
                    name = safe_path_component(
                        str(split_item.get("name") or record_item.get("name") or f"笔录{ri+1}"), "未命名"
                    )
                    output_pdf = duplex_dir / f"{name}_双面打印.pdf"
                    self.insert_blanks_for_double_sided(source_pdf, output_pdf, content_list_path)
                    duplex_count += 1
                except Exception:
                    pass
            manifest["outputs"]["duplex_print_dir"] = str(duplex_dir)
            manifest["outputs"]["duplex_print_count"] = duplex_count
            self.write_manifest(manifest)

            case_full_text = self._load_directory_full_text(directory_clean_dir)
            case_record_list = []
            participant_names = []
            for index, (split_item, validation, record_item) in enumerate(zip(split_results, validations, record_results), start=1):
                printed_pages = format_printed_pages(split_item.get("ranges"))
                record_date = validation.get("record_date") or validation.get("directory_date") or ""
                record_name = validation.get("name") or str(split_item.get("name") or "")
                record_type = validation.get("record_type") or str(split_item.get("record_type") or "")
                clean_full_md = record_item.get("clean_full_md", "")
                reference_format = ""
                if record_name and record_date and printed_pages:
                    reference_format = f"{record_name}于{record_date}（证据卷P{printed_pages}）的{record_type}中"
                participant_names.append(record_name)
                case_record_list.append(
                    {
                        "id": index,
                        "姓名": record_name,
                        "笔录类型": record_type,
                        "日期": record_date,
                        "文件路径": clean_full_md or record_item.get("split_pdf", ""),
                        "内容摘要": "",
                        "印刷页码": printed_pages,
                        "引用格式": reference_format,
                        "全文内容": Path(clean_full_md).read_text(encoding="utf-8", errors="ignore") if clean_full_md and Path(clean_full_md).exists() else "",
                        "页码映射": [],
                        "页码状态": validation.get("page_status", ""),
                    }
                )
            record_summaries = {
                str(record_item["id"]): {
                    "content": f"{record_item['姓名']}：{record_item['笔录类型']}，{record_item['日期']}",
                    "source": "auto_material_pipeline",
                }
                for record_item in case_record_list
            }
            person_summaries = {
                name: {
                    "content": "",
                    "record_count": participant_names.count(name),
                    "source": "auto_material_pipeline",
                }
                for name in dict.fromkeys(participant_names)
                if name
            }
            graph_nodes = [
                {"id": name, "label": name, "type": "person"}
                for name in dict.fromkeys(participant_names)
                if name
            ]

            case_data = {
                "案件名称": case_name,
                "案件编号": case_no,
                "笔录目录": [
                    {
                        "id": record_item["id"],
                        "姓名": record_item["姓名"],
                        "笔录类型": record_item["笔录类型"],
                        "日期": record_item["日期"],
                        "印刷页码": record_item["印刷页码"],
                        "文件路径": record_item["文件路径"],
                    }
                    for record_item in case_record_list
                ],
                "笔录总数": len(case_record_list),
                "笔录列表": case_record_list,
                "起诉书": indictment_data,
                "笔录摘要": record_summaries,
                "人物摘要": person_summaries,
                "案情图谱": {
                    "nodes": graph_nodes,
                    "edges": [],
                },
                "当事人清单": [
                    {
                        "姓名": record_item["姓名"],
                        "笔录类型": record_item["笔录类型"],
                        "日期": record_item["日期"],
                    }
                    for record_item in case_record_list
                ],
                "核心当事人": [case_record_list[0]["姓名"]] if case_record_list else [],
                "委托当事人": [str(params.get("entrusted_party") or "").strip()] if str(params.get("entrusted_party") or "").strip() else [],
                "涉案核心人物": [record_item["姓名"] for record_item in case_record_list if record_item["姓名"]],
                "全文内容": case_full_text,
            }
            case_json_dir = stage_dirs["case_json"]
            case_json_path = case_json_dir / f"{safe_path_component(case_id, 'case')}.json"
            case_json_path.write_text(json.dumps(case_data, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest["outputs"]["case_json"] = str(case_json_path)
            manifest["stage"] = "case_json"
            self.write_manifest(manifest)

            graphrag_dir = stage_dirs["graphrag"]
            graphrag_dir.mkdir(parents=True, exist_ok=True)
            graph_index = ""
            if self.graph_builder is not None:
                graph_result = self.graph_builder(case_id, case_data, self.base_dir, save=True)
                graph_index = self._graph_index_output(graph_result, case_id)
            manifest["outputs"]["graphrag_dir"] = str(graphrag_dir)
            manifest["outputs"]["graphrag_index"] = graph_index
            manifest["stage"] = "graphrag"
            self.write_manifest(manifest)

            manifest["status"] = "completed"
            manifest["stage"] = "completed"
            manifest["message"] = "自动材料管线完成"
            self.write_manifest(manifest)
            return manifest
        except Exception as exc:
            return self._fail_manifest(manifest, f"自动材料管线失败: {exc}")

    def _get_pdf_page_count(self, pdf_path):
        pymupdf = import_pymupdf()
        doc = pymupdf.open(str(pdf_path))
        try:
            return doc.page_count
        finally:
            doc.close()
