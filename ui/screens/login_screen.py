# ui/screens/login_screen.py — Secure Login with brute force protection
import customtkinter as ctk
# CODE FIX: Import unified backend security modules
from core.security import tracker, sessions, pwd_mgr, sanitizer
from database.db_manager import DatabaseManager

class LoginScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.db = DatabaseManager()
        self._build()

    def _build(self):
        # Background gradient effect
        bg = ctk.CTkFrame(self, fg_color=("#1a1a2e", "#16213e"), corner_radius=0)
        bg.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center card
        card = ctk.CTkFrame(bg, width=440, fg_color=("#ffffff", "#1e1e2e"),
                             corner_radius=24, border_width=1,
                             border_color=("#e0e0e0", "#3a3a5c"))
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=40, pady=40)

        # Logo area
        ctk.CTkLabel(inner, text="📝", font=ctk.CTkFont(size=48)).pack(pady=(0, 8))
        ctk.CTkLabel(inner, text="Smart Paper Checker",
                     font=ctk.CTkFont(size=22, weight="bold")).pack()
        ctk.CTkLabel(inner, text="Academic Assessment System",
                     font=ctk.CTkFont(size=12),
                     text_color=("gray50", "gray60")).pack(pady=(2, 24))

        # Username
        ctk.CTkLabel(inner, text="Username", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
        self.username_entry = ctk.CTkEntry(inner, height=42, placeholder_text="Enter your username",
                                            corner_radius=10)
        self.username_entry.pack(fill="x", pady=(4, 12))

        # Password
        ctk.CTkLabel(inner, text="Password", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
        pw_row = ctk.CTkFrame(inner, fg_color="transparent")
        pw_row.pack(fill="x", pady=(4, 12))
        self.password_entry = ctk.CTkEntry(pw_row, height=42, show="•",
                                            placeholder_text="Enter your password",
                                            corner_radius=10)
        self.password_entry.pack(side="left", fill="x", expand=True)
        self.show_pw_btn = ctk.CTkButton(pw_row, text="👁", width=42, height=42,
                                          corner_radius=10, fg_color="transparent",
                                          border_width=1, command=self._toggle_pw)
        self.show_pw_btn.pack(side="left", padx=(6, 0))

        # Role selector
        ctk.CTkLabel(inner, text="Login As", anchor="w",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x")
        self.role_var = ctk.StringVar(value="teacher")
        role_frame = ctk.CTkFrame(inner, fg_color="transparent")
        role_frame.pack(fill="x", pady=(4, 16))
        ctk.CTkRadioButton(role_frame, text="👩‍🏫 Teacher", variable=self.role_var,
                            value="teacher").pack(side="left", padx=(0, 20))
        ctk.CTkRadioButton(role_frame, text="🎓 Student", variable=self.role_var,
                            value="student").pack(side="left")

        # Error label
        self.error_label = ctk.CTkLabel(inner, text="", text_color="#ef4444",
                                         font=ctk.CTkFont(size=12))
        self.error_label.pack(pady=(0, 8))

        # Buttons
        self.login_btn = ctk.CTkButton(inner, text="Login", height=44,
                                        corner_radius=10, font=ctk.CTkFont(size=14, weight="bold"),
                                        command=self._login)
        self.login_btn.pack(fill="x", pady=(0, 8))
        self.username_entry.bind("<Return>", lambda e: self._login())
        self.password_entry.bind("<Return>", lambda e: self._login())

        ctk.CTkButton(inner, text="Create Account", height=44, corner_radius=10,
                       fg_color="transparent", border_width=1,
                       font=ctk.CTkFont(size=14),
                       command=self._show_register).pack(fill="x")

    def _toggle_pw(self):
        self.password_entry.configure(
            show="" if self.password_entry.cget("show") == "•" else "•"
        )

    def _login(self):
        raw_username = self.username_entry.get().strip()
        password = self.password_entry.get()
        role = self.role_var.get()

        username = sanitizer.sanitize_username(raw_username)
        if not username or not password:
            self.error_label.configure(text="Please enter username and password.")
            return

        # CODE FIX: Map directly to verified tracker properties
        locked, mins = tracker.is_locked(username)
        if locked:
            self.error_label.configure(
                text=f"Account locked. Try again in {mins} minute(s)."
            )
            return

        # CODE FIX: Changed get_user_by_username to get_user
        user = self.db.get_user(username)
        if not user or user["role"] != role:
            tracker.record(username, False)
            remaining = tracker.remaining(username)
            self.error_label.configure(
                text=f"Invalid credentials. {remaining} attempt(s) remaining."
            )
            self.db.log_audit("LOGIN_FAILED", username, f"role={role}")
            return

        # CODE FIX: Swapped out password_manager with pwd_mgr module properties
        if not pwd_mgr.verify_password(password, user["password_hash"]):
            tracker.record(username, False)
            remaining = tracker.remaining(username)
            self.error_label.configure(
                text=f"Invalid credentials. {remaining} attempt(s) remaining."
            )
            self.db.log_audit("LOGIN_FAILED", username, "wrong password")
            return

        # CODE FIX: Updated success trackers, timestamps, and session routing aliases
        tracker.record(username, True)
        self.db.touch_login(user["id"])
        token = sessions.create(dict(user))
        self.db.log_audit("LOGIN_SUCCESS", username, f"role={role}")
        self.app.login_success(dict(user), token)

    def _show_register(self):
        win = ctk.CTkToplevel(self)
        win.title("Create Account")
        win.geometry("420x520")
        win.resizable(False, False)
        win.grab_set()

        inner = ctk.CTkFrame(win, fg_color="transparent")
        inner.pack(expand=True, fill="both", padx=36, pady=36)

        ctk.CTkLabel(inner, text="Create New Account",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 20))

        fields = {}
        for label, placeholder, show in [
            ("Full Name", "e.g. Ahmed Khan", ""),
            ("Username", "Choose a username", ""),
            ("Password", "Min 8 chars, 1 upper, 1 number", "•"),
            ("Email (optional)", "your@email.com", ""),
        ]:
            ctk.CTkLabel(inner, text=label, anchor="w").pack(fill="x")
            e = ctk.CTkEntry(inner, height=40, show=show, placeholder_text=placeholder,
                              corner_radius=10)
            e.pack(fill="x", pady=(2, 10))
            fields[label] = e

        role_v = ctk.StringVar(value="student")
        rf = ctk.CTkFrame(inner, fg_color="transparent")
        rf.pack(fill="x", pady=(0, 12))
        ctk.CTkRadioButton(rf, text="Teacher", variable=role_v, value="teacher").pack(side="left", padx=(0,20))
        ctk.CTkRadioButton(rf, text="Student", variable=role_v, value="student").pack(side="left")

        msg = ctk.CTkLabel(inner, text="", text_color="#22c55e", wraplength=340)
        msg.pack()

        def do_register():
            name = sanitizer.sanitize_text(fields["Full Name"].get())
            uname = sanitizer.sanitize_username(fields["Username"].get())
            pw = fields["Password"].get()
            role = role_v.get()

            if not name or not uname or not pw:
                msg.configure(text="Name, username, and password are required.", text_color="#ef4444")
                return
            try:
                # CODE FIX: Map password checking and entry signatures to backend definitions
                pw_hash = pwd_mgr.hash_password(pw)
                self.db.create_user(uname, pw_hash, role, name)
                self.db.log_audit("REGISTER", uname, f"role={role}")
                msg.configure(text="✅ Account created! You can now login.", text_color="#22c55e")
            except ValueError as ve:
                msg.configure(text=str(ve), text_color="#ef4444")
            except Exception as e:
                if "UNIQUE" in str(e):
                    msg.configure(text="Username already taken.", text_color="#ef4444")
                else:
                    msg.configure(text=f"Error: {str(e)}", text_color="#ef4444")

        ctk.CTkButton(inner, text="Create Account", height=44, corner_radius=10,
                       command=do_register).pack(fill="x", pady=(12, 0))