# ============================================================
#   core/report.py — Marked-paper PDF report generator
#   Annotates the student's answer-sheet image(s) with red,
#   teacher-style marks per question, then builds a PDF with a
#   summary page + the marked pages.
# ============================================================

import logging
from pathlib import Path
from datetime import datetime

from PIL import Image as PILImage, ImageDraw, ImageFont

from config import REPORT_DIR

logger = logging.getLogger("report")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
RED = (220, 38, 38)
GREEN = (22, 163, 74)
AMBER = (217, 119, 6)


def _font(size):
    for name in ("arialbd.ttf", "arial.ttf", "segoeui.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _mark_kind(score, mx):
    if mx and score >= mx - 1e-6:
        return "ok", GREEN
    if score <= 1e-6:
        return "x", RED
    return "partial", AMBER


def _draw_mark(d, x, y, size, kind, color, width):
    """Draw a teacher-style tick / cross / dash (no font glyphs)."""
    if kind == "ok":
        d.line([(x, y + size * 0.55), (x + size * 0.4, y + size * 0.9),
                (x + size, y + size * 0.05)], fill=color, width=width, joint="curve")
    elif kind == "x":
        d.line([(x, y), (x + size, y + size)], fill=color, width=width)
        d.line([(x, y + size), (x + size, y)], fill=color, width=width)
    else:  # partial
        d.line([(x, y + size * 0.6), (x + size, y + size * 0.6)], fill=color, width=width)


def annotate_image(src_path: str, result: dict, meta: dict, page_index: int,
                   show_questions: bool) -> str:
    """Draw teacher-style marks on a copy of the answer-sheet image.
    Returns the path of the annotated PNG."""
    img = PILImage.open(src_path).convert("RGB")
    W, H = img.size
    # scale annotation sizes to image width
    base = max(18, int(W * 0.028))
    d = ImageDraw.Draw(img)
    f_big = _font(int(base * 1.4))
    f = _font(base)

    total = f"{result.get('total_score',0)} / {result.get('total_max',0)}"
    grade = result.get("grade", "")
    header = f"Total: {total}    Grade: {grade}"
    # red header strip
    pad = int(base * 0.4)
    tw = d.textlength(header, font=f_big)
    d.rectangle([0, 0, W, int(base * 1.4) + pad * 2], fill=(255, 255, 255))
    d.text((pad, pad), header, fill=RED, font=f_big)
    d.text((W - d.textlength("Checked by AI", font=f) - pad, pad + int(base * 0.3)),
           "Checked by AI", fill=RED, font=f)
    d.line([(0, int(base * 1.4) + pad * 2), (W, int(base * 1.4) + pad * 2)], fill=RED, width=2)

    # per-question marks down the right margin (only on the first marked page)
    if show_questions:
        qresults = result.get("question_results", {})
        try:
            items = sorted(qresults.items(), key=lambda kv: int(kv[0]))
        except (ValueError, TypeError):
            items = list(qresults.items())
        y = int(base * 1.4) + pad * 3
        line_h = int(base * 1.7)
        col_x = W - int(W * 0.30)
        # translucent panel behind the marks for readability
        if items:
            panel = PILImage.new("RGBA", (W - col_x, line_h * len(items) + pad * 2),
                                 (255, 255, 255, 210))
            img.paste(panel, (col_x - pad, y - pad), panel)
            d = ImageDraw.Draw(img)
        icon = int(base * 0.9)
        mw = max(3, int(base * 0.14))
        for qn, qr in items:
            kind, col = _mark_kind(qr.get("score", 0), qr.get("max_marks", 0))
            _draw_mark(d, col_x, y + int(base * 0.1), icon, kind, col, mw)
            d.text((col_x + icon + int(base * 0.5), y),
                   f"Q{qn}: {qr.get('score',0)}/{qr.get('max_marks',0)}", fill=col, font=f)
            y += line_h

    out = Path(REPORT_DIR) / f"_marked_{page_index}_{Path(src_path).stem}.png"
    img.save(out)
    return str(out)


def generate_report(meta: dict, result: dict, answer_files: list) -> str:
    """Build the marked-paper PDF and return its path."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, Image as RLImage, PageBreak)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, spaceAfter=6)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=10, textColor=colors.HexColor("#555555"))
    normal = styles["Normal"]

    name = meta.get("student_name", "") or "—"
    roll = meta.get("student_roll", "") or "—"
    title = meta.get("paper_title", "") or "—"
    subject = meta.get("subject", "") or "—"

    safe = "".join(c for c in f"{name}_{roll}" if c.isalnum() or c in ("_", "-")) or "student"
    out_path = Path(REPORT_DIR) / f"Result_{safe}_{datetime.now():%Y%m%d_%H%M%S}.pdf"

    story = []
    story.append(Paragraph("Smart Paper Checker — Result Report", h1))
    story.append(Paragraph(datetime.now().strftime("Generated %d %b %Y, %I:%M %p"), small))
    story.append(Spacer(1, 8))

    info = [
        ["Student Name", name, "Student ID", roll],
        ["Paper", title, "Subject", subject],
    ]
    it = Table(info, colWidths=[28*mm, 60*mm, 26*mm, 50*mm])
    it.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#4F46E5")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#4F46E5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(it)
    story.append(Spacer(1, 10))

    grade = result.get("grade", "")
    score = f"{result.get('total_score',0)} / {result.get('total_max',0)}"
    pct = result.get("percentage", 0)
    big = ParagraphStyle("big", parent=styles["Normal"], fontSize=15,
                         textColor=colors.HexColor("#111827"), spaceAfter=8)
    story.append(Paragraph(f"<b>Grade: {grade}</b> &nbsp;&nbsp; Score: <b>{score}</b> &nbsp;&nbsp; {pct}%", big))

    # per-question table
    head = ["Q#", "Max", "Awarded", "Result", "Feedback"]
    rows = [head]
    qresults = result.get("question_results", {})
    try:
        items = sorted(qresults.items(), key=lambda kv: int(kv[0]))
    except (ValueError, TypeError):
        items = list(qresults.items())
    for qn, qr in items:
        mx = qr.get("max_marks", 0)
        sc = qr.get("score", 0)
        verdict = "Correct" if mx and sc >= mx - 1e-6 else ("Wrong" if sc <= 1e-6 else "Partial")
        rows.append([str(qn), str(mx), str(sc), verdict,
                     Paragraph(str(qr.get("feedback", ""))[:300], small)])
    qt = Table(rows, colWidths=[12*mm, 14*mm, 18*mm, 18*mm, 102*mm], repeatRows=1)
    qt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
    ]))
    story.append(qt)
    story.append(Spacer(1, 10))

    if result.get("summary_feedback"):
        story.append(Paragraph("<b>Overall feedback:</b> " + str(result["summary_feedback"]), normal))

    # marked answer-sheet image pages
    images = [p for p in answer_files if Path(p).suffix.lower() in IMAGE_EXTS]
    page_w, page_h = A4
    avail_w = page_w - 30 * mm
    avail_h = page_h - 40 * mm
    first = True
    for i, src in enumerate(images):
        try:
            marked = annotate_image(src, result, meta, i, show_questions=first)
            first = False
            with PILImage.open(marked) as im:
                iw, ih = im.size
            scale = min(avail_w / iw, avail_h / ih)
            story.append(PageBreak())
            story.append(Paragraph(f"Marked answer sheet — page {i+1}", small))
            story.append(Spacer(1, 4))
            story.append(RLImage(marked, width=iw * scale, height=ih * scale))
        except Exception as e:
            logger.warning(f"Could not embed image {src}: {e}")

    if not images:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            "<i>Note: the answer sheet was a text/document file, so there is no image to mark. "
            "The marks above were applied per question.</i>", small))

    SimpleDocTemplate(str(out_path), pagesize=A4,
                      leftMargin=15*mm, rightMargin=15*mm,
                      topMargin=15*mm, bottomMargin=15*mm).build(story)
    logger.info(f"Report written: {out_path}")
    return str(out_path)
