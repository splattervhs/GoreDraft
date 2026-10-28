"""PDF output for screenplays, novels and reports."""
from __future__ import annotations

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import (QFont, QFontMetricsF, QPageLayout, QPageSize, QPainter,
                           QPdfWriter, QTextBlockFormat, QTextCursor, QTextDocument)

from .editor import block_formats, script_font
from .model import NON_PRINTING, ScriptData

DPI = 300


def _writer(path: str, page: str, title: str) -> QPdfWriter:
    w = QPdfWriter(path)
    w.setResolution(DPI)
    w.setTitle(title)
    w.setCreator("GORE DRAFT")
    size = QPageSize(QPageSize.A4 if page.upper() == "A4" else QPageSize.Letter)
    w.setPageLayout(QPageLayout(size, QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    return w


def _page_px(w: QPdfWriter):
    r = w.pageLayout().fullRectPixels(DPI)
    return r.width(), r.height()


def _paint_pages(painter: QPainter, writer: QPdfWriter, doc: QTextDocument,
                 left: float, top: float, font: QFont, first_page_number=1,
                 number_first=False, started=False):
    """Draw a paginated QTextDocument page by page with page numbers."""
    pw, ph = _page_px(writer)
    size = doc.pageSize()
    pages = doc.pageCount()
    for i in range(pages):
        if started or i:
            writer.newPage()
        started = True
        painter.save()
        painter.translate(left, top - i * size.height())
        clip = QRectF(0, i * size.height(), size.width(), size.height())
        doc.drawContents(painter, clip)
        painter.restore()
        num = first_page_number + i
        if num > 1 or number_first:
            painter.setFont(font)
            painter.drawText(QRectF(0, DPI * 0.5, pw - DPI * 1.0, DPI * 0.3),
                             Qt.AlignRight | Qt.AlignVCenter, f"{num}.")
    return started


def _title_page(painter: QPainter, writer: QPdfWriter, title: dict, font: QFont):
    pw, ph = _page_px(writer)
    painter.setFont(font)
    fm = QFontMetricsF(font, writer)
    lh = fm.lineSpacing()
    y = ph * 0.36
    t = (title.get("title") or "").upper()
    if t:
        bold = QFont(font)
        bold.setBold(True)
        bold.setUnderline(True)
        painter.setFont(bold)
        painter.drawText(QRectF(DPI, y, pw - 2 * DPI, lh * 3), Qt.AlignHCenter | Qt.TextWordWrap, t)
        painter.setFont(font)
        y += lh * 4
    for key, default in (("credit", "Written by"), ("author", ""), ("source", "")):
        v = title.get(key) or (default if title.get("author") and key == "credit" else "")
        if v:
            painter.drawText(QRectF(DPI, y, pw - 2 * DPI, lh * 3), Qt.AlignHCenter | Qt.TextWordWrap, v)
            y += lh * 2
    bottom = ph - DPI * 1.0
    left_block = "\n".join(x for x in (title.get("draft", ""), title.get("copyright", "")) if x)
    if left_block:
        painter.drawText(QRectF(DPI * 1.5, bottom - lh * 6, pw / 2, lh * 6),
                         Qt.AlignLeft | Qt.AlignBottom | Qt.TextWordWrap, left_block)
    if title.get("contact"):
        painter.drawText(QRectF(pw / 2, bottom - lh * 6, pw / 2 - DPI, lh * 6),
                         Qt.AlignRight | Qt.AlignBottom | Qt.TextWordWrap, title["contact"])


def _margin_scale(writer, font) -> float:
    """Qt may scale block margins depending on the paint device's DPI. Measure
    it once so a blank line comes out at exactly 1/6 inch on every platform."""
    probe = QTextDocument()
    probe.documentLayout().setPaintDevice(writer)
    probe.setDefaultFont(font)
    probe.setDocumentMargin(0)
    c = QTextCursor(probe)
    c.insertText("A")
    bf = QTextBlockFormat()
    bf.setTopMargin(100)
    c.insertBlock(bf)
    c.insertText("B")
    lay = probe.documentLayout()
    b1 = probe.firstBlock()
    b2 = b1.next()
    r1, r2 = lay.blockBoundingRect(b1), lay.blockBoundingRect(b2)
    gap = r2.top() - r1.bottom()
    return max(0.01, gap / 100.0)


def export_screenplay(sd: ScriptData, path: str, page="A4", title_page=True) -> int:
    writer = _writer(path, page, sd.title.get("title", "Screenplay"))
    pw, ph = _page_px(writer)
    font = script_font(12)
    fm = QFontMetricsF(font, writer)
    inch = DPI
    line_h = (DPI / 6) / _margin_scale(writer, font)  # one blank line = 1/6 inch
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(writer)
    doc.setDefaultFont(font)
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(pw - 2.5 * inch, ph - 2.0 * inch))
    c = QTextCursor(doc)
    first = True
    for p in sd.paras:
        if p["e"] in NON_PRINTING or not p["t"].strip():
            continue
        bf, cf = block_formats(p["e"], inch, line_h, first=first, pt=12)
        if first:
            c.setBlockFormat(bf)
            c.setBlockCharFormat(cf)
        else:
            c.insertBlock(bf, cf)
        c.insertText(p["t"], cf)
        first = False
    painter = QPainter(writer)
    started = False
    if title_page and sd.title.get("title"):
        _title_page(painter, writer, sd.title, font)
        started = True
    _paint_pages(painter, writer, doc, 1.5 * inch, 1.0 * inch, font, started=started)
    painter.end()
    return doc.pageCount()


def export_novel(title: dict, markdown: str, path: str, page="A4") -> int:
    writer = _writer(path, page, title.get("title", "Manuscript"))
    pw, ph = _page_px(writer)
    font = QFont()
    font.setFamilies(["Georgia", "Libre Baskerville", "DejaVu Serif", "Times New Roman"])
    font.setPointSize(12)
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(writer)
    doc.setDefaultFont(font)
    doc.setMarkdown(markdown)
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(pw - 2 * DPI, ph - 2 * DPI))
    painter = QPainter(writer)
    started = False
    if title.get("title"):
        _title_page(painter, writer, {"title": title.get("title"), "author": title.get("author", ""),
                                      "credit": "by" if title.get("author") else "",
                                      "contact": title.get("contact", "")}, font)
        started = True
    _paint_pages(painter, writer, doc, DPI, DPI, font, started=started)
    painter.end()
    return doc.pageCount()


def export_html(html: str, path: str, page="A4", title="Report") -> int:
    writer = _writer(path, page, title)
    pw, ph = _page_px(writer)
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(writer)
    f = script_font(10)
    doc.setDefaultFont(f)
    doc.setHtml(html)
    doc.setDocumentMargin(0)
    doc.setPageSize(QSizeF(pw - 1.5 * DPI, ph - 1.5 * DPI))
    painter = QPainter(writer)
    _paint_pages(painter, writer, doc, 0.75 * DPI, 0.9 * DPI, f, number_first=True)
    painter.end()
    return doc.pageCount()
