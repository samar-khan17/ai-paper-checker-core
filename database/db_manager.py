# database/db_manager.py — Secure SQLite Manager
import sqlite3, logging, json
from config import DB_PATH

logger = logging.getLogger("database")


class DatabaseManager:
    def __init__(self):
        self.db_path = str(DB_PATH)

    def get_connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init(self):
        return self.initialize()

    def initialize(self):
        conn = self.get_connection()
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    UNIQUE NOT NULL,
                password_hash   TEXT    NOT NULL,
                role            TEXT    NOT NULL,
                full_name       TEXT    NOT NULL DEFAULT "",
                email           TEXT    DEFAULT "",
                is_active       INTEGER DEFAULT 1,
                created_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
                last_login      TEXT    DEFAULT NULL
            );
            CREATE TABLE IF NOT EXISTS papers (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_id        INTEGER NOT NULL,
                subject           TEXT    NOT NULL,
                title             TEXT    NOT NULL,
                q_paper_path      TEXT    DEFAULT "",
                answer_key_path   TEXT    DEFAULT "",
                marking_path      TEXT    DEFAULT "",
                sample_path       TEXT    DEFAULT "",
                parsed_questions  TEXT    DEFAULT "[]",
                parsed_answers    TEXT    DEFAULT "{}",
                total_marks       INTEGER DEFAULT 100,
                difficulty        INTEGER DEFAULT 3,
                is_active         INTEGER DEFAULT 1,
                created_at        TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id        INTEGER NOT NULL,
                paper_id          INTEGER NOT NULL,
                answer_sheet_path TEXT    NOT NULL,
                submitted_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
                status            TEXT    DEFAULT "pending"
            );
            CREATE TABLE IF NOT EXISTS results (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                submission_id      INTEGER NOT NULL UNIQUE,
                total_score        REAL    DEFAULT 0,
                total_max          INTEGER DEFAULT 100,
                percentage         REAL    DEFAULT 0,
                grade              TEXT    DEFAULT "F",
                question_results   TEXT    DEFAULT "{}",
                summary_feedback   TEXT    DEFAULT "",
                red_flags          TEXT    DEFAULT "[]",
                overall_confidence REAL    DEFAULT 0,
                needs_review       INTEGER DEFAULT 0,
                manual_override    INTEGER DEFAULT 0,
                override_by        INTEGER DEFAULT NULL,
                override_notes     TEXT    DEFAULT "",
                graded_at          TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS student_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id   INTEGER NOT NULL,
                paper_id     INTEGER NOT NULL,
                subject      TEXT    NOT NULL,
                title        TEXT    NOT NULL,
                score        REAL,
                total_marks  INTEGER,
                percentage   REAL,
                grade        TEXT,
                recorded_at  TEXT    DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                action       TEXT    NOT NULL,
                performed_by TEXT,
                details      TEXT    DEFAULT "",
                timestamp    TEXT    DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # Safe migrations — add new columns without touching existing data
        sub_cols = [r[1] for r in conn.execute("PRAGMA table_info(submissions)").fetchall()]
        for col, ddl in [
            ("student_name",  "ALTER TABLE submissions ADD COLUMN student_name TEXT DEFAULT ''"),
            ("student_roll",  "ALTER TABLE submissions ADD COLUMN student_roll TEXT DEFAULT ''"),
            ("class_section", "ALTER TABLE submissions ADD COLUMN class_section TEXT DEFAULT ''"),
            ("checking_mode", "ALTER TABLE submissions ADD COLUMN checking_mode TEXT DEFAULT 'normal'"),
            ("answer_images", "ALTER TABLE submissions ADD COLUMN answer_images TEXT DEFAULT '[]'"),
            ("remarks",       "ALTER TABLE submissions ADD COLUMN remarks TEXT DEFAULT ''"),
            ("row_color",     "ALTER TABLE submissions ADD COLUMN row_color TEXT DEFAULT 'white'"),
            ("student_email", "ALTER TABLE submissions ADD COLUMN student_email TEXT DEFAULT ''"),
        ]:
            if col not in sub_cols:
                conn.execute(ddl)
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")

    # ── USERS ────────────────────────────────────────────────
    def create_user(self, username, password_hash, role, full_name, email=""):
        conn = self.get_connection()
        try:
            c = conn.execute(
                "INSERT INTO users (username,password_hash,role,full_name,email) VALUES (?,?,?,?,?)",
                (username, password_hash, role, full_name, email))
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def get_user(self, username):
        conn = self.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username=? AND is_active=1", (username,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def touch_login(self, user_id):
        conn = self.get_connection()
        try:
            conn.execute("UPDATE users SET last_login=datetime('now') WHERE id=?", (user_id,))
            conn.commit()
        finally:
            conn.close()

    # ── PAPERS ───────────────────────────────────────────────
    def create_paper(self, teacher_id, subject, title, total_marks, difficulty):
        conn = self.get_connection()
        try:
            c = conn.execute(
                "INSERT INTO papers (teacher_id,subject,title,total_marks,difficulty) VALUES (?,?,?,?,?)",
                (teacher_id, subject, title, total_marks, difficulty))
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def update_paper(self, paper_id, updates):
        if not updates:
            return
        allowed = {"q_paper_path","answer_key_path","marking_path","sample_path",
                   "parsed_questions","parsed_answers"}
        safe = {k: v for k, v in updates.items() if k in allowed}
        if not safe:
            return
        conn = self.get_connection()
        try:
            fields = ", ".join(f"{k}=?" for k in safe)
            conn.execute(f"UPDATE papers SET {fields} WHERE id=?",
                         list(safe.values()) + [paper_id])
            conn.commit()
        finally:
            conn.close()

    def papers_by_teacher(self, teacher_id):
        conn = self.get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM papers WHERE teacher_id=? AND is_active=1 ORDER BY created_at DESC",
                (teacher_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def all_papers(self):
        conn = self.get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM papers WHERE is_active=1 ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_paper(self, paper_id):
        conn = self.get_connection()
        try:
            row = conn.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def delete_paper(self, paper_id):
        conn = self.get_connection()
        try:
            conn.execute("UPDATE papers SET is_active=0 WHERE id=?", (paper_id,))
            conn.commit()
        finally:
            conn.close()

    # ── SUBMISSIONS ──────────────────────────────────────────
    def create_submission(self, student_id, paper_id, answer_path, student_name="",
                          student_roll="", class_section="", checking_mode="normal",
                          answer_images=None):
        import json as _json
        conn = self.get_connection()
        try:
            c = conn.execute(
                "INSERT INTO submissions (student_id,paper_id,answer_sheet_path,student_name,"
                "student_roll,class_section,checking_mode,answer_images) VALUES (?,?,?,?,?,?,?,?)",
                (student_id, paper_id, answer_path, student_name, student_roll,
                 class_section, checking_mode, _json.dumps(answer_images or [])))
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def search_submissions(self, teacher_id, query="", section=None, sort="Newest First"):
        conn = self.get_connection()
        try:
            q = f"%{(query or '').strip()}%"
            section_filter = " AND s.class_section = ?" if section else ""
            sort_map = {
                "Newest First":   "s.submitted_at DESC",
                "Oldest First":   "s.submitted_at ASC",
                "Marks High→Low": "COALESCE(r.percentage, -1) DESC",
                "Marks Low→High": "COALESCE(r.percentage, 999) ASC",
                "Name A-Z":       "LOWER(s.student_name) ASC",
            }
            order = sort_map.get(sort, "s.submitted_at DESC")
            params = [teacher_id, q, q, q, q]
            if section:
                params.append(section)
            rows = conn.execute(f'''
                SELECT s.id, s.student_name, s.student_roll, s.class_section, s.checking_mode,
                       s.submitted_at, s.status, s.remarks, s.row_color, s.student_email,
                       p.id as paper_id, p.title as paper_title, p.subject,
                       r.total_score, r.total_max, r.percentage, r.grade
                FROM submissions s
                JOIN papers p ON s.paper_id=p.id
                LEFT JOIN results r ON r.submission_id=s.id
                WHERE p.teacher_id=? AND (
                      s.student_name LIKE ? OR s.student_roll LIKE ?
                      OR CAST(p.id AS TEXT) LIKE ? OR p.title LIKE ?)
                ORDER BY s.submitted_at DESC''',
                (teacher_id, q, q, q, q)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def get_submission(self, submission_id):
        """Full submission row incl. parsed answer_images list."""
        import json as _json
        conn = self.get_connection()
        try:
            row = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["answer_images"] = _json.loads(d.get("answer_images") or "[]")
            except Exception:
                d["answer_images"] = []
            return d
        finally:
            conn.close()

    def set_status(self, submission_id, status):
        conn = self.get_connection()
        try:
            conn.execute("UPDATE submissions SET status=? WHERE id=?", (status, submission_id))
            conn.commit()
        finally:
            conn.close()

    def update_submission_remarks(self, submission_id, remarks, row_color):
        conn = self.get_connection()
        try:
            conn.execute("UPDATE submissions SET remarks=?, row_color=? WHERE id=?",
                         (remarks, row_color, submission_id))
            conn.commit()
        finally:
            conn.close()

    def update_submission_info(self, submission_id, name, roll, section, email=None):
        conn = self.get_connection()
        try:
            if email is None:
                conn.execute(
                    "UPDATE submissions SET student_name=?, student_roll=?, class_section=? WHERE id=?",
                    (name, roll, section, submission_id))
            else:
                conn.execute(
                    "UPDATE submissions SET student_name=?, student_roll=?, class_section=?, "
                    "student_email=? WHERE id=?",
                    (name, roll, section, email, submission_id))
            conn.commit()
        finally:
            conn.close()

    def delete_submission(self, submission_id):
        conn = self.get_connection()
        try:
            conn.execute("DELETE FROM results WHERE submission_id=?", (submission_id,))
            conn.execute("DELETE FROM submissions WHERE id=?", (submission_id,))
            conn.commit()
        finally:
            conn.close()

    def submissions_for_paper(self, paper_id):
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT s.*, u.full_name as _acct_name
                FROM submissions s JOIN users u ON s.student_id=u.id
                WHERE s.paper_id=? ORDER BY s.submitted_at DESC''', (paper_id,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                acct = d.pop("_acct_name", "")
                if not d.get("student_name"):
                    d["student_name"] = acct
                d["student_roll"] = d.get("student_roll") or ""
                out.append(d)
            return out
        finally:
            conn.close()

    def get_submission_meta(self, submission_id):
        """Name / roll / paper title / subject for one submission (for reports)."""
        conn = self.get_connection()
        try:
            row = conn.execute('''
                SELECT s.student_name, s.student_roll, s.answer_sheet_path, s.remarks,
                       u.full_name as acct_name, p.title as paper_title, p.subject
                FROM submissions s
                JOIN users u ON s.student_id=u.id
                JOIN papers p ON s.paper_id=p.id
                WHERE s.id=?''', (submission_id,)).fetchone()
            if not row:
                return {}
            d = dict(row)
            d["student_name"] = d.get("student_name") or d.get("acct_name") or ""
            d["student_roll"] = d.get("student_roll") or ""
            return d
        finally:
            conn.close()

    def submissions_for_student(self, student_id):
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT s.*, p.title as paper_title, p.subject
                FROM submissions s JOIN papers p ON s.paper_id=p.id
                WHERE s.student_id=? ORDER BY s.submitted_at DESC''', (student_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── STATS ────────────────────────────────────────────────
    def stats_for_teacher(self, teacher_id):
        conn = self.get_connection()
        try:
            papers = conn.execute(
                "SELECT COUNT(*) FROM papers WHERE teacher_id=? AND is_active=1",
                (teacher_id,)).fetchone()[0]
            checked = conn.execute('''
                SELECT COUNT(*) FROM submissions s
                JOIN papers p ON s.paper_id=p.id
                JOIN results r ON r.submission_id=s.id
                WHERE p.teacher_id=?''', (teacher_id,)).fetchone()[0]
            students = conn.execute('''
                SELECT COUNT(DISTINCT COALESCE(NULLIF(s.student_roll,''), CAST(s.id AS TEXT)))
                FROM submissions s JOIN papers p ON s.paper_id=p.id
                WHERE p.teacher_id=?''', (teacher_id,)).fetchone()[0]
            avg_row = conn.execute('''
                SELECT AVG(r.percentage) FROM results r
                JOIN submissions s ON r.submission_id=s.id
                JOIN papers p ON s.paper_id=p.id
                WHERE p.teacher_id=?''', (teacher_id,)).fetchone()[0]
            return {"papers": papers, "checked": checked,
                    "students": students, "avg": round(avg_row or 0, 1)}
        finally:
            conn.close()

    def get_sections(self, teacher_id):
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT DISTINCT s.class_section
                FROM submissions s JOIN papers p ON s.paper_id=p.id
                WHERE p.teacher_id=? AND s.class_section IS NOT NULL AND s.class_section != ''
                ORDER BY s.class_section''', (teacher_id,)).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()

    def section_stats(self, teacher_id, section):
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT r.percentage FROM results r
                JOIN submissions s ON r.submission_id=s.id
                JOIN papers p ON s.paper_id=p.id
                WHERE p.teacher_id=? AND s.class_section=?''', (teacher_id, section)).fetchall()
            pcts = [r[0] for r in rows if r[0] is not None]
            if not pcts:
                return {"count": 0, "avg": 0, "highest": 0, "pass_rate": 0}
            count = len(pcts)
            return {
                "count": count,
                "avg": round(sum(pcts) / count, 1),
                "highest": round(max(pcts), 1),
                "pass_rate": round(sum(1 for p in pcts if p >= 50) / count * 100, 1),
            }
        finally:
            conn.close()

    # ── RESULTS ──────────────────────────────────────────────
    def save_result(self, submission_id, result):
        conn = self.get_connection()
        try:
            c = conn.execute('''
                INSERT INTO results
                (submission_id,total_score,total_max,percentage,grade,
                 question_results,summary_feedback,red_flags,overall_confidence,needs_review)
                VALUES (?,?,?,?,?,?,?,?,?,?)''', (
                submission_id,
                result.get("total_score", 0),
                result.get("total_max", 100),
                result.get("percentage", 0),
                result.get("grade", "F"),
                json.dumps(result.get("question_results", {})),
                result.get("summary_feedback", ""),
                json.dumps(result.get("all_red_flags", [])),
                result.get("overall_confidence", 0),
                1 if result.get("needs_manual_review") else 0))
            conn.commit()
            return c.lastrowid
        finally:
            conn.close()

    def delete_result(self, submission_id):
        """Remove a result so it can be re-graded and re-saved."""
        conn = self.get_connection()
        try:
            conn.execute("DELETE FROM results WHERE submission_id=?", (submission_id,))
            conn.commit()
        finally:
            conn.close()

    def get_result_by_submission(self, submission_id):
        conn = self.get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM results WHERE submission_id=?", (submission_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["question_results"] = json.loads(res.get("question_results") or "{}")
            res["red_flags"] = json.loads(res.get("red_flags") or "[]")
            res["all_red_flags"] = res["red_flags"]
            return res
        finally:
            conn.close()

    def results_for_paper(self, paper_id):
        conn = self.get_connection()
        try:
            rows = conn.execute('''
                SELECT r.*, s.student_name as _sub_name, s.student_roll as student_roll,
                       u.full_name as _acct_name
                FROM results r
                JOIN submissions s ON r.submission_id=s.id
                JOIN users u ON s.student_id=u.id
                WHERE s.paper_id=? ORDER BY r.percentage DESC''', (paper_id,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["student_name"] = d.pop("_sub_name", "") or d.pop("_acct_name", "")
                d.pop("_acct_name", None)
                d["student_roll"] = d.get("student_roll") or ""
                d["question_results"] = json.loads(d.get("question_results") or "{}")
                out.append(d)
            return out
        finally:
            conn.close()

    def apply_override(self, result_id, new_score, total_max, notes, teacher_id):
        conn = self.get_connection()
        try:
            pct = round(new_score / total_max * 100, 1) if total_max else 0
            conn.execute('''
                UPDATE results SET manual_override=1, override_by=?, override_notes=?,
                total_score=?, percentage=?, grade=? WHERE id=?''',
                (teacher_id, notes, new_score, pct, self._grade(pct), result_id))
            conn.commit()
        finally:
            conn.close()

    # ── HISTORY ──────────────────────────────────────────────
    def save_history(self, student_id, paper_id, subject, title, score, total_marks, percentage, grade):
        conn = self.get_connection()
        try:
            conn.execute('''
                INSERT INTO student_history
                (student_id,paper_id,subject,title,score,total_marks,percentage,grade)
                VALUES (?,?,?,?,?,?,?,?)''',
                (student_id, paper_id, subject, title, score, total_marks, percentage, grade))
            conn.commit()
        finally:
            conn.close()

    def get_history(self, student_id):
        conn = self.get_connection()
        try:
            rows = conn.execute(
                "SELECT * FROM student_history WHERE student_id=? ORDER BY recorded_at DESC",
                (student_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    # ── AUDIT ────────────────────────────────────────────────
    def log_audit(self, action, performed_by, details=""):
        conn = self.get_connection()
        try:
            conn.execute(
                "INSERT INTO audit_log (action,performed_by,details) VALUES (?,?,?)",
                (action, str(performed_by), str(details)))
            conn.commit()
        finally:
            conn.close()

    def _grade(self, pct):
        for t, g in [(90,"A+"),(85,"A"),(80,"A-"),(75,"B+"),(70,"B"),
                     (65,"B-"),(60,"C+"),(55,"C"),(50,"D"),(0,"F")]:
            if pct >= t:
                return g
        return "F"


DB = DatabaseManager
