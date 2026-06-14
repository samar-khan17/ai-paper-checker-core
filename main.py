"""
Paper Checker AI — Complete Desktop Application
Run: python main.py
"""

import sys, os, json, shutil, threading, logging
from pathlib import Path
from datetime import datetime

# ── Dependency check ─────────────────────────────────────────
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

# ── App icon / Windows taskbar identity ───────────────────────
def resource_path(name: str) -> str:
    """Resolve a bundled resource both in dev and inside a PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", str(Path(__file__).parent))
    return os.path.join(base, name)

ICON_PATH = resource_path("app_icon.ico")

def apply_icon(window):
    """Give a window our custom icon (used for main window + all dialogs)."""
    try:
        if os.path.exists(ICON_PATH):
            window.iconbitmap(ICON_PATH)
    except Exception:
        pass

# Tell Windows this is its own app so the taskbar shows OUR icon, not python's.
try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SmartPaperChecker.App.1")
except Exception:
    pass

# Internal imports
sys.path.insert(0, str(Path(__file__).parent))
from config import (APP_NAME, APP_VERSION, WINDOW_SIZE, MIN_WINDOW,
                    SUBJECTS, DIFFICULTY_LEVELS, UPLOAD_DIR, REPORT_DIR, ALLOWED_EXTENSIONS)
from core.security import pwd_mgr, tracker, sessions
from core.ai_grader import AIGrader
from core.question_parser import QuestionParser
from database.db_manager import DB

logger = logging.getLogger("main")

# ── Globals ───────────────────────────────────────────────────
db = DB()
grader = AIGrader()
parser = QuestionParser()

# ── Color Palette ─────────────────────────────────────────────
C = {
    "bg_dark":     "#0d0d1a",
    "bg_card":     "#13132a",
    "bg_sidebar":  "#0a0a18",
    "accent":      "#6366f1",      # Indigo
    "accent2":     "#8b5cf6",      # Purple
    "success":     "#22c55e",
    "warning":     "#f59e0b",
    "danger":      "#ef4444",
    "text":        "#e2e8f0",
    "text_muted":  "#64748b",
    "border":      "#1e1e3a",
}

# ═══════════════════════════════════════════════════════════════
#  HELPER WIDGETS
# ═══════════════════════════════════════════════════════════════

def card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=C["bg_card"],
                        corner_radius=14, border_width=1,
                        border_color=C["border"], **kw)

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
    ctk.CTkFrame(f, height=2, fg_color=C["accent"]).pack(side="left", fill="x", expand=True, padx=(12,0), pady=(8,0))
    return f

def status_badge(parent, text, color):
    return ctk.CTkLabel(parent, text=text,
                        fg_color=color, corner_radius=8,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        padx=10, pady=3)

# ═══════════════════════════════════════════════════════════════
#  SCROLLABLE TABLE
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

    def add_row(self, values: list, on_click=None):
        row = ctk.CTkFrame(self, fg_color=C["bg_card"], corner_radius=8,
                            border_width=1, border_color=C["border"])
        row.pack(fill="x", pady=2)
        for i, (val, (col, w)) in enumerate(zip(values, self.columns)):
            if isinstance(val, tuple):  # (text, color) for badge
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
            if isinstance(w, ctk.CTkFrame) and w.cget("fg_color") != C["accent"]:
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
        # Left decorative panel
        left = ctk.CTkFrame(self, fg_color=C["bg_sidebar"], corner_radius=0, width=480)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        ctk.CTkFrame(left, fg_color="transparent").pack(expand=True)
        label(left, "📝", size=72).pack()
        label(left, APP_NAME, size=28, weight="bold").pack(pady=(8,4))
        label(left, "AI-Powered Academic Assessment", size=14, color=C["text_muted"]).pack()
        ctk.CTkFrame(left, height=2, width=120, fg_color=C["accent"]).pack(pady=20)

        features = ["🤖  NVIDIA AI Grading Engine", "🔒  Z-Plus Security",
                    "📊  Analytics Dashboard", "📄  PDF & Excel Reports",
                    "🚩  Red Flag Detection", "✏️  Manual Override"]
        for f in features:
            label(left, f, size=13, color=C["text_muted"]).pack(pady=3)
        ctk.CTkFrame(left, fg_color="transparent").pack(expand=True)
        label(left, f"v{APP_VERSION}", size=11, color=C["text_muted"]).pack(pady=12)

        # Right login card
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
        rf = ctk.CTkFrame(wrap, fg_color="transparent")
        rf.pack(anchor="w", pady=(4,20))
        ctk.CTkRadioButton(rf, text="👩‍🏫 Teacher", variable=self.role, value="teacher",
                            fg_color=C["accent"]).pack(side="left", padx=(0,24))
        ctk.CTkRadioButton(rf, text="🎓 Student", variable=self.role, value="student",
                            fg_color=C["accent"]).pack(side="left")

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
        u = self.u_entry.get().strip()
        p = self.p_entry.get()
        role = self.role.get()
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
        w.geometry("420x460"); w.resizable(False,False)
        w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(250, lambda: apply_icon(w))
        w.after(200, w.grab_set)
        f = ctk.CTkFrame(w, fg_color="transparent")
        f.pack(padx=36, pady=36, fill="both", expand=True)
        label(f, "Create Account", size=20, weight="bold").pack(pady=(0,20))
        fields = {}
        for lbl, ph, sh in [("Full Name","Your full name",""),("Username","Choose username",""),
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
            # Block duplicate accounts before touching the database.
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
            # Success → close the dialog and guide the user to sign in.
            w.destroy()
            self.err.configure(text=f"✅ Account created for '{uname}'. Please sign in.",
                               text_color=C["success"])
            self.role.set(rv.get())
            self.u_entry.delete(0, "end"); self.u_entry.insert(0, uname)
            self.p_entry.delete(0, "end")
            self.p_entry.focus_set()
        create_btn = btn(f, "Create Account", do, height=44, width=340)
        create_btn.pack(pady=(12,0))

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
        self.after(250, lambda: apply_icon(self))  # re-apply; CTk can reset it on init
        self._center_window()
        self.user = None
        self.token = None
        self._frame = None
        self._show(LoginScreen)

    def _center_window(self):
        """Place the window in the middle of the screen on launch."""
        try:
            self.update_idletasks()
            w, h = (int(x) for x in WINDOW_SIZE.split("x"))
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2 - 20)
            self.geometry(f"{w}x{h}+{x}+{y}")
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
#  DASHBOARD SHELL (Sidebar + Content Area)
# ═══════════════════════════════════════════════════════════════

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color=C["bg_dark"], corner_radius=0)
        self.app = app
        self.user = app.user
        self.role = self.user.get("role","student")
        self._content = None
        self._nav_btns = {}
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── Sidebar ───────────────────────────────────────────
        sb = ctk.CTkFrame(self, width=230, fg_color=C["bg_sidebar"],
                           corner_radius=0, border_width=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

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

        # ── Content ───────────────────────────────────────────
        self._area = ctk.CTkFrame(self, fg_color=("#f1f5f9","#080814"), corner_radius=0)
        self._area.grid(row=0, column=1, sticky="nsew")
        self._area.grid_rowconfigure(0, weight=1)
        self._area.grid_columnconfigure(0, weight=1)

        default = "upload" if self.role=="teacher" else "papers"
        self._nav(default)

    def _teacher_nav(self):
        return [
            ("upload",   "📥", "Set Up Paper"),
            ("check",    "🧮", "Check Answer Sheet"),
            ("papers",   "📋", "My Papers"),
            ("grade",    "✅", "Checked Sheets"),
            ("results",  "📊", "Results & Analytics"),
            ("override", "✏️", "Manual Override"),
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
            "papers":   ManagePapersScreen,
            "grade":    GradeScreen,
            "results":  ResultsScreen,
            "override": OverrideScreen,
            "submit":   StudentSubmitScreen,
            "history":  HistoryScreen,
        }
        cls = screen_map.get(key)
        if cls:
            self._content = cls(self._area, self.app)
            self._content.grid(row=0, column=0, sticky="nsew")

# ═══════════════════════════════════════════════════════════════
#  TEACHER — UPLOAD PAPER
# ═══════════════════════════════════════════════════════════════

class UploadPaperScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.user = app.user
        self.files = {"q_paper_path":"","answer_key_path":"","marking_path":"","sample_path":""}
        self.paper_id = None
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)

        section_title(scroll, "📥  Set Up Question Paper")
        label(scroll, "Add an already-made question paper + answer key here once. "
                      "Then go to 'Check Answer Sheet' to mark each student against it.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,10))

        # Paper info card  (Title on top, Total Marks right below)
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
                           height=40, corner_radius=10,
                           fg_color=C["bg_dark"]).grid(row=3,column=1,sticky="ew",padx=(16,0),pady=(4,12))

        label(ig, "Difficulty Level", size=12, weight="bold").grid(row=4,column=0,sticky="w")
        self.diff_var = ctk.StringVar(value="3 - Medium")
        ctk.CTkOptionMenu(ig, values=[f"{k} - {v}" for k,v in DIFFICULTY_LEVELS.items()],
                           variable=self.diff_var, height=40, corner_radius=10,
                           fg_color=C["bg_dark"]).grid(row=5,column=0,sticky="ew",pady=(4,0))

        # File uploads
        section_title(scroll, "📁  Upload Files")
        files_card = card(scroll); files_card.pack(fill="x", pady=(0,16))
        fg = ctk.CTkFrame(files_card, fg_color="transparent"); fg.pack(fill="x", padx=20, pady=16)

        self.file_labels = {}
        for key, title, icon, required in [
            ("q_paper_path",   "Question Paper",    "📄", True),
            ("answer_key_path","Answer Key",         "🔑", True),
            ("marking_path",   "Marking Scheme",    "📋", False),
            ("sample_path",    "Sample Solution",   "✅", False),
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

        # Status
        self.status = label(scroll, "", color=C["success"])
        self.status.pack(pady=(8,4))
        self.prog = ctk.CTkProgressBar(scroll, height=8, corner_radius=4, progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))

        self.save_btn = btn(scroll, "💾  Save Paper (Question + Answer Key)", self._create, height=50)
        self.save_btn.pack(fill="x")

    def _pick(self, key):
        path = filedialog.askopenfilename(
            filetypes=[("Supported","*.jpg *.jpeg *.png *.pdf *.docx"), ("All","*.*")]
        )
        if path:
            self.files[key] = path
            self.file_labels[key].configure(text=Path(path).name, text_color=C["success"])

    def _create(self):
        title = self.title_e.get().strip()
        subject = self.subject_var.get()
        if not title:
            self.status.configure(text="⚠ Paper title is required.", text_color=C["danger"]); return
        if not self.files["q_paper_path"] or not self.files["answer_key_path"]:
            self.status.configure(text="⚠ Question Paper and Answer Key are required.", text_color=C["danger"]); return
        try:
            marks = int(self.marks_e.get() or "100")
        except: marks = 100
        diff = int(self.diff_var.get().split(" - ")[0])

        self.status.configure(text="Creating paper...", text_color=C["text_muted"])
        self.prog.set(0.2)
        self.update()

        # Create DB record
        self.paper_id = db.create_paper(self.user["id"], subject, title, marks, diff)
        self.prog.set(0.4); self.update()

        # Copy uploaded files
        updates = {}
        for key, src in self.files.items():
            if src:
                sub = {"q_paper_path":"question_papers","answer_key_path":"answer_keys",
                       "marking_path":"marking_schemes","sample_path":"sample_solutions"}.get(key, "")
                dest_dir = UPLOAD_DIR / sub
                dest = dest_dir / f"{self.paper_id}_{Path(src).name}"
                shutil.copy2(src, dest)
                updates[key] = str(dest)

        self.prog.set(0.6)
        self.status.configure(text="📖 Reading questions and answer key (OCR / AI)...",
                              text_color=C["warning"])
        self.save_btn.configure(state="disabled")
        self.update()

        q_path = updates.get("q_paper_path", "")
        ak_path = updates.get("answer_key_path", "")
        paper_id = self.paper_id

        def work():
            from core import ocr
            img_dir = UPLOAD_DIR / "question_papers" / f"{paper_id}_pages"
            parsed_q, parsed_ak = [], {}
            # ---- questions: text first, vision for image/PDF ----
            try:
                text = ocr.extract_text(q_path) if q_path else ""
                if text:
                    parsed_q = parser.parse_questions(text)
                if not parsed_q and q_path:
                    imgs = ocr.to_images(q_path, str(img_dir))
                    if imgs:
                        parsed_q = grader.read_questions_from_images(imgs)
            except Exception as e:
                logger.warning(f"question parse failed: {e}")
            # ---- answer key: text first, vision for image/PDF ----
            try:
                text = ocr.extract_text(ak_path) if ak_path else ""
                if text:
                    parsed_ak = parser.parse_answer_key(text)
                if not parsed_ak and ak_path:
                    imgs = ocr.to_images(ak_path, str(img_dir))
                    if imgs:
                        parsed_ak = grader.read_answers_from_images(imgs)
            except Exception as e:
                logger.warning(f"answer key parse failed: {e}")

            updates["parsed_questions"] = json.dumps(parsed_q)
            updates["parsed_answers"] = json.dumps({str(k): v for k, v in parsed_ak.items()})
            db.update_paper(paper_id, updates)
            db.log_audit("PAPER_SAVED", self.user["username"], f"paper_id={paper_id}")
            nq = len(parsed_q)
            self.after(0, lambda: self._saved(title, paper_id, nq))

        threading.Thread(target=work, daemon=True).start()

    def _saved(self, title, paper_id, nq):
        self.prog.set(1.0)
        self.save_btn.configure(state="normal")
        extra = f"{nq} question(s) detected." if nq else \
                "No questions auto-detected — checking will still work per overall answer."
        self.status.configure(
            text=f"✅ Paper '{title}' saved (ID: {paper_id}). {extra} "
                 f"Now go to 'Check Answer Sheet'.",
            text_color=C["success"])

# ═══════════════════════════════════════════════════════════════
#  MANAGE PAPERS (Teacher & Student view)
# ═══════════════════════════════════════════════════════════════

class ManagePapersScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.user = app.user
        self.role = self.user.get("role")
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "📋  " + ("My Papers" if self.role=="teacher" else "Available Papers"))

        cols = [("ID",60),("Title",240),("Subject",120),("Marks",80),("Difficulty",100),("Created",160)]
        self.table = Table(f, cols)
        self.table.pack(fill="both", expand=True)
        self._load()

    def _load(self):
        self.table.clear()
        if self.role == "teacher":
            papers = db.papers_by_teacher(self.user["id"])
        else:
            papers = db.all_papers()
        if not papers:
            self.table.empty("No papers yet." if self.role=="teacher"
                             else "No papers available yet. Check back later.")
            return
        for p in papers:
            diff = DIFFICULTY_LEVELS.get(p.get("difficulty",3), "Medium")
            self.table.add_row([p["id"], p["title"], p["subject"],
                                 p["total_marks"], diff,
                                 p["created_at"][:10]])

# ═══════════════════════════════════════════════════════════════
#  STUDENT — SUBMIT ANSWER SHEET
# ═══════════════════════════════════════════════════════════════

class StudentSubmitScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.user = app.user
        self.answer_path = ""
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "📤  Submit Answer Sheet")

        # Select paper
        c = card(scroll); c.pack(fill="x", pady=(0,16))
        f = ctk.CTkFrame(c, fg_color="transparent"); f.pack(fill="x", padx=20, pady=16)
        label(f, "Select Paper *", size=12, weight="bold").pack(anchor="w")
        papers = db.all_papers()
        self.paper_map = {f"{p['id']} — {p['title']} ({p['subject']})": p for p in papers}
        self.paper_var = ctk.StringVar(value=list(self.paper_map.keys())[0] if self.paper_map else "No papers available")
        ctk.CTkOptionMenu(f, values=list(self.paper_map.keys()) or ["No papers available"],
                           variable=self.paper_var, height=42, corner_radius=10,
                           fg_color=C["bg_dark"], width=500).pack(anchor="w", pady=(4,0))

        # Upload
        c2 = card(scroll); c2.pack(fill="x", pady=(0,16))
        f2 = ctk.CTkFrame(c2, fg_color="transparent"); f2.pack(fill="x", padx=20, pady=16)
        label(f2, "Answer Sheet File *", size=12, weight="bold").pack(anchor="w")
        label(f2, "Supported: JPG, PNG, PDF, DOCX", size=11, color=C["text_muted"]).pack(anchor="w")
        row = ctk.CTkFrame(f2, fg_color="transparent"); row.pack(fill="x", pady=(8,0))
        self.file_lbl = label(row, "No file selected", color=C["text_muted"])
        self.file_lbl.pack(side="left")
        btn(row, "Browse", self._pick, height=36, width=100).pack(side="left", padx=12)

        self.status = label(scroll, "", color=C["success"])
        self.status.pack(pady=(12,4))
        self.prog = ctk.CTkProgressBar(scroll, height=8, corner_radius=4, progress_color=C["accent"])
        self.prog.set(0); self.prog.pack(fill="x", pady=(0,12))
        btn(scroll, "🚀  Submit & Grade with AI", self._submit, height=50).pack(fill="x")

    def _pick(self):
        path = filedialog.askopenfilename(
            filetypes=[("Supported","*.jpg *.jpeg *.png *.pdf *.docx"), ("All","*.*")]
        )
        if path:
            self.answer_path = path
            self.file_lbl.configure(text=Path(path).name, text_color=C["success"])

    def _submit(self):
        key = self.paper_var.get()
        if key not in self.paper_map:
            self.status.configure(text="⚠ Select a valid paper.", text_color=C["danger"]); return
        if not self.answer_path:
            self.status.configure(text="⚠ Please upload your answer sheet.", text_color=C["danger"]); return

        paper = self.paper_map[key]
        self.status.configure(text="⏳ Submitting...", text_color=C["text_muted"])
        self.prog.set(0.1); self.update()

        # Copy answer file
        dest = UPLOAD_DIR / "student_answers" / f"{self.user['id']}_{paper['id']}_{Path(self.answer_path).name}"
        shutil.copy2(self.answer_path, dest)
        sub_id = db.create_submission(self.user["id"], paper["id"], str(dest))

        self.status.configure(text="🤖 AI grading in progress...", text_color=C["warning"])
        self.prog.set(0.3); self.update()

        # Grade in background thread
        def grade_thread():
            try:
                # Extract text from answer sheet
                student_answers = self._extract_student_answers(str(dest))

                # Load parsed questions and answer key
                questions = json.loads(paper.get("parsed_questions","[]"))
                answer_key = json.loads(paper.get("parsed_answers","{}"))
                answer_key = {int(k):v for k,v in answer_key.items()}

                if not questions:
                    # Create dummy question set for demo
                    questions = [{"number":1,"text":"General Question","marks":paper["total_marks"]}]
                    answer_key = {1:{"model_answer":"Expected comprehensive answer","marking_notes":"Award marks for relevant content."}}

                result = grader.grade_paper(questions, answer_key, student_answers, paper["subject"])

                db.set_status(sub_id, "graded")
                res_id = db.save_result(sub_id, result)
                db.save_history(self.user["id"], paper["id"], paper["subject"], paper["title"],
                                result["total_score"], result["total_max"],
                                result["percentage"], result["grade"])
                db.log_audit("GRADED", self.user["username"], f"sub_id={sub_id} grade={result['grade']}")

                self.after(0, lambda: self._done(result))
            except Exception as e:
                logger.error(f"Grading error: {e}")
                self.after(0, lambda: self.status.configure(text=f"❌ Error: {e}", text_color=C["danger"]))

        threading.Thread(target=grade_thread, daemon=True).start()

    def _extract_student_answers(self, path: str) -> dict:
        """Extract text from student answer and map to Q numbers."""
        text = ""
        ext = Path(path).suffix.lower()
        try:
            if ext == ".docx":
                import docx as dx
                doc = dx.Document(path)
                text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            elif ext in [".jpg",".jpeg",".png",".pdf"]:
                # Try OCR if available
                try:
                    import pytesseract
                    from PIL import Image
                    if ext in [".jpg",".jpeg",".png"]:
                        img = Image.open(path).convert('L')
                        text = pytesseract.image_to_string(img)
                    elif ext == ".pdf":
                        import pdf2image
                        pages = pdf2image.convert_from_path(path, dpi=200)
                        text = "\n".join(pytesseract.image_to_string(p.convert('L')) for p in pages)
                except ImportError:
                    text = "Answer sheet uploaded but OCR not available. Install pytesseract for full OCR support."
        except Exception as e:
            logger.warning(f"Text extraction failed: {e}")
            text = "Could not extract text from answer sheet."

        # Parse individual answers
        qs = parser.parse_questions(text)
        if qs:
            return {q["number"]: q["text"] for q in qs}
        return {1: text}  # fallback: treat entire text as Q1 answer

    def _done(self, result):
        self.prog.set(1.0)
        grade = result["grade"]
        pct = result["percentage"]
        conf = result["overall_confidence"]
        review = "⚠ Needs review" if result.get("needs_manual_review") else "✅ Auto-graded"
        self.status.configure(
            text=f"✅ Graded! Grade: {grade} | Score: {pct}% | Confidence: {round(conf*100)}% | {review}",
            text_color=C["success"]
        )
        self._show_result_popup(result)

    def _show_result_popup(self, result):
        w = ctk.CTkToplevel(self)
        w.title("Grading Result")
        w.geometry("600x560")
        w.configure(fg_color=C["bg_dark"])
        apply_icon(w); w.after(250, lambda: apply_icon(w))
        w.after(200, w.grab_set)

        f = ctk.CTkScrollableFrame(w, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=24)

        label(f, "🎓 Grading Complete!", size=22, weight="bold").pack(pady=(0,4))

        # Grade badge
        grade = result["grade"]
        grade_colors = {"A+":C["success"],"A":C["success"],"A-":C["success"],
                        "B+":C["accent"],"B":C["accent"],"B-":C["accent"],
                        "C+":C["warning"],"C":C["warning"],"C-":C["warning"],
                        "D":C["danger"],"F":C["danger"]}
        ctk.CTkLabel(f, text=grade, font=ctk.CTkFont(size=48, weight="bold"),
                      text_color=grade_colors.get(grade, C["text"])).pack(pady=4)
        label(f, f"{result['percentage']}%  •  {result['total_score']}/{result['total_max']} marks",
              size=16, color=C["text_muted"]).pack()

        # Summary
        if result.get("summary_feedback"):
            sc = card(f); sc.pack(fill="x", pady=(16,8))
            label(sc, result["summary_feedback"], size=12, color=C["text_muted"],
                  wraplength=500).pack(padx=16, pady=12)

        # Per-question results
        label(f, "Question Breakdown", size=15, weight="bold").pack(anchor="w", pady=(16,8))
        for qnum, qr in result.get("question_results",{}).items():
            qc = card(f); qc.pack(fill="x", pady=3)
            qf = ctk.CTkFrame(qc, fg_color="transparent"); qf.pack(fill="x", padx=16, pady=10)
            label(qf, f"Q{qnum}", size=13, weight="bold").pack(side="left")
            label(qf, f"{qr.get('score',0)}/{qr.get('max_marks',10)}", size=13,
                  color=C["success"]).pack(side="left", padx=12)
            conf_c = C["success"] if qr.get("confidence",0) > 0.75 else C["warning"]
            label(qf, f"Conf: {round(qr.get('confidence',0)*100)}%", size=11,
                  color=conf_c).pack(side="left")
            if qr.get("feedback"):
                label(qc, qr["feedback"], size=11, color=C["text_muted"],
                      wraplength=520).pack(anchor="w", padx=16, pady=(0,8))

        # Red flags
        if result.get("all_red_flags"):
            label(f, "⚠ Red Flags", size=14, weight="bold", color=C["danger"]).pack(anchor="w", pady=(12,4))
            for fl in result["all_red_flags"]:
                label(f, f"• Q{fl['question']}: {fl['flag']}", size=12, color=C["danger"]).pack(anchor="w")

        btn(f, "Close", w.destroy, height=44).pack(pady=(16,0), fill="x")

# ═══════════════════════════════════════════════════════════════
#  TEACHER — CHECK A STUDENT ANSWER SHEET  (core workflow)
# ═══════════════════════════════════════════════════════════════

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

def _extract_docx_text(path):
    try:
        import docx as dx
        doc = dx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.warning(f"docx read failed: {e}")
        return ""

def save_report(parent, meta, result, files):
    """Build the marked PDF and let the teacher choose where to save it."""
    try:
        from core.report import generate_report
        tmp = generate_report(meta, result, files)
        dest = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF Report", "*.pdf")],
            initialfile=Path(tmp).name, title="Save Result Report")
        if dest:
            shutil.copy2(tmp, dest)
            messagebox.showinfo("Saved", f"Report saved:\n{dest}")
            try: os.startfile(dest)  # open it for them
            except Exception: pass
    except Exception as e:
        logger.error(f"Report error: {e}")
        messagebox.showerror("Report Error", f"Could not create the report:\n{e}")


class CheckSheetScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self.files = []
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(scroll, "🧮  Check a Student's Answer Sheet")
        label(scroll, "Pick the question paper, enter the student's details, upload their "
                      "answer sheet, and the AI will mark it against the answer key.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,10))

        # paper picker
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

        # student details
        c2 = card(scroll); c2.pack(fill="x", pady=(0,14))
        g = ctk.CTkFrame(c2, fg_color="transparent"); g.pack(fill="x", padx=20, pady=16)
        g.grid_columnconfigure((0,1), weight=1)
        label(g, "Student Name *", size=12, weight="bold").grid(row=0,column=0,sticky="w")
        label(g, "Student ID / Roll No *", size=12, weight="bold").grid(row=0,column=1,sticky="w",padx=(16,0))
        self.name_e = entry(g, "e.g. Ali Khan"); self.name_e.grid(row=1,column=0,sticky="ew",pady=(4,12))
        self.roll_e = entry(g, "e.g. FA21-BCS-001"); self.roll_e.grid(row=1,column=1,sticky="ew",padx=(16,0),pady=(4,12))

        label(g, "Class / Section (optional)", size=12, weight="bold").grid(row=2,column=0,sticky="w")
        label(g, "Checking Mode *", size=12, weight="bold").grid(row=2,column=1,sticky="w",padx=(16,0))
        self.class_e = entry(g, "e.g. BCS-5A"); self.class_e.grid(row=3,column=0,sticky="ew",pady=(4,0))
        self.mode_var = ctk.StringVar(value="Normal")
        ctk.CTkOptionMenu(g, values=["Lenient","Normal","Hard","Insane"], variable=self.mode_var,
                          height=40, corner_radius=10, fg_color=C["bg_dark"]
                          ).grid(row=3,column=1,sticky="ew",padx=(16,0),pady=(4,0))
        label(g, "Lenient 60% · Normal 75% · Hard 85% · Insane 95% semantic match to be fully correct.",
              size=10, color=C["text_muted"]).grid(row=4,column=0,columnspan=2,sticky="w",pady=(8,0))

        # answer sheet upload
        c3 = card(scroll); c3.pack(fill="x", pady=(0,14))
        f3 = ctk.CTkFrame(c3, fg_color="transparent"); f3.pack(fill="x", padx=20, pady=16)
        label(f3, "Student's Answer Sheet *", size=12, weight="bold").pack(anchor="w")
        label(f3, "Photos (JPG/PNG) of a handwritten sheet, or PDF/DOCX. You can pick multiple pages.",
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
            filetypes=[("Answer sheet","*.jpg *.jpeg *.png *.bmp *.webp *.pdf *.docx"), ("All","*.*")])
        if paths:
            self.files = list(paths)
            self.file_lbl.configure(text=f"{len(self.files)} file(s) selected", text_color=C["success"])

    def _check(self):
        key = self.paper_var.get()
        if key not in self.paper_map:
            self.status.configure(text="⚠ Add a question paper first (Set Up Paper).", text_color=C["danger"]); return
        name = self.name_e.get().strip(); roll = self.roll_e.get().strip()
        if not name or not roll:
            self.status.configure(text="⚠ Enter the student's name and ID.", text_color=C["danger"]); return
        if not self.files:
            self.status.configure(text="⚠ Upload the student's answer sheet.", text_color=C["danger"]); return

        paper = self.paper_map[key]
        cls = self.class_e.get().strip()
        mode = self.mode_var.get().lower()
        self.check_btn.configure(state="disabled")
        self.status.configure(text="🤖 Reading & marking the sheet (Run AI Test)...", text_color=C["warning"])
        self.prog.set(0.2); self.update()
        srcs = list(self.files)

        def work():
            from core import ocr
            try:
                import re as _re
                roll_safe = _re.sub(r'[^\w\-]', '_', roll) or "student"
                # uploads/{paper_id}/{roll_number}/   (spec storage layout)
                dest_dir = UPLOAD_DIR / str(paper["id"]) / roll_safe
                dest_dir.mkdir(parents=True, exist_ok=True)
                dests = []
                for src in srcs:
                    dest = dest_dir / Path(src).name
                    try:
                        shutil.copy2(src, dest); dests.append(str(dest))
                    except Exception as e:
                        logger.warning(f"copy failed: {e}")

                # ordered images for vision + the report (PDF pages rendered in order)
                images = []
                for d in dests:
                    images.extend(ocr.to_images(d, str(dest_dir)))

                questions = json.loads(paper.get("parsed_questions","[]"))
                answer_key = {int(k):v for k,v in json.loads(paper.get("parsed_answers","{}")).items()}
                if not questions:
                    questions = [{"number":1,"text":"Overall answer","marks":paper["total_marks"]}]
                    answer_key = {1:{"model_answer":"","marking_notes":"Award marks for correct, relevant content."}}

                student_answers = {}
                if images:
                    self.after(0, lambda: (self.status.configure(
                        text="🔎 Reading the student's answer sheet...", text_color=C["warning"]),
                        self.prog.set(0.45)))
                    student_answers = grader.read_answer_sheet(images, questions)
                self.after(0, lambda: (self.status.configure(
                    text=f"📝 Marking {len(questions)} question(s) against the answer key...",
                    text_color=C["warning"]), self.prog.set(0.7)))
                for d in dests:
                    if Path(d).suffix.lower() == ".docx":
                        txt = _extract_docx_text(d)
                        for q in parser.parse_questions(txt):
                            student_answers.setdefault(q["number"], q["text"])
                        if txt and not student_answers:
                            student_answers = {1: txt}
                if not student_answers:
                    student_answers = {questions[0]["number"]:
                                       "(Could not read the answer sheet automatically.)"}

                result = grader.grade_paper(questions, answer_key, student_answers,
                                            paper["subject"], mode)

                sub_id = db.create_submission(
                    self.user["id"], paper["id"], dests[0] if dests else "",
                    student_name=name, student_roll=roll, class_section=cls,
                    checking_mode=mode, answer_images=images)
                db.set_status(sub_id, "graded")
                db.save_result(sub_id, result)
                db.save_history(self.user["id"], paper["id"], paper["subject"], paper["title"],
                                result["total_score"], result["total_max"],
                                result["percentage"], result["grade"])
                db.log_audit("CHECKED", self.user["username"],
                             f"student={name} roll={roll} mode={mode} grade={result['grade']}")
                meta = {"student_name":name, "student_roll":roll, "class_section":cls,
                        "checking_mode":mode, "paper_title":paper["title"],
                        "subject":paper["subject"]}
                self.after(0, lambda: self._done(result, meta, images))
            except Exception as e:
                logger.error(f"Check error: {e}")
                self.after(0, lambda: (self.status.configure(text=f"❌ Error: {e}", text_color=C["danger"]),
                                       self.check_btn.configure(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    def _done(self, result, meta, files):
        self.prog.set(1.0)
        self.check_btn.configure(state="normal")
        self.status.configure(
            text=f"✅ {meta['student_name']} ({meta['student_roll']}) — "
                 f"{result['grade']} | {result['percentage']}% | "
                 f"{result['total_score']}/{result['total_max']}",
            text_color=C["success"])
        ResultPopup(self, result, meta, files)


class ResultPopup(ctk.CTkToplevel):
    """Shared result window with a Download Report (PDF) button."""
    def __init__(self, parent, result, meta, files):
        super().__init__(parent)
        self.title("Result")
        self.geometry("620x600")
        self.configure(fg_color=C["bg_dark"])
        apply_icon(self); self.after(250, lambda: apply_icon(self))
        self.after(200, self.grab_set)
        self.result, self.meta, self.files = result, meta, files

        f = ctk.CTkScrollableFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=24, pady=24)

        label(f, "🎓 Checking Complete", size=22, weight="bold").pack(pady=(0,2))
        label(f, f"{meta.get('student_name','')}  •  ID: {meta.get('student_roll','')}",
              size=13, color=C["text_muted"]).pack()
        label(f, f"{meta.get('paper_title','')}  ({meta.get('subject','')})",
              size=12, color=C["text_muted"]).pack(pady=(0,6))

        grade = result["grade"]
        gc = {"A+":C["success"],"A":C["success"],"A-":C["success"],"B+":C["accent"],
              "B":C["accent"],"B-":C["accent"],"C+":C["warning"],"C":C["warning"],
              "C-":C["warning"],"D":C["danger"],"F":C["danger"]}
        ctk.CTkLabel(f, text=grade, font=ctk.CTkFont(size=46, weight="bold"),
                     text_color=gc.get(grade, C["text"])).pack(pady=2)
        label(f, f"{result['percentage']}%  •  {result['total_score']}/{result['total_max']} marks",
              size=15, color=C["text_muted"]).pack()

        btn(f, "⬇  Download Report (PDF)",
            lambda: save_report(self, self.meta, self.result, self.files),
            height=46, color=C["success"]).pack(fill="x", pady=(16,4))
        imgs = [x for x in (self.files or []) if Path(x).suffix.lower() in IMAGE_EXTS]
        if imgs:
            btn(f, f"🖼  Open Answer Sheet ({len(imgs)} page(s))",
                lambda: [os.startfile(x) for x in imgs[:6]] if os.name == "nt" else None,
                height=40).pack(fill="x", pady=(0,8))

        if result.get("summary_feedback"):
            sc = card(f); sc.pack(fill="x", pady=(4,8))
            label(sc, result["summary_feedback"], size=12, color=C["text_muted"],
                  wraplength=520).pack(padx=16, pady=12)

        label(f, "Question-by-Question", size=15, weight="bold").pack(anchor="w", pady=(14,8))
        for qnum, qr in result.get("question_results", {}).items():
            mx = qr.get("max_marks",0); sc = qr.get("score",0)
            verdict = ("✓ Correct", C["success"]) if mx and sc>=mx-1e-6 else \
                      (("✗ Wrong", C["danger"]) if sc<=1e-6 else ("~ Partial", C["warning"]))
            qc = card(f); qc.pack(fill="x", pady=3)
            top = ctk.CTkFrame(qc, fg_color="transparent"); top.pack(fill="x", padx=16, pady=(10,2))
            label(top, f"Q{qnum}", size=13, weight="bold").pack(side="left")
            label(top, f"{sc}/{mx}", size=13, color=C["success"]).pack(side="left", padx=12)
            status_badge(top, verdict[0], verdict[1]).pack(side="left")
            if qr.get("question_text"):
                label(qc, f"Q: {qr['question_text']}", size=11, color=C["text"],
                      wraplength=540).pack(anchor="w", padx=16, pady=(2,0))
            if qr.get("student_answer"):
                label(qc, f"Student: {qr['student_answer']}", size=11, color=C["text_muted"],
                      wraplength=540).pack(anchor="w", padx=16, pady=(2,0))
            if qr.get("model_answer"):
                label(qc, f"Official: {qr['model_answer']}", size=11, color=C["accent2"],
                      wraplength=540).pack(anchor="w", padx=16, pady=(2,0))
            if qr.get("feedback"):
                label(qc, f"Remark: {qr['feedback']}", size=11, color=C["text_muted"],
                      wraplength=540).pack(anchor="w", padx=16, pady=(2,8))

        if result.get("all_red_flags"):
            label(f, "⚠ Red Flags", size=14, weight="bold", color=C["danger"]).pack(anchor="w", pady=(12,4))
            for fl in result["all_red_flags"]:
                label(f, f"• Q{fl['question']}: {fl['flag']}", size=12, color=C["danger"]).pack(anchor="w")

        btn(f, "Close", self.destroy, height=42).pack(pady=(16,0), fill="x")


# ═══════════════════════════════════════════════════════════════
#  GRADE SUBMISSIONS (Teacher)
# ═══════════════════════════════════════════════════════════════

class GradeScreen(ctk.CTkFrame):
    """Checked Papers — search & retrieve past results by roll / name / paper ID."""
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app; self.user = app.user
        self._build()

    def _build(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=28, pady=20)
        section_title(f, "✅  Checked Papers")

        top = card(f); top.pack(fill="x", pady=(0,16))
        tf = ctk.CTkFrame(top, fg_color="transparent"); tf.pack(fill="x", padx=20, pady=14)
        label(tf, "Search:", size=13, weight="bold").pack(side="left")
        self.search_e = entry(tf, "Roll number, student name, or paper ID", width=420, height=40)
        self.search_e.pack(side="left", padx=12)
        self.search_e.bind("<Return>", lambda e: self._load())
        btn(tf, "Search", self._load, height=40, width=110).pack(side="left")
        btn(tf, "Show All", lambda: (self.search_e.delete(0,"end"), self._load()),
            height=40, width=110, color=C["bg_dark"]).pack(side="left", padx=(8,0))

        cols = [("Roll",130),("Student",170),("Paper",200),("Mode",80),
                ("Score",90),("Grade",60),("Date",120),("Action",80)]
        self.table = Table(f, cols)
        self.table.pack(fill="both", expand=True)
        self._load()

    def _load(self):
        self.table.clear()
        rows = db.search_submissions(self.user["id"], self.search_e.get())
        if not rows:
            self.table.empty("No checked papers found. Use 'Check Answer Sheet' to mark one.")
            return
        for s in rows:
            score = f"{s.get('total_score','-')}/{s.get('total_max','-')}" if s.get("total_max") else "—"
            def view(sid=s["id"]):
                self._open(sid)
            self.table.add_row([
                s.get("student_roll","") or "—", s.get("student_name","") or "—",
                f"{s.get('paper_id')} — {s.get('paper_title','')}", (s.get("checking_mode","") or "").title(),
                score, s.get("grade","") or "—", (s.get("submitted_at","") or "")[:10], "View"
            ], on_click=view)

    def _open(self, sub_id):
        res = db.get_result_by_submission(sub_id)
        if not res:
            messagebox.showinfo("Not Checked", "This paper has not been checked yet."); return
        sub = db.get_submission(sub_id) or {}
        meta = db.get_submission_meta(sub_id) or {}
        meta["checking_mode"] = sub.get("checking_mode", "")
        meta["class_section"] = sub.get("class_section", "")
        files = sub.get("answer_images", []) or ([sub.get("answer_sheet_path")] if sub.get("answer_sheet_path") else [])
        ResultPopup(self, res, meta, files)

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
            label(tf, "Paper:", size=13, weight="bold").pack(side="left")
            papers = db.papers_by_teacher(self.user["id"])
            self.pmap = {f"{p['id']} — {p['title']}": p for p in papers}
            self.pvar = ctk.StringVar(value=list(self.pmap.keys())[0] if self.pmap else "")
            ctk.CTkOptionMenu(tf, values=list(self.pmap.keys()) or ["No papers"],
                               variable=self.pvar, height=40, fg_color=C["bg_dark"],
                               corner_radius=10, width=400).pack(side="left", padx=12)
            btn(tf, "Load", self._load_teacher, height=40, width=100).pack(side="left")

            self.stats_frame = ctk.CTkFrame(f, fg_color="transparent")
            self.stats_frame.pack(fill="x", pady=(0,12))
            cols = [("Roll",120),("Student",160),("Score",80),("Max",60),("Percent",90),("Grade",70),("Confidence",100),("Review",80)]
        else:
            cols = [("Paper",220),("Subject",120),("Score",80),("Max",60),("Grade",70),("Date",140)]

        self.table = Table(f, cols)
        self.table.pack(fill="both", expand=True)
        if self.role == "student": self._load_student()

    def _load_teacher(self):
        for w in self.stats_frame.winfo_children(): w.destroy()
        key = self.pvar.get()
        if key not in self.pmap: return
        paper = self.pmap[key]
        results = db.results_for_paper(paper["id"])
        if results:
            pcts = [r["percentage"] for r in results]
            avg = round(sum(pcts)/len(pcts),1)
            for label_text, val in [("Students",len(results)),("Average",f"{avg}%"),
                                      ("Highest",f"{max(pcts)}%"),("Lowest",f"{min(pcts)}%")]:
                sc = card(self.stats_frame)
                sc.pack(side="left", padx=(0,12), pady=4, ipadx=16, ipady=8)
                ctk.CTkLabel(sc, text=str(val), font=ctk.CTkFont(size=22,weight="bold"),
                              text_color=C["accent"]).pack(padx=20,pady=(10,2))
                label(sc, label_text, size=11, color=C["text_muted"]).pack(padx=20,pady=(0,10))
        self.table.clear()
        if not results:
            self.table.empty("No graded submissions for this paper yet.")
            return
        for r in results:
            review_badge = ("Review",C["warning"]) if r["needs_review"] else ("OK",C["success"])
            self.table.add_row([r.get("student_roll","") or "—", r["student_name"],
                                 r["total_score"],r["total_max"],
                                 f"{r['percentage']}%",r["grade"],
                                 f"{round(r['overall_confidence']*100)}%", review_badge])

    def _load_student(self):
        subs = db.submissions_for_student(self.user["id"])
        rows = 0
        for s in subs:
            res = db.get_result_by_submission(s["id"])
            if res:
                self.table.add_row([s["paper_title"],s["subject"],res["total_score"],
                                     res["total_max"],res["grade"],s["submitted_at"][:10]])
                rows += 1
        if rows == 0:
            self.table.empty("No results yet. Submit an answer sheet to see your grades here.")

# ═══════════════════════════════════════════════════════════════
#  MANUAL OVERRIDE (Teacher)
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
        label(f, "Search by Submission ID to apply manual grade override with audit trail.",
              size=12, color=C["text_muted"]).pack(anchor="w", pady=(0,16))

        top = card(f); top.pack(fill="x", pady=(0,16))
        tf = ctk.CTkFrame(top, fg_color="transparent"); tf.pack(fill="x", padx=20, pady=16)
        label(tf, "Submission ID:", size=13, weight="bold").pack(side="left")
        self.sid_e = entry(tf, "e.g. 3", width=120, height=40)
        self.sid_e.pack(side="left", padx=12)
        btn(tf, "Load", self._load, height=40, width=100).pack(side="left")

        self.detail = card(f); self.detail.pack(fill="x", pady=(0,12))
        self.detail_inner = ctk.CTkFrame(self.detail, fg_color="transparent")
        self.detail_inner.pack(fill="x", padx=20, pady=16)
        label(self.detail_inner, "Enter a Submission ID above to load result.",
              color=C["text_muted"]).pack()

    def _load(self):
        try: sid = int(self.sid_e.get())
        except: return
        res = db.get_result_by_submission(sid)
        if not res:
            messagebox.showwarning("Not Found", f"No result for submission {sid}")
            return
        for w in self.detail_inner.winfo_children(): w.destroy()
        label(self.detail_inner, f"Result ID: {res['id']}  |  Current Grade: {res['grade']}  |  Score: {res['total_score']}/{res['total_max']}",
              size=14, weight="bold").pack(anchor="w")
        label(self.detail_inner, "New Score:", size=12, weight="bold").pack(anchor="w", pady=(12,2))
        self.new_score_e = entry(self.detail_inner, f"Current: {res['total_score']}", width=200)
        self.new_score_e.pack(anchor="w", pady=(0,8))
        label(self.detail_inner, "Override Notes (required):", size=12, weight="bold").pack(anchor="w")
        self.notes_e = ctk.CTkTextbox(self.detail_inner, height=80, corner_radius=8)
        self.notes_e.pack(fill="x", pady=(4,12))
        btn(self.detail_inner, "✏️  Apply Override", lambda: self._apply(res), height=44, color=C["warning"]).pack(anchor="w")

    def _apply(self, res):
        try: new_s = float(self.new_score_e.get())
        except: messagebox.showerror("Error","Enter a valid score number."); return
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
        cols = [("Subject",140),("Paper",220),("Score",80),("Total",70),("Grade",70),("Percent",90),("Date",140)]
        t = Table(f, cols)
        t.pack(fill="both", expand=True)
        history = db.get_history(self.user["id"])
        if not history:
            t.empty("No graded papers yet. Submit an answer sheet to get started.")
        for h in history:
            t.add_row([h["subject"],h["title"],h["score"],h["total_marks"],
                        h["grade"],f"{h['percentage']}%",h["recorded_at"][:10]])

# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    db.init()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
