# -*- coding: utf-8 -*-
import threading
import json
import os
from datetime import datetime, timedelta
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QMessageBox, QApplication, QPushButton, QDialog, QGridLayout, QLineEdit, QMenu, QAction,
    QFileDialog, QComboBox, QStackedLayout, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QEvent, QRectF, QPointF
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QPainterPath, QLinearGradient

# UI + components
from src.gui.components.sidebar import Sidebar
from src.gui.components.password_list import PasswordList
from src.gui.components.modals import (
    LoginModal, RegisterModal, AddPasswordModal,
    EditPasswordModal, ViewPasswordModal, TwoFactorModal, PasswordStrengthChecker
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


class DonutChartWidget(QWidget):
    def __init__(self, segments: list[tuple[str, int, str]], parent=None):
        super().__init__(parent)
        self.segments = segments
        self.setMinimumHeight(180)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        size = min(w, h) - 24
        x = (w - size) / 2
        y = (h - size) / 2
        rect = QRectF(x, y, size, size)
        total = max(1, sum(max(0, int(v)) for _, v, _ in self.segments))

        bg_pen = QPen(QColor(255, 255, 255, 28), 18)
        p.setPen(bg_pen)
        p.drawArc(rect, 0, 360 * 16)

        start = 90 * 16
        for _name, value, color in self.segments:
            v = max(0, int(value))
            if v <= 0:
                continue
            span = int((v / total) * 360 * 16)
            pen = QPen(QColor(color), 18)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, start, -span)
            start -= span

        p.setPen(QColor(235, 240, 255))
        p.setFont(QFont("Segoe UI", 20, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, str(total))


class CategoryBarChartWidget(QWidget):
    def __init__(self, items: list[tuple[str, int]], parent=None):
        super().__init__(parent)
        self.items = items[:6]
        self.setMinimumHeight(180)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(16, 16, -16, -16)
        if not self.items:
            p.setPen(QColor(180, 190, 210))
            p.drawText(r, Qt.AlignCenter, "Aucune categorie")
            return

        maxv = max(1, max(v for _, v in self.items))
        row_h = max(24, int(r.height() / max(1, len(self.items))))
        bar_left = r.left() + 110
        bar_max_w = max(50, r.width() - 130)
        for idx, (name, val) in enumerate(self.items):
            y = r.top() + idx * row_h + 4
            p.setPen(QColor(170, 182, 204))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(r.left(), y + 14, str(name)[:14])

            bg = QRectF(bar_left, y, bar_max_w, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24))
            p.drawRoundedRect(bg, 6, 6)

            w = max(4, int((max(0, val) / maxv) * bar_max_w))
            fg = QRectF(bar_left, y, w, 12)
            grad = QLinearGradient(fg.topLeft(), fg.topRight())
            grad.setColorAt(0.0, QColor(59, 130, 246))
            grad.setColorAt(1.0, QColor(16, 185, 129))
            p.setBrush(grad)
            p.drawRoundedRect(fg, 6, 6)

            p.setPen(QColor(230, 238, 255))
            p.drawText(int(bar_left + bar_max_w + 8), y + 12, str(val))


class TrendChartWidget(QWidget):
    def __init__(self, labels: list[str], values: list[int], parent=None):
        super().__init__(parent)
        self.labels = labels
        self.values = values
        self.setMinimumHeight(170)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(18, 16, -18, -22)
        if not self.values:
            p.setPen(QColor(180, 190, 210))
            p.drawText(r, Qt.AlignCenter, "Pas de donnees")
            return

        maxv = max(1, max(self.values))
        n = len(self.values)
        if n == 1:
            points = [QPointF(r.center().x(), r.center().y())]
        else:
            step_x = r.width() / max(1, (n - 1))
            points = []
            for i, val in enumerate(self.values):
                x = r.left() + i * step_x
                y = r.bottom() - (max(0, val) / maxv) * (r.height() - 24)
                points.append(QPointF(x, y))

        p.setPen(QPen(QColor(255, 255, 255, 30), 1, Qt.DashLine))
        for k in range(1, 4):
            y = r.top() + (k * r.height() / 4)
            p.drawLine(r.left(), int(y), r.right(), int(y))

        line = QPainterPath()
        line.moveTo(points[0])
        for pt in points[1:]:
            line.lineTo(pt)

        area = QPainterPath(line)
        area.lineTo(points[-1].x(), r.bottom())
        area.lineTo(points[0].x(), r.bottom())
        area.closeSubpath()
        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QColor(59, 130, 246, 110))
        grad.setColorAt(1.0, QColor(59, 130, 246, 8))
        p.setPen(Qt.NoPen)
        p.setBrush(grad)
        p.drawPath(area)

        p.setPen(QPen(QColor(96, 165, 250), 2.5))
        p.setBrush(QColor(16, 185, 129))
        p.drawPath(line)
        for pt in points:
            p.drawEllipse(pt, 3.5, 3.5)

        p.setPen(QColor(176, 189, 214))
        p.setFont(QFont("Segoe UI", 8))
        if n > 1:
            step = max(1, n // 4)
            for i in range(0, n, step):
                p.drawText(int(points[i].x() - 12), r.bottom() + 16, self.labels[i])
            if (n - 1) % step != 0:
                p.drawText(int(points[-1].x() - 12), r.bottom() + 16, self.labels[-1])


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
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("profileCapsule")
        shell.setStyleSheet("""
            QFrame#profileCapsule {
                background: rgba(15, 23, 42, 0.62);
                border: 1px solid rgba(96, 165, 250, 0.30);
                border-radius: 18px;
            }
        """)
        row = QHBoxLayout(shell)
        row.setContentsMargins(10, 8, 12, 8)
        row.setSpacing(10)
        root.addWidget(shell)

        avatar = QPushButton(self.initials)
        avatar.setFixedSize(40, 40)
        avatar.setCursor(Qt.PointingHandCursor)
        avatar.clicked.connect(self._menu)
        avatar.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2563eb, stop:1 #38bdf8);
                border: 1px solid rgba(147, 197, 253, 0.6);
                border-radius: 20px;
                color:#f8fafc;
                font-weight:700;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #1d4ed8, stop:1 #0ea5e9);
            }
        """)
        row.addWidget(avatar)

        name_btn = QPushButton(self.username)
        name_btn.setCursor(Qt.PointingHandCursor)
        name_btn.clicked.connect(self._menu)
        name_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #e2e8f0;
                border: none;
                text-align: left;
                font-size: 13px;
                font-weight: 600;
                padding-right: 6px;
            }
            QPushButton:hover { color: #bfdbfe; }
        """)
        row.addWidget(name_btn)

    def _menu(self):
        m = QMenu(self)
        m.setStyleSheet("""
            QMenu {
                background: #0b1a30;
                border: 1px solid rgba(148, 163, 184, 0.28);
                border-radius: 12px;
                padding: 8px;
            }
            QMenu::item {
                padding: 8px 14px;
                border-radius: 8px;
                color: #e2e8f0;
                font-size: 12px;
            }
            QMenu::item:selected {
                background: rgba(59,130,246,0.22);
                color: #f8fafc;
            }
            QMenu::separator {
                height: 1px;
                background: rgba(148, 163, 184, 0.22);
                margin: 5px 8px;
            }
        """)

        head = QAction(f"Compte: {self.username}", self)
        head.setEnabled(False)
        m.addAction(head)
        m.addSeparator()

        act_edit = QAction("Modifier le profil", self)
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

        act_logout = QAction("Se deconnecter", self)
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
        self.stats_page = QScrollArea()
        self.stats_page.setWidgetResizable(True)
        self.stats_page.setFrameShape(QFrame.NoFrame)
        self.stats_page.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        stats_container = QWidget()
        stats_container.setStyleSheet("background: transparent;")
        self.stats_layout = QVBoxLayout(stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(0)
        self.stats_page.setWidget(stats_container)
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
            dlg.login_success.connect(lambda email, password, d=dlg: self._on_login_attempt(email, password, d))
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

    def _on_login_attempt(self, email: str, password: str, login_dlg: QDialog | None = None):
        # Always ask MFA method after password verification, so do not auto-send email code here.
        result = self.auth.authenticate(email, password, send_2fa=False)
        if result.get("error"):
            if login_dlg and hasattr(login_dlg, "set_error"):
                login_dlg.set_error(result["error"])
            else:
                self._show_error_dialog("Erreur de connexion", result["error"])
            return
        user = result.get("user")
        if not user:
            if login_dlg and hasattr(login_dlg, "set_error"):
                login_dlg.set_error("❌ Utilisateur introuvable dans la réponse de connexion.")
            else:
                self._show_error_dialog("Erreur", "Utilisateur introuvable dans la réponse de connexion.")
            return

        method = self._ask_login_mfa_method()
        if method == "totp":
            if not bool(user.get("totp_enabled")):
                if login_dlg and hasattr(login_dlg, "set_error"):
                    login_dlg.set_error("❌ Vérification Auth App indisponible. Activez TOTP dans Profil.")
                else:
                    self._show_error_dialog("MFA", "Vérification Auth App indisponible. Activez TOTP dans Profil.")
                return
            self._show_totp_login(user, login_dlg)
            return

        if method == "email":
            sent = self.auth.send_2fa_code(user["email"], int(user["id"]), "login")
            if sent:
                self._show_2fa_login(user, login_dlg)
            elif login_dlg and hasattr(login_dlg, "set_error"):
                login_dlg.set_error("❌ Impossible d'envoyer le code email de vérification.")
            else:
                self._show_error_dialog("Erreur", "Impossible d'envoyer le code email de vérification.")
            return

        if login_dlg and hasattr(login_dlg, "set_error"):
            login_dlg.set_error("ℹ️ Vérification annulée.")

    def _show_2fa_login(self, user: dict, login_dlg: QDialog | None = None):
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
                if login_dlg:
                    login_dlg.accept()
            else:
                self._show_error_dialog("Erreur", "Code invalide ou expiré"
)

        try:
            dlg.code_verified.disconnect()
        except Exception:
            pass
        dlg.code_verified.connect(verify)

        dlg.exec_()

    def _show_totp_login(self, user: dict, login_dlg: QDialog | None = None):
        dlg = TwoFactorModal(user["email"], "<totp>", self, method="totp")

        def verify():
            code = dlg.code_input.text().strip()
            if not code or len(code) != 6:
                self._show_error_dialog("Code invalide", "Code 6 chiffres requis")
                return
            ok = False
            if hasattr(self.auth, "verify_totp"):
                ok = self.auth.verify_totp(user["email"], code)
            if ok:
                if hasattr(self.auth, "trust_device"):
                    try:
                        self.auth.trust_device(int(user["id"]))
                    except Exception:
                        pass
                dlg.accept()
                self._finalize_login(user)
                if login_dlg:
                    login_dlg.accept()
            else:
                self._show_error_dialog("Erreur", "Code d'application invalide ou expiré")

        try:
            dlg.code_verified.disconnect()
        except Exception:
            pass
        dlg.code_verified.connect(verify)

        dlg.exec_()

    def _ask_login_mfa_method(self) -> str | None:
        box = QMessageBox(self)
        box.setWindowTitle("Vérification de connexion")
        box.setIcon(QMessageBox.Question)
        box.setText("Choisissez votre méthode de vérification pour cette connexion.")
        box.setInformativeText("Sélectionnez Email (Gmail) ou Application Authenticator (TOTP).")
        btn_totp = box.addButton("Application TOTP", QMessageBox.AcceptRole)
        btn_email = box.addButton("Code Gmail", QMessageBox.ActionRole)
        box.addButton("Annuler", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if clicked == btn_totp:
            return "totp"
        if clicked == btn_email:
            return "email"
        return None

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
            f"Adresse cible: {email}\n\n"
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

        state = {"email": email}

        # Info
        info = QLabel("")
        info.setAlignment(Qt.AlignCenter)
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:13px;")
        layout.addWidget(info)

        def refresh_info():
            info.setText(
                f"Un code de vérification a été envoyé à:\n"
                f"{state['email']}\n\n"
                f"Vérifiez votre boîte mail (et les spams)"
            )

        refresh_info()
        
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

        change_email_btn = QPushButton("✉️ Envoyer à une autre adresse")
        change_email_btn.setMinimumHeight(44)
        change_email_btn.setCursor(Qt.PointingHandCursor)
        change_email_btn.setStyleSheet(Styles.get_button_style(False))
        layout.addWidget(change_email_btn)
        
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
            try:
                timer.timeout.disconnect(update_countdown)
            except Exception:
                pass
            timer.timeout.connect(update_countdown)
            timer.start(1000)
        
        def verify_code():
            code = code_input.text().strip()
            
            if not code or len(code) != 6:
                QMessageBox.warning(dlg, "Code invalide", "Veuillez saisir un code à 6 chiffres")
                return
            
            # Verify the registration code
            ok = self.auth.verify_registration_code(state["email"], code)
            
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
                    "email": state["email"],
                    "username": state["email"].split('@')[0]
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
            ok = self.auth.resend_verification_code(state["email"])
            
            if ok:
                QMessageBox.information(
                    dlg,
                    "Code renvoyé",
                    f"✅ Un nouveau code a été envoyé à:\n{state['email']}\n\n"
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

        def change_email():
            new_email, ok = QInputDialog.getText(
                dlg,
                "Changer l'adresse email",
                "Nouvelle adresse email:",
                QLineEdit.Normal,
                state["email"],
            )
            if not ok:
                return
            new_email = (new_email or "").strip()
            if not new_email:
                return
            if new_email == state["email"]:
                QMessageBox.information(dlg, "Email", "Cette adresse est déjà utilisée pour la vérification.")
                return

            changed_ok, message, updated_email = self.auth.change_unverified_email(state["email"], new_email)
            if not changed_ok:
                QMessageBox.warning(dlg, "Erreur", message)
                return

            state["email"] = updated_email or new_email
            refresh_info()
            code_input.clear()
            QMessageBox.information(dlg, "Email mis à jour", message)
            start_countdown()
        
        verify_btn.clicked.connect(verify_code)
        resend_btn.clicked.connect(resend_code)
        change_email_btn.clicked.connect(change_email)
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
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(16)

        top = QHBoxLayout()
        title = QLabel("Security Analytics")
        title.setFont(QFont("Segoe UI", 26, QFont.Bold))
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; letter-spacing: 0.4px;")
        subtitle = QLabel("Vue globale de la santé de votre coffre")
        subtitle.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        top.addLayout(title_col)
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

        # Hero card
        hero = QFrame()
        hero.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(59,130,246,0.22),
                    stop:1 rgba(16,185,129,0.18)
                );
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 18px;
            }
        """)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(18, 16, 18, 16)
        hl.setSpacing(16)
        hero_left = QVBoxLayout()
        hero_left.setSpacing(3)
        hero_title = QLabel("Score de sécurité")
        hero_title.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        hero_value = QLabel(f"{score}%")
        hero_value.setStyleSheet(f"color:{score_color}; font-size:40px; font-weight:900;")
        hero_tip = QLabel(
            "Excellent niveau" if score >= 80 else ("Niveau correct" if score >= 50 else "Niveau à renforcer")
        )
        hero_tip.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:12px;")
        hero_left.addWidget(hero_title)
        hero_left.addWidget(hero_value)
        hero_left.addWidget(hero_tip)
        hl.addLayout(hero_left)
        hl.addStretch()
        ring = QLabel("🛡️")
        ring.setStyleSheet("font-size:56px;")
        hl.addWidget(ring)
        lay.addWidget(hero)

        cards = QGridLayout()
        cards.setHorizontalSpacing(14)
        cards.setVerticalSpacing(14)

        def card(icon_text, title_text, value_text, color):
            w = QFrame()
            w.setStyleSheet("""
                QFrame {
                    background: rgba(255,255,255,0.05);
                    border: 1px solid rgba(255,255,255,0.08);
                    border-radius: 16px;
                }
            """)
            v = QVBoxLayout(w)
            v.setContentsMargins(14, 12, 14, 12)
            v.setSpacing(4)
            row = QHBoxLayout()
            row.setSpacing(6)
            ic = QLabel(icon_text)
            ic.setStyleSheet("font-size:15px;")
            t = QLabel(title_text)
            t.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
            row.addWidget(ic)
            row.addWidget(t)
            row.addStretch()
            val = QLabel(str(value_text))
            val.setStyleSheet(f"color:{color}; font-size:24px; font-weight:800;")
            v.addLayout(row)
            v.addWidget(val)
            return w

        cards.addWidget(card("🧾", "Total", total, Styles.BLUE_PRIMARY), 0, 0)
        cards.addWidget(card("✅", "Forts", strong, Styles.STRONG_COLOR), 0, 1)
        cards.addWidget(card("⚖️", "Moyens", medium, Styles.MEDIUM_COLOR), 0, 2)
        cards.addWidget(card("⚠️", "Faibles", weak, Styles.WEAK_COLOR), 0, 3)
        cards.addWidget(card("⭐", "Favoris", favorites, Styles.BLUE_SECONDARY), 1, 0)
        cards.addWidget(card("🔁", "Réutilisés", reused, Styles.MEDIUM_COLOR), 1, 1)
        cards.addWidget(card("🕒", "Anciens (180j+)", old, Styles.WEAK_COLOR), 1, 2)
        cards.addWidget(card("🔎", "Pwned", pwned, Styles.WEAK_COLOR), 1, 3)
        lay.addLayout(cards)

        panels = QGridLayout()
        panels.setHorizontalSpacing(14)
        panels.setVerticalSpacing(14)

        panel_style = """
            QFrame {
                background: rgba(8, 20, 40, 0.62);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 16px;
            }
        """

        # Panel 1: Donut + legend
        donut_box = QFrame()
        donut_box.setStyleSheet(panel_style)
        dl = QVBoxLayout(donut_box)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.setSpacing(8)
        dtitle = QLabel("Répartition visuelle")
        dtitle.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:13px; font-weight:700;")
        dl.addWidget(dtitle)
        donut = DonutChartWidget([
            ("Forts", strong, Styles.STRONG_COLOR),
            ("Moyens", medium, Styles.MEDIUM_COLOR),
            ("Faibles", weak, Styles.WEAK_COLOR),
        ])
        dl.addWidget(donut)
        legend = QHBoxLayout()
        legend.setSpacing(14)
        for lbl, val, color in [("Forts", strong, Styles.STRONG_COLOR), ("Moyens", medium, Styles.MEDIUM_COLOR), ("Faibles", weak, Styles.WEAK_COLOR)]:
            dot = QLabel(f"● {lbl} {val}")
            dot.setStyleSheet(f"color:{color}; font-size:12px; font-weight:700;")
            legend.addWidget(dot)
        legend.addStretch()
        dl.addLayout(legend)

        # Panel 2: Top categories bars
        cat_counts = {}
        for p in passwords:
            c = str(p.get("category") or "other").strip()
            cat_counts[c] = cat_counts.get(c, 0) + 1
        top_cats = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        cat_box = QFrame()
        cat_box.setStyleSheet(panel_style)
        cl = QVBoxLayout(cat_box)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(8)
        ctitle = QLabel("Top catégories")
        ctitle.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:13px; font-weight:700;")
        cl.addWidget(ctitle)
        cl.addWidget(CategoryBarChartWidget(top_cats))

        # Panel 3: 6-month trend
        trend_box = QFrame()
        trend_box.setStyleSheet(panel_style)
        tl = QVBoxLayout(trend_box)
        tl.setContentsMargins(14, 12, 14, 12)
        tl.setSpacing(8)
        ttitle = QLabel("Activité mensuelle (6 mois)")
        ttitle.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:13px; font-weight:700;")
        tl.addWidget(ttitle)
        month_labels = []
        month_keys = []
        now = datetime.utcnow()
        for i in range(5, -1, -1):
            d = (now.replace(day=1) - timedelta(days=1)).replace(day=1) if i else now.replace(day=1)
            # normalize by subtracting i months
            cursor = now.replace(day=1)
            for _ in range(i):
                cursor = (cursor - timedelta(days=1)).replace(day=1)
            key = f"{cursor.year:04d}-{cursor.month:02d}"
            month_keys.append(key)
            month_labels.append(cursor.strftime("%b"))
        month_values = {k: 0 for k in month_keys}
        for p in passwords:
            ts = p.get("created_at") or p.get("last_updated") or ""
            dt = None
            s = str(ts).strip()
            if s:
                try:
                    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    try:
                        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
                    except Exception:
                        dt = None
            if dt is None:
                continue
            mk = f"{dt.year:04d}-{dt.month:02d}"
            if mk in month_values:
                month_values[mk] += 1
        trend_vals = [month_values[k] for k in month_keys]
        tl.addWidget(TrendChartWidget(month_labels, trend_vals))

        # Panel 4: Hygiene + tips
        hygiene = QFrame()
        hygiene.setStyleSheet(panel_style)
        hyl = QVBoxLayout(hygiene)
        hyl.setContentsMargins(14, 12, 14, 12)
        hyl.setSpacing(8)
        htitle = QLabel("Hygiène & recommandations")
        htitle.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:13px; font-weight:700;")
        hyl.addWidget(htitle)
        facts = QLabel(
            f"Réutilisés: {reused}\nAnciens: {old}\nPwned: {pwned}\nFaibles: {weak}"
        )
        facts.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        hyl.addWidget(facts)
        tips = []
        if weak > 0:
            tips.append("• Remplacez les mots de passe faibles.")
        if reused > 0:
            tips.append("• Évitez de réutiliser le même mot de passe.")
        if old > 0:
            tips.append("• Renouvelez les comptes anciens.")
        if total == 0:
            tips.append("• Ajoutez des comptes pour voir des stats utiles.")
        if not tips:
            tips.append("• Très bon niveau de sécurité, continuez ainsi.")
        tips_lbl = QLabel("\n".join(tips))
        tips_lbl.setWordWrap(True)
        tips_lbl.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:12px;")
        hyl.addWidget(tips_lbl)
        hyl.addStretch()

        panels.addWidget(donut_box, 0, 0)
        panels.addWidget(cat_box, 0, 1)
        panels.addWidget(trend_box, 1, 0)
        panels.addWidget(hygiene, 1, 1)
        lay.addLayout(panels)
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
                strength = payload.get("strength", "medium")
                
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
                    site_url=site_url,
                    strength=strength,
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
            strength = PasswordStrengthChecker.check_strength(new_plain)[0]
            ok, msg = self.api_client.update_password(
                password_id=_id,
                updates={
                    "site_name": p["site_name"],
                    "username": p["username"],
                    "encrypted_password": enc,
                    "category": p.get("category", "personal"),
                    "favorite": p.get("favorite", False),
                    "strength": strength,
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
