---
name: 案件智能分析台
description: 连接本地「案件智能分析台」Web 应用，提供案件查询、证据检索、AI 聊天（小扣）、证据解析、GraphRAG 索引管理等能力。自动发现 Web 应用位置，支持 Codex / Claude Code / Cursor 等 Agent 调用。
---

# 案件智能分析台 Skill

连接本地运行的「案件智能分析台」Web 应用（默认 `http://127.0.0.1:5000`）。

## 自动发现

按以下顺序查找 Web 应用：

1. 检查 `http://127.0.0.1:5000/api/agent/capabilities` 是否可达（已运行）
2. 搜索 `.server.pid` 文件（Windows: `dir /s /b %USERPROFILE%\*.server.pid`）
3. 检查环境变量 `ANALYSIS_PLATFORM_HOME`
4. 搜索常见安装路径：
   - `E:\codex\案件笔录检索通用版\project\app.py`
   - `%USERPROFILE%\codex\案件笔录检索通用版\project\app.py`
5. 如果以上都失败，提示用户提供安装路径或将 `ANALYSIS_PLATFORM_HOME` 设为项目根目录

如果找到代码但服务未运行，提示用户启动：
```bash
cd <项目根目录>\project && py app.py
```

## API 参考

### 发现与状态

**GET /api/agent/capabilities**
获取可用能力、案件列表、MinerU 配置状态。不返回密钥。
```python
import requests
r = requests.get("http://127.0.0.1:5000/api/agent/capabilities")
data = r.json()
# data["cases"] → [{id, name, record_count}, ...]
# data["capabilities"] → ["material_auto_build", "graphrag_retrieve", ...]
# data["mineru"]["configured"] → true/false
```

### 案件管理

**GET /api/cases** — 案件列表

**POST /api/cases** — 创建空案件
```json
{"case_name": "某某涉嫌某某罪案"}
```
返回 `{"case": {"id": "case_id", "name": "..."}}`

### 笔录检索

**POST /api/search** — 多关键词模糊搜索（推荐用 POST JSON，避免中文编码问题）
```python
requests.post("http://127.0.0.1:5000/api/search",
    json={"case": "case_id", "keyword": "当事人A 当事人B"})
```

**GET /api/records?case=ID&name=姓名** — 按姓名查笔录列表

**GET /api/record/<id>?case=ID** — 笔录详情（含全文）

### AI 聊天（小扣）

**POST /api/chat/stream** — SSE 流式聊天，小扣可自主调用 `[SEARCH]` `[FETCH_RECORD]` `[PARSE_EVIDENCE]` 等工具
```python
import requests, json

r = requests.post("http://127.0.0.1:5000/api/chat/stream",
    json={"case": "case_id", "message": "当事人A的付款方式是什么？", "profile": "strong"},
    stream=True)

for line in r.iter_lines(decode_unicode=True):
    if line and line.startswith("data: "):
        data = json.loads(line[6:])
        # Handle streaming response
```

SSE 事件类型：`stage`（状态更新）、`token`（流式文本）、`done`（完成）、`error`（错误）。

### 证据管理

**GET /api/evidence-directory?case=ID** — 证据目录（按类型分组）

**POST /api/evidence/parse** — 按需解析证据条目
```json
{"case": "case_id", "entries": [273, 289, 292]}
```

### 索引管理

**POST /api/graphrag/rebuild** — 重建 GraphRAG 索引
```json
{"case": "case_id"}
```

**POST /api/graphrag/retrieve** — GraphRAG 检索
```json
{"case": "case_id", "query": "关键词"}
```

### Agent 集成

**POST /api/agent/brief** — 生成分析任务包（供外接 Agent 使用）
```json
{"case": "case_id", "task": "record_summaries", "output_format": "markdown"}
```

**POST /api/agent/save-result** — 保存外接 Agent 分析结果
```json
{"case": "case_id", "title": "分析报告", "format": "md", "content": "# 分析结果..."}
```
保存到 `project/runtime/agent_outputs/{case_id}/`

### 建库任务

**POST /api/material/auto-build** — 启动自动 MinerU 建库
```json
{
  "case": "case_id",
  "raw_pdf": "E:\\案件材料\\证据卷.pdf",
  "case_name": "案件名称",
  "document_pdf": "E:\\案件材料\\文书卷.pdf",
  "document_type": "volume",
  "entrusted_party": "委托人"
}
```

**GET /api/jobs/{job_id}** — 查询任务状态
常见状态：`queued` → `running` → `completed` / `failed`

## 安全规则

- ❌ 不要读取、输出 API Key / MinerU Token / 案件敏感原文
- ❌ 不要分享 `project/config/ai_settings.json`、`project/data/*.json`、证据卷 PDF
- ❌ 不要暴露本地服务到公网
- ❌ 不要直接覆盖 `project/data/*.json`，走 API
- ✅ 涉及证据时必须标注来源（页码、笔录ID）
- ✅ 生成分享包时排除 `config/` `data/` `runtime/` 及密钥文件

## 错误处理

遇到错误时区分两类：

### Agent 自身错误
- 网络超时、Python 环境问题、文件权限 → Agent 自行排查

### Web 应用错误（API 返回 error）
收集以下信息并引导用户提交 GitHub Issue：

```
错误信息：{error message}
请求路径：{API path}
请求参数：{payload（脱敏后）}
案件ID：{case_id}
时间：{ISO timestamp}
平台版本：从 /api/agent/capabilities 获取
```

引导语：
> 案件智能分析台返回了一个错误。这通常是平台本身的问题，不是 Agent 的问题。
> 请将以下信息提交到 GitHub Issues：
> https://github.com/louie-1515/case-docket-studio/issues/new
> （附上错误信息、请求路径和时间）

## 最小调用流程

```
1. GET /api/agent/capabilities → 确认服务在线、获取案件列表
2. 选择已有案件 或 POST /api/cases 创建新案件
3. POST /api/chat/stream → 通过小扣进行案件分析（推荐，最强大）
   或 POST /api/search → 直接检索笔录
4. 按需 POST /api/agent/save-result → 保存分析结果
```

> GitHub Issue 地址可在 SKILL.md 中配置。将下方 `louie-1515/case-docket-studio` 替换为实际仓库：
> https://github.com/louie-1515/case-docket-studio/issues/new
