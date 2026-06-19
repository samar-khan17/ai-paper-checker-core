"""
Smart Paper Checker — AI-Powered Academic Assessment
Run: python main.py
"""

import sys, os, json, shutil, threading, logging, time, webbrowser
from pathlib import Path
from datetime import datetime
from collections import deque

def check_deps():
    missing = []
    for pkg in ["customtkinter","PIL","openai"]:
        try: __import__(pkg)
        except ImportError: missing.append(pkg)
    if missing:
        print(f"Missing: {', '.join(missing)}\nRun: pip install -r requirements.txt")
        sys.exit(1)
check_deps()

import customtkinter as ctk
from tkinter import filedialog, messagebox
import tkinter as tk

def resource_path(name: str) -> str:
    base = getattr(sys, "_MEIPASS", str(Path(__file__).parent))
    return os.path.join(base, name)

ICON_PATH = resource_path("app_icon.ico")

def apply_icon(window):
    try:
        if os.path.exists(ICON_PATH):
            window.iconbitmap(ICON_PATH)
    except Exception:
        pass

try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartPaperChecker.App.1")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from config import (APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW,
                    SUBJECTS, DIFFICULTY_LEVELS, UPLOAD_DIR, REPORT_DIR, ALLOWED_EXTENSIONS)
from core.security import pwd_mgr, tracker, sessions
from core.ai_grader import AIGrader
from core.question_parser import QuestionParser
from database.db_manager import DB
import core.settings_store as settings_store

logger = logging.getLogger("main")

db     = DB()
grader = AIGrader()
parser = QuestionParser()

# ── Color Palette ─────────────────────────────────────────────
C = {
    "bg_dark":    "#0d0d1a",
    "bg_card":    "#13132a",
    "bg_sidebar": "#0a0a18",
    "accent":     "#6366f1",
    "accent2":    "#8b5cf6",
    "success":    "#22c55e",
    "warning":    "#f59e0b",
    "danger":     "#ef4444",
    "text":       "#e2e8f0",
    "text_muted": "#64748b",
    "border":     "#1e1e3a",
}

# ── Rate Limiter (NVIDIA NIM safe: 37 RPM) ────────────────────
class RateLimiter:
    def __init__(self, max_rpm=35):
        self.max_rpm = max_rpm
        self._times = deque()

    def wait_if_needed(self):
        now = time.time()
        while self._times and self._times[0] < now - 60:
            self._times.popleft()
        if len(self._times) >= self.max_rpm:
            sleep_for = 60 - (now - self._times[0]) + 0.5
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._times.append(time.time())

rate_limiter = RateLimiter()

# ═══════════════════════════════════════════════════════════════
#  HELPER WIDGETS
# ═══════════════════════════════════════════════════════════════

def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=14,
                        border_width=1, border_color=C["border"], **kw)

def label(parent, text, size=13, weight="normal", color=None, **kw):
    return ctk.CTkLabel(parent, text=text,
                        font=ctk.CTkFont(size=size, weight=weight),
                        text_color=color or C["text"], **kw)

def btn(parent, text, command, color=None, height=40, width=None, **kw):
    kwargs = dict(text=text, command=command, height=height,
                  corner_radius=10, fg_color=color or C["accent"],
                  hover_color=C["accent2"], font=ctk.CTkFont(size=13))
    if width: kwargs["width"] = width
    return ctk.CTkButton(parent, **kwargs, **kw)

def entry(parent, placeholder="", show="", height=40, **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, show=show,
                        height=height, corner_radius=10, **kw)

def section_title(parent, text, pady=(20,8)):
    f = ctk.CTkFrame(parent, fg_color="transparent")
    f.pack(fill="x", pady=pady)
    label(f, text, size=18, weight="bold").pack(side="left")
    ctk.CTkFrame(f, height=2, fg_color=C["accent"]).pack(
        side="left", fill="x", expand=True, padx=(12,0), pady=(8,0))
    return f

def status_badge(parent, text, color):
    return ctk.CTkLabel(parent, text=text, fg_color=color, corner_radius=8,
                        font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=3)

def fix_popup(w):
    """Bring any CTkToplevel to the front and lock interaction."""
    w.grab_set(); w.lift(); w.focus_force()
    w.attributes('-topmost', True)
    w.after(150, lambda: w.attributes('-topmost', False))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# ═══════════════════════════════════════════════════════════════
#  SCROLLABLE TABLE (generic)
# ═══════════════════════════════════════════════════════════════

class Table(ctk.CTkScrollableFrame):
    def __init__(self, parent, columns: list, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.columns = columns
        self._build_header()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=C["accent"], corner_radius=8)
        hdr.pack(fill="x", pady=(0,4))
        for i, (col, w) in enumerate(self.columns):
            label(hdr, col, size=12, weight="bold").grid(row=0, column=i, padx=8, pady=8, sticky="w")
            hdr.grid_columnconfigure(i, minsize=w)

    def add_row(self, values: list, on_click=None, left_color=None):
        if left_color and left_color != "white":
            outer = ctk.CTkFrame(self, fg_color=left_color, corner_radius=8)
            outer.pack(fill="x", pady=2)
            row = ctk.CTkFrame(outer, fg_color=C["bg_card"], corner_radius=7)
            row.pack(fill="x", padx=(5,1), pady=1)
        else:
            row = ctk.CTkFrame(self, fg_color=C["bg_card"], corner_radius=8,
                               border_width=1, border_color=C["border"])
            row.pack(fill="x", pady=2)

        for i, (val, (col, w)) in enumerate(zip(values, self.columns)):
            if isinstance(val, tuple):
                status_badge(row, val[0], val[1]).grid(row=0, column=i, padx=8, pady=6, sticky="w")
            else:
                label(row, str(val), size=12).grid(row=0, column=i, padx=8, pady=6, sticky="w")
            row.grid_columnconfigure(i, minsize=w)

        if on_click:
            row.bind("<Button-1>", lambda e: on_click())
            for child in row.winfo_children():
                child.bind("<Button-1>", lambda e: on_click())

    def clear(self):
        for w in self.winfo_children():
            if isinstance(w, ctk.CTkFrame) and w.cget("fg_color") not in (C["accent"],):
                w.destroy()

    def empty(self, text="Nothing here yet."):
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", pady=28)
        label(row, text, size=13, color=C["text_muted"]).pack()

# ═══════════════════════════════════════════════════════════════
#  LOGIN SCREEN
# ═══════════════════════════════════════════════════════════════

class LoginScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=C["bg_dark"], corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        left = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, width=480)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        ctk.CTkFrame(left, fg_color="transparent").pack(expand=True)
        label(left, "📝", size=72).pack()
        label(left, APP_NAME, size=28, weight="bold").pack(pady=(8,4))
        label(left, "AI-Powered Academic Assessment", size=14, color=C["text_muted"]).pack()
        ctk.CTkFrame(left, height=2, width=120, fg_color=C["accent"]).pack(pady=20)
        for f in ["🤖  NVIDIA AI Grading Engine","🔒  Z-Plus Security",
                  "📊  Analytics Dashboard","📄  PDF Reports",
                  "🚩  Red Flag Detection","✏️  Manual Override"]:
            label(left, f, size=13, color=C["text_muted"]).pack(pady=3)
        ctk.CTkFrame(left, fg_color="transparent").pack(expand=True)
        label(left, f"v{APP_VERSION}", size=11, color=C["text_muted"]).pack(pady=12)

        right = ctk.CTkFrame(self, fg_color=C["bg_dark"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)
        wrap = ctk.CTkFrame(right, fg_color="transparent", width=400)
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        label(wrap, "Welcome Back", size=26, weight="bold").pack(anchor="w")
        label(wrap, "Sign in to your account", size=13, color=C["text_muted"]).pack(anchor="w", pady=(2,28))

        label(wrap, "Username", size=13, weight="bold").pack(anchor="w")
        self.u_entry = entry(wrap, "Enter username", width=380)
        self.u_entry.pack(pady=(4,14))

        label(wrap, "Password", size=13, weight="bold").pack(anchor="w")
        self.p_entry = entry(wrap, "Enter password", show="•", width=380)
        self.p_entry.pack(pady=(4,14))

        label(wrap, "Role", size=13, weight="bold").pack(anchor="w")
        self.role = ctk.StringVar(value="teacher")
        rf = ctk.CTkFrame(wrap, fg_color="transparent"); rf.pack(anchor="w", pady=(4,20))
        ctk.CTkRadioButton(rf, text="👩‍🏫 Teacher", variable=self.role,
                           value="teacher", fg_color=C["accent"]).pack(side="left", padx=(0,24))
        ctk.CTkRadioButton(rf, text="🎓 Student", variable=self.role,
                           value="student", fg_color=C["accent"]).pack(side="left")

        self.err = label(wrap, "", color=C["danger"])
        self.err.pack(pady=(0,8))
        btn(wrap, "Sign In", self._login, height=46, width=380).pack()
        ctk.CTkButton(wrap, text="Create Account", width=380, height=46, corner_radius=10,
                      fg_color="transparent", border_width=1, border_color=C["accent"],
                      text_color=C["accent"], hover_color=C["bg_card"],
                      font=ctk.CTkFont(size=13),
                      command=self._open_register).pack(pady=(10,0))
        self.u_entry.bind("<Return>", lambda e: self._login())
        self.p_entry.bind("<Return>", lambda e: self._login())

    def _login(self):
        u = self.u_entry.get().strip(); p = self.p_entry.get(); role = self.role.get()
        if not u or not p:
            self.err.configure(text="Please fill all fields."); return
        locked, mins = tracker.is_locked(u)
        if locked:
            self.err.configure(text=f"Locked. Try in {mins} min."); return
        user = db.get_user(u)
        if not user or user["role"] != role or not pwd_mgr.verify_password(p, user["password_hash"]):
            tracker.record(u, False)
            self.err.configure(text=f"Invalid credentials. {tracker.remaining(u)} attempts left.")
            return
        tracker.record(u, True)
        db.touch_login(user["id"])
        token = sessions.create(dict(user))
        db.log_audit("LOGIN", u)
        self.app.login_success(dict(user), token)

    def _open_register(self):
        w = ctk.CTkToplevel(self); w.title("Create Account")
        w.geometry("420x460"); w.resizable(False, False)
        w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(250, lambda: apply_icon(w))
        w.after(200, lambda: fix_popup(w))

        f = ctk.CTkFrame(w, fg_color="transparent")
        f.pack(padx=36, pady=36, fill="both", expand=True)
        label(f, "Create Account", size=20, weight="bold").pack(pady=(0,20))
        fields = {}
        for lbl, ph, sh in [("Full Name","Your full name",""),
                             ("Username","Choose username",""),
                             ("Password","Min 6 characters","•")]:
            label(f, lbl, size=12, weight="bold").pack(anchor="w")
            e = entry(f, ph, show=sh, width=340); e.pack(pady=(3,12))
            fields[lbl] = e
        rv = ctk.StringVar(value="student")
        rf = ctk.CTkFrame(f, fg_color="transparent"); rf.pack(anchor="w", pady=(0,16))
        ctk.CTkRadioButton(rf, text="Teacher", variable=rv, value="teacher",
                           fg_color=C["accent"]).pack(side="left", padx=(0,20))
        ctk.CTkRadioButton(rf, text="Student", variable=rv, value="student",
                           fg_color=C["accent"]).pack(side="left")
        msg = label(f, "", color=C["success"], wraplength=320); msg.pack()

        def do():
            full  = fields["Full Name"].get().strip()
            uname = fields["Username"].get().strip()
            pw    = fields["Password"].get()
            if not full or not uname or not pw:
                msg.configure(text="Please fill in all fields.", text_color=C["danger"]); return
            if db.get_user(uname):
                msg.configure(text=f"Username '{uname}' is already taken.", text_color=C["danger"]); return
            try:
                pw_h = pwd_mgr.hash_password(pw)
                db.create_user(uname, pw_h, rv.get(), full)
            except ValueError as ve:
                msg.configure(text=str(ve), text_color=C["danger"]); return
            except Exception as e:
                txt = "Username is already taken." if "UNIQUE" in str(e).upper() else str(e)
                msg.configure(text=txt, text_color=C["danger"]); return
            db.log_audit("ACCOUNT_CREATED", uname, f"role={rv.get()}")
            w.destroy()
            self.err.configure(
                text=f"✅ Account created for '{uname}'. Please sign in.",
                text_color=C["success"])
            self.role.set(rv.get())
            self.u_entry.delete(0, "end"); self.u_entry.insert(0, uname)
            self.p_entry.delete(0, "end"); self.p_entry.focus_set()

        btn(f, "Create Account", do, height=44, width=340).pack(pady=(12,0))

# ═══════════════════════════════════════════════════════════════
#  MAIN APP SHELL
# ═══════════════════════════════════════════════════════════════

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW)
        self.configure(fg_color=C["bg_dark"])
        apply_icon(self)
        self.after(250, lambda: apply_icon(self))
        self._center_window()
        self.user = self.token = self._frame = None
        self._show(LoginScreen)

    def _center_window(self):
        try:
            self.update_idletasks()
            w, h = (int(x) for x in WINDOW_SIZE.split("x"))
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{w}x{h}+{max(0,(sw-w)//2)}+{max(0,(sh-h)//2-20)}")
        except Exception:
            pass

    def _show(self, ScreenClass, **kw):
        if self._frame: self._frame.destroy()
        self._frame = ScreenClass(self, self, **kw)
        self._frame.pack(fill="both", expand=True)

    def login_success(self, user, token):
        self.user = user; self.token = token
        self._show(DashboardScreen)

    def logout(self):
        if self.token: sessions.destroy(self.token)
        self.user = self.token = None
        self._show(LoginScreen)

# ═══════════════════════════════════════════════════════════════
#  DASHBOARD SHELL
# ═══════════════════════════════════════════════════════════════

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=C["bg_dark"], corner_radius=0)
        self.app = app
        self.user = app.user
        self.role = self.user.get("role", "student")
        self._content = None
        self._nav_btns = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sb = ctk.CTkFrame(self, width=230, fg_color=C["bg_sidebar"], corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew"); sb.grid_propagate(False)

        label(sb, "📝", size=40).pack(pady=(24,4))
        label(sb, APP_NAME, size=14, weight="bold").pack()
        ctk.CTkLabel(sb,
            text="👩‍🏫 Teacher" if self.role=="teacher" else "🎓 Student",
            fg_color=C["accent"], corner_radius=8,
            font=ctk.CTkFont(size=11, weight="bold"), padx=10, pady=3
        ).pack(pady=(4,2))
        label(sb, self.user.get("full_name",""), size=12, color=C["text_muted"]).pack(pady=(0,16))
        ctk.CTkFrame(sb, height=1, fg_color=C["border"]).pack(fill="x", padx=16, pady=(0,12))

        nav = self._teacher_nav() if self.role=="teacher" else self._student_nav()
        for key, icon, title in nav:
            b = ctk.CTkButton(sb, text=f"  {icon}  {title}", anchor="w",
                              height=46, corner_radius=10, fg_color="transparent",
                              hover_color=C["bg_card"], text_color=C["text"],
                              font=ctk.CTkFont(size=13),
                              command=lambda k=key: self._nav(k))
            b.pack(fill="x", padx=12, pady=2)
            self._nav_btns[key] = b

        ctk.CTkFrame(sb, fg_color="transparent").pack(expand=True)
        ctk.CTkFrame(sb, height=1, fg_color=C["border"]).pack(fill="x", padx=16, pady=8)
        ctk.CTkButton(sb, text="  🚪  Sign Out", anchor="w", height=44, corner_radius=10,
                      fg_color="transparent", hover_color="#2a0a0a",
                      text_color=C["danger"], font=ctk.CTkFont(size=13),
                      command=self.app.logout).pack(fill="x", padx=12, pady=(0,16))

        # Right area
        self._area = ctk.CTkFrame(self, fg_color=("#f1f5f9","#080814"), corner_radius=0)
        self._area.grid(row=0, column=1, sticky="nsew")
        self._area.grid_columnconfigure(0, weight=1)

        if self.role == "teacher":
            self._area.grid_rowconfigure(0, weight=0)
            self._area.grid_rowconfigure(1, weight=1)
            self._stat_bar = ctk.CTkFrame(self._area, fg_color=C["bg_sidebar"],
                                          corner_radius=0, height=88)
            self._stat_bar.grid(row=0, column=0, sticky="ew")
            self._stat_bar.grid_propagate(False)
            self._stat_bar.grid_columnconfigure((0,1,2,3), weight=1)
            self._refresh_stats()
            self._content_area = ctk.CTkFrame(self._area, fg_color="transparent", corner_radius=0)
            self._content_area.grid(row=1, column=0, sticky="nsew")
        else:
            self._area.grid_rowconfigure(0, weight=1)
            self._content_area = self._area

        self._content_area.grid_rowconfigure(0, weight=1)
        self._content_area.grid_columnconfigure(0, weight=1)

        default = "upload" if self.role=="teacher" else "papers"
        self._nav(default)

    def _refresh_stats(self):
        for w in self._stat_bar.winfo_children(): w.destroy()
        stats = db.stats_for_teacher(self.user["id"])
        items = [("📋", "Papers Set Up", stats["papers"]),
                 ("✅", "Papers Checked", stats["checked"]),
                 ("👥", "Students Graded", stats["students"]),
                 ("📊", "Average Score", f"{stats['avg']}%")]
        for i, (icon, title, val) in enumerate(items):
            c = ctk.CTkFrame(self._stat_bar, fg_color=C["bg_card"], corner_radius=10)
            c.grid(row=0, column=i, padx=(12 if i==0 else 6, 6 if i<3 else 12),
                   pady=14, sticky="nsew")
            inner = ctk.CTkFrame(c, fg_color="transparent"); inner.pack(expand=True, fill="both")
            ctk.CTkLabel(inner, text=icon, font=ctk.CTkFont(size=22)).pack(side="left", padx=(12,8))
            vf = ctk.CTkFrame(inner, fg_color="transparent"); vf.pack(side="left")
            ctk.CTkLabel(vf, text=str(val),
                         font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=C["accent"]).pack(anchor="w")
            ctk.CTkLabel(vf, text=title,
                         font=ctk.CTkFont(size=10),
                         text_color=C["text_muted"]).pack(anchor="w")

    def _teacher_nav(self):
        return [
            ("upload",  "📥", "Set Up Paper"),
            ("check",   "🧮", "Check Answer Sheet"),
            ("bulk",    "📦", "Bulk Check Papers"),
            ("papers",  "📋", "My Papers"),
            ("grade",   "✅", "Checked Sheets"),
            ("results", "📊", "Results & Analytics"),
            ("analytics","📈", "Class Insights"),
            ("override","✏️", "Manual Override"),
            ("settings","⚙️", "Settings & API"),
        ]

    def _student_nav(self):
        return [
            ("papers",  "📋", "Available Papers"),
            ("submit",  "📤", "Submit Answer"),
            ("results", "📈", "My Results"),
            ("history", "📅", "My History"),
        ]

    def _nav(self, key):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=C["accent"] if k==key else "transparent")
        if self._content: self._content.destroy()
        screen_map = {
            "upload":   UploadPaperScreen,
            "check":    CheckSheetScreen,
            "bulk":     BulkCheckScreen,
            "papers":   ManagePapersScreen,
            "grade":    GradeScreen,
            "results":  ResultsScreen,
            "analytics":AnalyticsScreen,
            "override": OverrideScreen,
            "settings": SettingsScreen,
            "submit":   StudentSubmitScreen,
            "history":  HistoryScreen,
        }
        cls = screen_map.get(key)
        if cls:
            self._content = cls(self._content_area, self.app)
            self._content.grid(row=0, column=0, sticky="nsew")
        if self.role == "teacher":
            self.after(100, self._refresh_stats)

# ═══════════════════════════════════════════════════════════════
#  TEACHER — UPLOAD PAPER
# ═══════════════════════════════════════════════════════════════

class UploadPaperScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self.files = {"q_paper_path":"","answer_key_path":"","marking_path":"","sample_path":""}
        self.paper_id = None
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "📥  Set Up Question Paper")
        label(scroll, "Upload a question paper + answer key once. "
              "Then use 'Check Answer Sheet' or 'Bulk Check' to mark students.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,10))

        info = card(scroll); info.pack(fill="x", pady=(0,16))
        ig = ctk.CTkFrame(info, fg_color="transparent"); ig.pack(fill="x", padx=20, pady=16)
        ig.grid_columnconfigure((0,1), weight=1)

        label(ig, "Paper Title *", size=12, weight="bold").grid(row=0,column=0,columnspan=2,sticky="w")
        self.title_e = entry(ig, "e.g. OOP Mid Term 2024")
        self.title_e.grid(row=1,column=0,columnspan=2,sticky="ew",pady=(4,12))

        label(ig, "Total Marks *", size=12, weight="bold").grid(row=2,column=0,sticky="w")
        label(ig, "Subject *", size=12, weight="bold").grid(row=2,column=1,sticky="w",padx=(16,0))
        self.marks_e = entry(ig, "100"); self.marks_e.grid(row=3,column=0,sticky="ew",pady=(4,12))
        self.subject_var = ctk.StringVar(value=SUBJECTS[0])
        ctk.CTkOptionMenu(ig, values=SUBJECTS, variable=self.subject_var,
                          height=40, corner_radius=10, fg_color=C["bg_dark"]
                          ).grid(row=3,column=1,sticky="ew",padx=(16,0),pady=(4,12))

        label(ig, "Difficulty Level", size=12, weight="bold").grid(row=4,column=0,sticky="w")
        self.diff_var = ctk.StringVar(value="3 - Medium")
        ctk.CTkOptionMenu(ig, values=[f"{k} - {v}" for k,v in DIFFICULTY_LEVELS.items()],
                          variable=self.diff_var, height=40, corner_radius=10,
                          fg_color=C["bg_dark"]).grid(row=5,column=0,sticky="ew",pady=(4,0))

        section_title(scroll, "📁  Upload Files")
        files_card = card(scroll); files_card.pack(fill="x", pady=(0,16))
        fg = ctk.CTkFrame(files_card, fg_color="transparent"); fg.pack(fill="x", padx=20, pady=16)

        self.file_labels = {}
        for key, title, icon, required in [
            ("q_paper_path",   "Question Paper",  "📄", True),
            ("answer_key_path","Answer Key",       "🔑", True),
            ("marking_path",   "Marking Scheme",  "📋", False),
            ("sample_path",    "Sample Solution", "✅", False),
        ]:
            row = ctk.CTkFrame(fg, fg_color=C["bg_dark"], corner_radius=10)
            row.pack(fill="x", pady=4)
            ri = ctk.CTkFrame(row, fg_color="transparent"); ri.pack(fill="x", padx=12, pady=10)
            label(ri, f"{icon}  {title}", size=13, weight="bold").pack(side="left")
            if required: label(ri, " *", size=13, color=C["danger"]).pack(side="left")
            fl = label(ri, "No file selected", size=12, color=C["text_muted"])
            fl.pack(side="left", padx=12)
            self.file_labels[key] = fl
            btn(ri, "Browse", lambda k=key: self._pick(k), height=32, width=90).pack(side="right")

        self.status = label(scroll, "", color=C["success"]); self.status.pack(pady=(8,4))
        self.prog = ctk.CTkProgressBar(scroll, height=8, corner_radius=4, progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))
        self.save_btn = btn(scroll, "💾  Save Paper", self._create, height=50)
        self.save_btn.pack(fill="x")

    def _pick(self, key):
        path = filedialog.askopenfilename(
            filetypes=[("Supported","*.jpg *.jpeg *.png *.pdf *.docx"),("All","*.*")])
        if path:
            self.files[key] = path
            self.file_labels[key].configure(text=Path(path).name, text_color=C["success"])

    def _create(self):
        title = self.title_e.get().strip()
        if not title:
            self.status.configure(text="⚠ Paper title required.", text_color=C["danger"]); return
        if not self.files["q_paper_path"] or not self.files["answer_key_path"]:
            self.status.configure(text="⚠ Question Paper and Answer Key required.", text_color=C["danger"]); return
        try: marks = int(self.marks_e.get() or "100")
        except: marks = 100
        diff = int(self.diff_var.get().split(" - ")[0])

        self.status.configure(text="Creating paper...", text_color=C["text_muted"])
        self.prog.set(0.2); self.update()

        self.paper_id = db.create_paper(self.user["id"], self.subject_var.get(), title, marks, diff)
        self.prog.set(0.4); self.update()

        updates = {}
        for key, src in self.files.items():
            if src:
                sub = {"q_paper_path":"question_papers","answer_key_path":"answer_keys",
                       "marking_path":"marking_schemes","sample_path":"sample_solutions"}.get(key,"")
                dest_dir = UPLOAD_DIR / sub
                dest = dest_dir / f"{self.paper_id}_{Path(src).name}"
                shutil.copy2(src, dest); updates[key] = str(dest)

        self.prog.set(0.6)
        self.status.configure(text="📖 Reading questions via AI...", text_color=C["warning"])
        self.save_btn.configure(state="disabled"); self.update()

        q_path = updates.get("q_paper_path",""); ak_path = updates.get("answer_key_path","")
        paper_id = self.paper_id

        def work():
            from core import ocr
            img_dir = UPLOAD_DIR / "question_papers" / f"{paper_id}_pages"
            parsed_q, parsed_ak = [], {}
            try:
                text = ocr.extract_text(q_path) if q_path else ""
                if text: parsed_q = parser.parse_questions(text)
                if not parsed_q and q_path:
                    imgs = ocr.to_images(q_path, str(img_dir))
                    if imgs: parsed_q = grader.read_questions_from_images(imgs)
            except Exception as e: logger.warning(f"question parse failed: {e}")
            try:
                text = ocr.extract_text(ak_path) if ak_path else ""
                if text: parsed_ak = parser.parse_answer_key(text)
                if not parsed_ak and ak_path:
                    imgs = ocr.to_images(ak_path, str(img_dir))
                    if imgs: parsed_ak = grader.read_answers_from_images(imgs)
            except Exception as e: logger.warning(f"answer key parse failed: {e}")
            updates["parsed_questions"] = json.dumps(parsed_q)
            updates["parsed_answers"] = json.dumps({str(k):v for k,v in parsed_ak.items()})
            db.update_paper(paper_id, updates)
            db.log_audit("PAPER_SAVED", self.user["username"], f"paper_id={paper_id}")
            self.after(0, lambda: self._saved(title, paper_id, len(parsed_q)))

        threading.Thread(target=work, daemon=True).start()

    def _saved(self, title, paper_id, nq):
        self.prog.set(1.0); self.save_btn.configure(state="normal")
        extra = f"{nq} question(s) detected." if nq else "No questions auto-detected."
        self.status.configure(
            text=f"✅ Paper '{title}' saved (ID: {paper_id}). {extra}",
            text_color=C["success"])

# ═══════════════════════════════════════════════════════════════
#  MANAGE PAPERS
# ═══════════════════════════════════════════════════════════════

class ManagePapersScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self.role = self.user.get("role")
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "📋  " + ("My Papers" if self.role=="teacher" else "Available Papers"))

        if self.role == "teacher":
            # Custom table with View Details button
            scroll = ctk.CTkScrollableFrame(f, fg_color="transparent")
            scroll.pack(fill="both", expand=True)
            self._scroll = scroll
            self._load_teacher(scroll)
        else:
            cols = [("ID",60),("Title",240),("Subject",120),("Marks",80),("Difficulty",100),("Created",160)]
            self.table = Table(f, cols); self.table.pack(fill="both", expand=True)
            papers = db.all_papers()
            if not papers: self.table.empty("No papers available yet.")
            for p in papers:
                diff = DIFFICULTY_LEVELS.get(p.get("difficulty",3),"Medium")
                self.table.add_row([p["id"],p["title"],p["subject"],p["total_marks"],diff,p["created_at"][:10]])

    def _load_teacher(self, scroll):
        for w in scroll.winfo_children(): w.destroy()
        papers = db.papers_by_teacher(self.user["id"])
        if not papers:
            label(scroll, "No papers yet. Go to 'Set Up Paper' to add one.",
                  size=13, color=C["text_muted"]).pack(pady=40)
            return
        # Header
        hdr = ctk.CTkFrame(scroll, fg_color=C["accent"], corner_radius=8)
        hdr.pack(fill="x", pady=(0,4))
        for i, (col, w) in enumerate([("ID",50),("Title",220),("Subject",110),("Marks",70),("Created",110),("Action",120)]):
            label(hdr, col, size=12, weight="bold").grid(row=0,column=i,padx=8,pady=8,sticky="w")
            hdr.grid_columnconfigure(i, minsize=w)

        for p in papers:
            row = ctk.CTkFrame(scroll, fg_color=C["bg_card"], corner_radius=8,
                               border_width=1, border_color=C["border"])
            row.pack(fill="x", pady=2)
            for i, (val, w) in enumerate([(p["id"],50),(p["title"],220),(p["subject"],110),
                                           (p["total_marks"],70),(p["created_at"][:10],110)]):
                label(row, str(val), size=12).grid(row=0,column=i,padx=8,pady=6,sticky="w")
                row.grid_columnconfigure(i, minsize=w)
            af = ctk.CTkFrame(row, fg_color="transparent")
            af.grid(row=0, column=5, padx=8, pady=4, sticky="w")
            row.grid_columnconfigure(5, minsize=120)
            btn(af, "Details", lambda pid=p["id"]: self._view(pid),
                height=30, width=80, color=C["accent"]).pack(side="left", padx=(0,4))

    def _view(self, paper_id):
        p = db.get_paper(paper_id)
        if p: PaperDetailsPopup(self, p)


class PaperDetailsPopup(ctk.CTkToplevel):
    def __init__(self, parent, paper):
        super().__init__(parent)
        self.title("Paper Details")
        self.geometry("560x600"); self.configure(fg_color=C["bg_dark"])
        apply_icon(self); self.after(250, lambda: apply_icon(self))
        self.after(100, lambda: fix_popup(self))

        f = ctk.CTkScrollableFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=24)

        label(f, paper["title"], size=20, weight="bold").pack(anchor="w")
        label(f, f"{paper['subject']}  •  {paper['total_marks']} marks  •  ID: {paper['id']}",
              size=13, color=C["text_muted"]).pack(anchor="w", pady=(4,16))

        ctk.CTkFrame(f, height=1, fg_color=C["border"]).pack(fill="x", pady=(0,16))

        for section_lbl, key, icon in [
            ("Question Paper", "q_paper_path", "📄"),
            ("Answer Key",     "answer_key_path","🔑"),
            ("Marking Scheme", "marking_path",  "📋"),
            ("Sample Solution","sample_path",   "✅"),
        ]:
            path = paper.get(key,"")
            row = ctk.CTkFrame(f, fg_color=C["bg_card"], corner_radius=10)
            row.pack(fill="x", pady=4)
            rf = ctk.CTkFrame(row, fg_color="transparent"); rf.pack(fill="x", padx=16, pady=10)
            label(rf, f"{icon}  {section_lbl}", size=13, weight="bold").pack(side="left")
            if path and os.path.exists(path):
                label(rf, Path(path).name, size=11, color=C["text_muted"]).pack(side="left", padx=10)
                btn(rf, "Open", lambda p=path: os.startfile(p) if os.name=="nt" else None,
                    height=28, width=70).pack(side="right")
            else:
                label(rf, "Not uploaded", size=11, color=C["text_muted"]).pack(side="left", padx=10)

        ctk.CTkFrame(f, height=1, fg_color=C["border"]).pack(fill="x", pady=16)

        # Questions preview
        try:
            qs = json.loads(paper.get("parsed_questions","[]"))
            if qs:
                label(f, f"Questions Detected ({len(qs)})", size=15, weight="bold").pack(anchor="w", pady=(0,8))
                for q in qs[:20]:
                    qc = ctk.CTkFrame(f, fg_color=C["bg_card"], corner_radius=8)
                    qc.pack(fill="x", pady=2)
                    label(qc, f"Q{q.get('number')}: {q.get('text','')[:80]}…",
                          size=11, color=C["text_muted"]).pack(anchor="w", padx=12, pady=6)
        except Exception:
            pass

        btn(f, "Close", self.destroy, height=40).pack(pady=(16,0), fill="x")

# ═══════════════════════════════════════════════════════════════
#  STUDENT — SUBMIT
# ═══════════════════════════════════════════════════════════════

class StudentSubmitScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user; self.answer_path = ""
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "📤  Submit Answer Sheet")

        c = card(scroll); c.pack(fill="x", pady=(0,16))
        f = ctk.CTkFrame(c, fg_color="transparent"); f.pack(fill="x", padx=20, pady=16)
        label(f, "Select Paper *", size=12, weight="bold").pack(anchor="w")
        papers = db.all_papers()
        self.paper_map = {f"{p['id']} — {p['title']} ({p['subject']})": p for p in papers}
        self.paper_var = ctk.StringVar(
            value=list(self.paper_map.keys())[0] if self.paper_map else "No papers available")
        ctk.CTkOptionMenu(f, values=list(self.paper_map.keys()) or ["No papers available"],
                          variable=self.paper_var, height=42, corner_radius=10,
                          fg_color=C["bg_dark"], width=500).pack(anchor="w", pady=(4,0))

        c2 = card(scroll); c2.pack(fill="x", pady=(0,16))
        f2 = ctk.CTkFrame(c2, fg_color="transparent"); f2.pack(fill="x", padx=20, pady=16)
        label(f2, "Answer Sheet File *", size=12, weight="bold").pack(anchor="w")
        row = ctk.CTkFrame(f2, fg_color="transparent"); row.pack(fill="x", pady=(8,0))
        self.file_lbl = label(row, "No file selected", color=C["text_muted"])
        self.file_lbl.pack(side="left")
        btn(row, "Browse", self._pick, height=36, width=100).pack(side="left", padx=12)

        self.status = label(scroll, "", color=C["success"]); self.status.pack(pady=(12,4))
        self.prog = ctk.CTkProgressBar(scroll, height=8, corner_radius=4, progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))
        btn(scroll, "🚀  Submit & Grade", self._submit, height=50).pack(fill="x")

    def _pick(self):
        path = filedialog.askopenfilename(
            filetypes=[("Supported","*.jpg *.jpeg *.png *.pdf *.docx"),("All","*.*")])
        if path:
            self.answer_path = path
            self.file_lbl.configure(text=Path(path).name, text_color=C["success"])

    def _submit(self):
        key = self.paper_var.get()
        if key not in self.paper_map:
            self.status.configure(text="⚠ Select a valid paper.", text_color=C["danger"]); return
        if not self.answer_path:
            self.status.configure(text="⚠ Upload your answer sheet.", text_color=C["danger"]); return
        paper = self.paper_map[key]
        dest = UPLOAD_DIR/"student_answers"/f"{self.user['id']}_{paper['id']}_{Path(self.answer_path).name}"
        shutil.copy2(self.answer_path, dest)
        sub_id = db.create_submission(self.user["id"], paper["id"], str(dest))
        self.status.configure(text="🤖 AI grading...", text_color=C["warning"])
        self.prog.set(0.3); self.update()

        def grade_thread():
            try:
                questions = json.loads(paper.get("parsed_questions","[]"))
                answer_key = {int(k):v for k,v in json.loads(paper.get("parsed_answers","{}")).items()}
                if not questions:
                    questions = [{"number":1,"text":"General","marks":paper["total_marks"]}]
                    answer_key = {1:{"model_answer":"","marking_notes":"Award for correct content."}}
                from core import ocr
                imgs = ocr.to_images(str(dest), str(UPLOAD_DIR/"student_answers"))
                student_answers = grader.read_answer_sheet(imgs, questions) if imgs else {1: ""}
                result = grader.grade_paper(questions, answer_key, student_answers, paper["subject"])
                db.set_status(sub_id, "graded"); db.save_result(sub_id, result)
                db.save_history(self.user["id"], paper["id"], paper["subject"], paper["title"],
                                result["total_score"], result["total_max"],
                                result["percentage"], result["grade"])
                self.after(0, lambda: self._done(result))
            except Exception as e:
                self.after(0, lambda: self.status.configure(text=f"❌ {e}", text_color=C["danger"]))

        threading.Thread(target=grade_thread, daemon=True).start()

    def _done(self, result):
        self.prog.set(1.0)
        self.status.configure(text=f"✅ Graded! Grade: {result['grade']} | {result['percentage']}%",
                               text_color=C["success"])
        ResultPopup(self, result, {"paper_title":"","subject":""}, [])

# ═══════════════════════════════════════════════════════════════
#  TEACHER — CHECK A SINGLE STUDENT ANSWER SHEET
# ═══════════════════════════════════════════════════════════════

def _extract_docx_text(path):
    try:
        import docx as dx
        return "\n".join(p.text for p in dx.Document(path).paragraphs if p.text.strip())
    except Exception as e:
        logger.warning(f"docx read failed: {e}"); return ""

def save_report(parent, meta, result, files):
    try:
        from core.report import generate_report
        tmp = generate_report(meta, result, files)
        dest = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF Report","*.pdf")],
            initialfile=Path(tmp).name, title="Save Result Report")
        if dest:
            shutil.copy2(tmp, dest)
            messagebox.showinfo("Saved", f"Report saved:\n{dest}")
            try: os.startfile(dest)
            except Exception: pass
    except Exception as e:
        messagebox.showerror("Report Error", f"Could not create the report:\n{e}")


class CheckSheetScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user; self.files = []
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "🧮  Check a Student's Answer Sheet")
        label(scroll, "Pick the question paper, enter student details, upload their answer sheet, "
              "then click Run AI Test.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,10))

        c = card(scroll); c.pack(fill="x", pady=(0,14))
        f = ctk.CTkFrame(c, fg_color="transparent"); f.pack(fill="x", padx=20, pady=16)
        label(f, "Question Paper *", size=12, weight="bold").pack(anchor="w")
        papers = db.papers_by_teacher(self.user["id"])
        self.paper_map = {f"{p['id']} — {p['title']} ({p['subject']}, {p['total_marks']} marks)": p
                          for p in papers}
        keys = list(self.paper_map.keys())
        self.paper_var = ctk.StringVar(value=keys[0] if keys else "No papers — add one in 'Set Up Paper'")
        ctk.CTkOptionMenu(f, values=keys or ["No papers — add one in 'Set Up Paper'"],
                          variable=self.paper_var, height=42, corner_radius=10,
                          fg_color=C["bg_dark"], width=560).pack(anchor="w", pady=(4,0))

        c2 = card(scroll); c2.pack(fill="x", pady=(0,14))
        g = ctk.CTkFrame(c2, fg_color="transparent"); g.pack(fill="x", padx=20, pady=16)
        g.grid_columnconfigure((0,1), weight=1)
        label(g, "Student Name *", size=12, weight="bold").grid(row=0,column=0,sticky="w")
        label(g, "Student ID / Roll No *", size=12, weight="bold").grid(row=0,column=1,sticky="w",padx=(16,0))
        self.name_e = entry(g, "e.g. Ali Khan"); self.name_e.grid(row=1,column=0,sticky="ew",pady=(4,12))
        self.roll_e = entry(g, "e.g. FA21-BCS-001")
        self.roll_e.grid(row=1,column=1,sticky="ew",padx=(16,0),pady=(4,12))
        label(g, "Class / Section", size=12, weight="bold").grid(row=2,column=0,sticky="w")
        label(g, "Checking Mode *", size=12, weight="bold").grid(row=2,column=1,sticky="w",padx=(16,0))
        self.class_e = entry(g, "e.g. Y4-A"); self.class_e.grid(row=3,column=0,sticky="ew",pady=(4,0))
        self.mode_var = ctk.StringVar(value="Normal")
        ctk.CTkOptionMenu(g, values=["Lenient","Normal","Hard","Insane"], variable=self.mode_var,
                          height=40, corner_radius=10, fg_color=C["bg_dark"]
                          ).grid(row=3,column=1,sticky="ew",padx=(16,0),pady=(4,0))
        label(g, "Lenient 60%  ·  Normal 75%  ·  Hard 85%  ·  Insane 95%",
              size=10, color=C["text_muted"]).grid(row=4,column=0,columnspan=2,sticky="w",pady=(8,0))

        c3 = card(scroll); c3.pack(fill="x", pady=(0,14))
        f3 = ctk.CTkFrame(c3, fg_color="transparent"); f3.pack(fill="x", padx=20, pady=16)
        label(f3, "Student's Answer Sheet *", size=12, weight="bold").pack(anchor="w")
        label(f3, "JPG/PNG photos, PDF, or DOCX. Multiple pages supported.",
              size=11, color=C["text_muted"]).pack(anchor="w")
        row = ctk.CTkFrame(f3, fg_color="transparent"); row.pack(fill="x", pady=(8,0))
        self.file_lbl = label(row, "No files selected", color=C["text_muted"])
        self.file_lbl.pack(side="left")
        btn(row, "Browse", self._pick, height=36, width=100).pack(side="left", padx=12)

        self.status = label(scroll, "", color=C["success"]); self.status.pack(pady=(12,4))
        self.prog = ctk.CTkProgressBar(scroll, height=8, corner_radius=4, progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))
        self.check_btn = btn(scroll, "▶  Run AI Test", self._check, height=50)
        self.check_btn.pack(fill="x")

    def _pick(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Answer sheet","*.jpg *.jpeg *.png *.bmp *.webp *.pdf *.docx"),("All","*.*")])
        if paths:
            self.files = list(paths)
            self.file_lbl.configure(text=f"{len(self.files)} file(s) selected", text_color=C["success"])

    def _check(self):
        key = self.paper_var.get()
        if key not in self.paper_map:
            self.status.configure(text="⚠ Add a question paper first.", text_color=C["danger"]); return
        name = self.name_e.get().strip(); roll = self.roll_e.get().strip()
        if not name or not roll:
            self.status.configure(text="⚠ Enter student name and ID.", text_color=C["danger"]); return
        if not self.files:
            self.status.configure(text="⚠ Upload the student's answer sheet.", text_color=C["danger"]); return

        paper = self.paper_map[key]; cls = self.class_e.get().strip()
        mode = self.mode_var.get().lower()
        nq = len(json.loads(paper.get("parsed_questions","[]"))) or 1
        self._expected_s = min(25 + 7 * nq, 80)   # rough estimate
        self._t0 = time.time()
        self.check_btn.configure(state="disabled")
        self.status.configure(
            text=f"🤖 Starting AI check…  (expected ~{self._expected_s}s)",
            text_color=C["warning"])
        self.prog.set(0.1); self.update()
        srcs = list(self.files)

        def work():
            from core import ocr
            try:
                import re as _re
                roll_safe = _re.sub(r'[^\w\-]','_',roll) or "student"
                dest_dir = UPLOAD_DIR / str(paper["id"]) / roll_safe
                dest_dir.mkdir(parents=True, exist_ok=True)
                dests = []
                for src in srcs:
                    dest = dest_dir / Path(src).name
                    try: shutil.copy2(src, dest); dests.append(str(dest))
                    except Exception as e: logger.warning(f"copy failed: {e}")
                images = []
                for d in dests:
                    images.extend(ocr.to_images(d, str(dest_dir)))

                questions = json.loads(paper.get("parsed_questions","[]"))
                answer_key = {int(k):v for k,v in json.loads(paper.get("parsed_answers","{}")).items()}
                if not questions:
                    questions = [{"number":1,"text":"Overall answer","marks":paper["total_marks"]}]
                    answer_key = {1:{"model_answer":"","marking_notes":"Award for correct content."}}

                student_answers = {}
                if images:
                    self.after(0, lambda: (
                        self.status.configure(text="🔎 Reading answer sheet...", text_color=C["warning"]),
                        self.prog.set(0.45)))
                    student_answers = grader.read_answer_sheet(images, questions)
                    # Retry once if the read came back empty (never trust a single blank read).
                    if not student_answers:
                        student_answers = grader.read_answer_sheet(images, questions)
                for d in dests:
                    if Path(d).suffix.lower() == ".docx":
                        txt = _extract_docx_text(d)
                        for q in parser.parse_questions(txt):
                            student_answers.setdefault(q["number"], q["text"])
                        if txt and not student_answers: student_answers = {1: txt}
                # SAFETY: if there were images but we read nothing, this is a READ FAILURE.
                # Do NOT fabricate blanks and award a false zero — stop and tell the teacher.
                if images and not student_answers:
                    raise RuntimeError(
                        "Could not read the answer sheet (the AI returned nothing). "
                        "Please try again or upload a clearer photo/scan. "
                        "No grade was saved.")
                if not student_answers:
                    raise RuntimeError("No readable answers found. Nothing was graded.")

                self.after(0, lambda: (
                    self.status.configure(
                        text=f"📝 Marking {len(questions)} question(s)...", text_color=C["warning"]),
                    self.prog.set(0.7)))

                result = grader.grade_paper(questions, answer_key, student_answers, paper["subject"], mode)
                sub_id = db.create_submission(
                    self.user["id"], paper["id"], dests[0] if dests else "",
                    student_name=name, student_roll=roll, class_section=cls,
                    checking_mode=mode, answer_images=images)
                db.set_status(sub_id, "graded"); db.save_result(sub_id, result)
                db.save_history(self.user["id"], paper["id"], paper["subject"], paper["title"],
                                result["total_score"], result["total_max"],
                                result["percentage"], result["grade"])
                db.log_audit("CHECKED", self.user["username"],
                             f"student={name} roll={roll} mode={mode} grade={result['grade']}")
                meta = {"student_name":name,"student_roll":roll,"class_section":cls,
                        "checking_mode":mode,"paper_title":paper["title"],"subject":paper["subject"]}
                self.after(0, lambda: self._done(result, meta, images))
            except Exception as e:
                logger.error(f"Check error: {e}")
                self.after(0, lambda: (
                    self.status.configure(text=f"❌ Error: {e}", text_color=C["danger"]),
                    self.check_btn.configure(state="normal")))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, result, meta, files):
        self.prog.set(1.0); self.check_btn.configure(state="normal")
        took = time.time() - getattr(self, "_t0", time.time())
        self.status.configure(
            text=f"✅ {meta['student_name']} — {result['grade']} | {result['percentage']}% | "
                 f"{result['total_score']}/{result['total_max']}   "
                 f"⏱ took {took:.1f}s (expected ~{getattr(self,'_expected_s','?')}s)",
            text_color=C["success"])
        ResultPopup(self, result, meta, files)

# ═══════════════════════════════════════════════════════════════
#  RESULT POPUP
# ═══════════════════════════════════════════════════════════════

class ResultPopup(ctk.CTkToplevel):
    def __init__(self, parent, result, meta, files):
        super().__init__(parent)
        self.title("Result")
        self.geometry("640x640")
        self.configure(fg_color=C["bg_dark"])
        apply_icon(self); self.after(250, lambda: apply_icon(self))
        self.after(100, lambda: fix_popup(self))
        self.result, self.meta, self.files = result, meta, files
        self._build()

    def _build(self):
        f = ctk.CTkScrollableFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=24)

        label(f, "🎓 Checking Complete", size=22, weight="bold").pack(pady=(0,2))
        label(f, f"{self.meta.get('student_name','')}  •  ID: {self.meta.get('student_roll','')}",
              size=13, color=C["text_muted"]).pack()
        label(f, f"{self.meta.get('paper_title','')}  ({self.meta.get('subject','')})",
              size=12, color=C["text_muted"]).pack(pady=(0,4))

        grade = self.result["grade"]
        gc = {"A+":C["success"],"A":C["success"],"A-":C["success"],"B+":C["accent"],
              "B":C["accent"],"B-":C["accent"],"C+":C["warning"],"C":C["warning"],
              "C-":C["warning"],"D":C["danger"],"F":C["danger"]}
        ctk.CTkLabel(f, text=grade, font=ctk.CTkFont(size=46, weight="bold"),
                     text_color=gc.get(grade, C["text"])).pack(pady=2)
        label(f, f"{self.result['percentage']}%  •  {self.result['total_score']}/{self.result['total_max']} marks",
              size=15, color=C["text_muted"]).pack()

        conf = self.result.get("overall_confidence", 0)
        conf_color = C["success"] if conf >= 0.75 else C["warning"]
        label(f, f"AI Confidence: {round(conf*100)}%", size=11, color=conf_color).pack(pady=(2,8))

        btn(f, "⬇  Download Report (PDF)",
            lambda: save_report(self, self.meta, self.result, self.files),
            height=46, color=C["success"]).pack(fill="x", pady=(4,4))
        imgs = [x for x in (self.files or []) if Path(x).suffix.lower() in IMAGE_EXTS]
        if imgs:
            btn(f, f"🖼  Open Answer Sheet ({len(imgs)} page(s))",
                lambda: [os.startfile(x) for x in imgs[:6]] if os.name=="nt" else None,
                height=38).pack(fill="x", pady=(0,8))

        if self.meta.get("remarks"):
            rc = card(f); rc.pack(fill="x", pady=(0,8))
            label(rc, f"📝 Remarks: {self.meta['remarks']}", size=12,
                  color=C["text_muted"]).pack(padx=16, pady=10, anchor="w")

        if self.result.get("summary_feedback"):
            sc = card(f); sc.pack(fill="x", pady=(0,8))
            label(sc, self.result["summary_feedback"], size=12, color=C["text_muted"],
                  wraplength=560).pack(padx=16, pady=12)

        label(f, "Question-by-Question", size=15, weight="bold").pack(anchor="w", pady=(14,8))
        for qnum, qr in self.result.get("question_results",{}).items():
            mx = qr.get("max_marks",0); sc = qr.get("score",0)
            verdict = ("✓ Correct",C["success"]) if mx and sc>=mx-1e-6 else \
                      (("✗ Wrong",C["danger"]) if sc<=1e-6 else ("~ Partial",C["warning"]))
            qc = card(f); qc.pack(fill="x", pady=3)
            top = ctk.CTkFrame(qc, fg_color="transparent"); top.pack(fill="x", padx=16, pady=(10,2))
            label(top, f"Q{qnum}", size=13, weight="bold").pack(side="left")
            label(top, f"{sc}/{mx}", size=13, color=C["success"]).pack(side="left", padx=12)
            status_badge(top, verdict[0], verdict[1]).pack(side="left")
            conf_q = qr.get("confidence",0)
            label(top, f"Conf {round(conf_q*100)}%", size=10,
                  color=C["success"] if conf_q>=0.75 else C["warning"]).pack(side="right")
            if qr.get("feedback"):
                label(qc, f"Remark: {qr['feedback']}", size=11, color=C["text_muted"],
                      wraplength=560).pack(anchor="w", padx=16, pady=(2,8))

        if self.result.get("all_red_flags"):
            label(f, "⚠ Red Flags", size=14, weight="bold", color=C["danger"]).pack(anchor="w", pady=(12,4))
            for fl in self.result["all_red_flags"]:
                label(f, f"• Q{fl['question']}: {fl['flag']}", size=12, color=C["danger"]).pack(anchor="w")

        btn(f, "Close", self.destroy, height=42).pack(pady=(16,0), fill="x")

# ═══════════════════════════════════════════════════════════════
#  CHECKED PAPERS (teacher)
# ═══════════════════════════════════════════════════════════════

class GradeScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._active_section = "All"
        self._build()

    def _build(self):
        self._outer = ctk.CTkFrame(self, fg_color="transparent")
        self._outer.pack(fill="both", expand=True, padx=28, pady=20)

        section_title(self._outer, "✅  Checked Papers")

        # Search + sort row
        sr = ctk.CTkFrame(self._outer, fg_color="transparent")
        sr.pack(fill="x", pady=(0,8))
        self.search_e = entry(sr, "Search by roll, name…", width=320, height=38)
        self.search_e.pack(side="left")
        self.search_e.bind("<Return>", lambda e: self._reload())
        btn(sr, "Search", self._reload, height=38, width=90).pack(side="left", padx=(8,0))
        btn(sr, "All", lambda: (self.search_e.delete(0,"end"), self._reload()),
            height=38, width=70, color=C["bg_card"]).pack(side="left", padx=(6,0))

        btn(sr, "📋  Roster", self._roster_popup, height=38, width=100,
            color=C["bg_card"]).pack(side="right", padx=(8,0))
        btn(sr, "📧  Email All", self._email_all, height=38, width=130,
            color=C["accent2"]).pack(side="right", padx=(8,0))
        btn(sr, "⬇  Export Excel", self._export_excel, height=38, width=150,
            color=C["success"]).pack(side="right", padx=(8,0))

        self.sort_var = ctk.StringVar(value="Newest First")
        ctk.CTkOptionMenu(sr, values=["Newest First","Oldest First",
                                       "Marks High→Low","Marks Low→High","Name A-Z"],
                          variable=self.sort_var, height=38, width=170,
                          fg_color=C["bg_dark"], corner_radius=10,
                          command=lambda _: self._reload()).pack(side="right")
        label(sr, "Sort:", size=12, color=C["text_muted"]).pack(side="right", padx=(0,6))

        # Section filter buttons
        self._sec_frame = ctk.CTkFrame(self._outer, fg_color="transparent")
        self._sec_frame.pack(fill="x", pady=(0,4))

        # Stats bar (shown only when a section is selected)
        self._stats_bar = ctk.CTkFrame(self._outer, fg_color=C["bg_card"], corner_radius=10)

        # Table area
        self._table_wrap = ctk.CTkFrame(self._outer, fg_color="transparent")
        self._table_wrap.pack(fill="both", expand=True)

        self._build_sec_filters()
        self._reload()

    def _build_sec_filters(self):
        for w in self._sec_frame.winfo_children(): w.destroy()
        sections = ["All"] + db.get_sections(self.user["id"])
        for sec in sections:
            active = (sec == self._active_section)
            ctk.CTkButton(
                self._sec_frame, text=sec, width=max(50, len(sec)*9+16), height=32,
                corner_radius=8,
                fg_color=C["accent"] if active else C["bg_card"],
                hover_color=C["accent2"], text_color=C["text"],
                font=ctk.CTkFont(size=12),
                command=lambda s=sec: self._set_section(s)
            ).pack(side="left", padx=(0,6))

    def _set_section(self, sec):
        self._active_section = sec
        self._build_sec_filters()
        self._update_stats_bar()
        self._reload()

    def _update_stats_bar(self):
        if self._active_section == "All":
            self._stats_bar.pack_forget(); return
        self._stats_bar.pack(fill="x", pady=(0,8))
        for w in self._stats_bar.winfo_children(): w.destroy()
        st = db.section_stats(self.user["id"], self._active_section)
        label(self._stats_bar,
              f"{self._active_section}:  {st['count']} papers  |  "
              f"Avg {st['avg']}%  |  Highest {st['highest']}%  |  Pass Rate {st['pass_rate']}%",
              size=12, color=C["text_muted"]).pack(padx=16, pady=8, anchor="w")

    def _reload(self):
        for w in self._table_wrap.winfo_children(): w.destroy()
        query  = self.search_e.get() if hasattr(self,"search_e") else ""
        sort   = self.sort_var.get()  if hasattr(self,"sort_var")  else "Newest First"
        section = None if self._active_section=="All" else self._active_section
        rows = db.search_submissions(self.user["id"], query, section=section, sort=sort)

        if not rows:
            msg = (f"No papers in section '{self._active_section}'."
                   if section else "No checked papers yet. Use 'Check Answer Sheet'.")
            label(self._table_wrap, msg, size=13, color=C["text_muted"]).pack(pady=40)
            return

        scroll = ctk.CTkScrollableFrame(self._table_wrap, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        # Header
        hdr = ctk.CTkFrame(scroll, fg_color=C["accent"], corner_radius=8)
        hdr.pack(fill="x", pady=(0,4))
        cols = [("Roll",100),("Student",130),("Section",65),("Score",85),
                ("Grade",50),("Mode",65),("Remarks",110),("Color",45),("Actions",300)]
        for i,(col,w) in enumerate(cols):
            label(hdr,col,size=11,weight="bold").grid(row=0,column=i,padx=6,pady=7,sticky="w")
            hdr.grid_columnconfigure(i,minsize=w)

        for s in rows:
            self._add_row(scroll, s, cols)

    def _add_row(self, parent, s, cols):
        row_color = s.get("row_color","white") or "white"
        color_map = {"red":C["danger"],"yellow":C["warning"],"green":C["success"]}
        strip = color_map.get(row_color)

        if strip:
            outer = ctk.CTkFrame(parent, fg_color=strip, corner_radius=8)
            outer.pack(fill="x", pady=2)
            row = ctk.CTkFrame(outer, fg_color=C["bg_card"], corner_radius=7)
            row.pack(fill="x", padx=(5,1), pady=1)
        else:
            row = ctk.CTkFrame(parent, fg_color=C["bg_card"], corner_radius=8,
                               border_width=1, border_color=C["border"])
            row.pack(fill="x", pady=2)

        score = (f"{s.get('total_score','-')}/{s.get('total_max','-')}"
                 if s.get("total_max") else "—")
        rem   = (s.get("remarks","") or "")
        rem_s = rem[:22]+"…" if len(rem)>22 else (rem or "—")
        dot   = {"red":"🔴","yellow":"🟡","green":"🟢"}.get(row_color,"⚪")

        vals = [s.get("student_roll","") or "—",
                s.get("student_name","") or "—",
                s.get("class_section","") or "—",
                score,
                s.get("grade","") or "—",
                (s.get("checking_mode","") or "").title(),
                rem_s, dot]

        for i,(val,(_,w)) in enumerate(zip(vals,cols)):
            label(row,str(val),size=11).grid(row=0,column=i,padx=6,pady=5,sticky="w")
            row.grid_columnconfigure(i,minsize=w)

        af = ctk.CTkFrame(row, fg_color="transparent")
        af.grid(row=0, column=8, padx=6, pady=3, sticky="w")
        row.grid_columnconfigure(8, minsize=300)
        sid = s["id"]
        btn(af,"View",  lambda i=sid: self._view(i),  height=26,width=42,color=C["accent"]).pack(side="left",padx=(0,3))
        btn(af,"Edit",  lambda i=sid,r=s: self._edit(i,r), height=26,width=42,color=C["bg_dark"]).pack(side="left",padx=(0,3))
        btn(af,"Re-grade", lambda i=sid: self._regrade(i), height=26,width=64,color=C["warning"]).pack(side="left",padx=(0,3))
        btn(af,"📧", lambda i=sid,r=s: self._email_one(i,r), height=26,width=34,color=C["accent2"]).pack(side="left",padx=(0,3))
        btn(af,"Del",   lambda i=sid: self._delete(i), height=26,width=38,color=C["danger"]).pack(side="left")

    def _view(self, sub_id):
        res = db.get_result_by_submission(sub_id)
        if not res:
            messagebox.showinfo("Not Checked","Not graded yet."); return
        sub  = db.get_submission(sub_id) or {}
        meta = db.get_submission_meta(sub_id) or {}
        meta["checking_mode"] = sub.get("checking_mode","")
        meta["class_section"] = sub.get("class_section","")
        meta["remarks"]       = sub.get("remarks","")
        files = sub.get("answer_images",[]) or ([sub.get("answer_sheet_path")]
                                                 if sub.get("answer_sheet_path") else [])
        ResultPopup(self, res, meta, files)

    def _edit(self, sub_id, s):
        w = ctk.CTkToplevel(self); w.title("Edit Record")
        w.geometry("440x540"); w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(100, lambda: fix_popup(w))

        f = ctk.CTkFrame(w, fg_color="transparent")
        f.pack(padx=28, pady=24, fill="both", expand=True)
        label(f,"Edit Student Record",size=18,weight="bold").pack(pady=(0,16))

        label(f,"Student Name",size=12,weight="bold").pack(anchor="w")
        name_e = entry(f,"Student name",width=380)
        name_e.insert(0, s.get("student_name","") or ""); name_e.pack(pady=(3,10))

        label(f,"Roll Number",size=12,weight="bold").pack(anchor="w")
        roll_e = entry(f,"Roll number",width=380)
        roll_e.insert(0, s.get("student_roll","") or ""); roll_e.pack(pady=(3,10))

        label(f,"Section",size=12,weight="bold").pack(anchor="w")
        sec_e = entry(f,"e.g. Y4-A",width=380)
        sec_e.insert(0, s.get("class_section","") or ""); sec_e.pack(pady=(3,10))

        label(f,"Student Email (for sending report)",size=12,weight="bold").pack(anchor="w")
        email_e = entry(f,"student@example.com",width=380)
        email_e.insert(0, s.get("student_email","") or ""); email_e.pack(pady=(3,10))

        label(f,"Remarks",size=12,weight="bold").pack(anchor="w")
        rem_box = ctk.CTkTextbox(f, height=70, corner_radius=8, width=380)
        rem_box.insert("1.0", s.get("remarks","") or ""); rem_box.pack(pady=(3,12))

        label(f,"Row Color",size=12,weight="bold").pack(anchor="w")
        cf = ctk.CTkFrame(f,fg_color="transparent"); cf.pack(anchor="w",pady=(4,14))
        self._sel_color = s.get("row_color","white") or "white"
        cbtns = {}
        for col, hex_c, clbl in [("white","#1e1e3a","Default"),("green",C["success"],"Pass"),
                                   ("yellow",C["warning"],"Review"),("red",C["danger"],"Concern")]:
            cb = ctk.CTkButton(cf, text=clbl, width=80, height=30, corner_radius=8,
                               fg_color=hex_c, hover_color=hex_c,
                               text_color="#111" if col=="yellow" else C["text"],
                               font=ctk.CTkFont(size=11),
                               command=lambda c=col: self._pick_col(c, cbtns))
            cb.pack(side="left", padx=(0,6)); cbtns[col] = cb
        self._highlight_col(cbtns)

        msg_lbl = label(f,"",color=C["success"]); msg_lbl.pack()

        def save():
            db.update_submission_info(sub_id, name_e.get().strip(),
                                      roll_e.get().strip(), sec_e.get().strip(),
                                      email=email_e.get().strip())
            db.update_submission_remarks(sub_id, rem_box.get("1.0","end").strip(),
                                         self._sel_color)
            msg_lbl.configure(text="✅ Saved!")
            self._build_sec_filters(); self._reload()
            w.after(700, w.destroy)

        btn(f,"Save Changes",save,height=42,width=380).pack(pady=(4,0))

    def _pick_col(self, col, btns):
        self._sel_color = col; self._highlight_col(btns)

    def _highlight_col(self, btns):
        for c, b in btns.items():
            b.configure(border_width=3 if c==self._sel_color else 0,
                        border_color=C["text"])

    def _delete(self, sub_id):
        if messagebox.askyesno("Confirm Delete",
                               "Delete this record permanently? This cannot be undone."):
            db.delete_submission(sub_id)
            self._build_sec_filters(); self._reload()

    def _export_excel(self):
        query   = self.search_e.get() if hasattr(self,"search_e") else ""
        sort    = self.sort_var.get()  if hasattr(self,"sort_var")  else "Newest First"
        section = None if self._active_section=="All" else self._active_section
        rows = db.search_submissions(self.user["id"], query, section=section, sort=sort)
        if not rows:
            messagebox.showinfo("Nothing to Export",
                                "No checked papers match the current view."); return
        default = f"checked_papers_{datetime.now():%Y%m%d_%H%M}.xlsx"
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", initialfile=default,
            filetypes=[("Excel Workbook","*.xlsx")])
        if not path: return
        try:
            from core.exporter import export_results_to_excel
            export_results_to_excel(rows, path,
                                    title=f"Checked Papers — {self._active_section}")
            if messagebox.askyesno("Exported ✅",
                    f"Saved {len(rows)} records to:\n{path}\n\nOpen it now?"):
                try: os.startfile(path)
                except Exception: pass
        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            messagebox.showerror("Export Failed", str(e))

    def _regrade(self, sub_id):
        if not messagebox.askyesno("Re-grade",
                "Re-run AI grading on this paper?\nThe current grade will be replaced."):
            return
        sub = db.get_submission(sub_id)
        paper = db.get_paper(sub["paper_id"]) if sub else None
        if not (sub and paper):
            messagebox.showerror("Error","Could not load this submission's paper."); return

        pop = ctk.CTkToplevel(self); pop.title("Re-grading")
        pop.geometry("380x150"); pop.configure(fg_color=C["bg_dark"]); apply_icon(pop)
        pop.after(100, lambda: fix_popup(pop))
        label(pop, "🔄  Re-grading with AI…", size=15, weight="bold").pack(pady=(34,6))
        label(pop, "This may take up to a minute.", size=11,
              color=C["text_muted"]).pack()

        def work():
            try:
                questions = json.loads(paper.get("parsed_questions","[]"))
                answer_key = {int(k):v for k,v in json.loads(paper.get("parsed_answers","{}")).items()}
                if not questions:
                    questions = [{"number":1,"text":"Overall","marks":paper["total_marks"]}]
                    answer_key = {1:{"model_answer":"","marking_notes":"Award for correct content."}}
                imgs = sub.get("answer_images") or (
                    [sub["answer_sheet_path"]] if sub.get("answer_sheet_path") else [])
                mode = sub.get("checking_mode","normal")
                rate_limiter.wait_if_needed()
                answers = grader.read_answer_sheet(imgs, questions) if imgs else {}
                if not answers:
                    answers = {questions[0]["number"]:"(Could not read answer sheet.)"}
                rate_limiter.wait_if_needed()
                result = grader.grade_paper(questions, answer_key, answers,
                                            paper["subject"], mode)
                db.delete_result(sub_id); db.save_result(sub_id, result)
                def done():
                    pop.destroy()
                    messagebox.showinfo("Re-graded ✅",
                        f"New grade: {result['grade']} ({result['percentage']}%).")
                    self._reload()
                self.after(0, done)
            except Exception as e:
                logger.error(f"Re-grade failed: {e}")
                self.after(0, lambda: (pop.destroy(),
                                       messagebox.showerror("Re-grade Failed", str(e))))
        threading.Thread(target=work, daemon=True).start()

    # ── EMAIL ─────────────────────────────────────────────────
    def _student_email(self, row):
        """Explicit email if set, else auto-build from roll number + domain
        (e.g. FA21-BCS-007@umt.edu.pk). Returns '' if no roll either."""
        explicit = (row.get("student_email","") or "").strip()
        if explicit:
            return explicit
        roll = (row.get("student_roll","") or "").strip()
        if not roll:
            return ""
        domain = settings_store.get("email_domain","@umt.edu.pk") or "@umt.edu.pk"
        if not domain.startswith("@"):
            domain = "@" + domain
        return roll + domain

    def _email_creds(self):
        s = settings_store.load(force=True)
        addr = s.get("email_address","") or ""
        pw   = s.get("email_app_password","") or ""
        if not addr.strip() or not pw.strip():
            messagebox.showwarning("Email Not Set Up",
                "Set up your Gmail first:\n\nSettings & API  →  Email Results  →  "
                "enter your Gmail address and App Password  →  Send Test Email.")
            return None
        return addr.strip(), pw.strip(), (s.get("email_sender_name","") or "")

    def _progress_popup(self, text):
        pop = ctk.CTkToplevel(self); pop.title("Please wait")
        pop.geometry("400x140"); pop.configure(fg_color=C["bg_dark"]); apply_icon(pop)
        pop.after(100, lambda: fix_popup(pop))
        label(pop, text, size=15, weight="bold").pack(pady=(34,6))
        self._pop_msg = label(pop, "", size=11, color=C["text_muted"]); self._pop_msg.pack()
        return pop

    def _build_report(self, sub_id):
        res = db.get_result_by_submission(sub_id)
        if not res: return None
        meta = db.get_submission_meta(sub_id) or {}
        sub  = db.get_submission(sub_id) or {}
        meta.setdefault("student_name", sub.get("student_name",""))
        meta["student_roll"] = meta.get("student_roll") or sub.get("student_roll","")
        from core.exporter import export_student_report_pdf
        out = REPORT_DIR / f"report_{sub_id}.pdf"
        export_student_report_pdf(meta, res, str(out))
        return {"path": str(out), "meta": meta, "result": res}

    def _email_message(self, meta, result, sender_name):
        name = meta.get("student_name","Student") or "Student"
        paper = meta.get("paper_title","your exam")
        subject = f"Your result for {paper}"
        body = (f"Dear {name},\n\n"
                f"Please find attached your graded report for {paper} "
                f"({meta.get('subject','')}).\n\n"
                f"Score: {result.get('total_score','-')}/{result.get('total_max','-')} "
                f"({result.get('percentage','-')}%)  —  Grade {result.get('grade','-')}\n\n"
                f"{result.get('summary_feedback','')}\n\n"
                f"Regards,\n{sender_name or 'Your Teacher'}")
        return subject, body

    def _email_one(self, sub_id, s):
        creds = self._email_creds()
        if not creds: return
        email = self._student_email(s)
        if not email:
            if messagebox.askyesno("No Email Address",
                    "This student has no email and no roll number to build one from.\n"
                    "Add details now?"):
                self._edit(sub_id, s)
            return
        if not db.get_result_by_submission(sub_id):
            messagebox.showinfo("Not Graded","This paper has no result to send."); return
        if not messagebox.askyesno("Send Report", f"Email the report card to:\n{email} ?"):
            return
        addr, pw, sender = creds
        pop = self._progress_popup("📧  Sending email…")
        def work():
            from core import mailer
            try:
                rep = self._build_report(sub_id)
                subj, body = self._email_message(rep["meta"], rep["result"], sender)
                gs = mailer.GmailSender(addr, pw, sender)
                gs.send(email, subj, body, attachments=[rep["path"]]); gs.close()
                self.after(0, lambda: (pop.destroy(),
                    messagebox.showinfo("Sent ✅", f"Report emailed to {email}.")))
            except Exception as e:
                logger.error(f"Email send failed: {e}")
                self.after(0, lambda: (pop.destroy(),
                    messagebox.showerror("Email Failed", mailer._friendly_error(e))))
        threading.Thread(target=work, daemon=True).start()

    def _email_all(self):
        creds = self._email_creds()
        if not creds: return
        query   = self.search_e.get() if hasattr(self,"search_e") else ""
        sort    = self.sort_var.get()  if hasattr(self,"sort_var")  else "Newest First"
        section = None if self._active_section=="All" else self._active_section
        rows = db.search_submissions(self.user["id"], query, section=section, sort=sort)
        # Each target carries the resolved email (explicit or roll@domain).
        targets = []
        for r in rows:
            em = self._student_email(r)
            if em and r.get("total_max"):
                r = dict(r); r["_to"] = em
                targets.append(r)
        no_email = sum(1 for r in rows if not self._student_email(r))
        if not targets:
            messagebox.showinfo("No Recipients",
                "No students in this view have an email (or a roll number to build one).\n"
                "Set the student domain in Settings, or add emails via Edit."); return
        if not messagebox.askyesno("Send Bulk Email",
                f"Email report cards to {len(targets)} student(s)?"
                + (f"\n\n({no_email} have no email — they'll be skipped.)" if no_email else "")):
            return
        addr, pw, sender = creds
        pop = self._progress_popup("📧  Sending emails…")
        total = len(targets)
        def work():
            from core import mailer
            sent = 0; failed = []
            gs = mailer.GmailSender(addr, pw, sender)
            try:
                gs.connect()
            except Exception as e:
                self.after(0, lambda: (pop.destroy(),
                    messagebox.showerror("Gmail Login Failed", mailer._friendly_error(e))))
                return
            for i, r in enumerate(targets, 1):
                email = r.get("_to") or self._student_email(r)
                self.after(0, lambda i=i, n=(r.get("student_name","") or email):
                           self._pop_msg.configure(text=f"{i}/{total} — {n}"))
                try:
                    rep = self._build_report(r["id"])
                    if not rep:
                        failed.append(email); continue
                    subj, body = self._email_message(rep["meta"], rep["result"], sender)
                    gs.send(email, subj, body, attachments=[rep["path"]])
                    sent += 1
                    time.sleep(0.4)   # gentle pacing for Gmail
                except Exception as e:
                    logger.error(f"Bulk email to {email} failed: {e}")
                    failed.append(email)
            gs.close()
            def done():
                pop.destroy()
                msg = f"✅ Sent {sent} of {total} emails."
                if failed:
                    msg += f"\n\n❌ Failed ({len(failed)}):\n" + "\n".join(failed[:8])
                    if len(failed) > 8: msg += f"\n…and {len(failed)-8} more."
                messagebox.showinfo("Bulk Email Complete", msg)
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    # ── SECTION ROSTER (pick section → see students → send) ───
    def _roster_popup(self):
        w = ctk.CTkToplevel(self); w.title("Section Roster — Send by Section")
        w.geometry("900x600"); w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(120, lambda: fix_popup(w))
        w.grid_columnconfigure(1, weight=1); w.grid_rowconfigure(0, weight=1)

        left = ctk.CTkScrollableFrame(w, fg_color=C["bg_sidebar"], width=220, corner_radius=0)
        left.grid(row=0, column=0, sticky="nsew")
        label(left, "Sections", size=14, weight="bold").pack(anchor="w", pady=(10,6), padx=12)
        sections = db.get_sections(self.user["id"])
        right = ctk.CTkScrollableFrame(w, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=18, pady=14)

        def show_section(sec):
            for x in right.winfo_children(): x.destroy()
            rows = db.search_submissions(self.user["id"], "", section=sec, sort="Name A-Z")
            label(right, f"{sec}  —  {len(rows)} student(s)", size=16,
                  weight="bold").pack(anchor="w", pady=(0,4))
            label(right, "Each student's email is built from their roll number. "
                         "Click Send to email that student's report.",
                  size=11, color=C["text_muted"]).pack(anchor="w", pady=(0,10))
            hdr = ctk.CTkFrame(right, fg_color=C["accent"], corner_radius=8)
            hdr.pack(fill="x", pady=(0,4))
            for i,(c,wd) in enumerate([("Roll",150),("Name",150),("Email",240),("",90)]):
                label(hdr,c,size=11,weight="bold").grid(row=0,column=i,padx=8,pady=6,sticky="w")
                hdr.grid_columnconfigure(i,minsize=wd)
            for r in rows:
                em = self._student_email(r)
                rf = ctk.CTkFrame(right, fg_color=C["bg_card"], corner_radius=8,
                                  border_width=1, border_color=C["border"])
                rf.pack(fill="x", pady=2)
                vals=[r.get("student_roll","") or "—", r.get("student_name","") or "—", em or "—"]
                for i,(v,wd) in enumerate(zip(vals,[150,150,240])):
                    label(rf,str(v),size=11).grid(row=0,column=i,padx=8,pady=6,sticky="w")
                    rf.grid_columnconfigure(i,minsize=wd)
                act = ctk.CTkFrame(rf, fg_color="transparent")
                act.grid(row=0, column=3, padx=6, pady=4); rf.grid_columnconfigure(3,minsize=90)
                if r.get("total_max"):
                    btn(act,"Send",lambda rr=r: self._email_one(rr["id"], rr),
                        height=26,width=70,color=C["accent2"]).pack()
                else:
                    label(act,"not graded",size=10,color=C["text_muted"]).pack()

        if not sections:
            label(right, "No sections yet. Add a section to each student via Edit, "
                         "then they'll appear here.", color=C["text_muted"],
                  wraplength=500).pack(pady=30)
        for sec in sections:
            ctk.CTkButton(left, text=sec, anchor="w", height=40, corner_radius=8,
                          fg_color=C["bg_card"], hover_color=C["accent"],
                          command=lambda s=sec: show_section(s)).pack(fill="x", padx=10, pady=2)
        if sections:
            show_section(sections[0])

# ═══════════════════════════════════════════════════════════════
#  BULK CHECK PAPERS
# ═══════════════════════════════════════════════════════════════

class BulkCheckScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._rows = []      # list of dicts with entry vars + status label
        self._results = []   # filled after checking
        self._build()

    def _build(self):
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=28, pady=20)

        section_title(self._scroll, "📦  Bulk Check Papers")
        label(self._scroll,
              "Upload multiple student answer sheets at once. "
              "AI auto-reads each paper's header, then grades all of them in sequence.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,12))

        # Paper picker
        c = card(self._scroll); c.pack(fill="x", pady=(0,14))
        f = ctk.CTkFrame(c, fg_color="transparent"); f.pack(fill="x", padx=20, pady=16)
        label(f,"Question Paper *",size=12,weight="bold").pack(anchor="w")
        papers = db.papers_by_teacher(self.user["id"])
        self.paper_map = {f"{p['id']} — {p['title']} ({p['subject']}, {p['total_marks']} marks)": p
                          for p in papers}
        keys = list(self.paper_map.keys())
        self.paper_var = ctk.StringVar(value=keys[0] if keys else "No papers yet")
        ctk.CTkOptionMenu(f, values=keys or ["No papers yet"],
                          variable=self.paper_var, height=42, corner_radius=10,
                          fg_color=C["bg_dark"], width=560).pack(anchor="w", pady=(4,8))

        label(f,"Checking Mode",size=12,weight="bold").pack(anchor="w")
        self.mode_var = ctk.StringVar(value="Normal")
        ctk.CTkOptionMenu(f, values=["Lenient","Normal","Hard","Insane"],
                          variable=self.mode_var, height=40, corner_radius=10,
                          fg_color=C["bg_dark"], width=200).pack(anchor="w", pady=(4,0))

        # Upload button
        uf = ctk.CTkFrame(self._scroll, fg_color="transparent"); uf.pack(fill="x", pady=(0,12))
        btn(uf,"📂  Upload Answer Sheets (Multiple)",self._upload_files,height=46,width=320).pack(side="left")
        self.upload_lbl = label(uf,"No files selected",size=12,color=C["text_muted"])
        self.upload_lbl.pack(side="left",padx=14)

        # File table (built dynamically)
        self._table_outer = ctk.CTkFrame(self._scroll, fg_color="transparent")
        self._table_outer.pack(fill="x", pady=(0,12))

        # Progress
        self.status_lbl = label(self._scroll,"",color=C["success"]); self.status_lbl.pack(pady=(4,4))
        self.prog = ctk.CTkProgressBar(self._scroll, height=8, corner_radius=4,
                                        progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))

        bf = ctk.CTkFrame(self._scroll, fg_color="transparent"); bf.pack(fill="x")
        self.start_btn = btn(bf,"▶  Start Checking All",self._start_checking,height=50)
        self.start_btn.pack(side="left",fill="x",expand=True)
        # Appears only when some papers fail — re-checks ONLY those.
        self.retry_btn = btn(bf,"🔁  Retry Failed",self._retry_failed,height=50,
                             width=200,color=C["warning"])
        self.timing_lbl = label(self._scroll,"",size=12,color=C["text_muted"])
        self.timing_lbl.pack(anchor="w",pady=(8,0))

    def _upload_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Answer sheets","*.jpg *.jpeg *.png *.bmp *.webp *.pdf *.docx"),
                       ("All","*.*")])
        if not paths: return
        self._rows.clear()
        for w in self._table_outer.winfo_children(): w.destroy()

        self.upload_lbl.configure(text=f"{len(paths)} file(s) selected",text_color=C["success"])
        self.prog.set(0); self.status_lbl.configure(text="")

        # Build header
        hdr = ctk.CTkFrame(self._table_outer, fg_color=C["accent"], corner_radius=8)
        hdr.pack(fill="x", pady=(0,4))
        for i,(col,w) in enumerate([("#",35),("File",180),("Student Name",160),
                                     ("Roll No",130),("Section",90),("Status",120)]):
            label(hdr,col,size=11,weight="bold").grid(row=0,column=i,padx=6,pady=7,sticky="w")
            hdr.grid_columnconfigure(i,minsize=w)

        for idx, path in enumerate(paths):
            name_var = ctk.StringVar(); roll_var = ctk.StringVar(); sec_var = ctk.StringVar()
            row_frame = ctk.CTkFrame(self._table_outer, fg_color=C["bg_card"],
                                     corner_radius=8, border_width=1, border_color=C["border"])
            row_frame.pack(fill="x", pady=2)
            label(row_frame, str(idx+1), size=11).grid(row=0,column=0,padx=6,pady=5,sticky="w")
            row_frame.grid_columnconfigure(0, minsize=35)
            label(row_frame, Path(path).name[:24], size=11).grid(row=0,column=1,padx=6,pady=5,sticky="w")
            row_frame.grid_columnconfigure(1, minsize=180)
            for col_i, (var, ph, w) in enumerate(
                    [(name_var,"Auto-detect…",160),(roll_var,"Roll…",130),(sec_var,"Section",90)],
                    start=2):
                e = ctk.CTkEntry(row_frame, textvariable=var, placeholder_text=ph,
                                 height=30, corner_radius=8, width=w)
                e.grid(row=0, column=col_i, padx=6, pady=5, sticky="w")
                row_frame.grid_columnconfigure(col_i, minsize=w)
            st_lbl = label(row_frame, "⏳ Pending", size=11, color=C["text_muted"])
            st_lbl.grid(row=0, column=5, padx=6, pady=5, sticky="w")
            row_frame.grid_columnconfigure(5, minsize=120)

            row_data = {"path": path, "name_var": name_var, "roll_var": roll_var,
                        "sec_var": sec_var, "status_lbl": st_lbl, "images": []}
            self._rows.append(row_data)

        # Auto-detect student info in background for each file
        threading.Thread(target=self._auto_detect_all, daemon=True).start()

    def _auto_detect_all(self):
        from core import ocr
        tmp_dir = UPLOAD_DIR / "bulk_tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        for row in self._rows:
            try:
                imgs = ocr.to_images(row["path"], str(tmp_dir))
                if not imgs and Path(row["path"]).suffix.lower() in IMAGE_EXTS:
                    imgs = [row["path"]]
                row["images"] = imgs
                if imgs:
                    info = grader.extract_student_info(imgs)
                    def update(r=row, i=info):
                        if i.get("student_name") and not r["name_var"].get():
                            r["name_var"].set(i["student_name"])
                        if i.get("student_id") and not r["roll_var"].get():
                            r["roll_var"].set(i["student_id"])
                        if i.get("section") and not r["sec_var"].get():
                            r["sec_var"].set(i["section"])
                        r["status_lbl"].configure(text="✅ Info read", text_color=C["success"])
                    self.after(0, update)
                else:
                    self.after(0, lambda r=row: r["status_lbl"].configure(
                        text="⚠ Manual entry", text_color=C["warning"]))
            except Exception as e:
                logger.warning(f"Auto-detect failed for {row['path']}: {e}")
                self.after(0, lambda r=row: r["status_lbl"].configure(
                    text="⚠ Manual entry", text_color=C["warning"]))

    def _start_checking(self):
        if not self._rows:
            messagebox.showwarning("No Files","Upload answer sheets first."); return
        key = self.paper_var.get()
        if key not in self.paper_map:
            messagebox.showwarning("No Paper","Select a question paper first."); return
        # Validate rows
        for i, r in enumerate(self._rows, 1):
            if not r["name_var"].get().strip() or not r["roll_var"].get().strip():
                messagebox.showwarning("Missing Info",
                    f"Row {i}: Please fill Student Name and Roll Number before checking."); return
        # Fresh run — clear any prior result on every row.
        for r in self._rows:
            r.pop("result", None); r.pop("error", None); r.pop("sub_id", None)
        indices = list(range(len(self._rows)))
        self._launch_check(indices)

    def _retry_failed(self):
        """Re-check ONLY the papers that failed last time."""
        indices = [i for i, r in enumerate(self._rows) if not r.get("result")]
        if not indices:
            messagebox.showinfo("Nothing to Retry", "All papers checked successfully."); return
        self._launch_check(indices, is_retry=True)

    def _launch_check(self, indices, is_retry=False):
        self.start_btn.configure(state="disabled")
        self.retry_btn.configure(state="disabled")
        paper = self.paper_map[self.paper_var.get()]
        mode  = self.mode_var.get().lower()
        exp = len(indices) * 35   # ~35s per paper estimate
        self.timing_lbl.configure(
            text=f"⏱  Expected ~{exp//60}m {exp%60}s for {len(indices)} paper(s)…")
        threading.Thread(target=self._check_all,
                         args=(paper, mode, indices, is_retry), daemon=True).start()

    def _check_all(self, paper, mode, indices, is_retry):
        from core import ocr
        questions = json.loads(paper.get("parsed_questions","[]"))
        answer_key = {int(k):v for k,v in json.loads(paper.get("parsed_answers","{}")).items()}
        if not questions:
            questions = [{"number":1,"text":"Overall","marks":paper["total_marks"]}]
            answer_key = {1:{"model_answer":"","marking_notes":"Award for correct content."}}

        total = len(indices)
        batch_start = time.time()
        for pos, idx in enumerate(indices):
            row = self._rows[idx]
            name  = row["name_var"].get().strip()
            roll  = row["roll_var"].get().strip()
            sec   = row["sec_var"].get().strip()
            def upd_st(msg, color, r=row):
                self.after(0, lambda: r["status_lbl"].configure(text=msg, text_color=color))
            upd_st("🔄 Checking…", C["warning"])
            self.after(0, lambda p=pos: (
                self.status_lbl.configure(
                    text=f"{'Retrying' if is_retry else 'Checking'} {p+1}/{total}… "
                         f"(up to ~40s per paper)",
                    text_color=C["warning"]),
                self.prog.set((p+1)/total)))
            t0 = time.time()
            try:
                import re as _re
                roll_safe = _re.sub(r'[^\w\-]','_',roll) or "student"
                dest_dir = UPLOAD_DIR / str(paper["id"]) / roll_safe
                dest_dir.mkdir(parents=True, exist_ok=True)
                imgs = row.get("images",[])
                if not imgs:
                    imgs = ocr.to_images(row["path"], str(dest_dir))
                    if not imgs and Path(row["path"]).suffix.lower() in IMAGE_EXTS:
                        dest = dest_dir / Path(row["path"]).name
                        shutil.copy2(row["path"], dest); imgs = [str(dest)]
                row["images"] = imgs

                rate_limiter.wait_if_needed()
                student_answers = grader.read_answer_sheet(imgs, questions) if imgs else {}
                if not student_answers and imgs:
                    rate_limiter.wait_if_needed()
                    student_answers = grader.read_answer_sheet(imgs, questions)  # one retry
                # SAFETY: never award a false zero on a read failure — fail the row instead.
                if imgs and not student_answers:
                    raise RuntimeError("Could not read this answer sheet (AI returned nothing). "
                                       "Use 'Retry Failed' or upload a clearer image.")
                if not student_answers:
                    raise RuntimeError("No readable answers found on this sheet.")

                rate_limiter.wait_if_needed()
                result = grader.grade_paper(questions, answer_key, student_answers,
                                            paper["subject"], mode)
                sub_id = db.create_submission(
                    self.user["id"], paper["id"], row["path"],
                    student_name=name, student_roll=roll, class_section=sec,
                    checking_mode=mode, answer_images=imgs)
                db.set_status(sub_id, "graded"); db.save_result(sub_id, result)
                db.save_history(self.user["id"], paper["id"], paper["subject"], paper["title"],
                                result["total_score"], result["total_max"],
                                result["percentage"], result["grade"])
                elapsed = time.time() - t0
                row.update({"name": name, "roll": roll, "section": sec,
                            "result": result, "images": imgs, "sub_id": sub_id,
                            "elapsed": elapsed, "paper_title": paper["title"],
                            "subject": paper["subject"]})
                row.pop("error", None)
                grade = result["grade"]; pct = result["percentage"]
                color = C["success"] if pct>=50 else C["danger"]
                upd_st(f"✅ {grade} ({pct}%) · {elapsed:.1f}s", color)
            except Exception as e:
                elapsed = time.time() - t0
                logger.error(f"Bulk check error for {row['path']}: {e}")
                upd_st(f"❌ Failed · {elapsed:.1f}s", C["danger"])
                row.update({"name": name, "roll": roll, "section": sec,
                            "result": None, "error": str(e), "elapsed": elapsed,
                            "paper_title": paper["title"], "subject": paper["subject"]})

        self.after(0, lambda: self._checking_done(time.time() - batch_start))

    def _checking_done(self, batch_seconds):
        self.start_btn.configure(state="normal")
        # Rebuild the ordered results list from the rows.
        self._results = [
            {k: r.get(k) for k in ("name","roll","section","result","images",
                                    "error","sub_id","paper_title","subject","elapsed")}
            for r in self._rows
        ]
        done   = sum(1 for r in self._results if r.get("result"))
        failed = len(self._results) - done
        times  = [r.get("elapsed") for r in self._rows if r.get("elapsed")]
        avg    = (sum(times)/len(times)) if times else 0
        self.status_lbl.configure(
            text=f"✅ Done! {done} checked"
                 + (f", {failed} failed" if failed else "") + ". Opening preview…",
            text_color=C["success"] if not failed else C["warning"])
        self.timing_lbl.configure(
            text=f"⏱  Total time: {batch_seconds:.1f}s   •   "
                 f"Average per paper: {avg:.1f}s   •   "
                 f"{done}/{len(self._results)} successful")
        self.prog.set(1.0)
        # Show / hide Retry button based on failures.
        if failed:
            self.retry_btn.configure(state="normal")
            self.retry_btn.pack(side="left", padx=(10,0))
        else:
            self.retry_btn.pack_forget()
        BulkPreviewPopup(self, self._results)


class BulkPreviewPopup(ctk.CTkToplevel):
    def __init__(self, parent, results):
        super().__init__(parent)
        self.title("Bulk Check Preview — Confirm & Save")
        self.geometry("1100x680"); self.configure(fg_color=C["bg_dark"])
        apply_icon(self); self.after(250, lambda: apply_icon(self))
        self.after(100, lambda: fix_popup(self))
        self.results = results
        self._sel_idx = 0
        self._build()

    def _build(self):
        self.grid_columnconfigure(0, weight=0); self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1); self.grid_rowconfigure(1, weight=0)

        # Left panel — student list
        left = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, width=340)
        left.grid(row=0, column=0, sticky="nsew"); left.grid_propagate(False)
        label(left, f"Results ({len(self.results)} papers)",
              size=14, weight="bold").pack(pady=(16,8), padx=16, anchor="w")
        self._list_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._list_scroll.pack(fill="both", expand=True, padx=8, pady=(0,8))
        for i, r in enumerate(self.results):
            self._add_list_row(i, r)

        # Right panel — detail
        self._detail = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._detail.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        self._show_detail(0)

        # Bottom bar
        bot = ctk.CTkFrame(self, fg_color=C["bg_card"], height=70, corner_radius=0)
        bot.grid(row=1, column=0, columnspan=2, sticky="ew")
        bot.grid_propagate(False)
        bf = ctk.CTkFrame(bot, fg_color="transparent"); bf.pack(fill="x", padx=24, pady=14)
        label(bf, f"Review results then click Close. All {sum(1 for r in self.results if r.get('result'))} "
              f"papers are already saved.", size=12, color=C["text_muted"]).pack(side="left")
        btn(bf, "Close", self.destroy, height=42, width=120).pack(side="right")

    def _add_list_row(self, idx, r):
        result = r.get("result")
        if result:
            pct = result["percentage"]
            color = C["success"] if pct>=50 else C["danger"]
            badge = f"{result['grade']} • {pct}%"
        else:
            color = C["text_muted"]; badge = "Failed"

        row = ctk.CTkFrame(self._list_scroll, fg_color=C["bg_card"],
                           corner_radius=8, cursor="hand2")
        row.pack(fill="x", pady=2)
        rf = ctk.CTkFrame(row, fg_color="transparent"); rf.pack(fill="x", padx=10, pady=8)
        label(rf, r.get("name","—"), size=12, weight="bold").pack(anchor="w")
        label(rf, f"{r.get('roll','—')}  •  {r.get('section','—')}",
              size=10, color=C["text_muted"]).pack(anchor="w")
        status_badge(rf, badge, color).pack(anchor="w", pady=(3,0))
        for w in [row, rf]:
            w.bind("<Button-1>", lambda e, i=idx: self._show_detail(i))

    def _show_detail(self, idx):
        for w in self._detail.winfo_children(): w.destroy()
        if idx >= len(self.results): return
        r = self.results[idx]; result = r.get("result")

        label(self._detail, r.get("name","—"), size=20, weight="bold").pack(anchor="w")
        meta_line = f"Roll: {r.get('roll','—')}  •  Section: {r.get('section','—')}"
        if r.get("elapsed"):
            meta_line += f"  •  ⏱ {r['elapsed']:.1f}s"
        label(self._detail, meta_line,
              size=13, color=C["text_muted"]).pack(anchor="w", pady=(2,12))

        if not result:
            label(self._detail, f"❌ Checking failed: {r.get('error','Unknown error')}",
                  size=13, color=C["danger"]).pack(anchor="w"); return

        grade = result["grade"]
        gc = {"A+":C["success"],"A":C["success"],"A-":C["success"],"B+":C["accent"],
              "B":C["accent"],"B-":C["accent"],"C+":C["warning"],"C":C["warning"],
              "C-":C["warning"],"D":C["danger"],"F":C["danger"]}
        ctk.CTkLabel(self._detail, text=grade,
                     font=ctk.CTkFont(size=40, weight="bold"),
                     text_color=gc.get(grade,C["text"])).pack(anchor="w")
        label(self._detail,
              f"{result['percentage']}%  •  {result['total_score']}/{result['total_max']} marks",
              size=15, color=C["text_muted"]).pack(anchor="w", pady=(0,12))

        if result.get("summary_feedback"):
            sc = card(self._detail); sc.pack(fill="x", pady=(0,10))
            label(sc, result["summary_feedback"], size=12, color=C["text_muted"],
                  wraplength=680).pack(padx=16, pady=10)

        label(self._detail,"Question Breakdown",size=14,weight="bold").pack(anchor="w",pady=(0,6))
        for qnum, qr in result.get("question_results",{}).items():
            mx=qr.get("max_marks",0); sc=qr.get("score",0)
            color = C["success"] if mx and sc>=mx-1e-6 else (C["danger"] if sc<=1e-6 else C["warning"])
            qc = ctk.CTkFrame(self._detail, fg_color=C["bg_card"], corner_radius=8)
            qc.pack(fill="x", pady=2)
            qf = ctk.CTkFrame(qc, fg_color="transparent"); qf.pack(fill="x",padx=12,pady=6)
            label(qf,f"Q{qnum}",size=12,weight="bold").pack(side="left")
            label(qf,f"{sc}/{mx}",size=12,color=color).pack(side="left",padx=10)
            if qr.get("feedback"):
                label(qf, qr["feedback"],size=11,color=C["text_muted"],
                      wraplength=580).pack(side="left")

# ═══════════════════════════════════════════════════════════════
#  RESULTS & ANALYTICS
# ═══════════════════════════════════════════════════════════════

class ResultsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self.role = self.user.get("role")
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "📊  Results & Analytics")

        if self.role == "teacher":
            top = card(f); top.pack(fill="x", pady=(0,16))
            tf = ctk.CTkFrame(top, fg_color="transparent"); tf.pack(fill="x", padx=20, pady=14)
            label(tf,"Paper:",size=13,weight="bold").pack(side="left")
            papers = db.papers_by_teacher(self.user["id"])
            self.pmap = {f"{p['id']} — {p['title']}": p for p in papers}
            self.pvar = ctk.StringVar(value=list(self.pmap.keys())[0] if self.pmap else "")
            ctk.CTkOptionMenu(tf, values=list(self.pmap.keys()) or ["No papers"],
                              variable=self.pvar, height=40, fg_color=C["bg_dark"],
                              corner_radius=10, width=400).pack(side="left", padx=12)
            btn(tf,"Load",self._load_teacher,height=40,width=100).pack(side="left")
            self.stats_frame = ctk.CTkFrame(f, fg_color="transparent")
            self.stats_frame.pack(fill="x", pady=(0,12))
            cols = [("Roll",120),("Student",160),("Score",80),("Max",60),
                    ("Percent",90),("Grade",70),("Confidence",100),("Review",80)]
        else:
            cols = [("Paper",220),("Subject",120),("Score",80),("Max",60),("Grade",70),("Date",140)]

        self.table = Table(f, cols); self.table.pack(fill="both", expand=True)
        if self.role == "student": self._load_student()

    def _load_teacher(self):
        for w in self.stats_frame.winfo_children(): w.destroy()
        key = self.pvar.get()
        if key not in self.pmap: return
        paper = self.pmap[key]; results = db.results_for_paper(paper["id"])
        if results:
            pcts = [r["percentage"] for r in results]; avg = round(sum(pcts)/len(pcts),1)
            for lbl_txt, val in [("Students",len(results)),("Average",f"{avg}%"),
                                  ("Highest",f"{max(pcts)}%"),("Lowest",f"{min(pcts)}%")]:
                sc = card(self.stats_frame)
                sc.pack(side="left", padx=(0,12), pady=4, ipadx=16, ipady=8)
                ctk.CTkLabel(sc, text=str(val), font=ctk.CTkFont(size=22,weight="bold"),
                             text_color=C["accent"]).pack(padx=20,pady=(10,2))
                label(sc, lbl_txt, size=11, color=C["text_muted"]).pack(padx=20,pady=(0,10))
        self.table.clear()
        if not results:
            self.table.empty("No graded submissions for this paper yet."); return
        for r in results:
            review_badge = ("Review",C["warning"]) if r["needs_review"] else ("OK",C["success"])
            self.table.add_row([r.get("student_roll","") or "—", r["student_name"],
                                 r["total_score"], r["total_max"],
                                 f"{r['percentage']}%", r["grade"],
                                 f"{round(r['overall_confidence']*100)}%", review_badge])

    def _load_student(self):
        subs = db.submissions_for_student(self.user["id"]); rows = 0
        for s in subs:
            res = db.get_result_by_submission(s["id"])
            if res:
                self.table.add_row([s["paper_title"],s["subject"],res["total_score"],
                                    res["total_max"],res["grade"],s["submitted_at"][:10]])
                rows += 1
        if rows == 0:
            self.table.empty("No results yet. Submit an answer sheet to see your grades.")

# ═══════════════════════════════════════════════════════════════
#  MANUAL OVERRIDE
# ═══════════════════════════════════════════════════════════════

class OverrideScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "✏️  Manual Override")
        label(f, "Search by Submission ID to apply a manual grade override with audit trail.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,16))

        top = card(f); top.pack(fill="x", pady=(0,16))
        tf = ctk.CTkFrame(top, fg_color="transparent"); tf.pack(fill="x", padx=20, pady=16)
        label(tf,"Submission ID:",size=13,weight="bold").pack(side="left")
        self.sid_e = entry(tf,"e.g. 3",width=120,height=40); self.sid_e.pack(side="left",padx=12)
        btn(tf,"Load",self._load,height=40,width=100).pack(side="left")

        self.detail = card(f); self.detail.pack(fill="x", pady=(0,12))
        self.detail_inner = ctk.CTkFrame(self.detail, fg_color="transparent")
        self.detail_inner.pack(fill="x", padx=20, pady=16)
        label(self.detail_inner,"Enter a Submission ID above to load result.",
              color=C["text_muted"]).pack()

    def _load(self):
        try: sid = int(self.sid_e.get())
        except: return
        res = db.get_result_by_submission(sid)
        if not res:
            messagebox.showwarning("Not Found", f"No result for submission {sid}"); return
        for w in self.detail_inner.winfo_children(): w.destroy()
        label(self.detail_inner,
              f"Result ID: {res['id']}  |  Grade: {res['grade']}  |  "
              f"Score: {res['total_score']}/{res['total_max']}",
              size=14, weight="bold").pack(anchor="w")
        label(self.detail_inner,"New Score:",size=12,weight="bold").pack(anchor="w",pady=(12,2))
        self.new_score_e = entry(self.detail_inner,f"Current: {res['total_score']}",width=200)
        self.new_score_e.pack(anchor="w",pady=(0,8))
        label(self.detail_inner,"Override Notes (required):",size=12,weight="bold").pack(anchor="w")
        self.notes_e = ctk.CTkTextbox(self.detail_inner, height=80, corner_radius=8)
        self.notes_e.pack(fill="x", pady=(4,12))
        btn(self.detail_inner,"✏️  Apply Override",lambda: self._apply(res),
            height=44,color=C["warning"]).pack(anchor="w")

    def _apply(self, res):
        try: new_s = float(self.new_score_e.get())
        except: messagebox.showerror("Error","Enter a valid score."); return
        notes = self.notes_e.get("1.0","end").strip()
        if not notes: messagebox.showwarning("Required","Please enter override notes."); return
        db.apply_override(res["id"], new_s, res["total_max"], notes, self.user["id"])
        db.log_audit("MANUAL_OVERRIDE", self.user["username"],
                     f"result_id={res['id']} old={res['total_score']} new={new_s}")
        messagebox.showinfo("Done", f"Override applied. New score: {new_s}/{res['total_max']}")

# ═══════════════════════════════════════════════════════════════
#  STUDENT HISTORY
# ═══════════════════════════════════════════════════════════════

class HistoryScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "📅  My Academic History")
        cols = [("Subject",140),("Paper",220),("Score",80),("Total",70),
                ("Grade",70),("Percent",90),("Date",140)]
        t = Table(f, cols); t.pack(fill="both", expand=True)
        history = db.get_history(self.user["id"])
        if not history:
            t.empty("No graded papers yet.")
        for h in history:
            t.add_row([h["subject"],h["title"],h["score"],h["total_marks"],
                       h["grade"],f"{h['percentage']}%",h["recorded_at"][:10]])

# ═══════════════════════════════════════════════════════════════
#  TEACHER — SETTINGS & API KEY  (no code editing needed)
# ═══════════════════════════════════════════════════════════════

class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "⚙️  Settings & AI Connection")
        label(scroll,
              "Set your own NVIDIA API key and models here — no code editing required. "
              "Saved privately on this computer only.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,14))

        s = settings_store.load(force=True)

        # ── AI / API card ─────────────────────────────────────
        c = card(scroll); c.pack(fill="x", pady=(0,14))
        f = ctk.CTkFrame(c, fg_color="transparent"); f.pack(fill="x", padx=22, pady=18)
        label(f, "🔑  NVIDIA API Key", size=14, weight="bold").pack(anchor="w")
        label(f, "Get a free key at build.nvidia.com → your profile → API Keys.",
              size=11, color=C["text_muted"]).pack(anchor="w", pady=(0,6))
        kr = ctk.CTkFrame(f, fg_color="transparent"); kr.pack(fill="x")
        self.key_e = ctk.CTkEntry(kr, placeholder_text="nvapi-…", show="*",
                                  height=42, corner_radius=10)
        self.key_e.pack(side="left", fill="x", expand=True)
        if s.get("api_key"): self.key_e.insert(0, s["api_key"])
        self._show_key = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(kr, text="Show", variable=self._show_key, width=60,
                        command=lambda: self.key_e.configure(
                            show="" if self._show_key.get() else "*")
                        ).pack(side="left", padx=(10,0))

        # Second API key — automatic backup so checking never stops.
        label(f, "🔑  Backup API Key 2 (optional, recommended)", size=13, weight="bold").pack(anchor="w", pady=(14,0))
        label(f, "Add a second NVIDIA key. The app uses Key 1 first; if it is busy, "
                 "rate-limited, or fails, it instantly switches to Key 2 — so you can check "
                 "more papers without interruption (used in bulk checking too).",
              size=11, color=C["text_muted"], wraplength=820, justify="left").pack(anchor="w", pady=(0,6))
        kr2 = ctk.CTkFrame(f, fg_color="transparent"); kr2.pack(fill="x")
        self.key2_e = ctk.CTkEntry(kr2, placeholder_text="nvapi-… (second key)", show="*",
                                   height=42, corner_radius=10)
        self.key2_e.pack(side="left", fill="x", expand=True)
        if s.get("api_key2"): self.key2_e.insert(0, s["api_key2"])
        self._show_key2 = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(kr2, text="Show", variable=self._show_key2, width=60,
                        command=lambda: self.key2_e.configure(
                            show="" if self._show_key2.get() else "*")
                        ).pack(side="left", padx=(10,0))

        self.base_e = self._field(f, "Base URL", s.get("base_url",""),
                                  "https://integrate.api.nvidia.com/v1")
        self.model_e = self._field(f, "Grading Model", s.get("model",""),
                                   "meta/llama-3.3-70b-instruct")
        self.fast_e = self._field(f, "Fast Backup Model (used if main model is slow)",
                                  s.get("fast_model",""), "meta/llama-3.1-8b-instruct")
        self.vision_e = self._field(f, "Vision Model (reads handwriting)",
                                    s.get("vision_model",""),
                                    "nvidia/llama-3.1-nemotron-nano-vl-8b-v1")
        self.temp_e = self._field(f, "AI Temperature (0.0–1.0, lower = stricter)",
                                  str(s.get("temperature","0.1")), "0.1", width=120)

        # ── Preferences card ──────────────────────────────────
        c2 = card(scroll); c2.pack(fill="x", pady=(0,14))
        f2 = ctk.CTkFrame(c2, fg_color="transparent"); f2.pack(fill="x", padx=22, pady=18)
        label(f2, "🌐  Preferences", size=14, weight="bold").pack(anchor="w", pady=(0,8))

        lr = ctk.CTkFrame(f2, fg_color="transparent"); lr.pack(fill="x", pady=(0,8))
        label(lr, "Answer Language:", size=12, weight="bold", width=160,
              anchor="w").pack(side="left")
        self.lang_var = ctk.StringVar(value=s.get("language", settings_store.LANGUAGES[0]))
        ctk.CTkOptionMenu(lr, values=settings_store.LANGUAGES, variable=self.lang_var,
                          height=38, width=260, corner_radius=10,
                          fg_color=C["bg_dark"]).pack(side="left")

        tr = ctk.CTkFrame(f2, fg_color="transparent"); tr.pack(fill="x")
        label(tr, "Appearance:", size=12, weight="bold", width=160,
              anchor="w").pack(side="left")
        self.theme_var = ctk.StringVar(value=s.get("theme","dark").title())
        ctk.CTkOptionMenu(tr, values=["Dark","Light"], variable=self.theme_var,
                          height=38, width=160, corner_radius=10,
                          fg_color=C["bg_dark"],
                          command=self._preview_theme).pack(side="left")

        # ── Email (Gmail) card ────────────────────────────────
        c3 = card(scroll); c3.pack(fill="x", pady=(0,14))
        f3 = ctk.CTkFrame(c3, fg_color="transparent"); f3.pack(fill="x", padx=22, pady=18)
        hr = ctk.CTkFrame(f3, fg_color="transparent"); hr.pack(fill="x")
        label(hr, "📧  Email Results (Gmail)", size=14, weight="bold").pack(side="left")
        btn(hr, "❓ How to get App Password", self._app_password_guide,
            height=30, width=220, color=C["bg_dark"]).pack(side="right")
        label(f3, "Send report cards straight to students from your own Gmail. "
                  "Use a 16-character App Password, NOT your normal password.",
              size=11, color=C["text_muted"]).pack(anchor="w", pady=(2,4))

        # One-click link that opens the Google setup page in the browser.
        lk = ctk.CTkFrame(f3, fg_color="transparent"); lk.pack(fill="x", pady=(2,4))
        btn(lk, "🔗  Open Google App Passwords page", self._open_apppw_page,
            height=34, width=300, color=C["accent"]).pack(side="left")
        label(lk, "  ← click to set up / get your password",
              size=11, color=C["text_muted"]).pack(side="left")

        self.email_e = self._field(f3, "Your Gmail Address",
                                   s.get("email_address",""), "yourname@gmail.com")
        self.sender_e = self._field(f3, "Sender Name (shown to students)",
                                    s.get("email_sender_name",""), "Ms. Khan / Class Teacher")
        self.domain_e = self._field(f3, "Student Email Domain (their address = roll number + this)",
                                    s.get("email_domain","@umt.edu.pk"), "@umt.edu.pk")
        label(f3, "Gmail App Password (16 characters)", size=12, weight="bold").pack(anchor="w", pady=(12,2))
        pr = ctk.CTkFrame(f3, fg_color="transparent"); pr.pack(fill="x")
        self.emailpw_e = ctk.CTkEntry(pr, placeholder_text="abcd efgh ijkl mnop",
                                      show="*", height=40, corner_radius=10)
        self.emailpw_e.pack(side="left", fill="x", expand=True)
        if s.get("email_app_password"): self.emailpw_e.insert(0, s["email_app_password"])
        self._show_pw = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(pr, text="Show", variable=self._show_pw, width=60,
                        command=lambda: self.emailpw_e.configure(
                            show="" if self._show_pw.get() else "*")
                        ).pack(side="left", padx=(10,0))
        btn(f3, "📨  Send Test Email", self._test_email, height=42, width=200,
            color=C["bg_card"]).pack(anchor="w", pady=(12,0))

        # ── Actions ───────────────────────────────────────────
        self.status = label(scroll, "", size=12); self.status.pack(anchor="w", pady=(4,8))
        bf = ctk.CTkFrame(scroll, fg_color="transparent"); bf.pack(fill="x")
        self.test_btn = btn(bf, "🔌  Test Connection", self._test, height=46,
                            width=200, color=C["bg_card"])
        self.test_btn.pack(side="left", padx=(0,10))
        btn(bf, "💾  Save Settings", self._save, height=46, width=200).pack(side="left")

    def _field(self, parent, lbl, value, placeholder, width=None):
        label(parent, lbl, size=12, weight="bold").pack(anchor="w", pady=(12,2))
        e = ctk.CTkEntry(parent, placeholder_text=placeholder, height=40, corner_radius=10)
        if width: e.configure(width=width)
        e.pack(anchor="w", fill=(None if width else "x"))
        if value: e.insert(0, str(value))
        return e

    def _preview_theme(self, choice):
        try: ctk.set_appearance_mode(choice.lower())
        except Exception: pass

    def _collect(self):
        try: temp = float(self.temp_e.get().strip() or "0.1")
        except ValueError: temp = 0.1
        return {
            "api_key":      self.key_e.get().strip(),
            "api_key2":     self.key2_e.get().strip(),
            "base_url":     self.base_e.get().strip() or "https://integrate.api.nvidia.com/v1",
            "model":        self.model_e.get().strip() or "meta/llama-3.3-70b-instruct",
            "fast_model":   self.fast_e.get().strip() or "meta/llama-3.1-8b-instruct",
            "vision_model": self.vision_e.get().strip() or "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
            "temperature":  max(0.0, min(temp, 1.0)),
            "language":     self.lang_var.get(),
            "theme":        self.theme_var.get().lower(),
            "email_address":      self.email_e.get().strip(),
            "email_app_password": self.emailpw_e.get().strip(),
            "email_sender_name":  self.sender_e.get().strip(),
            "email_domain":       self.domain_e.get().strip() or "@umt.edu.pk",
        }

    def _save(self):
        settings_store.save(self._collect())
        ok = grader.reconfigure()
        self._preview_theme(self.theme_var.get())
        self.status.configure(
            text=("✅ Saved. AI is connected and ready." if ok
                  else "✅ Saved. (No API key — AI runs in offline fallback mode.)"),
            text_color=C["success"] if ok else C["warning"])

    def _test(self):
        # Save first so the test uses exactly what's on screen.
        settings_store.save(self._collect())
        grader.reconfigure()
        self.test_btn.configure(state="disabled", text="Testing…")
        self.status.configure(text="🔌 Contacting NVIDIA…", text_color=C["text_muted"])
        def work():
            ok, msg = grader.test_connection()
            def done():
                self.test_btn.configure(state="normal", text="🔌  Test Connection")
                self.status.configure(text=("✅ " if ok else "❌ ") + msg,
                                      text_color=C["success"] if ok else C["danger"])
            self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def _test_email(self):
        addr = self.email_e.get().strip()
        pw   = self.emailpw_e.get().strip()
        if not addr or not pw:
            self.status.configure(text="❌ Enter your Gmail address and App Password first.",
                                  text_color=C["danger"]); return
        settings_store.save(self._collect())
        self.status.configure(text="📨 Sending test email…", text_color=C["text_muted"])
        def work():
            from core import mailer
            ok, msg = mailer.send_test(addr, pw, self.sender_e.get().strip())
            self.after(0, lambda: self.status.configure(
                text=("✅ " if ok else "❌ ") + msg,
                text_color=C["success"] if ok else C["danger"]))
        threading.Thread(target=work, daemon=True).start()

    def _open_apppw_page(self):
        try:
            webbrowser.open("https://myaccount.google.com/apppasswords", new=2)
            self.status.configure(text="🔗 Opened Google App Passwords in your browser.",
                                  text_color=C["text_muted"])
        except Exception as e:
            self.status.configure(text=f"Could not open browser: {e}", text_color=C["danger"])

    def _app_password_guide(self):
        w = ctk.CTkToplevel(self); w.title("How to get a Gmail App Password")
        w.geometry("560x460"); w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(120, lambda: fix_popup(w))
        f = ctk.CTkScrollableFrame(w, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=20)
        label(f, "🔐  Get your Gmail App Password", size=18, weight="bold").pack(anchor="w", pady=(0,10))
        steps = [
            ("1. Turn on 2-Step Verification",
             "Go to myaccount.google.com → Security → 2-Step Verification → turn it ON. "
             "(App Passwords only work when this is on.)"),
            ("2. Open App Passwords",
             "Go to myaccount.google.com/apppasswords (or Security → App passwords)."),
            ("3. Create one",
             "Type a name like 'Smart Paper Checker' and click Create."),
            ("4. Copy the 16-letter code",
             "Google shows a code like 'abcd efgh ijkl mnop'. Copy it."),
            ("5. Paste it into the app",
             "Paste that code into the 'Gmail App Password' box here, add your Gmail "
             "address, then click 'Send Test Email'. Done!"),
        ]
        for title, body in steps:
            c = card(f); c.pack(fill="x", pady=4)
            label(c, title, size=13, weight="bold").pack(anchor="w", padx=14, pady=(10,2))
            label(c, body, size=12, color=C["text_muted"], wraplength=470,
                  justify="left").pack(anchor="w", padx=14, pady=(0,10))
        label(f, "Note: the App Password is safe — it only allows sending mail and you "
                 "can delete it anytime from your Google account.",
              size=11, color=C["warning"], wraplength=480, justify="left").pack(anchor="w", pady=(8,4))
        btn(f, "Got it", w.destroy, height=40).pack(pady=(8,0))

# ═══════════════════════════════════════════════════════════════
#  TEACHER — CLASS INSIGHTS (weak topics + copy detection)
# ═══════════════════════════════════════════════════════════════

class AnalyticsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "📈  Class Insights")

        top = card(f); top.pack(fill="x", pady=(0,12))
        tf = ctk.CTkFrame(top, fg_color="transparent"); tf.pack(fill="x", padx=20, pady=14)
        label(tf, "Paper:", size=13, weight="bold").pack(side="left")
        papers = db.papers_by_teacher(self.user["id"])
        self.pmap = {f"{p['id']} — {p['title']}": p for p in papers}
        self.pvar = ctk.StringVar(value=list(self.pmap.keys())[0] if self.pmap else "")
        ctk.CTkOptionMenu(tf, values=list(self.pmap.keys()) or ["No papers"],
                          variable=self.pvar, height=40, fg_color=C["bg_dark"],
                          corner_radius=10, width=380).pack(side="left", padx=12)
        btn(tf, "Analyze", self._load, height=40, width=110).pack(side="left")

        self._body = ctk.CTkScrollableFrame(f, fg_color="transparent")
        self._body.pack(fill="both", expand=True)
        if self.pmap: self._load()

    def _load(self):
        from core import analytics
        for w in self._body.winfo_children(): w.destroy()
        key = self.pvar.get()
        if key not in self.pmap:
            label(self._body, "No paper selected.", color=C["text_muted"]).pack(pady=30); return
        paper = self.pmap[key]
        results = db.results_for_paper(paper["id"])
        if not results:
            label(self._body, "No graded papers yet for this paper.",
                  color=C["text_muted"]).pack(pady=30); return

        # ── Weak topics ───────────────────────────────────────
        label(self._body, "🧩  Question Difficulty (weakest first)",
              size=15, weight="bold").pack(anchor="w", pady=(4,8))
        breakdown = sorted(analytics.question_breakdown(results),
                           key=lambda d: d["avg_pct"])
        for q in breakdown:
            avg = q["avg_pct"]
            color = C["danger"] if avg < 40 else (C["warning"] if avg < 65 else C["success"])
            row = ctk.CTkFrame(self._body, fg_color=C["bg_card"], corner_radius=8)
            row.pack(fill="x", pady=2)
            rf = ctk.CTkFrame(row, fg_color="transparent"); rf.pack(fill="x", padx=14, pady=8)
            label(rf, f"Q{q['qnum']}", size=13, weight="bold", width=50,
                  anchor="w").pack(side="left")
            bar_wrap = ctk.CTkFrame(rf, fg_color=C["bg_dark"], corner_radius=6,
                                    height=18, width=300)
            bar_wrap.pack(side="left", padx=10); bar_wrap.pack_propagate(False)
            fill = ctk.CTkFrame(bar_wrap, fg_color=color, corner_radius=6,
                                width=max(4, int(300 * avg/100)))
            fill.pack(side="left", fill="y")
            label(rf, f"{avg}% avg  •  {q['got_full']}/{q['total']} got full marks",
                  size=12, color=color).pack(side="left", padx=10)
        worst = breakdown[0] if breakdown else None
        if worst and worst["avg_pct"] < 65:
            tip = card(self._body); tip.pack(fill="x", pady=(8,4))
            label(tip, f"💡 Re-teach tip: the class struggled most with Q{worst['qnum']} "
                       f"(only {worst['avg_pct']}% average). Consider revising this topic.",
                  size=12, color=C["warning"], wraplength=820).pack(padx=16, pady=10, anchor="w")

        # ── Plagiarism ────────────────────────────────────────
        label(self._body, "🕵️  Possible Copying (similar answers)",
              size=15, weight="bold").pack(anchor="w", pady=(18,8))
        pairs = analytics.find_similar_pairs(results, threshold=0.65)
        if not pairs:
            label(self._body, "✅ No suspiciously similar answer sheets detected.",
                  size=12, color=C["success"]).pack(anchor="w")
        else:
            for p in pairs[:25]:
                sev = C["danger"] if p["similarity"] >= 85 else C["warning"]
                row = ctk.CTkFrame(self._body, fg_color=C["bg_card"], corner_radius=8)
                row.pack(fill="x", pady=2)
                rf = ctk.CTkFrame(row, fg_color="transparent"); rf.pack(fill="x", padx=14, pady=8)
                status_badge(rf, f"{p['similarity']}%", sev).pack(side="left")
                label(rf, f"  {p['a_name']} ({p['a_roll'] or '—'})  ⇄  "
                          f"{p['b_name']} ({p['b_roll'] or '—'})",
                      size=12).pack(side="left", padx=8)

# ═══════════════════════════════════════════════════════════════
#  LICENSE / TERMS ACCEPTANCE  (first launch)
# ═══════════════════════════════════════════════════════════════

LICENSE_TEXT = (
    "SMART PAPER CHECKER — END USER LICENSE AGREEMENT & TERMS OF USE\n\n"
    "By clicking \"I Agree\", you accept the following terms:\n\n"
    "1. PURPOSE. Smart Paper Checker is an AI-assisted grading aid for educators. "
    "It is provided to help teachers check answer sheets faster.\n\n"
    "2. AI ASSISTANCE, NOT A REPLACEMENT. Grades produced by the AI are suggestions. "
    "The teacher remains fully responsible for final marks and must review results, "
    "especially papers flagged for review.\n\n"
    "3. DATA & PRIVACY. Student data and answer sheets are stored locally on this "
    "computer. When AI grading is used, answer content is sent to the configured AI "
    "provider (NVIDIA) for processing. Do not upload data you are not permitted to share.\n\n"
    "4. API KEYS. Any API key you enter is stored locally on this device only and is "
    "your responsibility to keep secure.\n\n"
    "5. NO WARRANTY. The software is provided \"as is\", without warranty of any kind. "
    "The authors are not liable for any grading errors, data loss, or damages arising "
    "from its use.\n\n"
    "6. FAIR USE. You agree to use this tool ethically and in line with your "
    "institution's academic and assessment policies.\n\n"
    "This software is released under the MIT License. See the LICENSE file for details.\n"
)


class LicensePopup(ctk.CTkToplevel):
    def __init__(self, parent, on_accept):
        super().__init__(parent)
        self.on_accept = on_accept
        self.title("License Agreement & Terms of Use")
        self.geometry("680x600"); self.configure(fg_color=C["bg_dark"])
        self.resizable(False, False)
        apply_icon(self); self.after(250, lambda: apply_icon(self))
        self.protocol("WM_DELETE_WINDOW", self._decline)
        self.after(120, lambda: fix_popup(self))
        self._build()

    def _build(self):
        label(self, "📋  Please Read & Accept", size=20, weight="bold").pack(pady=(22,4))
        label(self, "You must accept these terms to use Smart Paper Checker.",
              size=12, color=C["text_muted"]).pack(pady=(0,12))

        box = ctk.CTkTextbox(self, corner_radius=10, fg_color=C["bg_card"],
                             wrap="word", font=ctk.CTkFont(size=12))
        box.pack(fill="both", expand=True, padx=26, pady=(0,10))
        box.insert("1.0", LICENSE_TEXT)
        box.configure(state="disabled")

        self.agree_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="  I have read and agree to the Terms of Use and License.",
                        variable=self.agree_var, command=self._toggle,
                        font=ctk.CTkFont(size=12)).pack(anchor="w", padx=28, pady=(0,10))

        bf = ctk.CTkFrame(self, fg_color="transparent"); bf.pack(fill="x", padx=26, pady=(0,20))
        btn(bf, "Decline & Exit", self._decline, height=44, width=160,
            color=C["bg_card"]).pack(side="left")
        self.accept_btn = btn(bf, "✅  I Agree — Continue", self._accept,
                              height=44, width=240, color=C["success"])
        self.accept_btn.pack(side="right")
        self.accept_btn.configure(state="disabled")

    def _toggle(self):
        self.accept_btn.configure(state="normal" if self.agree_var.get() else "disabled")

    def _accept(self):
        settings_store.accept_license()
        self.grab_release(); self.destroy()
        if self.on_accept: self.on_accept()

    def _decline(self):
        try: self.master.destroy()
        except Exception: pass
        sys.exit(0)

# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    db.init()
    _settings = settings_store.load()
    ctk.set_appearance_mode(_settings.get("theme", "dark"))
    ctk.set_default_color_theme("blue")
    app = App()
    # First-launch terms acceptance — like an official installed app.
    if not settings_store.is_license_accepted():
        app.after(300, lambda: LicensePopup(app, on_accept=None))
    app.mainloop()
