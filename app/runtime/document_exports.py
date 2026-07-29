"""Deterministic document exports for answers and editable artifacts."""

from __future__ import annotations

import re
import textwrap
from html import escape
from io import BytesIO
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile


def answer_with_references(content: str, evidence: list[dict[str, Any]]) -> str:
    """Replace internal evidence IDs and append a readable source list."""
    unique: list[dict[str, Any]] = []
    indexes: dict[str, int] = {}
    for item in evidence:
        evidence_id = str(item.get("id") or "")
        if not evidence_id or evidence_id in indexes:
            continue
        indexes[evidence_id] = len(unique) + 1
        unique.append(item)
    if not unique:
        return content

    body = re.sub(
        r"\[(ev_[0-9a-f]+)\]",
        lambda match: f"[{indexes[match.group(1)]}]" if match.group(1) in indexes else match.group(0),
        content,
    )
    used_ids = {
        marker
        for marker in re.findall(r"\[(ev_[0-9a-f]+)\]", content)
        if marker in indexes
    }
    references = [item for item in unique if str(item.get("id")) in used_ids] or unique
    lines = ["", "", "## 参考来源", ""]
    for item in references:
        index = indexes[str(item.get("id"))]
        title = str(item.get("title") or "未命名来源").replace("\n", " ")
        source = str(item.get("source") or "")
        locator = str(item.get("locator") or "")
        excerpt = " ".join(str(item.get("excerpt") or "").split())
        label = f"[{title}]({source})" if source.startswith(("http://", "https://")) else title
        suffix = f"（{locator}）" if locator else ""
        lines.append(f"{index}. {label}{suffix}")
        if excerpt:
            lines.append(f"   > {excerpt}")
    return body.rstrip() + "\n".join(lines)


def render_pdf(content: str, title: str = "OphAgent 文档") -> bytes:
    import fitz

    document = fitz.open()
    page = document.new_page()
    margin = 48
    y = margin
    line_height = 16
    page.insert_text((margin, y), title, fontsize=15, fontname="china-s")
    y += 26
    for raw_line in content.splitlines() or [""]:
        lines = textwrap.wrap(
            raw_line,
            width=52,
            replace_whitespace=False,
            drop_whitespace=False,
        ) or [""]
        for line in lines:
            if y > page.rect.height - margin:
                page = document.new_page()
                y = margin
            page.insert_text((margin, y), line, fontsize=10.5, fontname="china-s")
            y += line_height
        y += 3
    payload = document.tobytes(garbage=4, deflate=True)
    document.close()
    return payload


def render_docx(content: str, title: str = "OphAgent 文档") -> bytes:
    """Create a standards-compliant minimal DOCX without a runtime dependency."""

    paragraphs = [title, *content.splitlines()]

    def paragraph(text: str, *, heading: bool = False) -> str:
        properties = "<w:pPr><w:pStyle w:val=\"Title\"/></w:pPr>" if heading else ""
        return (
            f"<w:p>{properties}<w:r><w:t xml:space=\"preserve\">"
            f"{escape(text)}</w:t></w:r></w:p>"
        )

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(
            paragraph(text, heading=index == 0)
            for index, text in enumerate(paragraphs)
        )
        + (
            "<w:sectPr><w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
            "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\"/>"
            "</w:sectPr></w:body></w:document>"
        )
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", relationships)
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def render_jpg(content: str, title: str = "OphAgent 文档") -> bytes:
    import fitz

    source = fitz.open(stream=render_pdf(content, title), filetype="pdf")
    page = source[0]
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    payload = pixmap.tobytes("jpeg", jpg_quality=92)
    source.close()
    return payload
