---
name: 刑事文书提取
description: 从刑事案件的文书卷PDF中自动识别并提取起诉意见书或起诉书，保存为独立PDF文件。支持目录定位和页码映射。
level: 2
---

# 刑事文书提取

从刑事案件的**文书卷PDF**（如`文书卷.pdf`、`诉讼文书卷.pdf`等）中自动识别并提取**起诉意见书**或**起诉书**，保存为独立PDF文件。

与「刑事笔录分卷」skill联动：分卷完成后自动提示用户提取起诉意见书/起诉书。

## 触发关键词

- `"提取起诉意见书"`、`"提取起诉书"`、`"截取起诉书"`
- `"刑事文书提取"`、`"从文书卷提取"`、`"文书提取"`
- `"起诉意见书在哪"`、`"找起诉书"`、`"定位起诉意见书"`

## 核心功能

1. **目录定位**：读取PDF前几页目录，搜索"起诉意见书"或"起诉书"条目
2. **页码解析**：从目录条目提取页码范围（如`128-134`）
3. **系统页码映射**：将印刷页码映射到PDF系统页码（处理封面/目录造成的偏移）
4. **精确截取**：截取对应页面保存为独立PDF
5. **内容验证**：验证截取的首页和末页确实包含起诉意见书/起诉书内容

## 输入

| 参数 | 必须 | 说明 |
|------|------|------|
| 文书卷PDF路径 | 是 | 如`C:\Users\...\Desktop\文书卷.pdf` |
| 输出路径 | 否 | 默认保存到桌面，文件名为`起诉意见书.pdf`或`起诉书.pdf` |
| 文书类型 | 否 | `"起诉意见书"`（公安机关移送检察院）或`"起诉书"`（检察院移送法院），自动识别 |

## 工作流程

### 步骤1：获取文书卷PDF路径

询问用户提供文书卷PDF的完整路径。常见文件名：
- `文书卷.pdf`
- `诉讼文书卷.pdf`
- `程序卷.pdf`
- `法律文书卷.pdf`

### 步骤2：读取PDF并提取目录

```python
import fitz  # pymupdf
import re
import os

def extract_table_of_contents(pdf_path):
    """从文书卷PDF中提取目录，搜索起诉意见书/起诉书条目。

    Returns:
        list: [{"title": "...", "page_range": "128-134", "sys_start": 135, "sys_end": 141}, ...]
    """
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count

    # 目录通常在PDF的前10页内
    toc_pages = []
    for i in range(min(10, total_pages)):
        text = doc[i].get_text()
        # 搜索起诉意见书或起诉书
        if '起诉意见书' in text or '起诉书' in text:
            toc_pages.append((i, text))

    results = []
    for page_idx, text in toc_pages:
        lines = text.split('\n')
        for line in lines:
            # 匹配目录条目格式：... 起诉意见书 ... 128-134
            # 或：... 起诉书 ... 98-105
            if '起诉意见书' in line or '起诉书' in line:
                # 提取页码范围（如 128-134）
                range_match = re.search(r'(\d+)[-\s~]+(\d+)', line)
                if range_match:
                    start_page = int(range_match.group(1))
                    end_page = int(range_match.group(2))

                    # 映射印刷页码到系统页码
                    sys_start, sys_end = map_printed_to_system(
                        doc, start_page, end_page
                    )

                    doc_type = '起诉意见书' if '起诉意见书' in line else '起诉书'
                    results.append({
                        'type': doc_type,
                        'title': line.strip(),
                        'printed_range': f'{start_page}-{end_page}',
                        'sys_start': sys_start,
                        'sys_end': sys_end,
                        'page_count': sys_end - sys_start + 1,
                    })

    doc.close()
    return results
```

### 步骤3：印刷页码到系统页码映射

```python
def map_printed_to_system(doc, printed_start, printed_end):
    """将印刷页码映射到PDF系统页码。

    策略：扫描PDF中间区域，找到包含印刷页码标记的页面，
    建立印刷页码→系统页码的映射关系。

    Returns:
        (sys_start, sys_end)
    """
    # 建立印刷页码到系统页码的映射
    page_map = {}  # printed_page -> sys_page

    for sys_page in range(doc.page_count):
        text = doc[sys_page].get_text()
        # 搜索页面底部的印刷页码（通常在角落）
        # 格式如单独一行的数字，或"第 X 页"
        lines = text.strip().split('\n')
        for line in lines[-5:]:  # 看后5行
            line = line.strip()
            # 纯数字可能是页码
            if line.isdigit():
                pg = int(line)
                if 1 <= pg <= 999 and pg not in page_map:
                    page_map[pg] = sys_page + 1  # 转为1-based

    # 如果找不到映射，使用启发式估算
    # 通常系统页码 = 印刷页码 + 偏移量（封面+目录页数）
    if printed_start in page_map:
        sys_start = page_map[printed_start]
    else:
        # 启发式：找最接近的已知映射推算偏移
        if page_map:
            sample_pg = min(page_map.keys())
            sample_sys = page_map[sample_pg]
            offset = sample_sys - sample_pg
            sys_start = printed_start + offset
        else:
            # 默认偏移：系统页码 ≈ 印刷页码 + 7（常见情况）
            sys_start = printed_start + 7

    if printed_end in page_map:
        sys_end = page_map[printed_end]
    else:
        sys_end = sys_start + (printed_end - printed_start)

    # 边界检查
    sys_start = max(1, min(sys_start, doc.page_count))
    sys_end = max(sys_start, min(sys_end, doc.page_count))

    return sys_start, sys_end
```

### 步骤4：验证并截取

```python
def extract_and_verify(doc, sys_start, sys_end, expected_type):
    """截取指定页面并验证内容。

    Args:
        doc: fitz.Document
        sys_start: 系统起始页码（1-based）
        sys_end: 系统结束页码（1-based）
        expected_type: "起诉意见书" 或 "起诉书"

    Returns:
        (verified_start, verified_end) 或 None（验证失败）
    """
    # 验证首页
    first_text = doc[sys_start - 1].get_text()
    # 首页应包含标题相关文字
    has_title = expected_type in first_text or '犯罪嫌疑人' in first_text

    # 验证末页
    last_text = doc[sys_end - 1].get_text()
    # 末页通常有页码标记或落款
    has_end_marker = any(kw in last_text for kw in ['公安局', '人民检察院', '此页无正文'])

    # 如果首页验证失败，尝试在附近页面搜索
    if not has_title:
        for offset in range(-3, 4):
            test_page = sys_start - 1 + offset
            if 0 <= test_page < doc.page_count:
                test_text = doc[test_page].get_text()
                if expected_type in test_text:
                    sys_start = test_page + 1
                    has_title = True
                    break

    if not has_title:
        return None

    return sys_start, sys_end
```

### 步骤5：保存PDF

```python
def save_extracted_pdf(src_path, sys_start, sys_end, output_path):
    """截取指定页面保存为新的PDF。"""
    src = fitz.open(src_path)
    dst = fitz.open()

    for i in range(sys_start - 1, sys_end):
        dst.insert_pdf(src, from_page=i, to_page=i)

    dst.save(output_path, deflate=True)
    dst.close()
    src.close()

    return output_path
```

### 完整执行流程

```python
def extract_indictment(pdf_path, output_path=None):
    """从文书卷PDF中提取起诉意见书/起诉书。

    Args:
        pdf_path: 文书卷PDF路径
        output_path: 输出路径（可选，默认桌面）

    Returns:
        dict: 提取结果
    """
    import os

    if not output_path:
        desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
        output_path = os.path.join(desktop, '起诉意见书.pdf')

    # 步骤1-2：提取目录
    results = extract_table_of_contents(pdf_path)

    if not results:
        return {'success': False, 'error': '未在目录中找到起诉意见书或起诉书'}

    # 优先选择起诉意见书，其次是起诉书
    target = None
    for r in results:
        if r['type'] == '起诉意见书':
            target = r
            break
    if not target:
        target = results[0]

    # 更新输出文件名
    base, ext = os.path.splitext(output_path)
    output_path = f"{base.replace('起诉意见书', target['type']).replace('起诉书', target['type'])}.{ext.lstrip('.')}"
    output_path = os.path.join(os.path.dirname(output_path), f"{target['type']}.pdf")

    # 步骤3-4：验证
    doc = fitz.open(pdf_path)
    verified = extract_and_verify(doc, target['sys_start'], target['sys_end'], target['type'])
    doc.close()

    if not verified:
        return {'success': False, 'error': '验证失败：无法在预期位置找到文书内容'}

    v_start, v_end = verified

    # 步骤5：保存
    save_extracted_pdf(pdf_path, v_start, v_end, output_path)

    return {
        'success': True,
        'type': target['type'],
        'output_path': output_path,
        'printed_range': target['printed_range'],
        'sys_range': f'{v_start}-{v_end}',
        'page_count': v_end - v_start + 1,
    }
```

## 与刑事笔录分卷的联动

在「刑事笔录分卷」skill的**阶段3完成后**（插入空白页全部完成），自动提示用户：

> 分卷和空白页插入已全部完成。
>
> **下一步：提取起诉意见书/起诉书**
> 如果你有文书卷PDF（如"文书卷.pdf"），我可以帮你从中自动提取起诉意见书或起诉书。
> 请提供文书卷PDF的路径，或说"跳过"。

如果用户提供路径，调用本skill执行提取。提取完成后提示：

> 起诉意见书已提取到桌面（7页，系统页码135-141，印刷页码128-134）。
> 如需解析其内容，请用MinerU解析该PDF，然后使用「刑事笔录分卷」阶段4功能导入。

## 验证 checklist

- [ ] PDF文件存在且可读
- [ ] 目录中包含"起诉意见书"或"起诉书"条目
- [ ] 页码范围已正确解析
- [ ] 系统页码映射合理（偏移量通常在5-15页之间）
- [ ] 截取的首页包含起诉意见书/起诉书标题或犯罪嫌疑人信息
- [ ] 截取的末页包含落款或"此页无正文"等结束标记
- [ ] 输出PDF页数与目录标注一致
- [ ] 输出文件可正常打开

## 依赖

- Python + PyMuPDF (`pip install pymupdf`)

## 输出

- 独立PDF文件（默认保存到桌面）
- 提取结果汇报：文书类型、页码范围、文件路径
