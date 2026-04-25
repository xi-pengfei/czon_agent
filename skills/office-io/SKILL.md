---
name: office-io
description: Read and write common office files including Word docx, Excel xlsx, PDF, PowerPoint pptx, Markdown, text, and CSV. Use when the user asks to inspect, extract, summarize, create, or modify office documents.
---

# Office IO Skill

Use this skill for common office documents.

Supported MVP formats:
- Read: `.md`, `.txt`, `.csv`, `.docx`, `.xlsx`, `.pdf`, `.pptx`
- Write: `.md`, `.txt`, `.csv`, `.docx`, `.xlsx`, `.pptx`, simple text `.pdf`

Older binary formats such as `.doc`, `.xls`, and `.ppt` are not supported by this MVP. Ask the user to convert them to `.docx`, `.xlsx`, or `.pptx`.

## Commands

Inspect a file:

    bash: python skills/office-io/scripts/office.py inspect uploads/example.docx

Read a file as JSON/text:

    bash: python skills/office-io/scripts/office.py read uploads/example.docx

Write Markdown or text:

    bash: python skills/office-io/scripts/office.py write-md workspace/report.md --text "内容"

Write Word:

    bash: python skills/office-io/scripts/office.py write-docx workspace/report.docx --text "标题\n\n正文"

Write Excel from JSON:

    bash: python skills/office-io/scripts/office.py write-xlsx workspace/table.xlsx --json '[{"姓名":"张三","薪资":18000},{"姓名":"李四","薪资":22000}]'

Write PowerPoint from JSON:

    bash: python skills/office-io/scripts/office.py write-pptx workspace/slides.pptx --json '[{"title":"第一页","bullets":["要点一","要点二"]}]'

Write simple text PDF:

    bash: python skills/office-io/scripts/office.py write-pdf workspace/report.pdf --text "标题\n\n正文"

## Rules

- Always run the script and summarize its stdout. Do not merely tell the user the command.
- Use `inspect` first when the file type or path is unclear.
- Use exact uploaded/local paths from the user message.
- For PDF, this skill reads text and can generate a simple text PDF. It does not perform precise editing of existing PDF layout.
- For mutating writes, use `workspace/` as the output directory.
- After creating or modifying a workspace file, tell the user the output path and a download link like `[下载文件](/download/report.docx)`.
