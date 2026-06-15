# ui/app.py — Main app router
import customtkinter as ctk
from config import APP_NAME, WINDOW_SIZE, MIN_WINDOW_SIZE

class SmartPaperApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry(WINDOW_SIZE)
        self.minsize(*MIN_WINDOW_SIZE)
        self.current_user = None
        self.current_token = None
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._active_frame = None
        self.show_login()

    def show_login(self):
        self._clear()
        from ui.screens.login_screen import LoginScreen
        self._active_frame = LoginScreen(self, self)
        self._active_frame.grid(row=0, column=0, sticky="nsew")

    def show_dashboard(self):
        self._clear()
        from ui.screens.dashboard_screen import DashboardScreen
        self._active_frame = DashboardScreen(self, self, self.current_user)
        self._active_frame.grid(row=0, column=0, sticky="nsew")

    def login_success(self, user_data: dict, token: str):
        self.current_user = user_data
        self.current_token = token
        self.show_dashboard()

    def logout(self):
        from core.security import session_manager
        if self.current_token:
            session_manager.destroy_session(self.current_token)
        self.current_user = None
        self.current_token = None
        self.show_login()

    def _clear(self):
        if self._active_frame:
            self._active_frame.destroy()
            self._active_frame = None
