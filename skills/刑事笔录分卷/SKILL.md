---
name: 刑事笔录分卷
description: 处理刑事案件证据卷 PDF，按被讯问/询问人拆分为独立 PDF，提示用户用MinerU解析后插入空白页支持双面打印。
level: 2
---

# 刑事笔录分卷

处理刑事案件证据卷（如 `"证据卷.pdf"`、`"讯问笔录卷.pdf"` 等），将其中 **讯问笔录** 和 **询问笔录** 按被讯问/询问人拆分为独立 PDF，并插入空白页以支持双面打印。

## 触发关键词

- `"按人分卷"`、`"按人分PDF"`、`"拆分笔录"`
- `"双面打印"`、`"插空白页"`、`"奇数页对齐"`
- `"证据卷"`、`"讯问笔录"`、`"询问笔录"`、`"笔录分卷"`

## 核心原则

1. **只处理讯问笔录和询问笔录**，不处理其他文书类型（如权利义务告知书、鉴定意见、辨认笔录、搜查笔录、现场勘查笔录、照片等）。独立的身份信息文书（如"犯罪嫌疑人基本情况"表）不属于讯问/询问笔录，不得混入；但笔录正文开头的身份信息栏（姓名、性别、年龄、身份证号等）是每份笔录的标准格式，属于笔录本身，**不得排除**。
2. **空白页与分卷顺序铁律**：**必须先按人分卷，再在每人 PDF 内部独立插入空白页**。绝不能先合集插白再切分。
3. 所谓"奇数页"指**系统页码**（PDF文件中的物理位置，从 1 计），**不是**页面底部打印的视觉页码。
4. **扫描件PDF不能用PyMuPDF读文字**：证据卷通常是图片扫描件，`doc[i].get_text()` 只能读到水印，无法读到正文。分卷阶段只能靠目录或OCR；插空白页阶段必须依赖MinerU的OCR结果。

## 总体流程

```
原始证据卷 PDF
    │
    ▼
┌─────────────────────────┐
│ 阶段1：按人分卷          │  Skill 自主完成
│ （目录定位 或 内容扫描）  │
│ 产出：每人一份独立 PDF   │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ 阶段2：提示用户跑 MinerU │  Skill 停下来，等用户完成
│ （对每人PDF做OCR解析）    │
│ 产出：content_list_v2.json│
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ 阶段3：细分并插入空白页  │  Skill 读取MinerU结果后完成
│ （左到右偏移算法）        │
│ 产出：桌面双面打印PDF    │
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│ 阶段4：起诉意见书/起诉书 │  Skill 停下来，等用户完成
│ 解析（可选）              │  产出：结构化起诉书数据
└─────────────────────────┘
```

**严格按顺序执行，阶段之间不可跳过。阶段4为可选，用户可跳过。**

---

## 阶段1：按人分卷

从原始证据卷中，按被讯问/询问人拆分为独立PDF。

### 模式A：目录定位（首选）

通过证据卷目录自动定位所有讯问/询问笔录的页码范围。

**适用条件：**
- 证据卷前部有目录页
- 目录条目包含文书类型、被讯问/询问人姓名、页码范围

**步骤：**
1. 读取 PDF 前 10-20 页（目录区域），提取文本
2. 识别标题**包含** `"讯问笔录"` 或 `"询问笔录"` 的目录条目（如"第一次讯问笔录"）；排除标题含"辨认笔录""搜查笔录""现场勘查笔录"等排除词的条目
3. 从条目中提取：姓名、笔录类型、日期、页码范围（如 `108-112`）
4. 将 PDF 显示页码转换为系统页面索引（抽样建立页码映射关系）
5. 过滤非笔录条目（见"需排除的非笔录文书类型"）
6. 按姓名分组，确定每人的全部笔录页码区间（按原顺序排序）
7. 对每人新建空白文档，依次追加其每份笔录的所有页面，保存为 `{姓名}.pdf`

### 模式B：内容扫描（目录缺失时的备选）

**警告：此模式仅适用于文字型PDF。扫描件PDF（图片）无法用PyMuPDF读取文字，必须使用模式A。**

直接扫描 PDF 全部页面，通过页面内容特征识别笔录起始页。

**步骤：**
1. **严格识别起始页**：扫描所有页面，**只看每页顶部前 3-5 行非空文本**。只有顶部行以 `"讯问笔录"` 或 `"询问笔录"` 开头的页面才是笔录起始页。
   - **禁止搜索整页文本**——正文中间可能引用其他笔录的标题，整页搜索会导致严重误报。
   - 不得使用"包含'笔录'"的宽泛匹配——辨认笔录、搜查笔录等必须排除。
2. 确定每份笔录的结束页：下一个有效笔录起始页 - 1，中间的非笔录页跳过不纳入
3. 按姓名分组，确定每人的全部笔录页码区间
4. 对每人新建空白文档，依次追加其所有笔录页面，保存为 `{姓名}.pdf`

### 阶段1产出

```
输出目录/
├── 张三.pdf    （可能含多份笔录，但无空白页）
├── 李四.pdf
├── 王五.pdf
└── ...
```

---

## 阶段2：提示用户跑 MinerU

阶段1完成后，**Skill必须停下来**，提示用户对分卷PDF做MinerU解析。

**提示用户的内容：**

> 分卷完成，共 N 人，已保存到 `{输出目录}`。
>
> 下一步需要你用 MinerU 解析每份PDF，以便识别笔录首页位置来插入空白页。
> 请对 `{输出目录}` 下的所有PDF执行MinerU解析，解析结果放到 `{MinerU输出目录}`。
> 完成后告诉我，我继续处理空白页插入。

**等待用户确认MinerU完成后，再进入阶段3。**

---

## 阶段3：细分并插入空白页

读取MinerU的OCR结果，在每人PDF中识别多份笔录的真实首页，并插入空白页，确保每份笔录从奇数系统页开始。

### 阶段3输出位置

细分插页后的最终 PDF 必须复制或保存到桌面打印文件夹，方便律师直接双面打印阅卷：

```text
%USERPROFILE%\Desktop\案件笔录双面打印\{案件名称}\
├── 张三.pdf
├── 李四.pdf
├── 王五.pdf
└── ...
```

要求：
- 该目录只放阶段3完成后的最终双面打印版 PDF。
- 阶段1粗分 PDF、MinerU 解析结果、临时 PDF 不放入该目录。
- 如果目录不存在，必须自动创建。
- 保存完成后向用户汇报桌面文件夹路径和 PDF 数量。
- 这些 PDF 是给其他律师纸质阅卷使用的最终材料，命名必须自然清楚，优先使用 `{姓名}.pdf`。

### 数据源：MinerU 的 content_list_v2.json

MinerU输出目录结构：`{人名}.pdf-{uuid}/` 下有 `content_list_v2.json`、`full.md`、`images/` 等。

**定位笔录首页的方法：**
遍历 `content_list_v2.json` 的每一页（JSON数组的每个元素），检查内容块中是否有 `type=title` 且 `content.level=1` 的块。有则该页是一份新笔录的首页。

- **禁止使用 `full.md` 的 `#` 标题做正则匹配**——MinerU 的 markdown 中 `# 讯问笔录` 可能出现在页面内部（OCR从页面标题栏识别），导致误报。`content_list_v2.json` 的 `type=title` + `level=1` 是结构化标记，准确可靠。

### 算法：左到右偏移

**核心逻辑：**
1. 从 `content_list_v2.json` 提取该PDF所有笔录首页的系统页码（从1开始）
2. 从左到右遍历每份笔录首页，维护偏移量 `offset`（已插入的空白页数）
3. 对于系统页码 `sys_page`：
   - 如果 `(sys_page + offset)` 是**偶数** → 该页在输出PDF中是偶数系统页，需要在它前面插入空白页，`offset += 1`
   - 如果 `(sys_page + offset)` 是**奇数** → 该页已经是奇数系统页，不需要插入
4. 最后用PyMuPDF在对应的原始文档索引位置（`sys_page - 1`）**从后往前**插入空白页（从后往前插入是为了避免前面的插入改变后面的索引）

**为什么不能用"从后往前遍历笔录"的算法：**
当笔录首页在系统页 [18, 20, 22] 时：
- 从后往前遍历：在22前插空白→22变23(奇✓)，在20前插空白→20变21(奇✓)，在18前插空白→18变19(奇✓) — 但20和22已被18的插入推到20和22(偶✗)
- 左到右偏移：18是奇数不插，20+0=20偶数插空白→offset=1，22+1=23奇数不插 → 全部正确

### 参考实现

```python
import pymupdf
import json
import os


def get_title_pages_from_mineru(mineru_dir):
    """从MinerU的content_list_v2.json中提取笔录首页的系统页码（从1开始）"""
    cl_path = os.path.join(mineru_dir, "content_list_v2.json")
    with open(cl_path, "r", encoding="utf-8") as f:
        pages = json.load(f)

    title_pages = []
    for i, page_blocks in enumerate(pages):
        for block in page_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "title":
                continue
            content = block.get("content", {})
            if isinstance(content, dict) and content.get("level") == 1:
                title_pages.append(i + 1)
                break
    return title_pages


def insert_blanks_for_double_sided(pdf_path, title_pages):
    """在已拆分的单人PDF中插入空白页，确保每份笔录从奇数系统页开始。

    Args:
        pdf_path: PDF文件路径
        title_pages: 笔录首页的系统页码列表（从1开始）
    Returns:
        插入的空白页数
    """
    doc = pymupdf.open(pdf_path)

    # 左到右计算需要插入空白页的原始文档索引
    original_indices = []
    offset = 0
    for sys_page in title_pages:
        if (sys_page + offset) % 2 == 0:
            original_indices.append(sys_page - 1)
            offset += 1

    if not original_indices:
        doc.close()
        return 0

    # 从后往前在原始索引位置插入（避免索引偏移）
    for idx in reversed(original_indices):
        if idx > 0:
            w, h = doc[idx - 1].rect.width, doc[idx - 1].rect.height
        else:
            w, h = 595, 842
        doc.insert_page(idx, width=w, height=h)

    tmp_path = pdf_path + ".tmp"
    doc.save(tmp_path, deflate=True)
    doc.close()
    os.replace(tmp_path, pdf_path)

    return len(original_indices)
```

---

## 多Agent执行流程

大批量PDF处理（如30个以上分卷文件）建议采用多Agent并行：

### 阶段3并行处理

启动多个executor agent按文件大小分组并行插入空白页：

| 分组 | 页数范围 | 示例 |
|------|---------|------|
| Agent A | ≤10页 | 孙八、当事人X、当事人Y等 |
| Agent B | 11-40页 | 何某、王五、赵六等 |
| Agent C | >40页 | 张某、张三、陶某等 |

每个agent执行相同逻辑：
1. 从对应的MinerU输出目录加载 `content_list_v2.json`，提取笔录首页系统页码
2. 用左到右偏移算法确定需要插入空白页的原始索引
3. 从后往前在原始索引位置插入空白页
4. 先存临时文件再 `os.replace` 覆盖原文件
5. 将最终双面打印版 PDF 复制到桌面打印文件夹

### 验证

插入完成后，验证所有PDF：

- [ ] **奇数页检查**：模拟左到右偏移算法，确认输出PDF中每份笔录首页都在奇数系统页
- [ ] **页数检查**：输出PDF页数 = 原始页数 + 插入空白页数
- [ ] **计数检查**：每份PDF的笔录数量与MinerU识别的一致

---

## 页码体系说明

本场景涉及三种页码，**不可混淆**：

| 名称 | 含义 | 来源 | 用途 |
|------|------|------|------|
| 系统页码 | PDF文件中的物理位置，从1开始 | PyMuPDF `page.number + 1` | 双面打印奇偶判断 |
| 页面显示页码 | 扫描件上印刷的页码 | OCR识别 | **忽略**，不用于任何判断 |
| TOC页码 | 目录中记录的页码 | 目录OCR | 仅用于阶段1从大卷宗中切分 |

**阶段3只看系统页码，忽略页面显示页码。**

## 需排除的非笔录文书类型

从目录中识别到以下类型时 **跳过**：
- 权利义务告知书
- 鉴定意见 / 鉴定书
- 辨认笔录
- 搜查笔录
- 现场勘查笔录
- 提取笔录 / 扣押笔录
- 照片 / 图片
- 起诉意见书
- 证人通知书
- 犯罪嫌疑人诉讼权利义务告知书
- 独立的身份信息文书（如"犯罪嫌疑人基本情况"表，注意与笔录正文内的身份信息栏区分）

---

## 阶段4：起诉意见书/起诉书提取与解析（可选）

阶段3完成后，询问用户是否有文书卷PDF需要提取起诉意见书/起诉书，然后进行解析。此阶段为可选，用户可选择跳过。

### 4.0 提示用户提取起诉书PDF（可选）

> 分卷和空白页插入已全部完成。
>
> **如果你有文书卷PDF**（如`文书卷.pdf`、`诉讼文书卷.pdf`等），我可以自动从中提取起诉意见书或起诉书。
> 请提供文书卷PDF的路径，或说"跳过"。

如果用户提供了文书卷PDF路径：
- 调用「刑事文书提取」skill，自动识别目录中的起诉意见书/起诉书条目
- 解析页码范围，截取对应页面保存为独立PDF（默认到桌面）
- 汇报提取结果：文书类型、页码范围、保存路径

> 起诉意见书已提取到桌面，共7页（印刷页码128-134）。
>
> 下一步需要你用MinerU解析该PDF，以便提取结构化信息。

### 4.1 提示用户用MinerU解析

如果用户已有独立的起诉意见书/起诉书PDF（无论是从文书卷提取的，还是原本就有的）：

> 请将起诉意见书/起诉书的PDF用MinerU解析，解析结果放到指定目录。
> 完成后告诉我解析输出目录的路径，我继续提取结构化信息。

**等待用户确认MinerU解析完成，提供解析输出目录。**

### 4.2 读取MinerU输出

读取MinerU输出的 `full.md` 和 `content_list_v2.json`。

```python
import json
import os
import re

def parse_indictment(mineru_dir):
    """从MinerU输出中提取起诉书结构化信息。

    Args:
        mineru_dir: MinerU解析输出目录
    Returns:
        dict: 结构化起诉书数据
    """
    md_path = os.path.join(mineru_dir, 'full.md')
    cl_path = os.path.join(mineru_dir, 'content_list_v2.json')

    with open(md_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    result = {
        '原文': full_text,
        '案件编号': '',
        '案件名称': '',
        '犯罪嫌疑人': [],
        '指控罪名': [],
        '案件事实': '',
        '涉案金额': '',
        '证据列表': [],
        '适用法律': [],
    }

    # 提取案件编号
    m = re.search(r'案\s*号\s*[:：]\s*([A-Z\d\-]+)', full_text)
    if m:
        result['案件编号'] = m.group(1)

    # 提取案件名称
    m = re.search(r'([一-龥]+案)', full_text)
    if m:
        result['案件名称'] = m.group(1)

    # 提取犯罪嫌疑人列表
    # 匹配格式：犯罪嫌疑人XXX，男/女，X岁... 或 被告人XXX...
    person_patterns = [
        r'犯罪嫌疑人\s*[:：]?\s*([^，,。\n]{2,20})[，,]\s*(男|女)',
        r'被告人\s*[:：]?\s*([^，,。\n]{2,20})[，,]\s*(男|女)',
    ]
    for pattern in person_patterns:
        for m in re.finditer(pattern, full_text):
            name = m.group(1).strip()
            gender = m.group(2)
            if name and not any(p['姓名'] == name for p in result['犯罪嫌疑人']):
                result['犯罪嫌疑人'].append({'姓名': name, '性别': gender})

    # 提取指控罪名
    charge_patterns = [
        r'涉嫌\s*([一-龥]+罪)',
        r'犯\s*([一-龥]+罪)',
        r'指控.*?(?:犯|涉嫌)\s*([一-龥]+罪)',
    ]
    for pattern in charge_patterns:
        for m in re.finditer(pattern, full_text):
            charge = m.group(1)
            if charge not in result['指控罪名']:
                result['指控罪名'].append(charge)

    # 提取案件事实（经依法审查查明部分）
    fact_patterns = [
        r'经依法审查查明[：:](.*?)(?:认定上述事实|本院认为|上述事实)',
        r'经审查查明[：:](.*?)(?:认定上述事实|本院认为|上述事实)',
        r'现查明[：:](.*?)(?:认定上述事实|本院认为|上述事实)',
    ]
    for pattern in fact_patterns:
        m = re.search(pattern, full_text, re.DOTALL)
        if m:
            result['案件事实'] = m.group(1).strip()[:2000]  # 截取前2000字
            break

    # 提取涉案金额/数量
    amount_patterns = [
        r'(?:涉案|非法经营|销售金额|违法所得).*?(\d+[\d,\.]*\s*(?:万元|元|件|个|吨|克|千克))',
        r'(\d+[\d,\.]*\s*(?:万元|元))',
    ]
    for pattern in amount_patterns:
        m = re.search(pattern, full_text)
        if m:
            result['涉案金额'] = m.group(1)
            break

    # 提取证据列表
    evidence_section = re.search(r'(?:证据如下|证据有|列举如下)[：:](.*?)(?:本院认为|综上所述|依照)', full_text, re.DOTALL)
    if evidence_section:
        evidence_text = evidence_section.group(1)
        # 按序号或换行拆分证据条目
        evidence_items = re.split(r'\d+[\.、\s]', evidence_text)
        result['证据列表'] = [e.strip() for e in evidence_items if len(e.strip()) > 5][:20]

    # 提取适用法律条款
    law_patterns = [
        r'《([^》]+)》第[一二三四五六七八九十百零\d]+条',
        r'依照\s*《([^》]+)》',
        r'根据\s*《([^》]+)》',
    ]
    for pattern in law_patterns:
        for m in re.finditer(pattern, full_text):
            law = m.group(1)
            if law not in result['适用法律']:
                result['适用法律'].append(law)

    return result
```

### 4.3 写入案件JSON

将起诉书原文和结构化信息保存到案件JSON的"起诉书"字段。

```python
import json
import os

def save_indictment_to_case(case_name, indictment_data):
    """将起诉书数据写入案件JSON。

    Args:
        case_name: 案件名称
        indictment_data: parse_indictment的返回值
    """
    data_dir = r'<项目根目录>\project\data'
    json_path = os.path.join(data_dir, f'{case_name}.json')

    with open(json_path, 'r', encoding='utf-8') as f:
        case_data = json.load(f)

    case_data['起诉书'] = indictment_data

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(case_data, f, ensure_ascii=False, indent=2)

    return json_path
```

### 4.4 汇报结果

向用户汇报提取的结构化信息：
- 案件编号、案件名称
- 犯罪嫌疑人/被告人列表
- 指控罪名
- 案件事实摘要（前200字）
- 涉案金额
- 证据列表数量
- 适用法律条款

如果用户选择跳过阶段4：

> 已跳过起诉书解析。后续如需补充起诉书数据，可重新运行本skill或手动编辑案件JSON。

---

## 验证 checklist

### 阶段1-3
- [ ] **每份笔录起始页奇数检查**（关键）：用左到右偏移算法模拟，确认输出PDF中每份笔录首页的系统页码为奇数
- [ ] **流程顺序检查**（关键）：确认是先分卷→再跑MinerU→再插空白页，**不是**先合集插白再切分
- [ ] **算法检查**（关键）：确认使用左到右偏移算法，**不是**从后往前遍历笔录（从后往前对连续偶数页有bug）
- [ ] **数据源检查**（关键）：确认使用 MinerU 的 `content_list_v2.json`（`type=title` + `level=1`），**不是** `full.md` 的正则匹配
- [ ] 页数检查：输出PDF页数 = 原始页数 + 插入空白页数
- [ ] 计数检查：每份PDF的笔录数量与MinerU识别的一致
- [ ] 输出文件清单：汇报每人文件大小、页数、笔录份数、插入空白页数
- [ ] 清理临时文件并汇报清单

### 阶段4（如执行，含提取+解析）
- [ ] 起诉书PDF已用MinerU解析
- [ ] `full.md` 和 `content_list_v2.json` 可读
- [ ] 案件编号已提取（如文档中有）
- [ ] 犯罪嫌疑人/被告人列表非空
- [ ] 指控罪名已提取
- [ ] 案件事实已提取（前2000字）
- [ ] "起诉书"字段已写入案件JSON
- [ ] JSON保存成功，格式正确

## 依赖

- Python + PyMuPDF (`pip install pymupdf`)
- MinerU（阶段3必须，用于OCR解析扫描件PDF定位笔录首页）

## 输出规范

- 阶段1粗分个人 PDF 命名：`{姓名}.pdf`
- 阶段1输出目录：`按人分卷/`（或用户指定目录）
- 阶段3最终打印目录：`%USERPROFILE%\Desktop\案件笔录双面打印\{案件名称}\`
- 阶段3最终 PDF 命名：`{姓名}.pdf`
- 合集版命名：`证据卷_笔录_双面打印版.pdf`（且**不可**作为个人版的中间产物）

---

## 后续步骤

全部处理完成后，提示用户：

> 分卷和空白页插入已全部完成。
> 如已解析起诉书，数据已保存到案件JSON中。
> 下一步可选操作：
> 1. 导入检索库：使用 `/导入案件笔录检索app` 技能
> 2. 生成笔录摘要：使用 `/笔录摘要生成` 技能
> 3. 生成人物摘要：使用 `/人物摘要生成` 技能
> 4. 生成案情图谱：使用 `/案情图谱生成` 技能（需先完成摘要生成）
