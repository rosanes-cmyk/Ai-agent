"""Build the two Twin Home Buyer call SOPs as PDFs.

Two audiences, two documents, one system. The team's copy answers "what
do I do when the phone rings"; the admin copy answers "where is that
set and what do I change". Anything a rep cannot act on is kept out of
their copy - an SOP people skim is worth more than one that is complete.
"""

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, Frame, KeepTogether, ListFlowable, ListItem,
    PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#1a1a1a")
MUTED = colors.HexColor("#6b6b6b")
RULE = colors.HexColor("#d9d9d9")
BAND = colors.HexColor("#f4f4f2")
ACCENT = colors.HexColor("#1f5c3d")
WARN = colors.HexColor("#8a4b00")

BASE = getSampleStyleSheet()


def styles():
    s = {}
    s["title"] = ParagraphStyle(
        "title", parent=BASE["Title"], fontName="Helvetica-Bold",
        fontSize=24, leading=28, textColor=INK, alignment=TA_LEFT,
        spaceAfter=4,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=BASE["Normal"], fontName="Helvetica",
        fontSize=11.5, leading=15, textColor=MUTED, spaceAfter=18,
    )
    s["h1"] = ParagraphStyle(
        "h1", parent=BASE["Heading1"], fontName="Helvetica-Bold",
        fontSize=15, leading=19, textColor=ACCENT,
        spaceBefore=20, spaceAfter=8,
    )
    s["h2"] = ParagraphStyle(
        "h2", parent=BASE["Heading2"], fontName="Helvetica-Bold",
        fontSize=11.5, leading=15, textColor=INK,
        spaceBefore=12, spaceAfter=5,
    )
    s["body"] = ParagraphStyle(
        "body", parent=BASE["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15.5, textColor=INK, spaceAfter=7,
    )
    s["lead"] = ParagraphStyle(
        "lead", parent=s["body"], fontSize=11.5, leading=17,
        spaceAfter=10,
    )
    s["item"] = ParagraphStyle(
        "item", parent=s["body"], spaceAfter=3,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=BASE["Normal"], fontName="Helvetica",
        fontSize=9.5, leading=13, textColor=INK,
    )
    s["cellhead"] = ParagraphStyle(
        "cellhead", parent=s["cell"], fontName="Helvetica-Bold",
    )
    s["note"] = ParagraphStyle(
        "note", parent=s["body"], fontSize=10, leading=14.5,
        textColor=WARN, leftIndent=10, spaceBefore=4, spaceAfter=10,
    )
    s["foot"] = ParagraphStyle(
        "foot", parent=BASE["Normal"], fontName="Helvetica",
        fontSize=8, textColor=MUTED,
    )
    return s


S = styles()


def para(text, key="body"):
    return Paragraph(text, S[key])


def bullets(items, numbered=False):
    return ListFlowable(
        [ListItem(para(i, "item"), leftIndent=16) for i in items],
        bulletType="1" if numbered else "bullet",
        bulletFontName="Helvetica", bulletFontSize=9.5,
        leftIndent=18, bulletColor=ACCENT, spaceAfter=8,
    )


def table(rows, widths):
    data = [[Paragraph(c, S["cellhead"]) for c in rows[0]]] + [
        [Paragraph(c, S["cell"]) for c in r] for r in rows[1:]
    ]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BAND),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def callout(title, body):
    """A boxed aside. Used sparingly - one per page at most."""
    inner = [Paragraph("<b>%s</b>" % title, S["cell"]),
             Spacer(1, 3),
             Paragraph(body, S["cell"])]
    t = Table([[inner]], colWidths=[6.5 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BAND),
        ("LINEBEFORE", (0, 0), (0, -1), 3, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 10)])


def flow_steps(steps):
    """A call path drawn as stacked boxes, so it reads without a legend."""
    rows = []
    for i, (label, detail) in enumerate(steps):
        cell = [Paragraph("<b>%s</b>" % label, S["cell"])]
        if detail:
            cell.append(Paragraph(
                '<font color="#6b6b6b">%s</font>' % detail, S["cell"]))
        rows.append([cell])
        if i < len(steps) - 1:
            rows.append([Paragraph(
                '<font color="#1f5c3d" size="11"><b>&#9660;</b></font>',
                S["cell"])])

    t = Table(rows, colWidths=[4.6 * inch], hAlign="LEFT")
    style = [
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for r in range(len(rows)):
        if r % 2 == 0:
            style += [
                ("BACKGROUND", (0, r), (0, r), BAND),
                ("BOX", (0, r), (0, r), 0.6, RULE),
                ("TOPPADDING", (0, r), (0, r), 8),
                ("BOTTOMPADDING", (0, r), (0, r), 8),
            ]
        else:
            style += [
                ("TOPPADDING", (0, r), (0, r), 1),
                ("BOTTOMPADDING", (0, r), (0, r), 1),
                ("ALIGN", (0, r), (0, r), "CENTER"),
            ]
    t.setStyle(TableStyle(style))
    return KeepTogether([Spacer(1, 4), t, Spacer(1, 12)])


def build(path, title, subtitle, story_body, footer):
    doc = BaseDocTemplate(
        path, pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.85 * inch, bottomMargin=0.85 * inch,
        title=title, author="Twin Home Buyer",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin,
                  doc.width, doc.height, id="f")

    def decorate(canvas, d):
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        y = doc.bottomMargin - 16
        canvas.line(doc.leftMargin, y, doc.leftMargin + doc.width, y)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, y - 12, footer)
        canvas.drawRightString(doc.leftMargin + doc.width, y - 12,
                               "Page %d" % canvas.getPageNumber())
        canvas.restoreState()

    doc.addPageTemplates([PageTemplate(id="p", frames=[frame],
                                       onPage=decorate)])
    story = [para(title, "title"), para(subtitle, "subtitle")] + story_body
    doc.build(story)
    return path
