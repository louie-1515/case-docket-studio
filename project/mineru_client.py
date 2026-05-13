import json
import ssl
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# requests 用于 OSS PUT 上传（urllib.request 会自动添加 Content-Type 破坏 OSS 签名）
try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


class MinerUError(Exception):
    pass


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _default_ssl_context():
    """创建宽松 SSL 上下文，兼容某些 CDN/代理的 TLS 配置。"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _oss_put_upload(upload_url, data_bytes, timeout=120):
    """PUT 上传文件到 OSS 预签名 URL。

    关键约束：不能设置 Content-Type 等自定义 header，
    否则 OSS 签名验证失败返回 403（GitHub #4145）。
    """
    if _HAS_REQUESTS:
        resp = _requests.put(upload_url, data=data_bytes, headers={}, timeout=timeout)
        if resp.status_code not in (200, 204):
            raise MinerUError(
                f"OSS 上传失败 HTTP {resp.status_code}: {resp.text[:200]}"
            )
        return resp.status_code

    # 回退：显式设置 Content-Type 为空，避免 urllib 自动添加 form-urlencoded
    req = urllib.request.Request(upload_url, data=data_bytes, method="PUT")
    req.add_header("Content-Type", "")
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        raise MinerUError(
            f"OSS 上传失败 HTTP {exc.code}: "
            f"{exc.read().decode('utf-8', errors='ignore')[:200]}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        raise MinerUError(
            f"OSS 上传网络错误 ({upload_url[:60]}...): {exc}"
        ) from exc


def _default_http_request(method, url, headers=None, data=None, timeout=60):
    """通用 HTTP 请求。PUT 到 OSS 时走专门的 OSS 上传路径避免签名问题。"""
    # OSS PUT 上传：绕过 urllib 的 Content-Type 自动添加
    is_oss_put = (
        method == "PUT"
        and isinstance(data, (bytes, bytearray))
        and ("oss-cn-" in url or "aliyuncs.com" in url or ".oss." in url)
    )
    if is_oss_put:
        return _oss_put_upload(url, data, timeout=timeout)

    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    ctx = _default_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            body = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "application/json" in ctype:
                return json.loads(body.decode("utf-8"))
            return body
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
        raise MinerUError(
            f"MinerU 网络请求失败 ({url}): {exc}. "
            f"请检查网络连接，或确认是否需要配置代理（HTTP_PROXY / HTTPS_PROXY 环境变量）。"
        ) from exc
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise MinerUError(f"MinerU HTTP {exc.code}: {body[:300]}") from exc


class MinerUClient:
    def __init__(self, config, http_request=None, sleep=None):
        self.config = config or {}
        self.http_request = http_request or _default_http_request
        self.sleep = sleep or time.sleep

    def _base_url(self):
        base_url = (self.config.get("base_url") or "https://mineru.net").strip()
        return base_url.rstrip("/")

    def _api_token(self):
        api_token = (self.config.get("api_token") or "").strip()
        if not api_token:
            raise MinerUError("MinerU api_token 未配置")
        return api_token

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._api_token()}",
        }

    def submit_pdf(self, pdf_path, job_label=""):
        pdf_path = Path(pdf_path)
        if not pdf_path.exists() or not pdf_path.is_file():
            raise MinerUError(f"PDF 不存在: {pdf_path}")

        url = f"{self._base_url()}/api/v4/file-urls/batch"
        data_id = self._data_id(job_label or pdf_path.stem)
        file_item = {
            "name": pdf_path.name,
            "data_id": data_id,
            "is_ocr": bool(self.config.get("is_ocr", True)),
        }
        page_ranges = (self.config.get("page_ranges") or "").strip()
        if page_ranges:
            file_item["page_ranges"] = page_ranges
        payload = {
            "files": [file_item],
            "model_version": self.config.get("model_version") or "vlm",
            "enable_formula": bool(self.config.get("enable_formula", False)),
            "enable_table": bool(self.config.get("enable_table", True)),
            "language": self.config.get("language") or "ch",
        }
        headers = {"Content-Type": "application/json", **self._headers()}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        resp = self.http_request("POST", url, headers=headers, data=data, timeout=60)
        data = self._require_success_data(resp)
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise MinerUError("MinerU 返回缺少 batch_id 或 file_urls")

        upload_body = pdf_path.read_bytes()
        upload_resp = self.http_request("PUT", file_urls[0], headers={}, data=upload_body, timeout=120)
        if isinstance(upload_resp, dict) and upload_resp.get("code") not in (None, 0):
            raise MinerUError(upload_resp.get("msg") or "MinerU 文件上传失败")
        return batch_id

    def wait_for_result(self, batch_id):
        if not batch_id:
            raise MinerUError("batch_id 为空")
        poll = int(self.config.get("poll_interval_seconds", 3) or 3)
        timeout = int(self.config.get("timeout_seconds", 600) or 600)
        url = f"{self._base_url()}/api/v4/extract-results/batch/{batch_id}"
        headers = self._headers()

        started = time.time()
        while True:
            resp = self.http_request("GET", url, headers=headers, data=None, timeout=60)
            data = self._require_success_data(resp)
            result = self._first_extract_result(data)
            status = (result.get("state") or result.get("status") or "").lower()
            result_url = result.get("full_zip_url") or result.get("result_url")
            if status in ("done", "finished", "success") and result_url:
                return {**result, "result_url": result_url}
            if status in ("failed", "error"):
                raise MinerUError(result.get("err_msg") or result.get("message") or "MinerU 解析失败")
            if time.time() - started >= timeout:
                raise MinerUError("等待 MinerU 结果超时")
            self.sleep(poll)

    def download_result_zip(self, result_url, output_zip):
        if not result_url:
            raise MinerUError("result_url 为空")
        output_zip = Path(output_zip)
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        headers = self._headers()
        body = self.http_request("GET", result_url, headers=headers, data=None, timeout=60)
        if not isinstance(body, (bytes, bytearray)):
            raise MinerUError("下载结果不是二进制内容")
        output_zip.write_bytes(bytes(body))
        return output_zip

    def extract_clean_result(self, zip_path, output_dir, keep_debug=False):
        zip_path = Path(zip_path)
        output_dir = Path(output_dir)
        if not zip_path.exists() or not zip_path.is_file():
            raise MinerUError(f"zip 不存在: {zip_path}")
        output_dir.mkdir(parents=True, exist_ok=True)

        # full.md 是核心产出，必须存在
        essential_suffixes = ("full.md",)
        # 其他可选用后缀匹配（MinerU 可能在文件名前加 UUID 前缀）
        optional_suffixes = ("full.md", "content_list_v2.json", "layout.json")
        meta = {
            "source_zip": zip_path.name,
            "extracted_at": _now_iso(),
            "keep_debug": bool(keep_debug),
        }

        written = set()
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                norm = name.replace("\\", "/").lstrip("/")
                if not norm or norm.endswith("/"):
                    continue

                if any(norm.endswith(suffix) for suffix in optional_suffixes):
                    # 去掉 UUID 前缀，保存为规范文件名
                    clean_name = norm.split("_")[-1] if "_" in norm else norm
                    # 如果 clean_name 不是已知后缀，回退到原始文件名
                    if not any(clean_name.endswith(s) for s in optional_suffixes):
                        clean_name = norm.split("/")[-1]
                    target = output_dir / clean_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name, "r") as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    written.add(clean_name)
                    continue

                if keep_debug:
                    parts = Path(norm).parts
                    if any(part in ("..", "") for part in parts):
                        continue
                    target = output_dir / norm
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name, "r") as src, open(target, "wb") as dst:
                        dst.write(src.read())

        has_essential = any(w.endswith(s) for w in written for s in essential_suffixes)
        if not has_essential:
            raise MinerUError(f"MinerU zip 缺少关键文件 full.md（已提取: {sorted(written)}）")

        (output_dir / "mineru_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_dir

    def _download_result_bytes(self, result_url):
        """下载 MinerU 解析结果为 bytes，不落盘（避免 AV 文件锁）。"""
        if not result_url:
            raise MinerUError("result_url 为空")
        headers = self._headers()
        body = self.http_request("GET", result_url, headers=headers, data=None, timeout=60)
        if not isinstance(body, (bytes, bytearray)):
            raise MinerUError("下载结果不是二进制内容")
        return bytes(body)

    def _extract_clean_from_bytes(self, zip_bytes, output_dir, keep_debug=False):
        """从内存中的 zip bytes 直接解压，不经过磁盘文件。"""
        import io
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        essential_suffixes = ("full.md",)
        optional_suffixes = ("full.md", "content_list_v2.json", "layout.json")
        meta = {
            "extracted_at": _now_iso(),
            "keep_debug": bool(keep_debug),
        }
        written = set()
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in zf.namelist():
                norm = name.replace("\\", "/").lstrip("/")
                if not norm or norm.endswith("/"):
                    continue
                if any(norm.endswith(suffix) for suffix in optional_suffixes):
                    clean_name = norm.split("_")[-1] if "_" in norm else norm
                    if not any(clean_name.endswith(s) for s in optional_suffixes):
                        clean_name = norm.split("/")[-1]
                    target = output_dir / clean_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name, "r") as src, open(target, "wb") as dst:
                        dst.write(src.read())
                    written.add(clean_name)
                    continue
                if keep_debug:
                    parts = Path(norm).parts
                    if any(part in ("..", "") for part in parts):
                        continue
                    target = output_dir / norm
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name, "r") as src, open(target, "wb") as dst:
                        dst.write(src.read())
        has_essential = any(w.endswith(s) for w in written for s in essential_suffixes)
        if not has_essential:
            raise MinerUError(f"MinerU zip 缺少关键文件 full.md（已提取: {sorted(written)}）")
        (output_dir / "mineru_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_dir

    def parse_pdf_to_clean_dir(self, pdf_path, output_dir, job_label=""):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        batch_id = self.submit_pdf(pdf_path, job_label=job_label)
        status = self.wait_for_result(batch_id)
        result_url = status.get("result_url")
        zip_bytes = self._download_result_bytes(result_url)
        self._extract_clean_from_bytes(zip_bytes, output_dir, keep_debug=False)
        return output_dir

    def _require_success_data(self, resp):
        if not isinstance(resp, dict):
            raise MinerUError("MinerU 返回不是 JSON 对象")
        if resp.get("code") not in (0, None):
            raise MinerUError(resp.get("msg") or f"MinerU API 返回错误: {resp.get('code')}")
        data = resp.get("data")
        if not isinstance(data, dict):
            raise MinerUError("MinerU 返回缺少 data")
        return data

    def _first_extract_result(self, data):
        result = data.get("extract_result")
        if isinstance(result, list):
            if not result:
                raise MinerUError("MinerU 返回空 extract_result")
            result = result[0]
        if not isinstance(result, dict):
            raise MinerUError("MinerU 返回缺少 extract_result")
        return result

    # 批量提交上限（MinerU API 限制单次 ≤50 个文件）
    BATCH_MAX_FILES = 50

    def submit_files_batch(self, pdf_paths, job_label=""):
        """一次提交多个 PDF，返回 batch_id。内部并发上传所有文件。"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        if not pdf_paths:
            raise MinerUError("pdf_paths 为空")
        if len(pdf_paths) > self.BATCH_MAX_FILES:
            raise MinerUError(f"单次提交不能超过 {self.BATCH_MAX_FILES} 个文件，当前 {len(pdf_paths)}")

        url = f"{self._base_url()}/api/v4/file-urls/batch"
        files = []
        path_map = {}  # data_id → pdf_path
        for pdf_path in pdf_paths:
            p = Path(pdf_path)
            if not p.exists() or not p.is_file():
                raise MinerUError(f"PDF 不存在: {p}")
            data_id = self._data_id(f"{job_label}_{p.stem}" if job_label else p.stem)
            path_map[data_id] = p
            file_item = {
                "name": p.name,
                "data_id": data_id,
                "is_ocr": bool(self.config.get("is_ocr", True)),
            }
            page_ranges = (self.config.get("page_ranges") or "").strip()
            if page_ranges:
                file_item["page_ranges"] = page_ranges
            files.append(file_item)

        payload = {
            "files": files,
            "model_version": self.config.get("model_version") or "vlm",
            "enable_formula": bool(self.config.get("enable_formula", False)),
            "enable_table": bool(self.config.get("enable_table", True)),
            "language": self.config.get("language") or "ch",
        }
        headers = {"Content-Type": "application/json", **self._headers()}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        resp = self.http_request("POST", url, headers=headers, data=data, timeout=60)
        data = self._require_success_data(resp)
        batch_id = data.get("batch_id")
        file_urls = data.get("file_urls") or []
        if not batch_id or not file_urls:
            raise MinerUError("MinerU 返回缺少 batch_id 或 file_urls")
        if len(file_urls) != len(files):
            raise MinerUError(f"file_urls 数量不匹配: 期望 {len(files)}，实际 {len(file_urls)}")

        # 并发上传所有文件
        data_ids = [f["data_id"] for f in files]
        n_files = len(file_urls)
        upload_workers = min(n_files, 20)
        upload_errors = []

        def _upload_one(idx):
            try:
                pdf = path_map[data_ids[idx]]
                u = file_urls[idx]
                body = pdf.read_bytes()
                self.http_request("PUT", u, headers={}, data=body, timeout=120)
            except Exception as exc:
                upload_errors.append((idx, str(exc)))

        with ThreadPoolExecutor(max_workers=upload_workers) as ex:
            futures = [ex.submit(_upload_one, i) for i in range(n_files)]
            for f in futures:
                f.result()

        if upload_errors:
            first = upload_errors[0]
            raise MinerUError(
                f"批量上传失败 ({len(upload_errors)}/{n_files}): "
                f"文件 {first[0]+1}: {first[1][:120]}"
            )

        return batch_id

    def wait_for_batch(self, batch_id, expected_count):
        """等待批量任务完成，返回 extract_result 列表。

        单个文件解析失败不阻塞整批，失败的项 state 为 "failed"。
        """
        if not batch_id:
            raise MinerUError("batch_id 为空")
        poll = int(self.config.get("poll_interval_seconds", 3) or 3)
        timeout = int(self.config.get("timeout_seconds", 3600) or 3600)
        url = f"{self._base_url()}/api/v4/extract-results/batch/{batch_id}"
        headers = self._headers()

        started = time.time()
        while True:
            resp = self.http_request("GET", url, headers=headers, data=None, timeout=60)
            data = self._require_success_data(resp)
            results = data.get("extract_result")
            if not isinstance(results, list) or not results:
                raise MinerUError("MinerU 返回缺少 extract_result")
            if len(results) != expected_count:
                raise MinerUError(
                    f"extract_result 数量不匹配: 期望 {expected_count}，实际 {len(results)}"
                )

            states = [
                (r.get("state") or r.get("status") or "").lower()
                for r in results
            ]
            # 每个文件到达终态（done/failed/error）即视为完成
            terminal = {"done", "finished", "success", "failed", "error"}
            if all(s in terminal for s in states):
                for r in results:
                    if not r.get("result_url"):
                        r["result_url"] = r.get("full_zip_url")
                return results
            if time.time() - started >= timeout:
                raise MinerUError("等待 MinerU 批量结果超时")
            self.sleep(poll)

    def parse_pdfs_batch(self, pdf_paths, output_dirs, job_label=""):
        """批量解析 PDF：一次提交，并发上传，统一轮询，分别下载解压。

        返回 [(status, error_msg), ...] 每项 status 为 "completed" 或 "failed"。
        单个下载失败不影响其他文件。
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        pdf_paths = [Path(p) for p in pdf_paths]
        output_dirs = [Path(d) for d in output_dirs]
        if len(pdf_paths) != len(output_dirs):
            raise MinerUError("pdf_paths 与 output_dirs 数量不一致")
        for d in output_dirs:
            d.mkdir(parents=True, exist_ok=True)

        batch_id = self.submit_files_batch(pdf_paths, job_label=job_label)
        extract_results = self.wait_for_batch(batch_id, len(pdf_paths))

        n = len(extract_results)
        batch_results = [("failed", "未处理") for _ in range(n)]

        def _download_one(idx):
            try:
                r = extract_results[idx]
                state = (r.get("state") or r.get("status") or "").lower()
                if state in ("failed", "error"):
                    err = r.get("err_msg") or r.get("message") or "MinerU 解析失败"
                    batch_results[idx] = ("failed", err)
                    return
                result_url = r.get("result_url") or r.get("full_zip_url")
                if not result_url:
                    batch_results[idx] = ("failed", "缺少 result_url")
                    return
                zip_bytes = self._download_result_bytes(result_url)
                self._extract_clean_from_bytes(zip_bytes, output_dirs[idx])
                batch_results[idx] = ("completed", None)
            except Exception as exc:
                batch_results[idx] = ("failed", str(exc))

        dl_workers = min(n, 10)
        with ThreadPoolExecutor(max_workers=dl_workers) as ex:
            futures = [ex.submit(_download_one, i) for i in range(n)]
            for f in futures:
                try:
                    f.result()
                except Exception:
                    pass  # 已在 _download_one 内部捕获

        return batch_results

    def _data_id(self, label):
        value = "".join(ch if ch.isalnum() or ch in "_-." else "_" for ch in str(label or "pdf"))
        value = value.strip("._-")[:96] or "pdf"
        return f"{value}_{uuid.uuid4().hex[:12]}"
