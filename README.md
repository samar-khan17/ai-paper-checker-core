# AI Paper Checker — Core Engine

AI-powered exam paper grading system backend.  
Handles AI grading, OCR extraction, database management, security, and report generation.

## Modules

| Module | Description |
|--------|-------------|
| `core/ai_grader.py` | NVIDIA NIM LLM-based grading engine |
| `core/security.py` | Password hashing, brute-force protection, session management |
| `core/report.py` | PDF and Excel report generation |
| `core/ocr.py` | OCR text extraction from scanned papers |
| `core/ocr_engine.py` | OCR backend wrapper |
| `core/question_parser.py` | Exam question paper parser |
| `database/db_manager.py` | SQLite database engine with full audit logging |
| `config.py` | Application configuration and API settings |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your NVIDIA NIM API key
```

## Tech Stack

- Python 3.10+
- NVIDIA NIM API (LLM grading)
- SQLite (database)
- pytesseract + pdf2image (OCR)
- reportlab + openpyxl (report generation)
- bcrypt (password security)
