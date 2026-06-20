# ui/screens/dashboard_screen.py — Role-based dashboard
import customtkinter as ctk
from database.db_manager import DatabaseManager

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app, user):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.user = user
        self.db = DatabaseManager()
        self.role = user.get("role", "student")
        self._build()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0,
                                fg_color=("#1e1e2e", "#12121f"))
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        # App logo in sidebar
        ctk.CTkLabel(sidebar, text="📝", font=ctk.CTkFont(size=36)).pack(pady=(30, 4))
        ctk.CTkLabel(sidebar, text="Smart Paper\nChecker",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     justify="center").pack(pady=(0, 4))
        
        role_badge = "👩‍🏫 Teacher" if self.role == "teacher" else "🎓 Student"
        ctk.CTkLabel(sidebar, text=role_badge,
                     font=ctk.CTkFont(size=11),
                     fg_color=("#3b82f6", "#2563eb"),
                     corner_radius=8, padx=8, pady=2).pack(pady=(0, 24))

        ctk.CTkLabel(sidebar, text=f"Hi, {self.user.get('full_name', 'User').split()[0]}!",
                     font=ctk.CTkFont(size=13), text_color="gray").pack(pady=(0, 16))

        ctk.CTkFrame(sidebar, height=1, fg_color="gray30").pack(fill="x", padx=20, pady=(0, 16))

        # Navigation buttons
        nav_items = self._get_nav_items()
        self.nav_buttons = {}
        for label, icon, key in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=f"  {icon}  {label}", anchor="w",
                height=44, corner_radius=10,
                fg_color="transparent",
                hover_color=("#2a2a3e", "#2a2a4e"),
                font=ctk.CTkFont(size=13),
                command=lambda k=key: self._navigate(k)
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[key] = btn

        # Logout at bottom
        ctk.CTkFrame(sidebar, height=1, fg_color="gray30").pack(fill="x", padx=20, pady=16, side="bottom")
        ctk.CTkButton(sidebar, text="  🚪  Logout", anchor="w", height=44, corner_radius=10,
                       fg_color="transparent", hover_color=("#3a1a1a", "#4a1a1a"),
                       font=ctk.CTkFont(size=13),
                       command=self.app.logout).pack(fill="x", padx=12, pady=8, side="bottom")

        # Main content area
        self.content = ctk.CTkFrame(self, fg_color=("#f0f4f8", "#0f0f1a"), corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # Show default screen
        default = "upload_paper" if self.role == "teacher" else "my_papers"
        self._navigate(default)

    def _get_nav_items(self):
        if self.role == "teacher":
            return [
                ("Upload Paper", "📤", "upload_paper"),
                ("Manage Papers", "📋", "manage_papers"),
                ("Grade Submissions", "✅", "grade"),
                ("Analytics", "📊", "analytics"),
                ("Manual Override", "✏️", "override"),
            ]
        else:
            return [
                ("Available Papers", "📋", "my_papers"),
                ("Submit Answer", "📤", "submit"),
                ("My Results", "📈", "my_results"),
                ("My History", "📅", "history"),
            ]

    def _navigate(self, key: str):
        # Highlight active nav button
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=("#2563eb","#1d4ed8") if k == key else "transparent")

        # Clear content
        for widget in self.content.winfo_children():
            widget.destroy()

        # Load screen
        frame = self._load_screen(key)
        if frame:
            frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

    def _load_screen(self, key: str):
        screens = {
            "upload_paper": lambda: self._placeholder("Upload Paper", "📤", "Hiba & Leader implement this"),
            "manage_papers": lambda: self._placeholder("Manage Papers", "📋", "Leader implements this"),
            "grade": lambda: self._placeholder("Grade Submissions", "✅", "Leader implements this"),
            "analytics": lambda: self._placeholder("Analytics Dashboard", "📊", "Hamza implements this"),
            "override": lambda: self._placeholder("Manual Override", "✏️", "Leader implements this"),
            "my_papers": lambda: self._placeholder("Available Papers", "📋", "Hussam & Hamza implement this"),
            "submit": lambda: self._placeholder("Submit Answer Sheet", "📤", "Hiba implements this"),
            "my_results": lambda: self._placeholder("My Results", "📈", "Hamza implements this"),
            "history": lambda: self._placeholder("My History", "📅", "Hussam implements this"),
        }
        factory = screens.get(key)
        return factory() if factory else None

    def _placeholder(self, title, icon, note):
        """Placeholder for screens not yet implemented."""
        f = ctk.CTkFrame(self.content, fg_color="transparent")
        f.grid_rowconfigure(0, weight=1)
        f.grid_columnconfigure(0, weight=1)
        inner = ctk.CTkFrame(f, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(inner, text=icon, font=ctk.CTkFont(size=64)).pack()
        ctk.CTkLabel(inner, text=title, font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(8, 4))
        ctk.CTkLabel(inner, text=note, font=ctk.CTkFont(size=14), text_color="gray").pack()
        return f
