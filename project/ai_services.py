import json
import ssl
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


class AIServiceError(Exception):
    pass


class AIStore:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.config_dir = self.base_dir / "config"
        self.runtime_dir = self.base_dir / "runtime"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.config_dir / "ai_settings.json"
        self.jobs_path = self.runtime_dir / "analysis_jobs.json"
        self.chat_path = self.runtime_dir / "chat_history.json"
        self._lock = threading.Lock()

    def default_settings(self):
        profile = {
            "protocol": "openai",
            "base_url": "",
            "api_key": "",
            "model": "",
            "temperature": 0.2,
            "max_tokens": 1200,
        }
        return {
            "strong": {**profile, "role": "综合分析、复核、图谱、辩护思路"},
            "cheap": {**profile, "role": "批量摘要、基础抽取、分类、参数适配"},
            "mineru": {
                "base_url": "https://mineru.net",
                "api_token": "",
                "poll_interval_seconds": 3,
                "timeout_seconds": 600,
            },
            "routing": {
                "chat_default": "strong",
                "extract_default": "cheap",
                "review_default": "strong",
                "max_concurrency": 3,
            },
        }

    def read_json(self, path, default):
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return default

    def write_json(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        tmp.replace(path)

    def get_settings(self, masked=True):
        settings = self.read_json(self.settings_path, self.default_settings())
        merged = self.default_settings()
        for key in ("strong", "cheap"):
            merged[key].update(settings.get(key, {}))
        merged["mineru"].update(settings.get("mineru", {}) if isinstance(settings.get("mineru"), dict) else {})
        merged["routing"].update(settings.get("routing", {}))
        if masked:
            for key in ("strong", "cheap"):
                api_key = merged[key].get("api_key", "")
                merged[key]["api_key"] = "********" if api_key else ""
                merged[key]["has_api_key"] = bool(api_key)
            api_token = merged["mineru"].get("api_token", "")
            merged["mineru"]["api_token"] = "********" if api_token else ""
            merged["mineru"]["has_api_token"] = bool(api_token)
        else:
            merged["mineru"]["has_api_token"] = bool(merged["mineru"].get("api_token", ""))
        return merged

    def save_settings(self, payload):
        current = self.get_settings(masked=False)
        for key in ("strong", "cheap"):
            incoming = payload.get(key, {})
            if not isinstance(incoming, dict):
                continue
            for field in ("protocol", "base_url", "model", "temperature", "max_tokens"):
                if field in incoming:
                    current[key][field] = incoming[field]
            if incoming.get("api_key") and incoming.get("api_key") != "********":
                current[key]["api_key"] = incoming["api_key"]
            if incoming.get("clear_api_key"):
                current[key]["api_key"] = ""
        incoming_mineru = payload.get("mineru", {})
        if isinstance(incoming_mineru, dict):
            current["mineru"]["base_url"] = "https://mineru.net"
            for field in ("poll_interval_seconds", "timeout_seconds"):
                if field in incoming_mineru:
                    current["mineru"][field] = incoming_mineru[field]
            if incoming_mineru.get("api_token") and incoming_mineru.get("api_token") != "********":
                current["mineru"]["api_token"] = incoming_mineru["api_token"]
            if incoming_mineru.get("clear_api_token"):
                current["mineru"]["api_token"] = ""
        if isinstance(payload.get("routing"), dict):
            current["routing"].update(payload["routing"])
        self.write_json(self.settings_path, current)
        return self.get_settings(masked=True)

    def get_jobs(self):
        return self.read_json(self.jobs_path, [])

    def save_jobs(self, jobs):
        self.write_json(self.jobs_path, jobs)

    def create_job(self, case_id, job_type, title, params=None, profile="cheap"):
        job = {
            "id": str(uuid.uuid4()),
            "case": case_id,
            "type": job_type,
            "title": title,
            "profile": profile,
            "status": "queued",
            "progress": 0,
            "message": "等待执行",
            "logs": [],
            "params": params or {},
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "finished_at": "",
        }
        with self._lock:
            jobs = self.get_jobs()
            jobs.insert(0, job)
            self.save_jobs(jobs)
        return job

    def update_job(self, job_id, **changes):
        with self._lock:
            jobs = self.get_jobs()
            for job in jobs:
                if job["id"] == job_id:
                    log_message = changes.pop("log", None)
                    job.update(changes)
                    job["updated_at"] = now_iso()
                    if log_message:
                        job.setdefault("logs", []).append({
                            "time": now_iso(),
                            "message": log_message,
                        })
                    self.save_jobs(jobs)
                    return job
        return None

    def append_chat(self, case_id, role, content, profile="strong"):
        history = self.read_json(self.chat_path, {})
        items = history.setdefault(case_id, [])
        item = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "profile": profile,
            "created_at": now_iso(),
        }
        items.append(item)
        self.write_json(self.chat_path, history)
        return item

    def get_chat(self, case_id):
        return self.read_json(self.chat_path, {}).get(case_id, [])


class AIClient:
    def __init__(self, settings):
        self.settings = settings

    def chat(self, profile, messages, system="", max_tokens=None):
        config = self.settings.get(profile, {})
        protocol = (config.get("protocol") or "openai").lower()
        if not config.get("base_url") or not config.get("api_key") or not config.get("model"):
            raise AIServiceError(f"{profile} AI 尚未配置完整")
        if protocol == "anthropic":
            return self._anthropic_chat(config, messages, system, max_tokens)
        return self._openai_chat(config, messages, system, max_tokens)

    def chat_stream(self, profile, messages, system="", max_tokens=None):
        """流式聊天 — 返回生成器，逐段 yield 文本。"""
        config = self.settings.get(profile, {})
        protocol = (config.get("protocol") or "openai").lower()
        if not config.get("base_url") or not config.get("api_key") or not config.get("model"):
            raise AIServiceError(f"{profile} AI 尚未配置完整")
        if protocol == "anthropic":
            yield from self._anthropic_chat_stream(config, messages, system, max_tokens)
        else:
            yield from self._openai_chat_stream(config, messages, system, max_tokens)

    def _openai_chat(self, config, messages, system, max_tokens):
        base_url = config["base_url"].rstrip("/")
        # 智能 URL 拼接：处理裸域名、/v1、自定义路径等情况
        if base_url.endswith("/chat/completions"):
            url = base_url
        elif base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        elif "/anthropic" in base_url:
            # DeepSeek 等 Anthropic 兼容端点没有 /chat/completions，建议切 protocol
            raise AIServiceError(
                f"当前 base_url ({base_url}) 看起来是 Anthropic 兼容端点，"
                f"但 protocol 配置为 'openai'。请将 protocol 改为 'anthropic'，"
                f"或将 base_url 改为 OpenAI 兼容端点（如 https://api.deepseek.com）"
            )
        else:
            # 尝试标准 OpenAI 路径：base_url/v1/chat/completions
            url = f"{base_url}/v1/chat/completions"
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        payload = {
            "model": config["model"],
            "messages": payload_messages,
            "temperature": float(config.get("temperature", 0.2)),
            "max_tokens": int(max_tokens or config.get("max_tokens", 1200)),
        }
        data = self._request_json(url, config["api_key"], payload)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIServiceError("OpenAI 兼容接口返回格式无法识别") from exc

    def _anthropic_chat(self, config, messages, system, max_tokens):
        base_url = config["base_url"].rstrip("/")
        url = base_url if base_url.endswith("/v1/messages") else f"{base_url}/v1/messages"
        payload = {
            "model": config["model"],
            "messages": messages,
            "system": system,
            "temperature": float(config.get("temperature", 0.2)),
            "max_tokens": int(max_tokens or config.get("max_tokens", 1200)),
        }
        data = self._request_json(url, config["api_key"], payload, anthropic=True)
        try:
            return "".join(part.get("text", "") for part in data.get("content", []))
        except (AttributeError, TypeError) as exc:
            raise AIServiceError("Anthropic 兼容接口返回格式无法识别") from exc

    def _openai_chat_stream(self, config, messages, system, max_tokens):
        """OpenAI 兼容流式请求。yield 每个 delta 文本片段。"""
        base_url = config["base_url"].rstrip("/")
        if base_url.endswith("/chat/completions"):
            url = base_url
        elif base_url.endswith("/v1"):
            url = f"{base_url}/chat/completions"
        else:
            url = f"{base_url}/v1/chat/completions"
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)
        payload = {
            "model": config["model"],
            "messages": payload_messages,
            "temperature": float(config.get("temperature", 0.2)),
            "max_tokens": int(max_tokens or config.get("max_tokens", 1200)),
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config["api_key"]}",
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                for line in resp:
                    line = line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")
                        if text:
                            yield text
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise AIServiceError(f"接口返回 {exc.code}: {body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise AIServiceError(f"接口连接失败 ({url}): {exc}") from exc

    def _anthropic_chat_stream(self, config, messages, system, max_tokens):
        """Anthropic 兼容流式请求。yield 每个 delta 文本片段。"""
        base_url = config["base_url"].rstrip("/")
        url = base_url if base_url.endswith("/v1/messages") else f"{base_url}/v1/messages"
        payload = {
            "model": config["model"],
            "messages": messages,
            "system": system,
            "temperature": float(config.get("temperature", 0.2)),
            "max_tokens": int(max_tokens or config.get("max_tokens", 1200)),
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                for line in resp:
                    line = line.decode("utf-8", errors="ignore").strip()
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                        if event.get("type") == "content_block_delta":
                            text = event.get("delta", {}).get("text", "")
                            if text:
                                yield text
                    except (json.JSONDecodeError, KeyError):
                        continue
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise AIServiceError(f"接口返回 {exc.code}: {body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise AIServiceError(f"接口连接失败 ({url}): {exc}") from exc

    def _request_json(self, url, api_key, payload, anthropic=False):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        if anthropic:
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        try:
            with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise AIServiceError(f"接口返回 {exc.code}: {body[:300]}") from exc
        except (urllib.error.URLError, TimeoutError, ssl.SSLError, OSError) as exc:
            raise AIServiceError(
                f"接口连接失败 ({url}): {exc}. 请检查 base_url 和网络连接。"
            ) from exc


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_job_background(store, job_id, handler):
    thread = threading.Thread(target=handler, args=(store, job_id), daemon=True)
    thread.start()
    return thread


def simulate_material_job(store, job_id):
    steps = [
        (15, "读取任务参数"),
        (35, "准备 skill 调参方案"),
        (60, "等待接入固定 PDF 执行脚本"),
        (100, "入口已创建，下一期接入真实 PDF 处理器"),
    ]
    store.update_job(job_id, status="running", message="任务启动", progress=5)
    for progress, message in steps:
        time.sleep(0.4)
        store.update_job(job_id, progress=progress, message=message, log=message)
    store.update_job(
        job_id,
        status="completed",
        message="材料处理入口已记录，真实 PDF 执行器待接入",
        finished_at=now_iso(),
    )


def simulate_analysis_job(store, job_id):
    steps = [
        (20, "读取委托人上下文"),
        (45, "准备任务提示词和模型路由"),
        (75, "写入任务骨架"),
        (100, "任务入口已完成"),
    ]
    store.update_job(job_id, status="running", message="任务启动", progress=5)
    for progress, message in steps:
        time.sleep(0.4)
        store.update_job(job_id, progress=progress, message=message, log=message)
    store.update_job(
        job_id,
        status="completed",
        message="AI 分析入口已完成，配置模型后可接真实生成逻辑",
        finished_at=now_iso(),
    )
