---
name: paper-translation-to-docx
description: 将英文技术/学术论文PDF翻译为中文Word文档的完整流程。含PDF文本提取、分章节翻译、结构化Word构建、文件发送与清理。
tags: [translation, pdf, word, chinese, paper]
---

# 论文PDF → 中文Word文档翻译流程

## 触发条件

用户要求翻译一篇英文技术论文或学术论文PDF为中文，并生成Word文档。

## 前置条件

- `pypdf` 和 `python-docx` 可用（本环境中 `python-docx` 已预装，`pypdf` 可通过 `python3 -m pip install --user pypdf` 安装）
- 原始PDF已下载到服务器

## 步骤

### 1. 提取PDF全文

```python
from pypdf import PdfReader

reader = PdfReader("/path/to/paper.pdf")
full_text = ""
for i, page in enumerate(reader.pages):
    text = page.extract_text()
    full_text += f"\n\n=== PAGE {i+1} ===\n\n{text}"

# 写入临时文件以便分段翻译
with open("/tmp/paper_raw.txt", "w", encoding="utf-8") as f:
    f.write(full_text)
```

### 2. 分析结构并规划分节

查看提取的文本，识别出论文的主要章节结构（摘要、引言、相关工作、方法、实验、结论、参考文献等），按章节划分翻译任务。

### 3. 逐章节翻译（通过模型）

将每个章节的内容逐段交给模型翻译。翻译要点：
- **保持学术术语一致性**（如 MoE → 混合专家模型，attention → 注意力机制）
- **保留数字、公式引用、图表编号**原样
- **参考文献格式**保持原文引用方式（如 [1], Smith et al. 2024）
- 长段落分段翻译后拼接，注意段落之间的衔接

### 4. 构建Word文档（python-docx）

```python
from docx import Document
from docx.shared import Pt, Inches, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn

doc = Document()

# 设置默认字体（中文字体支持）
style = doc.styles['Normal']
font = style.font
font.name = '宋体'
style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

# 封面/标题
title_para = doc.add_paragraph()
title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title_para.add_run(original_title + " 中文翻译版")
run.bold = True
run.font.size = Pt(22)

# 副标题/译者信息
subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run(f"翻译自: {original_title}")
run.font.size = Pt(11)
run.font.color.rgb = RGBColor(100, 100, 100)

# 各章节 - 用 Heading 样式
doc.add_heading('摘要', level=1)
doc.add_paragraph(translated_abstract)

doc.add_heading('1. 引言', level=1)
# ... 逐段

# 保存
doc.save(output_path)
```

### 5. 通过Discord发送文件

使用 Hermes 的文件发送机制（通常通过系统工具或API）将生成的Word文档发给用户。

### 6. 清理

```bash
# 清理中间文件
rm -f /tmp/paper_raw.txt /tmp/doc_part*.py
rm -f /path/to/cache/doc_*.pdf  # 清理PDF缓存
rm -f /path/to/translated_*.docx  # 清理分步文档

# 保留Python库不卸载
```

## 注意事项

### PDF提取问题
- `pypdf` 提取的文本可能丢失格式（粗体/斜体、表格、公式），需要手动补全
- 一些PDF的列布局会导致阅读顺序错乱，可视情况手动重排

### 翻译质量
- 模型翻译学术论文效果较好，但专业术语（尤其是缩写）首次出现时应给出全称中文
- 对于数学公式、代码片段、表格数据，建议保留原文
- 参考文献条目保持原文格式，不翻译人名和期刊名

### Word文档格式
- 中文文档推荐用宋体/NSimSun 作为正文，标题用黑体
- 段落首行缩进用 `paragraph.paragraph_format.first_line_indent = Cm(0.74)`
- 行距建议 1.5 倍

### 文件大小
- 长论文（50+页）生成的Word文档可能较大（数MB），确保发送渠道支持

### 文件发送
- 使用 MEDIA 标签发送文件时，注意检查路径是否正确、文件是否可读
- 如果 MEDIA 标签未能成功发送，可考虑直接通过 Discord API 或其他机制传输
- 发送后务必请用户确认是否成功收到

## 验证步骤

1. 打开生成的Word文档，检查所有章节是否完整
2. 抽查翻译质量，尤其是术语和数字是否准确
3. 确认参考文献清单完整
4. 确认无乱码
