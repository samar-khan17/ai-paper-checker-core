# AI Paper Checker

An AI-powered exam paper grading system built with Python, featuring OCR-based answer extraction, intelligent grading via NVIDIA NIM AI, and a full desktop GUI.

---

## Team Members and Roles

| Member | GitHub | Role |
|--------|--------|------|
| **Samar Khan** | [@samar-khan17](https://github.com/samar-khan17) | Core AI Engine, OCR, Database, Security |
| **Hiba** | [@f2024408117](https://github.com/f2024408117) | UI Screens, Login, Dashboard |
| **Hussam** | [@HSMVENOM](https://github.com/HSMVENOM) | Build, Distribution, Installer |
| **Maham** | [@f2024408114-del](https://github.com/f2024408114-del) | Configuration, Documentation |
| **Hamza** | [@f2024408113-commits](https://github.com/f2024408113-commits) | Data Management, Assets |

---

## Technologies

- **Python 3.10+** - Core language
- **Tkinter** - Desktop GUI framework
- **SQLite** - Local database (via `database/`)
- **NVIDIA NIM AI** - LLM-based intelligent grading engine
- **Tesseract / EasyOCR** - OCR for scanned answer extraction
- **PyInstaller + Inno Setup** - Build and installer toolchain
- **ReportLab / OpenPyXL** - PDF and Excel report generation

---

## Project Structure

```
SmartPaperChecker/
├── core/                    # AI Engine (Samar Khan)
│   ├── ai_grader.py         # NVIDIA NIM grading engine
│   ├── ocr.py               # OCR text extraction
│   ├── ocr_engine.py        # OCR backend wrapper
│   ├── question_parser.py   # Exam structure parser
│   ├── report.py            # Report generation
│   └── security.py          # Authentication & sessions
├── database/                # Database layer (Hamza)
│   ├── db_manager.py        # SQLite backend
│   └── smart_paper.db       # Application database
├── ui/                      # User Interface (Hiba)
│   ├── app.py               # Main application window
│   └── screens/
│       ├── login_screen.py  # Login interface
│       └── dashboard_screen.py  # Main dashboard
├── config.py                # Configuration (Maham)
├── main.py                  # Application entry point (Samar Khan)
├── requirements.txt         # Python dependencies (Maham)
├── installer.iss            # Inno Setup script (Hussam)
├── RUN_APP.bat              # Windows launcher (Hussam)
└── HOW_TO_INSTALL.txt       # Installation guide (Hussam)
```

---

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- Tesseract OCR installed and added to PATH
- NVIDIA NIM API key (for AI grading)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/samar-khan17/ai-paper-checker-core.git
   cd ai-paper-checker-core
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   source .venv/bin/activate   # Linux/Mac
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   copy .env.example .env     # Windows
   cp .env.example .env       # Linux/Mac
   ```
   Then edit `.env` and add your NVIDIA NIM API key.

5. **Run the application:**
   ```bash
   python main.py
   ```
   Or on Windows, double-click `RUN_APP.bat`.

### Building the Installer (Windows)

1. Install [PyInstaller](https://pyinstaller.org/) and [Inno Setup](https://jrsoftware.org/isinfo.php)
2. Build the executable:
   ```bash
   pyinstaller SmartPaperChecker.spec
   ```
3. Compile the installer using `installer.iss` in Inno Setup

---

## Branch Structure

| Branch | Owner | Purpose |
|--------|-------|---------|
| `main` | All | Stable, reviewed code |
| `samar/core-engine` | Samar Khan | AI engine, OCR, database, security |
| `hiba/ui-screens` | Hiba | Login, dashboard, UI screens |
| `hussam/build-distribution` | Hussam | Build scripts, installer, distribution |
| `maham/config-docs` | Maham | Config, documentation, assets |
| `hamza/data-assets` | Hamza | Database, logs, reports, uploads |

---

## Contributing

Each team member works on their designated branch. To contribute:

1. Pull the latest main: `git pull origin main`
2. Checkout your branch: `git checkout <your-branch>`
3. Make changes and commit
4. Push and open a Pull Request to `main`

---

## Contribution Credits

- **Samar Khan** - AI grading engine, OCR pipeline, security module, database schema, pipeline orchestration
- **Hiba** - Login screen UI, dashboard interface, application window management
- **Hussam** - PyInstaller build configuration, Inno Setup installer, distribution packaging, launch scripts
- **Maham** - Environment configuration, project documentation, application assets, dependency management
- **Hamza** - Database management, log file structure, report storage, upload directory management
