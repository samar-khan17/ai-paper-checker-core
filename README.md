# Smart Paper Checker — AI Paper Grading System

An AI-powered exam paper grading desktop app built with Python + CustomTkinter.  
Teachers upload question papers and student answer sheets — the AI grades them automatically using NVIDIA NIM, generates detailed PDF/Excel reports, and can email report cards directly to students.

---

## Screenshots

| Login Screen | Setup Paper | Check Answer Sheet |
|---|---|---|
| ![Login](screenshots/01_login.png) | ![Setup](screenshots/02_setup_paper.png) | ![Check](screenshots/03_check_sheet.png) |

| Checked Papers | Class Insights | Settings & API |
|---|---|---|
| ![Results](screenshots/04_checked_papers.png) | ![Analytics](screenshots/05_class_insights.png) | ![Settings](screenshots/06_settings.png) |

> Screenshots folder: save app screenshots as `screenshots/01_login.png` etc. and they will appear above automatically.

---

## Features

- **AI Grading** — NVIDIA NIM (Llama 3.3 70B) grades answers with per-question marks and detailed feedback
- **Vision OCR** — reads handwritten answer sheets automatically via NVIDIA vision AI
- **Dual API Key Failover** — two NVIDIA keys work simultaneously; if one fails the other takes over instantly
- **Multi-Language** — grades papers written in English, Urdu, or Roman Urdu
- **Bulk Checking** — check an entire class in one click with retry-failed option and timing display
- **Class Insights** — identifies weakest topics and detects suspicious copy/plagiarism pairs
- **Email Report Cards** — teacher sends PDF reports to students directly from the app via Gmail
- **Excel Export** — full class results exported to a formatted `.xlsx` spreadsheet
- **Teacher Settings** — API key, model, language, email — all configurable inside the app, no coding needed
- **Dark / Light Theme** — fully themed modern CustomTkinter UI

---

## Team Members and Roles

| Member | GitHub | Branch | Role |
|--------|--------|--------|------|
| **Samar Khan** | [@samar-khan17](https://github.com/samar-khan17) | `samar/core-engine` | Core AI Engine, Grading, OCR, Database, Full App |
| **Hiba** | [@f2024408117](https://github.com/f2024408117) | `hiba/ui-screens` | UI Screens, Login, Dashboard |
| **Hussam** | [@HSMVENOM](https://github.com/HSMVENOM) | `hussam/build-distribution` | Build, Distribution, Installer |
| **Maham** | [@f2024408114-del](https://github.com/f2024408114-del) | `maham/config-docs` | Configuration, Documentation, Assets |
| **Hamza** | [@f2024408113-commits](https://github.com/f2024408113-commits) | `hamza/data-assets` | Database Management, Data Assets |

---

## Technologies

| Technology | Purpose |
|---|---|
| Python 3.10+ | Core language |
| CustomTkinter | Modern desktop GUI framework |
| NVIDIA NIM API | LLM-based intelligent grading (Llama 3.3 70B) |
| NVIDIA Vision AI | Handwriting OCR (Nemotron Nano VL 8B) |
| SQLite | Local database via `database/db_manager.py` |
| ReportLab | PDF report card generation |
| OpenPyXL | Excel export |
| smtplib / SSL | Gmail email sending (App Password method) |
| PyInstaller | Windows executable packaging |
| Inno Setup | Windows installer |

---

## Project Structure

```
SmartPaperChecker/
├── core/
│   ├── ai_grader.py         # NVIDIA NIM grading engine (dual-key failover)
│   ├── analytics.py         # Class insights: weak topics + plagiarism detection
│   ├── exporter.py          # Excel + PDF report export
│   ├── mailer.py            # Gmail SMTP email sender
│   ├── settings_store.py    # Teacher-editable runtime settings
│   ├── ocr.py               # OCR text extraction
│   ├── report.py            # Marked PDF report generation
│   └── security.py          # Authentication & session management
├── database/
│   └── db_manager.py        # SQLite backend with auto-migrations
├── ui/
│   └── screens/             # UI screen components
├── config.py                # App configuration (reads from .env)
├── main.py                  # Full app UI — all screens (CustomTkinter)
├── requirements.txt         # Python dependencies
├── SmartPaperChecker.spec   # PyInstaller build config
├── installer.iss            # Inno Setup installer script
├── RUN_APP.bat              # Windows launch script
└── .env.example             # Environment variable template (no real keys)
```

---

## Setup Instructions

### Prerequisites

- Python 3.10 or higher
- NVIDIA NIM API key — free at [build.nvidia.com](https://build.nvidia.com)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/samar-khan17/ai-paper-checker-core.git
   cd ai-paper-checker-core
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   source .venv/bin/activate     # Linux/Mac
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   copy .env.example .env        # Windows
   cp .env.example .env          # Linux/Mac
   ```
   Open `.env` and paste your NVIDIA NIM API key.

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
3. Open `installer.iss` in Inno Setup and compile

---

## Branch Structure

| Branch | Owner | Purpose |
|--------|-------|---------|
| `main` | All | Stable, reviewed, merged code |
| `samar/core-engine` | Samar Khan | AI grading engine, all core modules |
| `hiba/ui-screens` | Hiba | UI screens and interface components |
| `hussam/build-distribution` | Hussam | Build scripts, installer, packaging |
| `maham/config-docs` | Maham | Configuration, documentation, assets |
| `hamza/data-assets` | Hamza | Database layer, data folder structure |

---

## GitHub Issues & PRs

- Issues track each member's assigned work — see the [Issues tab](https://github.com/samar-khan17/ai-paper-checker-core/issues)
- Each member opens a Pull Request from their branch to `main` after completing their work
- PRs are reviewed before merging to keep `main` stable

---

## Contribution Credits

| Member | Contribution |
|---|---|
| **Samar Khan** | Entire AI grading engine (dual-key NVIDIA NIM failover), vision OCR, all core modules (analytics, exporter, mailer, settings_store), full app UI (all screens in main.py), database schema and migrations, security, report generation, PyInstaller build, Desktop installer |
| **Hiba** | UI screens branch — login screen, dashboard screen, screen management |
| **Hussam** | Build & distribution — PyInstaller spec, Inno Setup installer, launch scripts |
| **Maham** | Configuration & docs — `.env.example`, README, LICENSE, app icon, documentation |
| **Hamza** | Data & assets — database manager, folder structure for logs/reports/uploads |

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
