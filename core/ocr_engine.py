# core/ocr_engine.py — Multi-format OCR with security validation
import os, logging
import pytesseract
from PIL import Image
import pdf2image
import docx
from pathlib import Path
from core.security import file_validator
from config import UPLOAD_DIR

logger = logging.getLogger("ocr_engine")

if os.name == 'nt':
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

class OCREngine:
    def extract_text(self, file_path: str) -> dict:
        validation = file_validator.validate(file_path)
        if not validation["valid"]:
            return {"success": False, "error": validation["error"], "text": "", "confidence": 0}
        ext = Path(file_path).suffix.lower().lstrip('.')
        try:
            if ext in ['jpg', 'jpeg', 'png']:
                text, conf = self._from_image(file_path)
            elif ext == 'pdf':
                text, conf = self._from_pdf(file_path)
            elif ext == 'docx':
                text, conf = self._from_docx(file_path)
            else:
                return {"success": False, "error": "Unsupported format", "text": "", "confidence": 0}
            return {"success": True, "text": text, "confidence": conf, "error": None}
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return {"success": False, "error": str(e), "text": "", "confidence": 0}

    def _preprocess(self, img):
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 140 else 255)
        return img

    def _from_image(self, path):
        img = Image.open(path)
        img = self._preprocess(img)
        text = pytesseract.image_to_string(img, config='--psm 6')
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        confs = [int(c) for c in data['conf'] if str(c).isdigit() and int(c) > 0]
        conf = sum(confs)/len(confs)/100 if confs else 0.5
        return text.strip(), round(conf, 2)

    def _from_pdf(self, path):
        pages = pdf2image.convert_from_path(path, dpi=300)
        texts, confs = [], []
        for i, page in enumerate(pages):
            page = self._preprocess(page)
            t = pytesseract.image_to_string(page, config='--psm 6')
            texts.append(f"--- Page {i+1} ---\n{t}")
            d = pytesseract.image_to_data(page, output_type=pytesseract.Output.DICT)
            c = [int(x) for x in d['conf'] if str(x).isdigit() and int(x)>0]
            if c: confs.append(sum(c)/len(c))
        avg_conf = sum(confs)/len(confs)/100 if confs else 0.8
        return "\n".join(texts), round(avg_conf, 2)

    def _from_docx(self, path):
        doc = docx.Document(path)
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return text, 0.98  # DOCX is always high confidence
