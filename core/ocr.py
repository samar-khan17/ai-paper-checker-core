# ============================================================
#   core/ocr.py — Document → images + text (OCR/ingest module)
#   - Images pass through (order preserved)
#   - PDFs are rendered to page images (PyMuPDF, no system deps)
#   - DOCX text is extracted
#   Vision reading of the images is handled in core/ai_grader.
# ============================================================

import logging
from pathlib import Path

logger = logging.getLogger("ocr")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _fitz():
    """Return the PyMuPDF module (works whether it's named pymupdf or fitz)."""
    try:
        import pymupdf as f
    except ImportError:
        import fitz as f
    return f


def to_images(path: str, out_dir: str, dpi: int = 170) -> list:
    """Return an ordered list of image paths for a file.
    Images -> themselves; PDF -> one image per page (in order); DOCX -> []."""
    p = Path(path)
    ext = p.suffix.lower()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if ext in IMAGE_EXTS:
        return [str(p)]

    if ext == ".pdf":
        images = []
        try:
            fitz = _fitz()  # PyMuPDF
            doc = fitz.open(str(p))
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=mat)
                img_path = out / f"{p.stem}_page{i+1:02d}.png"
                pix.save(str(img_path))
                images.append(str(img_path))
            doc.close()
        except Exception as e:
            logger.error(f"PDF render failed for {p.name}: {e}")
        return images

    return []


def extract_text(path: str) -> str:
    """Extract selectable text from DOCX or text-based PDF. '' for images."""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext == ".docx":
            import docx as dx
            doc = dx.Document(str(p))
            return "\n".join(par.text for par in doc.paragraphs if par.text.strip())
        if ext == ".pdf":
            fitz = _fitz()
            doc = fitz.open(str(p))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text.strip()
    except Exception as e:
        logger.warning(f"text extract failed for {p.name}: {e}")
    return ""
