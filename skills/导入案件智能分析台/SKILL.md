---
name: 导入案件智能分析台
description: 将MinerU解析后的笔录数据导入案件智能分析台的JSON格式，写入data目录。
level: 2
---

# 导入案件智能分析台

将MinerU解析后的笔录数据转换为案件智能分析台的JSON格式，导入到 `<项目根目录>\project\data\` 目录。

## 触发关键词

- `"导入检索"`、`"导入app"`、`"导入笔录检索"`
- `"生成检索数据"`、`"检索库导入"`

## 前置条件

- MinerU已解析完成，输出目录中存在 `full.md` 和 `content_list_v2.json`
- 已知案件名称、案件编号
- 已知每人在证据卷中的页码范围（来自分卷时的TOC或目录）

## app数据格式

`data/{案件名}.json`：

```json
{
  "案件名称": "某案",
  "案件编号": "A3300000000000000000000",
  "笔录目录": "E:\\claude code workspace\\案件笔录md格式转译",
  "笔录总数": 155,
  "笔录列表": [
    {
      "姓名": "孙八",
      "笔录类型": "讯问笔录",
      "次数": "",
      "日期": "2025年10月31日",
      "文件路径": "孙八.pdf-2cde7e14-...\\full.md",
      "内容摘要": "...",
      "印刷页码": "507-513",
      "id": 1,
      "引用格式": "孙八于2025年10月31日（证据卷P507-513）的讯问笔录中",
      "全文内容": "# 讯问笔录\n\n时间...",
      "页码映射": [
        {"start_line": 50, "end_line": 123, "evidence_page": 507, "internal_page": 1},
        {"start_line": 124, "end_line": 171, "evidence_page": 509, "internal_page": 3}
      ]
    }
  ]
}
```

### 字段说明

| 字段 | 来源 | 说明 |
|------|------|------|
| `姓名` | MinerU目录名或笔录内容 | 被讯问/询问人姓名 |
| `笔录类型` | `content_list_v2.json` 的 level=1 title | "讯问笔录"或"询问笔录" |
| `次数` | 笔录内容中提取 | 如"第二次"，无则空字符串 |
| `日期` | `content_list_v2.json` 笔录正文 | 从"时间 2025年X月X日"提取 |
| `文件路径` | MinerU目录结构 | 相对于`笔录目录`，指向`full.md` |
| `内容摘要` | `full.md` | 笔录正文前200字左右 |
| `印刷页码` | TOC | 该笔录在证据卷中的页码范围 |
| `id` | 自动生成 | 从1递增 |
| `引用格式` | 模板生成 | `"{姓名}于{日期}（证据卷P{页码}）的{笔录类型}中"` |
| `全文内容` | `full.md` | 完整markdown文本 |
| `页码映射` | `full.md`页码标记 + TOC | md行号→证据卷页码的映射 |

### 页码映射构建规则

`页码映射` 将 `full.md` 的行号映射到证据卷的页码。

**构建步骤：**
1. 读取 `full.md`，找到所有 `第 X 页 共 Y 页` 格式的页码标记及其行号
2. 每个标记前的行属于该页，标记本身属于该页的最后一行
3. `evidence_page` = 该笔录的起始证据卷页码 + (internal_page - 1)
4. `internal_page` = 页码标记中的X值

**示例：**笔录印刷页码为 `507-513`（共7页）：
- 第1页标记前的行 → `evidence_page=507, internal_page=1`
- 第2页标记前的行 → `evidence_page=509, internal_page=2`（注意：双面打印时奇数页在正面，所以508是背面，509是下一张正面）

> **注意：** `evidence_page` 的具体值取决于原始证据卷的页码排列，需要结合TOC确定。如果TOC给的是连续范围（如507-513），则 `evidence_page` 按顺序递增。

## 工作流程

### 步骤1：收集信息

向用户确认：
- 案件名称、案件编号
- MinerU输出目录路径
- 每人在证据卷中的页码范围（TOC数据，如有）

### 步骤2：扫描MinerU输出目录

遍历MinerU输出目录，识别所有 `{人名}.pdf-{uuid}/` 子目录。

```python
import os, re

def find_mineru_dirs(mineru_root):
    """找出所有MinerU输出子目录，返回 {人名: 目录路径} 的字典"""
    dirs = {}
    for d in os.listdir(mineru_root):
        full_path = os.path.join(mineru_root, d)
        if not os.path.isdir(full_path):
            continue
        # 格式: {人名}.pdf-{uuid}
        match = re.match(r'^(.+)\.pdf-[a-f0-9\-]+$', d)
        if match:
            name = match.group(1)
            if os.path.exists(os.path.join(full_path, 'full.md')):
                dirs[name] = full_path
    return dirs
```

### 步骤3：提取每条笔录的元数据

对每个MinerU目录，读取 `content_list_v2.json` 提取笔录结构。

```python
import json

def extract_records_from_mineru(mineru_dir, person_name):
    """从MinerU输出中提取该人的所有笔录。

    一个人的MinerU目录可能包含多份笔录（多份讯问/询问笔录）。
    通过 level=1 的 title 识别每份笔录的起始页。

    返回: [{"type": "讯问笔录", "start_page": 1, "date": "2025-10-31", "pages_count": 7}, ...]
    """
    cl_path = os.path.join(mineru_dir, 'content_list_v2.json')
    with open(cl_path, 'r', encoding='utf-8') as f:
        pages = json.load(f)

    records = []
    for i, page_blocks in enumerate(pages):
        for block in page_blocks:
            if not isinstance(block, dict):
                continue
            if block.get('type') != 'title':
                continue
            content = block.get('content', {})
            if not isinstance(content, dict) or content.get('level') != 1:
                continue

            # 找到笔录标题
            title_parts = content.get('title_content', [])
            title_text = ''.join(
                p.get('content', '') for p in title_parts if p.get('type') == 'text'
            )

            # 提取笔录类型
            rec_type = ''
            if '讯问笔录' in title_text:
                rec_type = '讯问笔录'
            elif '询问笔录' in title_text:
                rec_type = '询问笔录'
            else:
                continue  # 非笔录标题，跳过

            # 提取日期：从该页的后续段落中找"时间"字段
            date_str = _extract_date_from_page(pages, i)

            records.append({
                'type': rec_type,
                'start_page': i + 1,  # 系统页码从1开始
                'date': date_str,
            })
            break  # 每页只取第一个level=1标题

    # 计算每份笔录的页数
    for j in range(len(records)):
        if j + 1 < len(records):
            records[j]['pages_count'] = records[j + 1]['start_page'] - records[j]['start_page']
        else:
            records[j]['pages_count'] = len(pages) - records[j]['start_page'] + 1

    return records


def _extract_date_from_page(pages, page_idx):
    """从指定页的内容块中提取日期。"""
    import re
    for block in pages[page_idx]:
        if not isinstance(block, dict):
            continue
        content = block.get('content', {})
        if not isinstance(content, dict):
            continue
        # 段落内容
        para_parts = content.get('paragraph_content', [])
        text = ''.join(p.get('content', '') for p in para_parts if isinstance(p, dict))
        # 匹配日期
        m = re.search(r'(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日', text)
        if m:
            return f'{m.group(1)}年{m.group(2)}月{m.group(3)}日'
    return ''
```

### 步骤4：构建全文内容和页码映射

读取 `full.md`，按笔录拆分内容，构建页码映射。

```python
def build_full_content_and_mapping(mineru_dir, records, toc_pages=None):
    """读取full.md，按笔录拆分，构建全文内容和页码映射。

    Args:
        mineru_dir: MinerU输出目录
        records: extract_records_from_mineru 的返回值
        toc_pages: 该人在证据卷中的页码范围列表，如 [(507,513)]，可选

    返回: 在records中添加 'full_content' 和 'page_mapping' 字段
    """
    md_path = os.path.join(mineru_dir, 'full.md')
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 找到所有页码标记的位置
    page_marker_pattern = re.compile(r'第\s*(\d+)\s*页\s*共\s*\d+\s*页')
    markers = []  # [(line_idx, page_num), ...]
    for i, line in enumerate(lines):
        m = page_marker_pattern.search(line)
        if m:
            markers.append((i, int(m.group(1))))

    # 按笔录拆分
    for j, rec in enumerate(records):
        start_page = rec['start_page']
        if j + 1 < len(records):
            end_page = records[j + 1]['start_page'] - 1
        else:
            end_page = len(lines)  # 到文件末尾

        # 找该笔录在full.md中的行范围
        # start_page对应的marker之前的行是起始
        # end_page对应的marker是结束
        rec_start_line = 0
        rec_end_line = len(lines) - 1

        for k, (marker_line, page_num) in enumerate(markers):
            if page_num == 1 and k == 0 and start_page == markers[0][1] if markers else False:
                rec_start_line = 0
            elif page_num == start_page:
                # 该页标记之前的行属于上一页，该标记开始属于本页
                # 但我们需要找这份笔录的起始：通常是level=1标题所在的行
                pass

        # 简化方案：用content_list_v2.json的页码来切分
        # full.md的内容顺序与content_list_v2.json的页面顺序一致
        # 按页码标记切分
        rec_markers = [(line, pg) for line, pg in markers
                       if rec['start_page'] <= pg <= rec['start_page'] + rec['pages_count'] - 1]

        if rec_markers:
            # 起始行：笔录第一页的内容开始位置（跳过标题行）
            first_marker_line = rec_markers[0][0]
            rec_start_line = _find_content_start(lines, 0, first_marker_line)
            # 结束行：最后一页标记之后的内容
            last_marker_line = rec_markers[-1][0]
            rec_end_line = _find_content_end(lines, last_marker_line)
        else:
            rec_start_line = 0
            rec_end_line = len(lines) - 1

        # 提取全文
        rec['full_content'] = ''.join(lines[rec_start_line:rec_end_line + 1])

        # 构建页码映射
        rec['page_mapping'] = []
        evidence_base = toc_pages[j][0] if toc_pages and j < len(toc_pages) else None

        for k, (marker_line, internal_pg) in enumerate(rec_markers):
            if k == 0:
                start = rec_start_line
            else:
                start = rec_markers[k - 1][0] + 1
            end = marker_line

            ev_page = (evidence_base + internal_pg - 1) if evidence_base else internal_pg
            rec['page_mapping'].append({
                'start_line': start,
                'end_line': end,
                'evidence_page': ev_page,
                'internal_page': internal_pg,
            })


def _find_content_start(lines, from_line, to_line):
    """找到第一个非空、非标题行。"""
    for i in range(from_line, to_line):
        line = lines[i].strip()
        if line and not line.startswith('#'):
            return i
    return from_line


def _find_content_end(lines, marker_line):
    """找到页码标记之后的最后一个有意义的行。"""
    for i in range(len(lines) - 1, marker_line, -1):
        if lines[i].strip():
            return i
    return marker_line
```

### 步骤5：生成JSON并写入

```python
def generate_case_json(case_name, case_id, mineru_root, records_dir, toc_data=None):
    """生成案件JSON并写入app的data目录。

    Args:
        case_name: 案件名称
        case_id: 案件编号
        mineru_root: MinerU输出根目录
        records_dir: 笔录目录路径（app中读取full.md时的基础路径）
        toc_data: {人名: [(起始页, 终止页), ...]} 的字典，可选
    """
    mineru_dirs = find_mineru_dirs(mineru_root)

    all_records = []
    record_id = 0

    for person_name, md_dir in sorted(mineru_dirs.items()):
        recs = extract_records_from_mineru(md_dir, person_name)
        toc_pages = toc_data.get(person_name) if toc_data else None

        build_full_content_and_mapping(md_dir, recs, toc_pages)

        for j, rec in enumerate(recs):
            record_id += 1
            # 文件路径：相对于records_dir
            rel_path = os.path.relpath(os.path.join(md_dir, 'full.md'), records_dir)

            # 印刷页码
            if toc_pages and j < len(toc_pages):
                start_p, end_p = toc_pages[j]
                printed_pages = f'{start_p}-{end_p}'
            else:
                printed_pages = ''

            # 引用格式
            cite = f'{person_name}于{rec["date"]}（证据卷P{printed_pages}）的{rec["type"]}中' if printed_pages else f'{person_name}的{rec["type"]}'

            # 内容摘要
            content = rec.get('full_content', '')
            summary = content[:200].replace('\n', ' ').strip() if content else ''

            all_records.append({
                '姓名': person_name,
                '笔录类型': rec['type'],
                '次数': '',
                '日期': rec['date'],
                '文件路径': rel_path,
                '内容摘要': summary,
                '印刷页码': printed_pages,
                'id': record_id,
                '引用格式': cite,
                '全文内容': content,
                '页码映射': rec.get('page_mapping', []),
            })

    case_data = {
        '案件名称': case_name,
        '案件编号': case_id,
        '笔录目录': records_dir,
        '笔录总数': len(all_records),
        '笔录列表': all_records,
    }

    # 写入app的data目录
    app_data_dir = r'<项目根目录>\project\data'
    os.makedirs(app_data_dir, exist_ok=True)
    output_path = os.path.join(app_data_dir, f'{case_name}.json')

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(case_data, f, ensure_ascii=False, indent=2)

    return output_path, len(all_records)
```

## 需要向用户收集的信息

| 信息 | 必须 | 说明 |
|------|------|------|
| 案件名称 | 是 | 如"某案" |
| 案件编号 | 是 | 如"A3300000000000000000000" |
| MinerU输出目录 | 是 | 如"D:\MinerU输出目录" |
| TOC页码数据 | 否 | 每人在证据卷中的页码范围，用于生成印刷页码和引用格式 |

## 验证 checklist

- [ ] JSON格式正确，可被app正常加载
- [ ] 每条笔录的 `文件路径` 指向实际存在的 `full.md`
- [ ] `全文内容` 不为空
- [ ] `姓名` 准确
- [ ] `笔录类型` 为"讯问笔录"或"询问笔录"
- [ ] `id` 从1开始连续递增
- [ ] `页码映射` 的 `start_line`/`end_line` 在全文范围内
- [ ] 启动app后能正常搜索到导入的笔录内容

## 依赖

- Python（标准库即可，无需额外包）
- MinerU输出目录（包含 `full.md` 和 `content_list_v2.json`）

## 输出

- JSON文件写入 `<项目根目录>\project\data\{案件名}.json`
