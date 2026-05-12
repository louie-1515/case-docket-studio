# 案件智能分析台 v3

面向刑事案件经办人员（检察官、律师、侦查人员）的智能案卷分析平台。支持 GraphRAG 证据检索、AI 深度分析（自动深入调查+流式对话）、笔录检索、人物画像、案情图谱、证据材料管理。

---

## 技术栈

- **后端**: Python + Flask（无ORM，PDF处理使用 PyMuPDF）
- **前端**: 纯 HTML/CSS/JavaScript，无框架
- **图谱渲染**: D3.js v7（CDN引入）
- **数据**: 本地 JSON 文件
- **AI处理**: 本地配置的 OpenAI/Anthropic 兼容接口 + 项目内置办案 skills
- **启动器**: Tkinter / VBS

---

## 快速启动

### 方式1：命令行启动

```bash
cd project
pip install -r requirements.txt
python app.py
# 浏览器打开 http://localhost:5000
```

### 方式2：桌面双击启动（Windows）

在 `project/` 目录中双击 `start_app.vbs`，或运行 `launcher.bat`。

关闭 launcher.py 窗口自动结束 Flask 进程。

### 可移植性说明

- 项目已按 `&lt;项目根目录&gt;` 规范整理
- 启动脚本使用项目当前目录，不依赖固定盘符
- 默认数据目录是 `project/data/`
- 如需读取外部 `full.md` 原文，可在案件 JSON 中填写相对路径，基准目录为 `project/`
- 也可以通过环境变量覆盖：
  - `DATA_DIR`：案件 JSON 目录
  - `RECORDS_ROOT`：外部笔录原文根目录

---

## 完整使用流程

```
打开 Web App
    │
    ├─ 进入旧案件 → 选择案件 → 进入工作台
    │
    └─ 建立新案件
          │
          ├─ 填写案件名称
          ├─ 配置 AI / MinerU API（已有配置可跳过）
          └─ 选择原始证据卷 PDF
    │
    ▼
┌─────────────────────────┐
│ 自动 MinerU 建库         │
│ 云 API 解析目录/拆分/OCR  │
│ 生成案件JSON和复核清单    │
└─────────────────────────┘
    │
    ▼
确认委托人 → GraphRAG 检索 → AI 摘要/图谱/聊天
```

---

## 项目结构

```
project/
├── app.py                  # Flask 后端（所有API）
├── analysis_pipeline.py    # AI 分析任务执行器
├── auto_material_pipeline.py # 自动 MinerU 建库流水线
├── graphrag_pipeline.py    # GraphRAG 索引与检索
├── material_pipeline.py    # 材料粗分、插页和任务清单
├── mineru_client.py        # MinerU 云 API 客户端
├── requirements.txt        # Python依赖
├── launcher.py             # Tkinter启动器
├── launcher.bat            # Windows批处理启动
├── start_app.vbs           # 桌面双击启动（无黑窗）
├── PRODUCT.md              # 产品文档
├── DESIGN.md               # 设计规范
├── data/                   # 案件JSON数据目录（需自行放入）
│   └── sample_data.json    # 示例数据（格式参考）
├── records/                # 可选：外部 full.md 原文目录
├── templates/
│   └── index.html          # 单页应用
└── static/
    ├── style.css           # 样式系统
    └── app.js              # 前端逻辑
```

---

## API 接口

### 已有接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/cases` | 案件列表 |
| GET | `/api/records?case=ID&name=...&type=...&date=...` | 笔录列表（支持筛选） |
| GET | `/api/record/<id>?case=ID` | 笔录详情（含全文） |
| GET `/POST` | `/api/search?case=ID&keyword=...` | 多关键词模糊搜索（智能识别人名）。**推荐用 POST JSON body 传中文** |
| GET | `/api/filters?case=ID&name=...&type=...&date=...` | 筛选条件（联动过滤） |
| GET | `/api/names?case=ID` | 案件中所有人员姓名 |
| GET | `/api/record/<id>/page/<num>` | 按页码获取笔录内容 |

### 新增接口（v2）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/cases` | 创建空案件，用于新案件建库向导 |
| GET | `/api/summaries?case=ID` | 笔录AI摘要 |
| GET | `/api/person-summaries?case=ID` | 人物综合摘要 |
| GET | `/api/indictment?case=ID` | 起诉书/起诉意见书 |
| GET | `/api/graph?case=ID` | 案情图谱数据 |
| GET | `/api/graph/drawio?case=ID` | 导出 drawio |
| GET | `/api/ai/settings` | 读取 AI 配置 |
| POST | `/api/ai/settings` | 保存 AI 配置 |
| POST | `/api/ai/test` | 测试 AI 连接 |
| GET | `/api/agent/capabilities` | 外接 Agent 可调用能力说明，不返回密钥 |
| GET | `/api/jobs?case=ID` | 任务列表 |
| POST | `/api/jobs/start` | 启动材料/AI任务 |
| GET | `/api/jobs/<job_id>/manifest?case=ID` | 读取材料任务清单 |
| GET | `/api/jobs/<job_id>/manifest/download?case=ID` | 下载材料任务清单 |
| GET | `/api/jobs/<job_id>/artifact?case=ID&kind=split_plan_preview` | 下载材料任务产物，如分卷预览 |
| GET | `/api/jobs/<job_id>/artifact/preview?case=ID&kind=split_plan_preview` | 读取分卷预览表格数据 |
| GET | `/api/jobs/<job_id>/review-items` | 读取自动建库复核项 |
| POST | `/api/jobs/<job_id>/open-output?case=ID` | 打开材料任务输出文件夹 |
| POST | `/api/material/auto-build` | 启动自动 MinerU 建库 |
| GET | `/api/graphrag/index?case=ID` | GraphRAG 索引状态 |
| POST | `/api/graphrag/rebuild` | 重建 GraphRAG 索引 |
| POST | `/api/graphrag/retrieve` | GraphRAG 证据检索 |
| GET | `/api/chat/history?case=ID` | 案件聊天记录 |
| POST | `/api/chat` | GraphRAG 增强聊天 |
| POST | `/api/agent/brief` | 为外接 Agent 生成临时分析任务包 |
| POST | `/api/agent/save-result` | 保存外接 Agent 的临时分析结果 |
| GET | `/api/evidence-directory?case=ID` | 证据目录（按类型分类的全部条目） |
| POST | `/api/evidence/parse` | 按需解析选中的证据条目 |

### 自动 MinerU 建库任务参数

每次打开页面会先显示启动封面：可以选择“进入旧案件”，也可以选择“建立新案件”。建立新案件会先创建一个空案件 JSON，再进入 API 配置和 PDF 选择步骤。已有配置可以直接跳过接口配置，沿用本机旧配置。

系统仅支持 MinerU 云 API：用户选择整本证据卷 PDF 后，后端调用 MinerU 解析目录，自动计算目录印刷页码与 PDF 系统页码的偏移，再拆分笔录、逐份调用 MinerU OCR，并生成案件 JSON、复核清单和 GraphRAG 索引。

MinerU Token 在“AI 分析 → MinerU 云 API”中配置，保存到本机 `project/config/ai_settings.json`；接口返回时只显示是否已配置，不返回明文 Token。

`POST /api/jobs/start` 启动 `material_auto_build` 时支持：

```json
{
  "case": "case_id",
  "type": "material_auto_build",
  "params": {
    "raw_pdf": "E:\\案件材料\\证据卷.pdf",
    "case_name": "某某涉嫌某某罪案",
    "document_pdf": "E:\\案件材料\\文书卷.pdf",
    "document_type": "volume",
    "entrusted_party": "委托人姓名"
  }
}
```

行为：

- `raw_pdf` 是整本证据卷 PDF。
- `case_name` 为空时默认使用当前案件名称。
- 页码偏移由系统自动计算，用户和外置 Agent 都不需要传入 `page_offset`。
- `document_pdf` 是起诉书 / 起诉意见书或文书卷 PDF。
- `document_type` 可填 `direct` 或 `volume`，分别表示直接文书和带目录文书卷。
- `entrusted_party` 可先传入已知委托人；后续会由自动初筛和用户确认补强。
- 目录日期与 OCR 日期一致或目录有日期但正文未识别出日期时，自动采用目录日期。
- 目录日期与 OCR 日期冲突时，写入 `review_items.json`，不静默改成无证据日期。
- 没有目录可解析条目时，任务失败并保留清单，方便排查。

自动建库输出统一放在任务包内：

```text
project/runtime/material_jobs/{job_id}/
├─ 00_upload/
├─ 01_directory_mineru/
├─ 02_directory_parse/
│  └─ split_plan.json
├─ 03_split_pdfs/
├─ 04_record_mineru_clean/
├─ 05_validation/
├─ 06_case_json/
├─ 07_graphrag/
├─ review_items.json
└─ manifest.json
```

页面中的材料任务卡片支持查看阶段进度、复核项数量、下载 `manifest.json`、打开输出文件夹。旧的手动粗分/细分能力仍保留在后端用于兼容历史任务，但不再作为用户入口展示。

### 中文编码注意事项

Windows 终端（bash/curl）默认编码为 GBK，直接用 curl 发送中文查询参数可能导致乱码。系统已内置自动检测修复（检测 GBK 查询字符串并转换为 UTF-8）。

仍推荐以下方式避免编码问题：

- **方式一（推荐）**：用 POST JSON body 传参
  ```python
  requests.post("http://127.0.0.1:5000/api/search",
      json={"case": "case_id", "keyword": "张三"})
  ```
- **方式二**：用 Python `requests.get(params=...)` 自动 URL 编码
  ```python
  requests.get("http://127.0.0.1:5000/api/search",
      params={"case": "case_id", "keyword": "张三"})
  ```
- **方式三**：直接用 curl + 手动 URL 编码
  ```bash
  curl "http://127.0.0.1:5000/api/search?case=case_id&keyword=%E6%9C%B1%E9%9C%9E%E9%9C%9E"
  ```

---

## 外接 Agent

本系统提供 Skill 供 Claude Code / Codex / Cursor 等本地 Agent 调用。

将 `skills/案件智能分析台/` 目录复制到对应 Agent 的 skills 路径：

| Agent | Skills 路径 |
|-------|------------|
| Claude Code | `~/.claude/skills/案件智能分析台/` |
| Codex | `%USERPROFILE%\.codex\skills\案件智能分析台\` |

Skill 会自动发现 Web 应用位置、提供完整 API 参考和安全规则、遇到平台错误时引导提交 GitHub Issue。

---

## 数据格式

### 案件JSON（最小示例）

见 `project/data/sample_data.json`

```json
{
  "案件名称": "示例案件",
  "案件编号": "A0000000000000000000",
  "笔录目录": "E:\\\\案件\\\\笔录md格式转译",
  "笔录总数": 2,
  "笔录列表": [
    {
      "姓名": "张三",
      "笔录类型": "讯问笔录",
      "次数": "",
      "日期": "2025年1月1日",
      "文件路径": "张三.pdf-xxx\\\\full.md",
      "内容摘要": "笔录前200字...",
      "印刷页码": "1-5",
      "id": 1,
      "引用格式": "张三于2025年1月1日（证据卷P1-5）的讯问笔录中",
      "全文内容": "# 讯问笔录\\n\\n时间...",
      "页码映射": [
        {"start_line": 0, "end_line": 50, "evidence_page": 1, "internal_page": 1}
      ]
    }
  ],
  "笔录摘要": {
    "1": {"content": "AI生成的每份笔录摘要...", "generated_at": "2026-01-01T00:00:00"}
  },
  "人物摘要": {
    "张三": {
      "姓名": "张三",
      "角色定位": "组织联络人员",
      "笔录数量": 2,
      "总字数": 5000,
      "认罪态度": "认罪认罚",
      "综合摘要": "该人物所有笔录的综合摘要..."
    }
  },
  "起诉书": {
    "has_content": true,
    "content": "起诉意见书全文...",
    "structured": {
      "当事人": ["张三"],
      "案件事实": "经依法审查查明...",
      "罪名": "XX罪",
      "涉案金额": "1000万元"
    }
  },
  "案情图谱": {
    "version": "1.0",
    "generated_at": "2026-01-01T00:00:00",
    "selected_parties": ["张三"],
    "nodes": [
      {
        "id": "node1",
        "label": "张三",
        "type": "person",
        "subtype": "组织联络人员",
        "description": "1983年生，某市人。涉及组织联络、资金往来等事实...",
        "importance": "primary",
        "members": [],
        "records": [1]
      }
    ],
    "edges": [
      {
        "id": "edge1",
        "source": "node1",
        "target": "node2",
        "label": "控制",
        "type": "direct",
        "style": "solid",
        "flow": "指挥联络",
        "evidence": "张三讯问笔录P3"
      }
    ]
  },
  "委托人上下文": {
    "content": "AI生成的委托人上下文...",
    "generated_at": "2026-05-08T00:00:00+08:00",
    "profile": "strong"
  },
  "分析复核": {
    "content": "AI生成的复核意见...",
    "generated_at": "2026-05-08T00:00:00+08:00",
    "profile": "strong"
  }
}
```

**说明**：所有新增字段（`笔录摘要`、`人物摘要`、`起诉书`、`案情图谱`、`委托人上下文`、`分析复核`）均为可选，后端向后兼容无这些字段的旧数据。

### GraphRAG 运行数据

GraphRAG 索引保存在：

```text
project/runtime/graphrag/{case_id}/index.json
```

索引由案件 JSON、笔录全文、笔录摘要、人物摘要、起诉书和案情图谱生成。聊天接口会先检索证据片段、人物节点和关系线，再调用配置的 AI 生成回答。

**常驻小扣聊天**：页面右下角提供“小扣”入口。它不依赖当前所在页面，打开后复用当前案件、委托人、GraphRAG 检索结果和同一份聊天历史；AI 分析页里的“案件 AI 聊天”仍作为完整工作台保留。

**人物摘要格式**：支持两种格式——旧版 `{content, record_count}` 和新版 `{姓名, 角色定位, 笔录数量, 总字数, 认罪态度, 综合摘要}`，前端自动兼容。

**案情图谱节点描述**：description字段应包含丰富信息（年龄、籍贯、角色、关键行为、前科记录），用于图谱悬停提示。

**案情图谱显示规则**：办案导图和 drawio 导出默认以 `委托当事人` 为中心，不再要求人工筛选当事人。图中只展示真实人物节点；犯罪团伙、下游买家、车辆、账户、地点、案件事件等信息应作为关系标签、证据说明或人物描述出现，不作为和人物同级的圆点/方框节点。主体关系图使用人物方框和黑灰正交关系线，方便后续在 drawio 中继续编辑。

**AI 批处理规则**：笔录摘要和人物摘要默认支持断点续跑，已有非空摘要不会重复生成。需要覆盖旧结果时勾选“重跑已有摘要”。大案可填写起始序号和本批数量，分批生成摘要。

**图谱复核规则**：`graph` 任务会先构建 GraphRAG 索引和基础/cheap 图谱；如强 AI 配置完整，会再进行一次图谱复核，重点清理非人物节点、校正委托人中心和关系来源。复核失败或返回格式无效时保留原图。

**临时分析与外接 Agent 入口**：旧案件工作台不再单独展示“临时分析”页面。用户临时需求统一通过右下角“小扣”聊天提出；外接 Agent 则直接调用 `/api/agent/capabilities`、`/api/jobs/start`、`/api/material/auto-build`、`/api/agent/brief` 等本地接口。能力说明不会返回 API Key 或 MinerU Token，外接 Agent 的最终结果可保存到 `project/runtime/agent_outputs/{case_id}/`。

---

---

## Skills 说明

将 `skills/` 目录下的子目录复制到 `~/.claude/skills/` 即可使用。

| Skill | 触发关键词 | 功能 |
|-------|-----------|------|
| 刑事笔录分卷 | "按人分卷"、"拆分笔录"、"双面打印" | 4阶段：PDF分卷→MinerU→插空白页→起诉书解析 |
| 刑事文书提取 | "提取起诉意见书"、"文书提取" | 从文书卷PDF自动识别目录并提取起诉意见书/起诉书 |
| 导入案件智能分析台 | "导入检索"、"导入app" | 将MinerU输出转为案件JSON |
| 案件智能分析台 | "分析台"、"案件分析" | 连接本地 Web 应用，供外接 Agent 调用 |
| 笔录摘要生成 | "生成笔录摘要"、"AI摘要" | 为每份笔录生成结构化AI摘要 |
| 人物摘要生成 | "生成人物摘要"、"人物画像" | 为每个人物生成综合摘要 |
| 案情图谱生成 | "生成案情图谱"、"案情图谱" | 提取实体和关系，生成图谱JSON |

### Skill联动关系

```
刑事笔录分卷
    ├── 阶段1-3: 笔录分卷 → 导入案件智能分析台
    │
    └── 阶段4: 起诉书处理
            ├── 4.0: 刑事文书提取（从文书卷PDF提取）
            └── 4.1-4.4: 起诉书解析（MinerU + 结构化提取）

导入案件智能分析台
    ├── 笔录摘要生成
    ├── 人物摘要生成
    └── 案情图谱生成（需先完成摘要）
```

---

## 设计原则

- **纯前端**：HTML + CSS + JS，无框架，零构建步骤
- **单页应用**：无路由，视图通过Tab切换
- **本地数据**：所有数据来自本地JSON，无需网络
- **联动筛选**：姓名/类型/日期三个维度实时联动过滤
- **克制设计**：slate色系，无渐变，卡片hover左侧边框高亮

---

## 浏览器兼容性

- Chrome / Edge / Firefox 最新版
- D3.js v7 需要现代浏览器（不支持IE）
