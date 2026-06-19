# ============================================================
#   config.py — Central Configuration
#   Reads from .env file. Never hardcode keys here.
#   This file IS pushed to GitHub (no secrets inside).
# ============================================================

import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# ── BASE PATHS (dev vs. installed/frozen) ────────────────────
FROZEN = getattr(sys, "frozen", False)

# RES_DIR = read-only bundled resources (code, .env, icon).
# When frozen by PyInstaller these live in the temp _MEIPASS folder.
RES_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.absolute()))

# DATA_DIR = writable location for the database, uploads, logs, reports.
# Installed apps cannot write to Program Files, so use %LOCALAPPDATA%.
if FROZEN:
    _root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    DATA_DIR = Path(_root) / "SmartPaperChecker"
else:
    DATA_DIR = Path(__file__).parent.absolute()

BASE_DIR   = DATA_DIR
UPLOAD_DIR = DATA_DIR / "uploads"
REPORT_DIR = DATA_DIR / "reports"
LOG_DIR    = DATA_DIR / "logs"
TEMPLATE_DIR = RES_DIR / "templates"
ASSETS_DIR   = RES_DIR / "assets"

# Auto-create writable runtime directories
for d in [DATA_DIR, UPLOAD_DIR, REPORT_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
for sub in ["question_papers", "answer_keys", "marking_schemes", "sample_solutions", "student_answers"]:
    (UPLOAD_DIR / sub).mkdir(parents=True, exist_ok=True)

# Load env: bundled .env first (ships the API key), then a user override in DATA_DIR.
load_dotenv(RES_DIR / ".env")
load_dotenv(DATA_DIR / ".env", override=True)

# ── NVIDIA API ───────────────────────────────────────────────
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_API_KEY2 = os.getenv("NVIDIA_API_KEY2", "")  # optional backup key for failover
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_FAST_MODEL = os.getenv("NVIDIA_FAST_MODEL", "meta/llama-3.1-8b-instruct")
NVIDIA_VISION_MODEL = os.getenv("NVIDIA_VISION_MODEL", "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")
AI_TEMPERATURE = float(os.getenv("AI_TEMPERATURE", "0.1"))

if not NVIDIA_API_KEY:
    print("[WARNING] NVIDIA_API_KEY not set in .env — AI grading will use fallback mode.")

# ── SECURITY ─────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(64).hex())  # Fallback: random each run
SESSION_TIMEOUT_MINUTES = int(os.getenv("SESSION_TIMEOUT_MINUTES", "30"))
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_MINUTES", "15"))
BCRYPT_ROUNDS = 12  # Password hashing strength

# ── FILE SECURITY ────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_MB", "25")) * 1024 * 1024
ALLOWED_EXTENSIONS = set(os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,pdf,docx").split(","))
ALLOWED_MIME_TYPES = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg",
    "png": "image/png", "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

# ── DATABASE ─────────────────────────────────────────────────
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "database/smart_paper.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── APP ──────────────────────────────────────────────────────
APP_NAME = "Smart Paper Checker"
APP_VERSION = "1.0.0"
WINDOW_SIZE = "1280x780"
MIN_WINDOW_SIZE = (1024, 640)
MIN_WINDOW = (1024, 640)

# ── GRADING ──────────────────────────────────────────────────
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.75"))
DIFFICULTY_LEVELS = {1: "Very Easy", 2: "Easy", 3: "Medium", 4: "Hard", 5: "Very Hard"}
SUBJECTS = ["OSSD", "PF", "OOP", "DSA", "COAL", "Professional Practices"]
GRADE_SCALE = {
    90: "A+", 85: "A", 80: "A-",
    75: "B+", 70: "B", 65: "B-",
    60: "C+", 55: "C", 50: "D", 0: "F"
}

# ── LOGGING ──────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOG_DIR / os.getenv("LOG_FILE", "logs/app.log").split("/")[-1]

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SmartPaperChecker")
logger.info(f"Config loaded. App: {APP_NAME} v{APP_VERSION}")
