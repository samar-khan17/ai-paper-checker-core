# Smart Paper Checker — Claude Code Setup Prompt

## Copy and paste this entire prompt into Claude Code

---

You are helping me fix and run a Python desktop application called **Smart Paper Checker**.
It is an AI-powered academic paper grading app using NVIDIA NIM API and CustomTkinter UI.

## Project Location
All files are in this folder — work directly on them:
```
C:\Users\Admin\Downloads\PaperCheckerAI_FINAL\PaperCheckerAI\
```

## Current Problem
The app crashes on startup with this error:
```
TypeError: LoginScreen._register() takes 1 positional argument but 4 were given
```
This is caused by **Python 3.14 incompatibility** with customtkinter.

## What You Need To Do (in order)

### Step 1 — Check Python version
```bash
python --version
py -3.11 --version
```

### Step 2 — Install Python 3.11 if not present
If Python 3.11 is not installed:
- Download from: https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe
- Install with "Add to PATH" and "Install for all users" checked
- Use `py -3.11` for all commands

### Step 3 — Install all dependencies using Python 3.11
```bash
py -3.11 -m pip install customtkinter Pillow openai python-dotenv reportlab openpyxl matplotlib python-docx pytesseract pdf2image
```

### Step 4 — Set up .env file
Create a `.env` file in the project root with:
```
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=meta/llama-3.1-405b-instruct
```

### Step 5 — Delete old database and run
```bash
del database\smart_paper.db
py -3.11 main.py
```

---

## Project Structure
```
PaperCheckerAI/
├── main.py                  ← Complete standalone UI app (DO NOT change imports)
├── config.py                ← App config, reads from .env
├── requirements.txt
├── .env                     ← API keys (create this)
├── core/
│   ├── __init__.py
│   ├── ai_grader.py         ← NVIDIA NIM grader (NvidiaGrader class, AIGrader alias)
│   ├── security.py          ← Auth, sessions, password hashing
│   ├── question_parser.py   ← Parses question papers
│   └── ocr_engine.py        ← OCR for images/PDFs
├── database/
│   ├── __init__.py
│   └── db_manager.py        ← SQLite manager (DB alias for DatabaseManager)
└── ui/
    ├── __init__.py
    ├── app.py
    └── screens/
        ├── __init__.py
        ├── login_screen.py
        └── dashboard_screen.py
```

---

## Key Facts About This App

### main.py calls these exact methods — DO NOT rename them:
```python
# Database (db_manager.py — class DatabaseManager, alias DB)
db.init()
db.get_user(username)                          # returns dict or None
db.touch_login(user_id)
db.create_user(username, pw_hash, role, full_name)
db.log_audit(action, username, details)
db.create_paper(teacher_id, subject, title, total_marks, difficulty)
db.update_paper(paper_id, updates_dict)        # keys: q_paper_path, answer_key_path, marking_path, sample_path, parsed_questions, parsed_answers
db.papers_by_teacher(teacher_id)              # returns list of dicts with keys: id, title, subject, total_marks, difficulty, created_at
db.all_papers()                               # returns list with same keys
db.create_submission(student_id, paper_id, answer_path)
db.set_status(submission_id, status)
db.submissions_for_paper(paper_id)            # returns list with student_name field
db.submissions_for_student(student_id)        # returns list with paper_title, subject fields
db.save_result(submission_id, result_dict)
db.get_result_by_submission(submission_id)    # returns dict with question_results (parsed json), all_red_flags
db.results_for_paper(paper_id)               # returns list with student_name
db.apply_override(result_id, new_score, total_max, notes, teacher_id)
db.save_history(student_id, paper_id, subject, title, score, total_marks, percentage, grade)
db.get_history(student_id)                   # returns list with: subject, title, score, total_marks, grade, percentage, recorded_at

# Security (security.py)
pwd_mgr.hash_password(password)              # raises ValueError if weak
pwd_mgr.verify_password(password, hash)
tracker.is_locked(username)                  # returns (bool, minutes)
tracker.record(username, success_bool)
tracker.remaining(username)                  # returns int
sessions.create(user_dict)                   # returns token string
sessions.destroy(token)

# AI Grader (ai_grader.py — class NvidiaGrader, aliases AIGrader)
grader.grade_paper(questions, answer_key, student_answers, subject)
# questions = [{"number":1, "text":"...", "marks":10}, ...]
# answer_key = {1: {"model_answer":"...", "marking_notes":"..."}, ...}
# student_answers = {1: "student text", ...}
# returns: {"total_score":x, "total_max":x, "percentage":x, "grade":"A+",
#           "overall_confidence":0.9, "needs_manual_review":False,
#           "summary_feedback":"...", "question_results":{}, "all_red_flags":[]}
```

### Database column names (exact):
```sql
papers:  id, teacher_id, subject, title, q_paper_path, answer_key_path,
         marking_path, sample_path, parsed_questions, parsed_answers,
         total_marks, difficulty, is_active, created_at

users:   id, username, password_hash, role, full_name, email, is_active, created_at, last_login

submissions: id, student_id, paper_id, answer_sheet_path, submitted_at, status

results: id, submission_id, total_score, total_max, percentage, grade,
         question_results, summary_feedback, red_flags, overall_confidence,
         needs_review, manual_override, override_by, override_notes, graded_at

student_history: id, student_id, paper_id, subject, title, score, total_marks,
                 percentage, grade, recorded_at
```

---

## What Has Been Done Already
- All backend files written and tested — 14/14 logic tests pass
- Database schema fixed (removed `datetime("now")` defaults, using CURRENT_TIMESTAMP)
- All method name mismatches fixed between main.py and backend files
- Security aliases added (pwd_mgr, tracker, sessions with correct method names)
- AI grader alias added (grade_paper wraps grade_full_paper)
- The ONLY remaining issue is Python 3.14 vs customtkinter incompatibility

## After App Loads — Test Flow:
1. Click "Create Account" → make a Teacher account (password must have 8+ chars, 1 uppercase, 1 number)
2. Login as Teacher
3. Go to "Upload Paper" → fill title, subject, upload question paper + answer key (DOCX files work best)
4. Go to student account → "Submit Answer" → upload answer sheet → AI grades it automatically
5. Teacher can see results in "Grade Submissions" and "Results & Analytics"

---

## If Any Error Occurs:
- Share the full error traceback
- Check if Python 3.11 is being used: `py -3.11 --version`
- Make sure .env file exists with real NVIDIA API key
- Make sure database\smart_paper.db was deleted before first run
