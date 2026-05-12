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

    def parse_pdf_to_clean_dir(self, pdf_path, output_dir, job_label=""):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        batch_id = self.submit_pdf(pdf_path, job_label=job_label)
        status = self.wait_for_result(batch_id)
        result_url = status.get("result_url")
        zip_path = output_dir / f"{batch_id}.zip"
        self.download_result_zip(result_url, zip_path)
        self.extract_clean_result(zip_path, output_dir, keep_debug=False)
        try:
            zip_path.unlink(missing_ok=True)
        except OSError:
            pass
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

    def _data_id(self, label):
        value = "".join(ch if ch.isalnum() or ch in "_-." else "_" for ch in str(label or "pdf"))
        value = value.strip("._-")[:96] or "pdf"
        return f"{value}_{uuid.uuid4().hex[:12]}"
