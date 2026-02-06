# -*- coding: utf-8 -*-
import threading
import json
import os
from datetime import datetime, timedelta
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QMessageBox, QApplication, QPushButton, QDialog, QGridLayout, QLineEdit, QMenu, QAction,
    QFileDialog, QComboBox, QStackedLayout
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent
from PyQt5.QtGui import QFont

# UI + components
from src.gui.components.sidebar import Sidebar
from src.gui.components.password_list import PasswordList
from src.gui.components.modals import (
    LoginModal, RegisterModal, AddPasswordModal,
    EditPasswordModal, ViewPasswordModal, TwoFactorModal
)
from src.gui.styles.styles import Styles
from src.gui.autofill import (
    autofill_with_selenium,
    open_and_type_credentials,
    simple_copy_paste_method
)
# Services
from src.backend.api_client import APIClient
from src.auth.auth_manager import AuthManager, verify_password
from src.security.encryption import (
    encrypt_for_storage,
    decrypt_any,
    encrypt_vault_payload,
    decrypt_vault_payload,
)


# ----------------------------- Small helpers -----------------------------
class Quick2FADialog(QDialog):
    code_verified = pyqtSignal()

    def __init__(self, email: str, parent=None):
        super().__init__(parent)
        self.email = email
        self._build()

    def _build(self):
        self.setWindowTitle("Vérification 2FA")
        self.setFixedSize(420, 300)
        self.setModal(True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        icon = QLabel("🔐")
        icon.setStyleSheet("font-size:48px;")
        icon.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon)

        title = QLabel("Vérification de sécurité")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignLeft)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY};")
        lay.addWidget(title)

        info = QLabel(f"Code envoyé à :\n{self.email}")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:13px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Code à 6 chiffres")
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignCenter)
        self.code_input.setFont(QFont("Courier New", 18, QFont.Bold))
        self.code_input.setStyleSheet(f"""
            QLineEdit {{
                {Styles.get_input_style()}
                padding: 12px;
                font-size: 20px;
                letter-spacing: 8px;
            }}
        """)
        self.code_input.returnPressed.connect(self.code_verified.emit)
        lay.addWidget(self.code_input)

        verify_btn = QPushButton("✔ Vérifier")
        verify_btn.setMinimumHeight(44)
        verify_btn.setCursor(Qt.PointingHandCursor)
        verify_btn.setStyleSheet(Styles.get_button_style(True))
        verify_btn.clicked.connect(self.code_verified.emit)
        lay.addWidget(verify_btn)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(Styles.get_button_style(False))
        cancel_btn.clicked.connect(self.reject)
        lay.addWidget(cancel_btn)

        self.code_input.setFocus()


class UserProfileWidget(QWidget):
    logout_clicked = pyqtSignal()
    show_statistics = pyqtSignal()
    edit_profile_clicked = pyqtSignal()
    show_devices_clicked = pyqtSignal()
    lock_now_clicked = pyqtSignal()

    def __init__(self, username: str, initials: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.initials = initials
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        avatar = QPushButton(self.initials)
        avatar.setFixedSize(40, 40)
        avatar.setCursor(Qt.PointingHandCursor)
        avatar.clicked.connect(self._menu)
        avatar.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.PURPLE});
                border-radius: 20px; color:#fff; font-weight:bold;
            }}
        """)
        row.addWidget(avatar)

        name_btn = QPushButton(self.username)
        name_btn.setCursor(Qt.PointingHandCursor)
        name_btn.clicked.connect(self._menu)
        name_btn.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{Styles.TEXT_PRIMARY};
                          border:none; font-size:14px; }}
            QPushButton:hover {{ color:{Styles.BLUE_SECONDARY}; }}
        """)
        row.addWidget(name_btn)

    def _menu(self):
        m = QMenu(self)
        m.setStyleSheet(f"""
            QMenu {{background:#0f1e36; border:1px solid rgba(255,255,255,0.2);
                    border-radius:10px; padding:10px; }}
            QMenu::item {{padding:8px 14px; border-radius:8px; color:{Styles.TEXT_PRIMARY};}}
            QMenu::item:selected {{background:rgba(59,130,246,0.25); }}
        """)

        head = QAction(f"👤 {self.username}", self)
        head.setEnabled(False)
        m.addAction(head)
        m.addSeparator()

        act_edit = QAction("✏️ Modifier le profil", self)
        act_edit.triggered.connect(self.edit_profile_clicked.emit)
        m.addAction(act_edit)

        act_stats = QAction("Statistiques", self)
        act_stats.triggered.connect(self.show_statistics.emit)
        m.addAction(act_stats)

        act_devices = QAction("Appareils & sessions", self)
        act_devices.triggered.connect(self.show_devices_clicked.emit)
        m.addAction(act_devices)

        act_lock = QAction("Verrouiller", self)
        act_lock.triggered.connect(self.lock_now_clicked.emit)
        m.addAction(act_lock)

        m.addSeparator()

        act_logout = QAction("🚪 Se déconnecter", self)
        act_logout.triggered.connect(self.logout_clicked.emit)
        m.addAction(act_logout)

        m.exec_(self.mapToGlobal(self.rect().bottomRight()))


# ----------------------------- Main Window -----------------------------
class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = APIClient("http://127.0.0.1:5000")
        self.auth = AuthManager()
        # State
        self.current_user = None
        self._all_passwords = []
        self._locked_user = None
        self._lock_timeout_ms = 3 * 60 * 1000
        self._lock_timer = QTimer(self)
        self._lock_timer.setSingleShot(True)
        self._lock_timer.timeout.connect(self._lock_due_to_inactivity)

        # UI
        self._build_ui()
        self._wire_basic_signals()
        self._install_inactivity_monitor()
        self._auth_flow()

    # ---------------- UI / Theme ----------------
    def _build_ui(self):
        self.setWindowTitle("Password Guardian")
        self.setMinimumSize(1280, 780)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                    stop:0 #0a1628, stop:1 #1a2942);
            }
            QDialog, QMessageBox {
                background-color: #0E1B32;
                color: #E6EFFB;
                border: 1px solid rgba(255,255,255,0.08);
            }
            QMessageBox QPushButton {
                background-color: #2563EB;
                color: white; border-radius:8px; padding:6px 14px;
            }
            QMessageBox QPushButton:hover { background-color: #1D4ED8; }
            QScrollArea { background: transparent; }
            QScrollArea::viewport { background: transparent; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.04);
                width: 8px;
                margin: 6px 0 6px 0;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(59,130,246,0.6);
                min-height: 22px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(59,130,246,0.85);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(20)

        # Header
        head = QHBoxLayout()
        icon = QLabel("🔑")
        icon.setStyleSheet("font-size:32px;")
        title = QLabel("Password Guardian")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY};")
        self.user_box = QHBoxLayout()
        uw = QWidget()
        uw.setLayout(self.user_box)
        head.addWidget(icon)
        head.addWidget(title)
        head.addStretch()
        actions_wrap = QWidget()
        actions = QHBoxLayout(actions_wrap)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        def header_btn(text: str, primary: bool = False) -> QPushButton:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                Styles.get_button_style(primary)
                if primary
                else """
                    QPushButton {
                        background: rgba(255,255,255,0.06);
                        color: #E6EFFB;
                        border: 1px solid rgba(255,255,255,0.08);
                        border-radius: 10px;
                        padding: 4px 10px;
                        font-size: 11px;
                    }
                    QPushButton:hover { background: rgba(255,255,255,0.12); }
                """
            )
            return btn

        self.score_badge = header_btn("Score: --%", False)
        self.score_badge.setEnabled(False)
        actions.addWidget(self.score_badge)

        btn_stats = header_btn("Statistiques")
        btn_stats.clicked.connect(self._show_statistics_page)
        actions.addWidget(btn_stats)

        btn_pw = header_btn("Mots de passe")
        btn_pw.clicked.connect(self._show_passwords_page)
        actions.addWidget(btn_pw)

        btn_journal = header_btn("Journal")
        btn_journal.clicked.connect(self._show_journal_placeholder)
        actions.addWidget(btn_journal)

        btn_profile = header_btn("Profile")
        btn_profile.clicked.connect(self._show_edit_profile_modal)
        actions.addWidget(btn_profile)

        btn_export = header_btn("Export")
        btn_export.setStyleSheet(btn_export.styleSheet() + "border-radius: 14px;")
        btn_export.clicked.connect(self._export_encrypted_vault)
        actions.addWidget(btn_export)

        btn_import = header_btn("Import")
        btn_import.setStyleSheet(btn_import.styleSheet() + "border-radius: 14px;")
        btn_import.clicked.connect(self._import_encrypted_vault)
        actions.addWidget(btn_import)

        self.btn_lock = header_btn("Verrouiller")
        self._init_lock_menu()
        actions.addWidget(self.btn_lock)

        btn_logout = header_btn("Déconnexion", True)
        btn_logout.setStyleSheet("""
            QPushButton {
                background: rgba(239, 68, 68, 0.20);
                color: #fee2e2;
                border: 1px solid rgba(239, 68, 68, 0.45);
                border-radius: 10px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QPushButton:hover { background: rgba(239, 68, 68, 0.35); }
        """)
        btn_logout.clicked.connect(self.on_logout)
        actions.addWidget(btn_logout)

        head.addWidget(actions_wrap)
        head.addWidget(uw)
        root.addLayout(head)

        # Body (Sidebar + List)
        body = QHBoxLayout()
        self.sidebar = Sidebar()
        body.addWidget(self.sidebar)

        frame = QFrame()
        frame.setStyleSheet("background:transparent;")
        v = QVBoxLayout(frame)
        v.setContentsMargins(0, 0, 0, 0)

        self.content_stack = QStackedLayout()
        self.password_list = PasswordList()
        self.stats_page = QWidget()
        self.stats_layout = QVBoxLayout(self.stats_page)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(0)
        self.content_stack.addWidget(self.password_list)
        self.content_stack.addWidget(self.stats_page)
        v.addLayout(self.content_stack)
        body.addWidget(frame, 1)
        root.addLayout(body)

    def _wire_basic_signals(self):
        """Connect sidebar, list and card signals AES-256 guard every optional signal."""
        # Sidebar
        if hasattr(self.sidebar, "category_changed"):
            self.sidebar.category_changed.connect(self.on_category_changed)
        if hasattr(self.sidebar, "add_password_clicked"):
            self.sidebar.add_password_clicked.connect(self._show_add_password_modal)
        if hasattr(self.sidebar, "stats_clicked"):
            self.sidebar.stats_clicked.connect(self._show_statistics_page)

        if hasattr(self.sidebar, "stats_clicked"):
            self.sidebar.stats_clicked.connect(self._show_statistics_page)

        # PasswordList signals
        if hasattr(self.password_list, "copy_password"):
            self.password_list.copy_password.connect(self.on_copy_password)
        if hasattr(self.password_list, "view_password"):
            self.password_list.view_password.connect(self.on_view_password)
        if hasattr(self.password_list, "edit_password"):
            self.password_list.edit_password.connect(self.on_edit_password)
        if hasattr(self.password_list, "delete_password"):
            self.password_list.delete_password.connect(self.on_delete_password)
        if hasattr(self.password_list, "favorite_password"):
            self.password_list.favorite_password.connect(self.on_favorite_password)
        if hasattr(self.password_list, "restore_password"):
            self.password_list.restore_password.connect(self.on_restore_password)
        
        # Auto-fill signal (NEW)
        if hasattr(self.password_list, "auto_login_clicked"):
            self.password_list.auto_login_clicked.connect(self.on_auto_login_clicked)

        # Optional 2FA request signals (cards may emit before view/copy)
        if hasattr(self.password_list, "request_2fa_for_view"):
            self.password_list.request_2fa_for_view.connect(self._handle_2fa_view)
        if hasattr(self.password_list, "request_2fa_for_copy"):
            self.password_list.request_2fa_for_copy.connect(self._handle_2fa_copy)

    # ---------------- Inactivity / Lock ----------------
    def _install_inactivity_monitor(self):
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)
        self._reset_inactivity_timer()

    def eventFilter(self, obj, event):
        if event.type() in (
            QEvent.MouseMove,
            QEvent.MouseButtonPress,
            QEvent.KeyPress,
            QEvent.Wheel,
            QEvent.TouchBegin,
        ):
            self._reset_inactivity_timer()
        return super().eventFilter(obj, event)

    def _reset_inactivity_timer(self):
        if self.current_user:
            self._lock_timer.start(self._lock_timeout_ms)

    def _lock_due_to_inactivity(self):
        if self.current_user:
            self._lock_now(show_message=True)

    def _lock_now(self, show_message: bool = False):
        if not self.current_user:
            return
        self._lock_timer.stop()
        if show_message:
            QMessageBox.information(self, "Verrouillage", "Coffre verrouillé après inactivité.")
        self._locked_user = self.current_user
        self.current_user = None
        self._all_passwords = []
        self.password_list.load_passwords([])
        self._show_passwords_page()
        self._show_lock_dialog()

    def _apply_lock_timeout(self, minutes: int):
        self._lock_timeout_ms = int(minutes * 60 * 1000)
        self._reset_inactivity_timer()

    def _init_lock_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#0f1e36; border:1px solid rgba(255,255,255,0.2);
                    border-radius:10px; padding:8px; }
            QMenu::item { padding:6px 12px; border-radius:6px; color:#E6EFFB; }
            QMenu::item:selected { background:rgba(59,130,246,0.25); }
        """)
        act_now = QAction("Lock now", self)
        act_now.triggered.connect(lambda: self._lock_now(show_message=False))
        menu.addAction(act_now)
        menu.addSeparator()
        for m in (2, 3, 5):
            act = QAction(f"Auto-lock {m} min", self)
            act.triggered.connect(lambda _=False, mm=m: self._apply_lock_timeout(mm))
            menu.addAction(act)
        self.btn_lock.setMenu(menu)

    def _show_lock_dialog(self):
        if not self._locked_user:
            return
        d = QDialog(self)
        d.setWindowTitle("Verrouillé")
        d.setFixedSize(480, 300)
        d.setModal(True)
        d.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                color: {Styles.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 20px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)
        lay = QVBoxLayout(d)
        lay.setContentsMargins(26, 24, 26, 24)
        lay.setSpacing(16)

        title = QLabel("🔒 Verrouillé")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        lay.addWidget(title)
        subtitle = QLabel("Saisissez votre mot de passe pour déverrouiller")
        subtitle.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)

        pwd = QLineEdit()
        pwd.setEchoMode(QLineEdit.Password)
        pwd.setMinimumHeight(46)
        pwd.setStyleSheet(Styles.get_input_style() + "border-radius:14px;")
        lay.addWidget(pwd)

        row = QHBoxLayout()
        unlock = QPushButton("Déverrouiller")
        unlock.setMinimumHeight(44)
        unlock.setStyleSheet(
            Styles.get_button_style(True) + "border-radius: 18px; padding: 10px 16px;"
        )
        logout = QPushButton("Déconnexion")
        logout.setMinimumHeight(44)
        logout.setStyleSheet(
            Styles.get_button_style(False) + "border-radius: 18px; padding: 10px 16px;"
        )
        row.addWidget(unlock)
        row.addWidget(logout)
        lay.addLayout(row)

        def _unlock():
            ok = False
            try:
                u = self.auth._user_by_email(self._locked_user.get("email"))
                if u:
                    ok = verify_password(u["password_hash"], u["salt"], pwd.text())
            except Exception:
                ok = False
            if ok:
                self.current_user = self._locked_user
                self._locked_user = None
                d.accept()
                self.load_passwords()
                self._reset_inactivity_timer()
            else:
                QMessageBox.warning(d, "Erreur", "Mot de passe incorrect.")

        def _logout():
            self._locked_user = None
            d.reject()
            self.on_logout()

        unlock.clicked.connect(_unlock)
        logout.clicked.connect(_logout)
        d.exec_()

    # ---------------- Auth flow ----------------
    def _auth_flow(self):
        self.hide()
        while not self.current_user:
            dlg = LoginModal(self)
            dlg.login_success.connect(self._on_login_attempt)
            dlg.switch_to_register.connect(self._switch_to_register)
            res = dlg.exec_()
            if res != QDialog.Accepted and not self.current_user:
                QApplication.quit()
                return
        self.show()
        self.raise_()
        self.activateWindow()

    def _switch_to_register(self):
        dlg = RegisterModal(self)
        dlg.register_success.connect(self._on_register_attempt)
        dlg.switch_to_login.connect(self._auth_flow)
        dlg.exec_()

    def _on_login_attempt(self, email: str, password: str):
        result = self.auth.authenticate(email, password)
        if result.get("error"):
            self._show_error_dialog("Erreur de connexion", result["error"])
            return
        if not result.get("2fa_sent", False):
            self._show_error_dialog("Erreur", "Impossible d'envoyer le code 2FA")
            return
        user = result.get("user")
        self._show_2fa_login(user)

    def _show_2fa_login(self, user: dict):
        dlg = TwoFactorModal(user["email"], "<code envoyé>", self)

        def verify():
            code = dlg.code_input.text().strip()
            if not code or len(code) != 6:
                self._show_error_dialog("Code invalide", "Code 6 chiffres requis")
                return
            ok = False
            if hasattr(self.auth, "verify_2fa_email"):
                ok = self.auth.verify_2fa_email(user["email"], code)
            elif hasattr(self.auth, "verify_2fa"):
                ok = self.auth.verify_2fa(user["email"], code)
            if ok:
                dlg.accept()
                self._finalize_login(user)
            else:
                self._show_error_dialog("Erreur", "Code invalide ou expiré"
)

        try:
            dlg.code_verified.disconnect()
        except Exception:
            pass
        dlg.code_verified.connect(verify)

        if dlg.exec_() != QDialog.Accepted:
            self._auth_flow()

    def _on_register_attempt(self, name, email, password):
        """Handle registration with email verification"""
        ok, msg, extra = self.auth.register_user(name, email, password)
        
        if not ok:
            self._show_error_dialog("Erreur d'inscription", msg)
            return
        
        # Show success message
        QMessageBox.information(
            self, 
            "Inscription réussie", 
            f"✅ {msg}\n\n"
            "Un code de vérification a été envoyé à votre email.\n"
            "Veuillez vérifier votre boîte mail (et les spams)."
        )
        
        # Get user_id from extra data
        user_id = extra.get('user_id')
        if not user_id:
            self._show_error_dialog("Erreur", "Impossible de récupérer l'ID utilisateur")
            self._auth_flow()
            return
        
        # Show email verification dialog
        self._show_email_verification(email, user_id)

    def _show_email_verification(self, email: str, user_id: int):
        """Show email verification dialog with resend option"""
        dlg = QDialog(self)
        dlg.setWindowTitle("✅ Vérification de l'email")
        dlg.setFixedSize(480, 380)
        dlg.setModal(True)
        dlg.setAttribute(Qt.WA_StyledBackground, True)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)
        
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)
        
        # Icon
        icon = QLabel("✅")
        icon.setStyleSheet("font-size:56px;")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        
        # Title
        title = QLabel("Vérifiez votre email"
)
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY};")
        layout.addWidget(title)
        
        # Info
        info = QLabel(
            f"Un code de vérification a été envoyé à:\n"
            f"{email}\n\n"
            f"Vérifiez votre boîte mail (et les spams)"
        )
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:13px;")
        layout.addWidget(info)
        
        # Code input
        code_input = QLineEdit()
        code_input.setPlaceholderText("Code à 6 chiffres")
        code_input.setMaxLength(6)
        code_input.setAlignment(Qt.AlignCenter)
        code_input.setFont(QFont("Courier New", 20, QFont.Bold))
        code_input.setMinimumHeight(56)
        code_input.setStyleSheet(f"""
            QLineEdit {{
                {Styles.get_input_style()}
                padding: 12px;
                font-size: 24px;
                letter-spacing: 10px;
            }}
        """)
        layout.addWidget(code_input)
        
        # Status label
        status_label = QLabel("")
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 12px;")
        layout.addWidget(status_label)
        
        # Verify button
        verify_btn = QPushButton("✔ Vérifier")
        verify_btn.setMinimumHeight(48)
        verify_btn.setCursor(Qt.PointingHandCursor)
        verify_btn.setStyleSheet(Styles.get_button_style(True))
        layout.addWidget(verify_btn)
        
        # Resend button
        resend_btn = QPushButton("❌ Renvoyer le code")
        resend_btn.setMinimumHeight(44)
        resend_btn.setCursor(Qt.PointingHandCursor)
        resend_btn.setStyleSheet(Styles.get_button_style(False))
        layout.addWidget(resend_btn)
        
        # Countdown timer state
        countdown = {"seconds": 60, "active": False}
        timer = QTimer(dlg)
        
        def update_countdown():
            if countdown["seconds"] > 0:
                countdown["seconds"] -= 1
                status_label.setText(f"❌ Renvoyer disponible dans {countdown['seconds']}s")
                resend_btn.setEnabled(False)
            else:
                timer.stop()
                countdown["active"] = False
                status_label.setText("")
                resend_btn.setEnabled(True)
        
        def start_countdown():
            countdown["seconds"] = 60
            countdown["active"] = True
            resend_btn.setEnabled(False)
            timer.timeout.connect(update_countdown)
            timer.start(1000)
        
        def verify_code():
            code = code_input.text().strip()
            
            if not code or len(code) != 6:
                QMessageBox.warning(dlg, "Code invalide", "Veuillez saisir un code à 6 chiffres")
                return
            
            # Verify the registration code
            ok = self.auth.verify_registration_code(email, code)
            
            if ok:
                dlg.accept()
                QMessageBox.information(
                    self, 
                    "Email vérifié", 
                    "✅ Votre email a été vérifié avec succès!\n\n"
                    "Vous pouvez maintenant vous connecter."
                )
                user = {
                    "id": user_id,
                    "email": email,
                    "username": email.split('@')[0]
                }
                self._finalize_login(user)
            else:
                QMessageBox.warning(
                    dlg,
                    "Code invalide", 
                    "❌ Le code saisi est invalide ou a expiré.\n\n"
                    "Cliquez sur 'Renvoyer le code' pour recevoir un nouveau code."
                )
        
        def resend_code():
            ok = self.auth.resend_verification_code(email)
            
            if ok:
                QMessageBox.information(
                    dlg,
                    "Code renvoyé",
                    f"✅ Un nouveau code a été envoyé à:\n{email}\n\n"
                    "Vérifiez votre boîte mail (et les spams)"
                )
                code_input.clear()
                start_countdown()
            else:
                QMessageBox.warning(
                    dlg,
                    "Erreur",
                    "❌ Impossible de renvoyer le code.\n\n"
                    "L'email est peut-être déjà vérifié."
                )
        
        verify_btn.clicked.connect(verify_code)
        resend_btn.clicked.connect(resend_code)
        code_input.returnPressed.connect(verify_code)
        
        # Start countdown
        start_countdown()
        
        # Focus on input
        code_input.setFocus()
        
        result = dlg.exec_()
        
        if result != QDialog.Accepted:
            QMessageBox.warning(
                self,
                "Vérification annulée",
                "❌ Votre email n'a pas été vérifié.\n\n"
                "Vous devrez vérifier votre email pour vous connecter."
            )
            self._auth_flow()

    def _finalize_login(self, user: dict):
        name = (user.get("username") or user.get("email", "").split("@")[0]).capitalize()
        initials = (name[:2] or "US").upper()

        # Clear user box
        for i in reversed(range(self.user_box.count())):
            w = self.user_box.itemAt(i).widget()
            if w:
                w.setParent(None)

        self.current_user = {
            "id": user["id"],
            "username": name,
            "email": user["email"],
            "name": name,
            "initials": initials,
        }

        prof = UserProfileWidget(name, initials, self)
        prof.logout_clicked.connect(self.on_logout)
        prof.show_statistics.connect(self._show_statistics_page)
        prof.show_devices_clicked.connect(self._show_devices_placeholder)
        prof.lock_now_clicked.connect(lambda: self._lock_now(show_message=False))
        prof.edit_profile_clicked.connect(self._show_edit_profile_modal)
        self.user_box.addWidget(prof)

        QTimer.singleShot(0, self.load_passwords)
        QMessageBox.information(self, "Bienvenue", f"✅ Bienvenue {name}!")

    def _show_error_dialog(self, title: str, message: str):
        """Show error message with proper word wrap and sizing"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Styles.PRIMARY_BG};
                color: {Styles.TEXT_PRIMARY};
            }}
            QMessageBox QLabel {{
                color: {Styles.TEXT_PRIMARY};
                min-width: 300px;
                max-width: 500px;
            }}
            QPushButton {{
                {Styles.get_button_style(True)}
                min-width: 80px;
                min-height: 32px;
            }}
        """)
        msg_box.exec_()

    # ---------------- Data loading / filtering ----------------
    def load_passwords(self):
        if not self.current_user:
            return
        
        ok, msg, data = self.api_client.get_passwords(self.current_user["id"])
        self._all_passwords = data if ok else []
        # Normalize trash status from backend (uses trashed_at)
        for p in self._all_passwords:
            if p.get("trashed_at"):
                p["category"] = "trash"
        
        visible = [p for p in self._all_passwords if p.get("category") != "trash"]
        self.password_list.load_passwords(visible)

        counts = {k: 0 for k in ["all", "work", "personal", "finance", "game", "study", "favorites", "trash"]}
        counts["all"] = len(visible)
        counts["trash"] = len([p for p in self._all_passwords if p.get("category") == "trash"])
        for p in visible:
            c = p.get("category")
            if c in counts:
                counts[c] += 1
            if p.get("favorite"):
                counts["favorites"] += 1

        counts["strong"] = sum(1 for p in visible if p.get("strength") == "strong")
        counts["medium"] = sum(1 for p in visible if p.get("strength") == "medium")
        counts["weak"] = sum(1 for p in visible if p.get("strength") == "weak")

        # Dynamic categories from data
        cat_set = []
        for p in self._all_passwords:
            c = (p.get("category") or "").strip()
            if c and c not in ("trash",):
                if c not in cat_set:
                    cat_set.append(c)
        if hasattr(self.sidebar, "set_categories"):
            self.sidebar.set_categories(cat_set)

        self.sidebar.update_counts(counts)
        self._update_score_badge(visible)
        if self.content_stack.currentWidget() == self.stats_page:
            self._render_stats_page()

    def _update_score_badge(self, visible):
        total = len(visible)
        strong = sum(1 for p in visible if p.get("strength") == "strong")
        medium = sum(1 for p in visible if p.get("strength") == "medium")
        score = int((strong * 2 + medium) / max(1, total * 2) * 100)
        if hasattr(self, "score_badge"):
            self.score_badge.setText(f"Score: {score}%")

    def on_category_changed(self, cat: str):
        base = self._all_passwords
        if cat == "all":
            f = [p for p in base if p.get("category") != "trash"]
        elif cat == "trash":
            f = [p for p in base if p.get("category") == "trash"]
        elif cat == "favorites":
            f = [p for p in base if p.get("favorite") and p.get("category") != "trash"]
        else:
            f = [p for p in base if p.get("category") == cat]
        self.password_list.load_passwords(f)

    # ---------------- 2FA helper for sensitive actions ----------------
    def _confirm_sensitive(self, purpose: str) -> bool:
        """Send a 2FA email and verify. If unavailable, ask to proceed without it."""
        if not self.current_user:
            return False
        email = self.current_user["email"]

        sent = False
        if hasattr(self.auth, "send_2fa_email"):
            sent = self.auth.send_2fa_email(email, purpose)
        if not sent and hasattr(self.auth, "send_2fa_code"):
            sent = self.auth.send_2fa_code(to_email=email, user_id=self.current_user["id"], purpose=purpose)

        if not sent:
            resp = QMessageBox.question(
                self,
                "2FA indisponible",
                "Impossible d'envoyer le code 2FA (email non configuré?).\n\nVoulez-vous continuer sans 2FA ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return resp == QMessageBox.Yes

        dlg = Quick2FADialog(email, self)
        verified = {"ok": False}

        def _verify():
            code = dlg.code_input.text().strip()
            if not code or len(code) != 6:
                self._show_error_dialog("Code invalide", "Code 6 chiffres requis")
                return
            ok = False
            if hasattr(self.auth, "verify_2fa_email"):
                ok = self.auth.verify_2fa_email(email, code)
            elif hasattr(self.auth, "verify_2fa"):
                ok = self.auth.verify_2fa(email, code)
            if ok:
                verified["ok"] = True
                dlg.accept()
            else:
                self._show_error_dialog("Erreur", "Code invalide ou expir?")

        try:
            dlg.code_verified.disconnect()
        except Exception:
            pass
        dlg.code_verified.connect(_verify)
        dlg.exec_()
        return verified["ok"]

    # ---------------- Export / Import ----------------
    def _prompt_passphrase(self, title: str, confirm: bool = False) -> str | None:
        d = QDialog(self)
        d.setWindowTitle(title)
        d.setFixedSize(420, 220 if confirm else 170)
        d.setModal(True)
        d.setStyleSheet(f"""
            QDialog {{
                background: {Styles.PRIMARY_BG};
                color: {Styles.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)
        lay = QVBoxLayout(d)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Mot de passe du fichier:"))
        p1 = QLineEdit()
        p1.setEchoMode(QLineEdit.Password)
        p1.setStyleSheet(Styles.get_input_style())
        lay.addWidget(p1)

        p2 = None
        if confirm:
            lay.addWidget(QLabel("Confirmer le mot de passe:"))
            p2 = QLineEdit()
            p2.setEchoMode(QLineEdit.Password)
            p2.setStyleSheet(Styles.get_input_style())
            lay.addWidget(p2)

        row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.get_button_style(True) + "border-radius: 14px;")
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(Styles.get_button_style(False) + "border-radius: 14px;")
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

        result = {"value": None}

        def _accept():
            if confirm and p2 is not None and p1.text() != p2.text():
                QMessageBox.warning(d, "Erreur", "Les mots de passe ne correspondent pas.")
                return
            if not p1.text():
                QMessageBox.warning(d, "Erreur", "Mot de passe requis.")
                return
            result["value"] = p1.text()
            d.accept()

        ok_btn.clicked.connect(_accept)
        cancel_btn.clicked.connect(d.reject)
        d.exec_()
        return result["value"]

    def _prompt_import_mode(self) -> str | None:
        d = QDialog(self)
        d.setWindowTitle("Import - Duplicates")
        d.setFixedSize(420, 200)
        d.setModal(True)
        d.setStyleSheet(f"""
            QDialog {{
                background: {Styles.PRIMARY_BG};
                color: {Styles.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)
        lay = QVBoxLayout(d)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        lay.addWidget(QLabel("Conflits (mêmes site + identifiant):"))
        mode = QComboBox()
        mode.addItems(["Merge", "Skip", "Overwrite"])
        mode.setStyleSheet(Styles.get_input_style())
        lay.addWidget(mode)

        row = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(Styles.get_button_style(True) + "border-radius: 14px;")
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setStyleSheet(Styles.get_button_style(False) + "border-radius: 14px;")
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)

        result = {"value": None}

        def _accept():
            result["value"] = mode.currentText().lower()
            d.accept()

        ok_btn.clicked.connect(_accept)
        cancel_btn.clicked.connect(d.reject)
        d.exec_()
        return result["value"]

    def _export_encrypted_vault(self):
        if not self.current_user:
            return
        ok, msg, vault = self.api_client.export_vault(self.current_user["id"])
        if not ok:
            self._show_error_dialog("Erreur", msg)
            return

        passphrase = self._prompt_passphrase("Export chiffré (.pgvault)", confirm=True)
        if not passphrase:
            return

        enc = encrypt_vault_payload(vault, passphrase)
        filename, _ = QFileDialog.getSaveFileName(
            self, "Exporter le coffre", "vault.pgvault", "Password Guardian Vault (*.pgvault)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".pgvault"):
            filename += ".pgvault"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(enc, f, indent=2)
        QMessageBox.information(self, "Export", " Export chiffré terminé.")

    def _import_encrypted_vault(self):
        if not self.current_user:
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Importer un coffre", "", "Password Guardian Vault (*.pgvault)"
        )
        if not filename:
            return

        passphrase = self._prompt_passphrase("Importer un coffre chiffré", confirm=False)
        if not passphrase:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                blob = json.load(f)
            vault = decrypt_vault_payload(blob, passphrase)
        except Exception as e:
            self._show_error_dialog("Erreur", f"Impossible de déchiffrer: {e}")
            return

        items = vault.get("passwords") or []
        if not isinstance(items, list):
            self._show_error_dialog("Erreur", "Format de coffre invalide.")
            return

        mode = self._prompt_import_mode()
        if not mode:
            return

        existing = {}
        for p in self._all_passwords:
            key = (str(p.get("site_name", "")).strip().lower(), str(p.get("username", "")).strip().lower())
            if key[0] or key[1]:
                existing[key] = p

        imported = 0
        updated = 0
        skipped = 0

        for it in items:
            if not it.get("site_name") or not it.get("username") or not it.get("encrypted_password"):
                continue
            key = (str(it.get("site_name", "")).strip().lower(), str(it.get("username", "")).strip().lower())
            match = existing.get(key)

            if match:
                if mode == "skip":
                    skipped += 1
                    continue
                if mode == "overwrite":
                    ok, msg = self.api_client.update_password(
                        match["id"],
                        {
                            "site_name": it.get("site_name"),
                            "site_url": it.get("site_url") or "",
                            "site_icon": it.get("site_icon") or "ðŸ”’",
                            "username": it.get("username"),
                            "encrypted_password": it.get("encrypted_password"),
                            "category": it.get("category") or "personal",
                            "strength": it.get("strength") or "medium",
                            "favorite": bool(it.get("favorite") or False),
                        },
                    )
                    if ok:
                        updated += 1
                    else:
                        skipped += 1
                    continue

                # merge
                updates = {}
                for field in ["site_url", "site_icon", "category", "strength"]:
                    if not match.get(field) and it.get(field):
                        updates[field] = it.get(field)
                if not match.get("favorite") and it.get("favorite"):
                    updates["favorite"] = True
                if updates:
                    ok, msg = self.api_client.update_password(match["id"], updates)
                    if ok:
                        updated += 1
                    else:
                        skipped += 1
                else:
                    skipped += 1
                continue

            ok, msg, _ = self.api_client.add_password(
                user_id=self.current_user["id"],
                site_name=str(it.get("site_name")),
                username=str(it.get("username")),
                encrypted_password=str(it.get("encrypted_password")),
                category=str(it.get("category") or "personal"),
                site_url=str(it.get("site_url") or ""),
                site_icon=str(it.get("site_icon") or "ðŸ”’"),
                strength=str(it.get("strength") or "medium"),
            )
            if ok:
                imported += 1
            else:
                skipped += 1

        self.load_passwords()
        QMessageBox.information(
            self,
            "Import terminÃ©",
            f"AjoutÃ©s: {imported}\nMises Ã  jour: {updated}\nIgnorÃ©s: {skipped}",
        )

    def _show_devices_placeholder(self):
        if not self.current_user:
            QMessageBox.warning(self, "Appareils & sessions", "Utilisateur non connecté.")
            return
        ok_s, msg_s, sessions = self.api_client.get_sessions(self.current_user["id"])
        ok_d, msg_d, devices = self.api_client.get_devices(self.current_user["id"])
        if not ok_s and not ok_d:
            QMessageBox.warning(self, "Appareils & sessions", f"Impossible de charger: {msg_s or msg_d}")
            return
        try:
            from src.gui.components.modals import DeviceSessionsModal
        except Exception:
            QMessageBox.warning(self, "Appareils & sessions", "Interface indisponible.")
            return

        items = []
        sessions = sessions or []
        devices = devices or []

        # Active sessions
        for s in sessions:
            items.append({
                "device_name": s.get("device_info") or "Session",
                "ip_address": "-",
                "id": s.get("id"),
                "status": "Actif",
                "last_used": s.get("created_at"),
            })

        # Known devices (history) not currently active
        active_names = {s.get("device_info") for s in sessions if s.get("device_info")}
        for d in devices:
            name = d.get("device_name") or "Appareil"
            if name not in active_names:
                items.append({
                    "device_name": name,
                    "ip_address": d.get("ip_address") or "-",
                    "id": None,
                    "status": "Historique",
                    "last_used": d.get("last_used"),
                })

        def _revoke_session(session_id: int):
            ok2, _msg = self.api_client.revoke_session(session_id)
            return ok2

        def _revoke_device(device_name: str):
            ok2, _msg = self.api_client.revoke_device_sessions(self.current_user["id"], device_name)
            return ok2

        if not items:
            items = [{
                "device_name": "Appareil actuel",
                "ip_address": "-",
                "id": None,
                "status": "Actif",
            }]
        DeviceSessionsModal(items, _revoke_session, _revoke_device, self).exec_()

    def _show_journal_placeholder(self):
        if not self.current_user:
            QMessageBox.warning(self, "Journal", "Utilisateur non connecté.")
            return
        try:
            from src.gui.components.modals import AuditLogModal
        except Exception:
            QMessageBox.information(self, "Journal", "Journal indisponible pour le moment.")
            return
        AuditLogModal(self.current_user["id"], self.auth, self).exec_()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)

    def _show_statistics_page(self):
        self._render_stats_page()
        self.content_stack.setCurrentWidget(self.stats_page)

    def _show_passwords_page(self):
        self.content_stack.setCurrentWidget(self.password_list)

    def _render_stats_page(self):
        self._clear_layout(self.stats_layout)

        wrap = QWidget()
        wrap.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)

        top = QHBoxLayout()
        title = QLabel("Mes statistiques")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY};")
        top.addWidget(title)
        top.addStretch()
        back_btn = QPushButton("← Retour")
        back_btn.setStyleSheet(
            Styles.get_button_style(False)
            + "padding: 8px 16px; border-radius: 14px; font-weight: 600;"
        )
        back_btn.setMinimumHeight(36)
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(self._show_passwords_page)
        top.addWidget(back_btn)
        lay.addLayout(top)

        passwords = [p for p in self._all_passwords if p.get("category") != "trash"]
        total = len(passwords)
        strong = sum(1 for p in passwords if p.get("strength") == "strong")
        medium = sum(1 for p in passwords if p.get("strength") == "medium")
        weak = sum(1 for p in passwords if p.get("strength") == "weak")
        favorites = sum(1 for p in passwords if p.get("favorite"))

        pw_map = {}
        for p in passwords:
            tok = p.get("encrypted_password") or ""
            pw_map[tok] = pw_map.get(tok, 0) + 1
        reused = sum(1 for p in passwords if pw_map.get(p.get("encrypted_password") or "", 0) > 1)

        old = 0
        cutoff = datetime.utcnow() - timedelta(days=180)
        for p in passwords:
            ts = p.get("last_updated") or p.get("created_at") or ""
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                if dt < cutoff:
                    old += 1
            except Exception:
                pass

        pwned = 0
        score = int((strong * 2 + medium) / max(1, total * 2) * 100)
        score_color = Styles.STRONG_COLOR if score >= 80 else (
            Styles.MEDIUM_COLOR if score >= 50 else Styles.WEAK_COLOR
        )

        cards = QGridLayout()
        cards.setHorizontalSpacing(16)
        cards.setVerticalSpacing(16)

        def card(title_text, value_text, color):
            w = QFrame()
            w.setStyleSheet("""
                QFrame {
                    background: rgba(255,255,255,0.04);
                    border: 1px solid rgba(255,255,255,0.06);
                    border-radius: 14px;
                }
            """)
            v = QVBoxLayout(w)
            v.setContentsMargins(16, 12, 16, 12)
            v.setSpacing(6)
            t = QLabel(title_text)
            t.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
            val = QLabel(str(value_text))
            val.setStyleSheet(f"color:{color}; font-size:26px; font-weight:800;")
            v.addWidget(t)
            v.addWidget(val)
            return w

        cards.addWidget(card("Total", total, Styles.BLUE_PRIMARY), 0, 0)
        cards.addWidget(card("Forts", strong, Styles.STRONG_COLOR), 0, 1)
        cards.addWidget(card("Moyens", medium, Styles.MEDIUM_COLOR), 0, 2)
        cards.addWidget(card("Faibles", weak, Styles.WEAK_COLOR), 0, 3)
        cards.addWidget(card("Favoris", favorites, Styles.BLUE_SECONDARY), 1, 0)
        cards.addWidget(card("Reused", reused, Styles.MEDIUM_COLOR), 1, 1)
        cards.addWidget(card("Old (180j+)", old, Styles.WEAK_COLOR), 1, 2)
        cards.addWidget(card("Pwned", pwned, Styles.WEAK_COLOR), 1, 3)
        lay.addLayout(cards)

        score_wrap = QFrame()
        score_wrap.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
            }
        """)
        sw = QHBoxLayout(score_wrap)
        sw.setContentsMargins(14, 10, 14, 10)
        score_label = QLabel("Score de securite")
        score_label.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:14px;")
        sw.addWidget(score_label, alignment=Qt.AlignLeft)
        score_value = QLabel(f"{score}%")
        score_value.setStyleSheet(f"color:{score_color}; font-size:26px; font-weight:800;")
        sw.addWidget(score_value, alignment=Qt.AlignRight)
        lay.addWidget(score_wrap)

        graphs = QGridLayout()
        graphs.setHorizontalSpacing(18)
        graphs.setVerticalSpacing(18)

        def bar_row(label, value, color, total_width=260):
            roww = QHBoxLayout()
            roww.setSpacing(8)
            lbl = QLabel(f"{label} ({value})")
            lbl.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
            bar = QFrame()
            bar.setFixedHeight(10)
            bar.setStyleSheet(f"background:{color}; border-radius:5px;")
            width = total_width if total == 0 else int(total_width * (value / max(1, total)))
            bar.setFixedWidth(width)
            roww.addWidget(lbl)
            roww.addWidget(bar)
            roww.addStretch(1)
            return roww

        chart = QFrame()
        chart.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
            }
        """)
        cl = QVBoxLayout(chart)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(10)
        chart_title = QLabel("Repartition des forces")
        chart_title.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        cl.addWidget(chart_title)
        cl.addLayout(bar_row("Forts", strong, Styles.STRONG_COLOR))
        cl.addLayout(bar_row("Moyens", medium, Styles.MEDIUM_COLOR))
        cl.addLayout(bar_row("Faibles", weak, Styles.WEAK_COLOR))

        chart2 = QFrame()
        chart2.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 12px;
            }
        """)
        c2 = QVBoxLayout(chart2)
        c2.setContentsMargins(16, 14, 16, 14)
        c2.setSpacing(10)
        t2 = QLabel("Hygiene")
        t2.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        c2.addWidget(t2)
        c2.addLayout(bar_row("Reused", reused, Styles.MEDIUM_COLOR, total_width=220))
        c2.addLayout(bar_row("Old", old, Styles.WEAK_COLOR, total_width=220))
        c2.addLayout(bar_row("Pwned", pwned, Styles.WEAK_COLOR, total_width=220))

        graphs.addWidget(chart, 0, 0)
        graphs.addWidget(chart2, 0, 1)
        lay.addLayout(graphs)
        lay.addStretch(1)

        self.stats_layout.addWidget(wrap)

    def _handle_2fa_view(self, payload: dict):
        if not self._confirm_sensitive("visualisation"):
            return
        self.on_view_password(payload)

    def _handle_2fa_copy(self, token_or_dict):
        if not self._confirm_sensitive("copie"):
            return
        self.on_copy_password(token_or_dict)

    def _decrypt_from_backend(self, password_id: int) -> str:
        """
        Get plain password from backend reveal.
        Backend returns stored value; decrypt locally if needed.
        """
        ok, msg, token = self.api_client.reveal_password(password_id)
        if not ok:
            raise ValueError(msg or "Erreur API")
        if not token:
            raise ValueError("Mot de passe vide")

        # If it's an encrypted token, decrypt locally
        try:
            if isinstance(token, str) and (token.startswith("gAAAA") or token.startswith("gcm1:")):
                return decrypt_any(token)
        except Exception:
            pass

        # Otherwise treat as plain
        return token

    # ---------------- View / Copy with 2FA ----------------
    def on_view_password(self, payload):
        pid = None
        if isinstance(payload, dict):
            pid = payload.get("id")
        elif isinstance(payload, int):
            pid = payload

        if pid is None:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return

        if not self._confirm_sensitive("visualisation"):
            return
        
        try:
            # Backend returns PLAIN password - no need to decrypt
            plain = self._decrypt_from_backend(int(pid))
        except Exception as e:
            self._show_error_dialog("Erreur", str(e))
            return

        p = next((x for x in self._all_passwords if x.get("id") == int(pid)), {}).copy()
        # Set the plain password for display
        p["encrypted_password"] = plain
        p["password"] = plain  # Add this for ViewPasswordModal
        ViewPasswordModal(p, self.api_client, self).exec_()

    def on_copy_password(self, payload):
        pid = None
        if isinstance(payload, dict):
            pid = payload.get("id")
        elif isinstance(payload, int):
            pid = payload

        if pid is None:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return

        if not self._confirm_sensitive("copie"):
            return
        
        try:
            # Backend returns PLAIN password - no need to decrypt
            plain = self._decrypt_from_backend(int(pid))
        except Exception as e:
            self._show_error_dialog("Erreur", str(e))
            return

        QApplication.clipboard().setText(plain)
        QMessageBox.information(self, "Copié", "📋 Mot de passe copié dans le presse-papier!")

    def on_edit_password(self, pid: int):
        p = next((x for x in self._all_passwords if x.get("id") == pid), None)
        if not p:
            return

        p_prefill = p.copy()
        try:
            # Backend returns PLAIN password - no need to decrypt
            pt = self._decrypt_from_backend(pid)
            p_prefill["password"] = pt
            p_prefill["encrypted_password"] = pt
        except Exception as e:
            self._show_error_dialog("Erreur", f"Impossible de récupérer le mot de passe: {str(e)}")
            return

        dlg = EditPasswordModal(p_prefill, self)

        def _upd(_id, new_plain, _lm):
            # Don't encrypt here - backend will encrypt it
            ok, msg = self.api_client.update_password(
                password_id=_id,
                updates={
                    "site_name": p["site_name"],
                    "username": p["username"],
                    "password": new_plain,  # Send plain - backend encrypts
                    "category": p.get("category", "personal"),
                    "favorite": p.get("favorite", False),
                }
            )
            if ok:
                self.load_passwords()
                QMessageBox.information(self, "Succès", "✅ Mot de passe mis à jour.")
            else:
                self._show_error_dialog("Erreur", msg)

        dlg.password_updated.connect(_upd)
        dlg.exec_()

    def _get_plain_password_for_view(self, password_id: int) -> str:
        """
        Get plain password for viewing.
        For OLD encrypted passwords: returns as-is from DB.
        For NEW hashed passwords: Cannot retrieve - returns error message.
        """
        try:
            # Try to get from temporary storage first (recently added passwords)
            import requests
            response = requests.post(
                f"{self.api_client.base_url}/passwords/{password_id}/get-plain-temp",
                timeout=5
            )
            
            if response.ok:
                data = response.json()
                return data.get('password', '')
            
            # If not in temp storage, try to reveal (for old encrypted passwords)
            response = requests.post(
                f"{self.api_client.base_url}/passwords/{password_id}/reveal",
                timeout=5
            )
            
            if response.ok:
                data = response.json()
                
                if data.get('type') == 'encrypted':
                    # Old format - can be retrieved
                    return data.get('password', '')
                elif data.get('type') == 'hashed':
                    # New format - cannot retrieve
                    return None
                
            return None
            
        except Exception as e:
            print(f"âŒ Error getting plain password: {e}")
            return None

    # ---------------- CRUD ----------------
    def _show_add_password_modal(self):
        if not self.current_user or "id" not in self.current_user:
            QMessageBox.warning(self, "Erreur", "Utilisateur non connecté.")
            return
        dlg = AddPasswordModal(self.current_user["id"], self.api_client, self)

        def _add(payload: dict):
            """Handle adding a new password"""
            try:
                # Extract data from payload
                site_name = payload.get("site_name", "")
                site_url = payload.get("site_url", "")
                username = payload.get("username", "")
                plain_password = payload.get("password", "")  #  Now expects 'password' key
                category = payload.get("category", "personal")
                
                # Debug logging
                print(f"\n{'='*60}")
                print(f"ðŸ“ Adding Password")
                print(f"{'='*60}")
                print(f"Site Name: {site_name}")
                print(f"Site URL: {site_url}")
                print(f"Username: {username}")
                print(f"Password Length: {len(plain_password)}")
                print(f"Category: {category}")
                print(f"User ID: {self.current_user['id']}")
                print(f"{'='*60}\n")
                
                # Validate all required fields
                if not site_name:
                    QMessageBox.warning(self, "Erreur", "Le nom du site est requis")
                    return
                
                if not username:
                    QMessageBox.warning(self, "Erreur", "L'identifiant est requis")
                    return
                
                if not plain_password:
                    QMessageBox.warning(self, "Erreur", "Le mot de passe est requis")
                    return
                
                if not self.current_user or 'id' not in self.current_user:
                    QMessageBox.warning(self, "Erreur", "Utilisateur non connecté.")
                    return
                
                #  Send plain password to backend - backend will hash it
                ok, msg, response = self.api_client.add_password(
                    user_id=self.current_user["id"],
                    site_name=site_name,
                    username=username,
                    encrypted_password=plain_password,  # Backend expects this key name
                    category=category,
                    site_url=site_url
                )
                
                if ok:
                    print(f" Password added successfully: {response}")
                    self.load_passwords()
                    QMessageBox.information(
                        self, 
                        "Succès", 
                        f" Mot de passe ajouté avec succès!\n\n"
                        f"Site: {site_name}\n"
                        f"Identifiant: {username}"
                    )
                else:
                    print(f" Failed to add password: {msg}")
                    QMessageBox.warning(
                        self, 
                        "Erreur", 
                        f" Impossible d'ajouter le mot de passe:\n\n{msg}"
                    )
                    
            except Exception as e:
                print(f" Exception in _add: {e}")
                import traceback
                traceback.print_exc()
                QMessageBox.critical(
                    self, 
                    "Erreur", 
                    f" Une erreur s'est produite:\n\n{str(e)}"
                )

        dlg.password_added.connect(_add)
        dlg.exec_()

    def on_edit_password(self, pid: int):
        p = next((x for x in self._all_passwords if x.get("id") == pid), None)
        if not p:
            return

        p_prefill = p.copy()
        try:
            pt = self._decrypt_from_backend(pid)
            p_prefill["password"] = pt
            p_prefill["encrypted_password"] = pt
        except Exception as e:
            self._show_error_dialog("Erreur", f"Impossible de déchiffrer: {str(e)}")
            return

        dlg = EditPasswordModal(p_prefill, self)

        def _upd(_id, new_plain, _lm):
            enc = encrypt_for_storage(new_plain)
            ok, msg = self.api_client.update_password(
                password_id=_id,
                updates={
                    "site_name": p["site_name"],
                    "username": p["username"],
                    "encrypted_password": enc,
                    "category": p.get("category", "personal"),
                    "favorite": p.get("favorite", False),
                }
            )
            if ok:
                self.load_passwords()
                QMessageBox.information(self, "Succès", "✅ Mot de passe mis à jour.")
            else:
                self._show_error_dialog("Erreur", msg)

        dlg.password_updated.connect(_upd)
        dlg.exec_()

    def on_delete_password(self, pid: int):
        """Delete or trash a password - FIXED VERSION"""
        p = next((x for x in self._all_passwords if x.get("id") == pid), None)
        if not p:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return
        
        cat = p.get("category", "personal")

        if cat == "trash":
            # Permanent deletion
            rep = QMessageBox.question(
                self, 
                "Suppression définitive",
                "⚠️ Supprimer définitivement ? Cette action est irréversible.",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if rep != QMessageBox.Yes:
                return
            
            ok, msg = self.api_client.delete_password(pid)
            if ok:
                self.load_passwords()
                QMessageBox.information(self, "Supprimé", "🗑️ Supprimé définitivement.")
            else:
                self._show_error_dialog("Erreur", msg)
        else:
            # Move to trash
            rep = QMessageBox.question(
                self, 
                "Corbeille",
                "Déplacer vers la corbeille ? (Auto-suppression après 48h)",
                QMessageBox.Yes | QMessageBox.No, 
                QMessageBox.No
            )
            if rep != QMessageBox.Yes:
                return
            
            # Move to trash via API endpoint
            ok, msg = self.api_client.trash_password(pid)
            
            if ok:
                self.load_passwords()
                QMessageBox.information(self, "Corbeille", "🗑️ Déplacé vers la corbeille.")
            else:
                self._show_error_dialog("Erreur", msg)

    def on_restore_password(self, pid: int):
        """Restore password from trash - FIXED VERSION"""
        p = next((x for x in self._all_passwords if x.get("id") == pid), None)
        if not p:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return
        
        rep = QMessageBox.question(
            self, 
            "Restaurer", 
            "Restaurer ce mot de passe ?",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.Yes
        )
        if rep != QMessageBox.Yes:
            return
        
        # Restore via API endpoint
        ok, msg = self.api_client.restore_password(pid)
        
        if ok:
            self.load_passwords()
            QMessageBox.information(self, "Restauré", "✅ Restauré avec succès.")
        else:
            self._show_error_dialog("Erreur", msg)

    def on_favorite_password(self, pid: int):
        """Toggle favorite status for a password"""
        try:
            print(f"\n🌟 Toggling favorite for password ID={pid}")
            
            # Find the password in local cache
            p = next((x for x in self._all_passwords if x.get("id") == pid), None)
            if not p:
                print(f"   ❌ Password not found in local cache")
                self._show_error_dialog("Erreur", "Mot de passe introuvable")
                return
            
            current_status = p.get("favorite", False)
            print(f"   Current status: {current_status}")
            
            # Call API to toggle
            ok, msg, new_status = self.api_client.toggle_favorite(pid)
            
            if ok:
                print(f"   ✅ Successfully toggled: {current_status} → {new_status}")
                
                # Update local cache
                p["favorite"] = new_status
                
                # Reload to refresh UI
                self.load_passwords()
                
                # Show confirmation
                status_text = "ajouté aux favoris" if new_status else "retiré des favoris"
                QMessageBox.information(
                    self, 
                    "Favoris", 
                    f"✅ {p.get('site_name', 'Mot de passe')} {status_text}!"
                )
            else:
                print(f"   ❌ Failed to toggle: {msg}")
                self._show_error_dialog("Erreur", f"Impossible de modifier les favoris:\n{msg}")
                
        except Exception as e:
            print(f"   ❌ Exception in on_favorite_password: {e}")
            import traceback
            traceback.print_exc()
            self._show_error_dialog("Erreur", f"Une erreur s'est produite:\n{str(e)}")

    # ---------------- View / Copy with 2FA ----------------
    def on_view_password(self, payload):
        pid = None
        if isinstance(payload, dict):
            pid = payload.get("id")
        elif isinstance(payload, int):
            pid = payload

        if pid is None:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return

        if not self._confirm_sensitive("visualisation"):
            return

        try:
            plain = self._decrypt_from_backend(int(pid))
        except Exception as e:
            self._show_error_dialog("Erreur de déchiffrement", str(e))
            return

        p = next((x for x in self._all_passwords if x.get("id") == int(pid)), {}).copy()
        p["encrypted_password"] = plain
        ViewPasswordModal(p, self.api_client, self).exec_()

    def on_copy_password(self, payload):
        pid = None
        if isinstance(payload, dict):
            pid = payload.get("id")
        elif isinstance(payload, int):
            pid = payload

        if pid is None:
            self._show_error_dialog("Erreur", "Mot de passe introuvable")
            return

        try:
            plain = self._decrypt_from_backend(int(pid))
        except Exception as e:
            self._show_error_dialog("Erreur de déchiffrement", str(e))
            return

        QApplication.clipboard().setText(plain)
        QMessageBox.information(self, "Copié", "Mot de passe copié dans le presse-papier!")
    # ---------------- AUTO-FILL HANDLER ----------------
    def on_auto_login_clicked(self, payload: dict):
        """
        Handle auto-login with METHOD CHOICE
        FIXED: Uses threading to prevent event loop blocking
        """
        # Extract details
        pid = payload.get('id')
        site_url = payload.get('site_url', '')
        username = payload.get('username', '')
        
        if not site_url:
            self._show_error_dialog("URL manquante", "Impossible d'effectuer le remplissage automatique sans URL.")
            return
        
        if not pid:
            self._show_error_dialog("Erreur", "Identifiant du mot de passe manquant.")
            return
        
        # 2FA verification
        if not self._confirm_sensitive("remplissage automatique"):
            return
        
        # Decrypt password (backend returns plain text)
        try:
            plain_password = self._decrypt_from_backend(int(pid))
        except Exception as e:
            self._show_error_dialog("Erreur", f"Impossible de récupérer le mot de passe:\n{str(e)}")
            return
        
        # Method selection dialog
        choice_dialog = QMessageBox(self)
        choice_dialog.setWindowTitle("Méthode d'auto-remplissage")
        choice_dialog.setText(
            f"🚀 Choisissez la méthode d'auto-remplissage:\n\n"
            f"🌐 Site: {site_url}\n"
            f"👤 Identifiant: {username}"
        )
        choice_dialog.setIcon(QMessageBox.Question)
        
        # Custom buttons
        btn_selenium = choice_dialog.addButton("🤖 Selenium (Best)", QMessageBox.YesRole)
        btn_assisted = choice_dialog.addButton("🤝 Assisted (Safe)", QMessageBox.NoRole)
        btn_simple = choice_dialog.addButton("📋 Copy-Paste", QMessageBox.RejectRole)
        btn_cancel = choice_dialog.addButton("❌ Cancel", QMessageBox.RejectRole)
        
        choice_dialog.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Styles.PRIMARY_BG};
                color: {Styles.TEXT_PRIMARY};
            }}
            QMessageBox QLabel {{
                color: {Styles.TEXT_PRIMARY};
                min-width: 400px;
            }}
            QPushButton {{
                {Styles.get_button_style(True)}
                min-width: 120px;
                min-height: 35px;
                margin: 3px;
            }}
        """)
        
        choice_dialog.exec_()
        clicked = choice_dialog.clickedButton()
        
        if clicked == btn_cancel:
            return
        
        # Run in separate thread to avoid blocking Qt event loop
        def run_autofill():
            try:
                from src.gui.autofill import (
                    autofill_with_selenium,
                    open_and_type_credentials,
                    simple_copy_paste_method
                )
                
                if clicked == btn_selenium:
                    print("\n🤖 Starting Selenium auto-fill...")
                    success = autofill_with_selenium(site_url, username, plain_password)
                elif clicked == btn_assisted:
                    print("\n🤝 Starting assisted auto-fill...")
                    success = open_and_type_credentials(site_url, username, plain_password, delay=6.0)
                else:  # Simple
                    print("\n📋 Starting copy-paste method...")
                    success = simple_copy_paste_method(site_url, username, plain_password)
                    
            except ImportError as e:
                print(f"\n❌ Import error: {e}")
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()
        
        # Preparation message
        prep_msg = QMessageBox(self)
        prep_msg.setWindowTitle("Préparation...")
        prep_msg.setIcon(QMessageBox.Information)
        
        if clicked == btn_selenium:
            prep_msg.setText(
                "🤖 MODE SELENIUM\n\n"
                "Le navigateur va s'ouvrir.\n"
                "Les champs seront remplis automatiquement.\n"
                "Le bouton submit sera cliqué.\n\n"
                "⏰ Attendez 5 secondes..."
            )
        elif clicked == btn_assisted:
            prep_msg.setText(
                "🤝 MODE ASSISTÉ\n\n"
                "Le site va s'ouvrir.\n"
                "Cliquez sur les champs quand demandé.\n"
                "Les données seront collées automatiquement.\n\n"
                "👁️ Regardez la console pour les instructions!"
            )
        else:  # Simple
            prep_msg.setText(
                "📋 MODE COPIER-COLLER\n\n"
                "Le site va s'ouvrir.\n"
                "Les identifiants seront copiés un par un.\n"
                "Vous les collerez manuellement.\n\n"
                "👁️ Regardez la console pour les instructions!"
            )
        
        prep_msg.setStandardButtons(QMessageBox.Ok)
        prep_msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Styles.PRIMARY_BG};
                color: {Styles.TEXT_PRIMARY};
            }}
            QMessageBox QLabel {{
                color: {Styles.TEXT_PRIMARY};
                min-width: 400px;
            }}
            QPushButton {{
                {Styles.get_button_style(True)}
                min-width: 80px;
                min-height: 32px;
            }}
        """)
        
        prep_msg.exec_()
        
        # Run in thread
        print(f"\n{'='*70}")
        print(f"🚀 LAUNCHING AUTO-FILL")
        print(f"{'='*70}")
        
        thread = threading.Thread(target=run_autofill, daemon=True)
        thread.start()
        
        # Success message (will appear immediately, actual work happens in thread)
        QTimer.singleShot(1000, lambda: QMessageBox.information(
            self,
            "Auto-fill Started",
            "✅ Auto-fill process started!\n\n"
            "Watch the console and browser.\n\n"
            "If it doesn't work:\n"
            "• Try the 'Assisted' method\n"
            "• Or use 'Copy-Paste' for full control"
        ))
    # ---------------- Stats / Profile / Logout ----------------
    def _show_statistics_modal(self):
        self._show_statistics_page()

    def _show_edit_profile_modal(self):
        from src.gui.components.modals import EditProfileModal

        dlg = EditProfileModal(self.current_user, self.auth, self)

        def on_updated(u):
            self.current_user["username"] = u["username"]
            self.current_user["name"] = u["username"]
            self.current_user["initials"] = (u["username"][:2] or "US").upper()
            for i in reversed(range(self.user_box.count())):
                w = self.user_box.itemAt(i).widget()
                if w:
                    w.setParent(None)
            prof = UserProfileWidget(self.current_user["username"], self.current_user["initials"], self)
            prof.logout_clicked.connect(self.on_logout)
            prof.show_statistics.connect(self._show_statistics_page)
            prof.show_devices_clicked.connect(self._show_devices_placeholder)
            prof.lock_now_clicked.connect(lambda: self._lock_now(show_message=False))
            prof.edit_profile_clicked.connect(self._show_edit_profile_modal)
            self.user_box.addWidget(prof)

        dlg.profile_updated.connect(on_updated)
        dlg.exec_()

    def on_logout(self):
        rep = QMessageBox.question(self, "Déconnexion", "Se déconnecter ?",
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if rep != QMessageBox.Yes:
            return
        self.current_user = None
        for i in reversed(range(self.user_box.count())):
            w = self.user_box.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._all_passwords = []
        self.password_list.load_passwords([])
        self._auth_flow()
