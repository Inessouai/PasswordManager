# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QCheckBox, QComboBox, QWidget, QFrame, QMessageBox,
    QApplication, QProgressBar, QSizePolicy, QTextEdit, QScrollArea, QSpinBox,
    QFileDialog, QInputDialog, QGridLayout, QAbstractSpinBox
)

from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtGui import QFont, QPixmap
import random, string, re
from datetime import datetime
from src.auth.auth_manager import AuthManager, verify_password
from src.backend.api_client import APIClient
from src.security.password_tools import check_pwned_password
from src.gui.styles.styles import Styles
try:
    from src.security.audit import log_action
except Exception:  # fallback if module is missing
    def log_action(*_args, **_kwargs):
        return None
import csv
import webbrowser

try:
    import qrcode
    from PIL import ImageQt
    _QR_AVAILABLE = True
except Exception:
    _QR_AVAILABLE = False


def style_line_edit(line_edit):
    """Apply consistent styling to QLineEdit widgets"""
    line_edit.setMinimumHeight(48)
    line_edit.setFont(QFont("Segoe UI", 12))
    line_edit.setStyleSheet(Styles.get_input_style())


class PasswordStrengthChecker:
    """Password strength checking utilities"""

    @staticmethod
    def check_strength(password):
        """Check password strength - Returns: (strength_level, score, feedback)"""
        if not password:
            return "weak", 0, ["Password is empty"]

        score = 0
        feedback = []

        # Length check
        length = len(password)
        if length >= 12:
            score += 2
        elif length >= 8:
            score += 1
        else:
            feedback.append("Utilisez au moins 8 caractères")

        # Character variety
        if re.search(r'[a-z]', password):
            score += 1
        else:
            feedback.append("Ajoutez des minuscules")

        if re.search(r'[A-Z]', password):
            score += 1
        else:
            feedback.append("Ajoutez des majuscules")

        if re.search(r'\d', password):
            score += 1
        else:
            feedback.append("Ajoutez des chiffres")

        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            score += 1
        else:
            feedback.append("Ajoutez des caractères spéciaux")

        # Determine strength level
        if score >= 5:
            return "strong", score, ["Mot de passe fort !"]
        elif score >= 3:
            return "medium", score, feedback or ["Bon mot de passe"]
        else:
            return "weak", score, feedback or ["Mot de passe faible"]

    @staticmethod
    def generate_strong_password(length=16):
        """Generate a strong random password"""
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(random.choice(chars) for _ in range(length))
        return password


class PasswordStrengthWidget(QWidget):
    """Visual password strength indicator"""

    def __init__(self, user_id=None, api_client=None, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setMaximum(6)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 4px;
                background: rgba(255,255,255,0.05);
            }
            QProgressBar::chunk {
                border-radius: 3px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #ef4444, stop:0.5 #f59e0b, stop:1 #10b981);
            }
        """)
        layout.addWidget(self.progress)

        # Status label
        self.label = QLabel("Entrez un mot de passe")
        self.label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 12px; background: transparent;")
        layout.addWidget(self.label)

    def update_strength(self, password):
        """Update strength indicator based on password"""
        strength, score, feedback = PasswordStrengthChecker.check_strength(password)

        self.progress.setValue(score)

        colors = {
            'weak': Styles.WEAK_COLOR,
            'medium': Styles.MEDIUM_COLOR,
            'strong': Styles.STRONG_COLOR
        }

        color = colors.get(strength, Styles.TEXT_MUTED)

        if not password:
            self.label.setText("Entrez un mot de passe")
            self.label.setStyleSheet(f"color: {Styles.TEXT_MUTED}; font-size: 12px; background: transparent;")
        else:
            self.label.setText(f"{strength.capitalize()}: {', '.join(feedback)}")
            self.label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: bold; background: transparent;")


class AnimatedButton(QPushButton):
    """Button with hover animation"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)


# ==================== LOGIN MODAL ====================
class LoginModal(QDialog):
    login_success = pyqtSignal(str, str)
    switch_to_register = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Password Guardian - Connexion")
        self.setFixedSize(450, 570)
        self.setModal(True)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowTitleHint)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 25px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
            QLineEdit, QComboBox, QSpinBox {{
                background-color: rgba(15, 30, 54, 0.85);
                border: 1px solid rgba(96, 165, 250, 0.35);
                border-radius: 12px;
                color: {Styles.TEXT_PRIMARY};
                padding: 10px 12px;
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
                border: 1px solid rgba(96, 165, 250, 0.8);
                background-color: rgba(15, 30, 54, 0.95);
            }}
            QComboBox QAbstractItemView {{
                background: #0f1e36;
                color: #e6effb;
                selection-background-color: rgba(59,130,246,0.35);
                border: 1px solid rgba(255,255,255,0.1);
            }}
            QCheckBox {{
                color: {Styles.TEXT_SECONDARY};
            }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
            }}
            QCheckBox::indicator:unchecked {{
                border: 1px solid rgba(255,255,255,0.35);
                background: rgba(255,255,255,0.04);
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                border: 1px solid rgba(59,130,246,0.9);
                background: rgba(59,130,246,0.9);
                border-radius: 3px;
            }}
            QProgressBar {{
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 6px;
                color: {Styles.TEXT_PRIMARY};
                text-align: center;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(22)

        head = QVBoxLayout()
        head.setSpacing(12)
        head.setAlignment(Qt.AlignCenter)
        icon = QLabel("🔐")
        icon.setStyleSheet("font-size:46px; background: transparent;")
        title = QLabel("Connexion")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(Styles.get_label_style(24))
        sub = QLabel("Accédez à votre coffre-fort sécurisé")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(Styles.get_label_style(14, Styles.TEXT_SECONDARY))
        head.addWidget(icon)
        head.addWidget(title)
        head.addWidget(sub)
        layout.addLayout(head)

        # Scroll area for long content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 10, 0)
        content_layout.setSpacing(12)

        form = QVBoxLayout()
        form.setSpacing(18)

        # Email
        lbl = QLabel("📧 Adresse e-mail")
        lbl.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        form.addWidget(lbl)

        self.email_input = QLineEdit()
        style_line_edit(self.email_input)
        self.email_input.setPlaceholderText("votre@email.com")
        form.addWidget(self.email_input)
        form.addSpacing(6)

        # Password
        lbl2 = QLabel("🔒 Mot de passe")
        lbl2.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        form.addWidget(lbl2)

        row = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        style_line_edit(self.password_input)
        self.password_input.setPlaceholderText("Entrez votre mot de passe")
        self.toggle_pwd_btn = QPushButton("👁️")
        self.toggle_pwd_btn.setFixedSize(40, 40)
        self.toggle_pwd_btn.setCheckable(True)
        self.toggle_pwd_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.1); border:none; border-radius:8px; }
            QPushButton:checked { background-color: rgba(59,130,246,0.3); }
        """)
        self.toggle_pwd_btn.toggled.connect(
            lambda c: self.password_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        row.addWidget(self.password_input)
        row.addWidget(self.toggle_pwd_btn)
        form.addLayout(row)

        # Error message
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ef4444; font-size: 12px; font-weight: bold; background: transparent;")
        self.error_label.setWordWrap(True)
        form.addWidget(self.error_label)

        layout.addLayout(form)

        login_btn = AnimatedButton("🚀 Se connecter")
        login_btn.setStyleSheet(Styles.get_button_style(primary=True))
        login_btn.setMinimumHeight(50)
        login_btn.clicked.connect(self.on_login)
        layout.addWidget(login_btn)

        # Forgot password
        forgot_layout = QHBoxLayout()
        forgot_layout.setAlignment(Qt.AlignCenter)
        forgot_text = QLabel("Mot de passe oublié?")
        forgot_text.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_MUTED))
        forgot_link = QLabel(
            "<a href='#' style='color:#60a5fa; text-decoration:none; font-weight:bold;'>Réinitialiser</a>")
        forgot_link.setOpenExternalLinks(False)
        forgot_link.linkActivated.connect(self.show_forgot_password)
        forgot_layout.addWidget(forgot_text)
        forgot_layout.addWidget(forgot_link)
        layout.addLayout(forgot_layout)

        # Register link
        footer = QHBoxLayout()
        footer.setAlignment(Qt.AlignCenter)
        t = QLabel("Nouveau chez Password Guardian?")
        t.setStyleSheet(Styles.get_label_style(14, Styles.TEXT_MUTED))
        link = QLabel("<a href='#' style='color:#60a5fa; text-decoration:none; font-weight:bold;'>Créer un compte</a>")
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda: self.switch_to_register.emit())
        footer.addWidget(t)
        footer.addWidget(link)
        layout.addLayout(footer)

    def on_login(self):
        email = self.email_input.text().strip()
        pwd = self.password_input.text()

        self.error_label.setText("")

        if not email:
            self.error_label.setText("❌ Veuillez saisir votre adresse email")
            return
        if not pwd:
            self.error_label.setText("❌ Veuillez saisir votre mot de passe")
            return
        if '@' not in email or '.' not in email:
            self.error_label.setText("❌ Adresse email invalide")
            return

        self.login_success.emit(email, pwd)
        self.accept()

    def show_forgot_password(self):
        """Open forgot password dialog"""
        from src.auth.auth_manager import AuthManager
        from src.gui.components.auth_dialogs import ForgotPasswordDialog

        auth = AuthManager()  # No parameters needed

        dlg = ForgotPasswordDialog(auth, parent=self)
        result = dlg.exec_()

        if result == QDialog.Accepted:
            self.email_input.clear()
            self.password_input.clear()
            self.error_label.setStyleSheet(
                "color: #10b981; font-size: 12px; font-weight: bold; background: transparent;"
            )
            self.error_label.setText(
                "✅ Mot de passe réinitialisé. Connectez-vous avec votre nouveau mot de passe."
            )


# ==================== REGISTER MODAL ====================

class RegisterModal(QDialog):
    register_success = pyqtSignal(str, str, str)
    switch_to_login = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Password Guardian - Inscription")
        self.setFixedSize(500, 750)
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1); border-radius: 25px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        head = QVBoxLayout()
        head.setAlignment(Qt.AlignCenter)
        head.setSpacing(10)
        icon = QLabel("🛡️")
        icon.setStyleSheet("font-size:46px; background: transparent;")
        title = QLabel("Créer un compte")
        title.setFont(QFont("Segoe UI", 24, QFont.Bold))
        title.setStyleSheet(Styles.get_label_style(24))
        sub = QLabel("Rejoignez la communauté Password Guardian")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(Styles.get_label_style(14, Styles.TEXT_SECONDARY))
        head.addWidget(icon)
        head.addWidget(title)
        head.addWidget(sub)
        layout.addLayout(head)

        form = QVBoxLayout()
        form.setSpacing(18)

        # Name
        nlab = QLabel("👤 Nom complet")
        nlab.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        self.name_input = QLineEdit()
        style_line_edit(self.name_input)
        self.name_input.setPlaceholderText("Entrez votre nom complet")
        form.addWidget(nlab)
        form.addWidget(self.name_input)
        form.addSpacing(6)

        # Email
        elab = QLabel("📧 Adresse e-mail")
        elab.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        self.email_input = QLineEdit()
        style_line_edit(self.email_input)
        self.email_input.setPlaceholderText("votre@email.com")
        form.addWidget(elab)
        form.addWidget(self.email_input)
        form.addSpacing(6)

        # Password
        plab = QLabel("🔒 Mot de passe maître")
        plab.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        form.addWidget(plab)

        prow = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        style_line_edit(self.password_input)
        self.password_input.setPlaceholderText("Créez un mot de passe fort")
        self.toggle_pwd_btn = QPushButton("👁️")
        self.toggle_pwd_btn.setFixedSize(40, 40)
        self.toggle_pwd_btn.setCheckable(True)
        self.toggle_pwd_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.1); border:none; border-radius:8px; }
            QPushButton:checked { background-color: rgba(59,130,246,0.3); }
        """)
        self.toggle_pwd_btn.toggled.connect(lambda c: (
            self.password_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password),
            self.confirm_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        ))
        prow.addWidget(self.password_input)
        prow.addWidget(self.toggle_pwd_btn)
        form.addLayout(prow)

        self.strength_widget = PasswordStrengthWidget()
        self.password_input.textChanged.connect(self.on_password_changed)
        form.addWidget(self.strength_widget)

        # Weak password warning
        self.weak_password_container = QFrame()
        self.weak_password_container.setVisible(False)
        self.weak_password_container.setStyleSheet("""
            QFrame {
                background-color: rgba(239, 68, 68, 0.1);
                border: 1px solid rgba(239, 68, 68, 0.3);
                border-radius: 10px;
                padding: 12px;
            }
        """)
        weak_layout = QVBoxLayout(self.weak_password_container)
        weak_layout.setContentsMargins(8, 8, 8, 8)
        weak_layout.setSpacing(8)

        weak_label = QLabel("⚠️ Mot de passe faible détecté")
        weak_label.setStyleSheet("color: #ef4444; font-weight: bold; font-size: 12px; background: transparent;")
        weak_layout.addWidget(weak_label)

        weak_btn_layout = QHBoxLayout()
        self.generate_strong_btn = AnimatedButton("🎲 Générer un mot de passe fort")
        self.generate_strong_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {Styles.STRONG_COLOR}, stop:1 #059669);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 {Styles.STRONG_COLOR});
            }}
        """)
        self.generate_strong_btn.clicked.connect(self.generate_strong_password)
        weak_btn_layout.addWidget(self.generate_strong_btn)
        weak_btn_layout.addStretch()
        weak_layout.addLayout(weak_btn_layout)

        form.addWidget(self.weak_password_container)
        form.addSpacing(6)

        # Confirm password
        clab = QLabel("✅ Confirmer le mot de passe")
        clab.setStyleSheet(
            f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; font-weight: normal; background: transparent;")
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        style_line_edit(self.confirm_input)
        self.confirm_input.setPlaceholderText("Confirmez votre mot de passe")
        form.addWidget(clab)
        form.addWidget(self.confirm_input)

        layout.addLayout(form)

        btn = AnimatedButton("🎉 Créer mon compte")
        btn.setStyleSheet(Styles.get_button_style(primary=True))
        btn.setMinimumHeight(50)
        btn.clicked.connect(self.on_register)
        layout.addWidget(btn)

        foot = QHBoxLayout()
        foot.setAlignment(Qt.AlignCenter)
        t = QLabel("Déjà un compte?")
        t.setStyleSheet(Styles.get_label_style(14, Styles.TEXT_MUTED))
        link = QLabel("<a href='#' style='color:#60a5fa; text-decoration:none; font-weight:bold;'>Se connecter</a>")
        link.setOpenExternalLinks(False)
        link.linkActivated.connect(lambda: self.switch_to_login.emit())
        foot.addWidget(t)
        foot.addWidget(link)
        layout.addLayout(foot)

    def on_password_changed(self, password):
        """Called when password text changes"""
        self.strength_widget.update_strength(password)

        if password:
            strength, _, _ = PasswordStrengthChecker.check_strength(password)
            self.weak_password_container.setVisible(strength == "weak")
        else:
            self.weak_password_container.setVisible(False)

    def generate_strong_password(self):
        """Generate a strong password and fill it in"""
        strong_pwd = PasswordStrengthChecker.generate_strong_password(16)
        self.password_input.setText(strong_pwd)
        self.confirm_input.setText(strong_pwd)

        self.toggle_pwd_btn.setChecked(True)

        QMessageBox.information(
            self,
            "Mot de passe généré",
            f"Un mot de passe fort a été généré :\n\n{strong_pwd}\n\n"
            "💡 Conseil : Copiez-le et conservez-le dans un endroit sûr !"
        )

    def on_register(self):
        name = self.name_input.text().strip()
        email = self.email_input.text().strip()
        pwd = self.password_input.text()
        cpwd = self.confirm_input.text()
        if not name:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir votre nom complet")
            return
        if not email:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir votre adresse e-mail")
            return
        if '@' not in email or '.' not in email:
            QMessageBox.warning(self, "Erreur", "Adresse e-mail invalide")
            return
        if not pwd:
            QMessageBox.warning(self, "Erreur", "Veuillez créer un mot de passe maître")
            return
        if pwd != cpwd:
            QMessageBox.warning(self, "Erreur", "Les mots de passe ne correspondent pas")
            return
        # Vérification HIBP avec k-anonymity (préfixe SHA1 5 caractères uniquement)
        compromised, breach_count = check_pwned_password(pwd, timeout=3)
        if compromised:
            message = (
                f"⚠️ MOT DE PASSE COMPROMIS !\n\n"
                f"Ce mot de passe a été trouvé dans {breach_count:,} fuites de données.\n\n"
                "Confidentialité préservée (k-anonymity):\n"
                "• Seuls les 5 premiers caractères du hash SHA1 sont envoyés\n"
                "• La comparaison complète est faite localement\n\n"
                "Voulez-vous vraiment utiliser ce mot de passe ?"
            )
            reply = QMessageBox.critical(
                self,
                "ALERTE DE SÉCURITÉ",
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        strength, _, _ = PasswordStrengthChecker.check_strength(pwd)
        if strength == "weak":
            reply = QMessageBox.question(
                self,
                "⚠️ Mot de passe faible",
                "Votre mot de passe est faible et pourrait être facilement deviné.\n\n"
                "Voulez-vous :\n"
                "• Générer un mot de passe fort automatiquement ?\n"
                "• Ou continuer avec ce mot de passe faible ?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )

            if reply == QMessageBox.Yes:
                self.generate_strong_password()
                return

        self.register_success.emit(name, email, pwd)
        self.accept()


# ==================== ADD PASSWORD MODAL (SANS "Nom du site") ====================

class AddPasswordModal(QDialog):
    password_added = pyqtSignal(dict)

    def __init__(self, user_id=None, api_client=None, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.api_client = api_client
        self.setWindowTitle("Ajouter un mot de passe")
        self.setFixedSize(640, 680)
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1); border-radius: 25px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(16)

        # Header
        head = QHBoxLayout()
        icon = QLabel("🔐")
        icon.setStyleSheet("font-size:30px; background: transparent;")
        title = QLabel("Nouveau Mot de Passe")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; background:transparent;")
        head.addWidget(icon)
        head.addWidget(title)
        head.addStretch()
        layout.addLayout(head)

        # Scroll area for long content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        form = QVBoxLayout()
        form.setSpacing(12)

        dark_input = f"""
            QLineEdit {{
                background-color: rgba(15, 30, 54, 0.85);
                border: 1px solid rgba(96, 165, 250, 0.35);
                border-radius: 12px;
                color: {Styles.TEXT_PRIMARY};
                padding: 10px 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(96, 165, 250, 0.8);
                background-color: rgba(15, 30, 54, 0.95);
            }}
        """
        dark_combo = f"""
            QComboBox {{
                background-color: rgba(15, 30, 54, 0.85);
                border: 1px solid rgba(96, 165, 250, 0.35);
                border-radius: 12px;
                color: {Styles.TEXT_PRIMARY};
                padding: 8px 10px;
            }}
            QComboBox:focus {{
                border: 1px solid rgba(96, 165, 250, 0.8);
                background-color: rgba(15, 30, 54, 0.95);
            }}
            QComboBox QAbstractItemView {{
                background: #0f1e36;
                color: #e6effb;
                selection-background-color: rgba(59,130,246,0.35);
                border: 1px solid rgba(255,255,255,0.1);
            }}
        """

        # Website URL
        lab_url = QLabel("🌐 URL du site web")
        lab_url.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:14px; background:transparent;")
        self.url_input = QLineEdit()
        self.url_input.setMinimumHeight(48)
        self.url_input.setFont(QFont("Segoe UI", 12))
        self.url_input.setStyleSheet(dark_input)
        self.url_input.setPlaceholderText("https://example.com/login")
        form.addWidget(lab_url)

        url_row = QHBoxLayout()
        url_row.addWidget(self.url_input)

        # Open URL button
        self.open_url_btn = QPushButton("🔗")
        self.open_url_btn.setFixedSize(48, 48)
        self.open_url_btn.setToolTip("Ouvrir le site dans le navigateur")
        self.open_url_btn.setCursor(Qt.PointingHandCursor)
        self.open_url_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba(59, 130, 246, 0.15);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 10px;
                font-size: 18px;
            }}
            QPushButton:hover {{
                background-color: rgba(59, 130, 246, 0.25);
                border: 1px solid rgba(59, 130, 246, 0.5);
            }}
        """)
        self.open_url_btn.clicked.connect(self.open_website)
        url_row.addWidget(self.open_url_btn)
        form.addLayout(url_row)

        # Email/Username
        lab2 = QLabel("📧 Email / Identifiant")
        lab2.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:14px; background:transparent;")
        self.email_input = QLineEdit()
        self.email_input.setMinimumHeight(48)
        self.email_input.setFont(QFont("Segoe UI", 12))
        self.email_input.setStyleSheet(dark_input)
        self.email_input.setPlaceholderText("votre@email.com ou nom d'utilisateur")
        form.addWidget(lab2)
        form.addWidget(self.email_input)

        # Password
        lab3 = QLabel("🔒 Mot de passe")
        lab3.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:14px; background:transparent;")
        row = QHBoxLayout()
        self.pwd_input = QLineEdit()
        self.pwd_input.setEchoMode(QLineEdit.Password)
        self.pwd_input.setMinimumHeight(48)
        self.pwd_input.setFont(QFont("Segoe UI", 12))
        self.pwd_input.setStyleSheet(dark_input)
        self.pwd_input.setPlaceholderText("Saisissez ou générez un mot de passe")
        self.toggle_pwd_btn = QPushButton("👁️")
        self.toggle_pwd_btn.setFixedSize(48, 48)
        self.toggle_pwd_btn.setCheckable(True)
        self.toggle_pwd_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255,255,255,0.1); border:none; border-radius:10px; }
            QPushButton:checked { background-color: rgba(59,130,246,0.3); }
        """)
        self.toggle_pwd_btn.toggled.connect(
            lambda c: self.pwd_input.setEchoMode(QLineEdit.Normal if c else QLineEdit.Password)
        )
        row.addWidget(self.pwd_input)
        row.addWidget(self.toggle_pwd_btn)
        form.addWidget(lab3)
        form.addLayout(row)

        # Generate password section
        gen = QHBoxLayout()
        self.generate_checkbox = QCheckBox("🎲 Générer un mot de passe sécurisé")
        self.generate_checkbox.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:14px; background:transparent;")
        self.generate_checkbox.toggled.connect(self.toggle_password_generation)
        gen.addWidget(self.generate_checkbox)

        self.generate_btn = QPushButton("Générer")
        self.generate_btn.setVisible(False)
        self.generate_btn.setMinimumHeight(36)
        self.generate_btn.setCursor(Qt.PointingHandCursor)
        self.generate_btn.clicked.connect(self.generate_password)
        self.generate_btn.setStyleSheet(Styles.get_button_style(primary=False))
        gen.addWidget(self.generate_btn)
        gen.addStretch()
        form.addLayout(gen)

        # Generator options
        gen_opts = QHBoxLayout()
        gen_opts.setSpacing(10)
        gen_len_lbl = QLabel("Longueur")
        gen_len_lbl.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:11px; background:transparent;")
        self.gen_len = QSpinBox()
        self.gen_len.setRange(6, 64)
        self.gen_len.setValue(16)
        self.gen_len.setFixedWidth(68)
        self.gen_len.setMinimumHeight(18)
        self.gen_len.setAlignment(Qt.AlignCenter)
        self.gen_len.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        self.gen_len.setStyleSheet(f"""
            QSpinBox {{
                background-color: rgba(15, 30, 54, 0.9);
                border: 1px solid rgba(96, 165, 250, 0.4);
                border-radius: 10px;
                color: {Styles.TEXT_PRIMARY};
                padding: 2px 6px;
            }}
            QSpinBox:focus {{
                border: 1px solid rgba(96, 165, 250, 0.8);
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 14px;
                border: none;
                background: transparent;
            }}
            QSpinBox::up-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-bottom: 7px solid rgba(226,239,251,0.8);
                width: 0; height: 0;
            }}
            QSpinBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 7px solid rgba(226,239,251,0.8);
                width: 0; height: 0;
            }}
        """)

        self.opt_upper = QCheckBox("A-Z")
        self.opt_upper.setChecked(True)
        self.opt_lower = QCheckBox("a-z")
        self.opt_lower.setChecked(True)
        self.opt_digits = QCheckBox("0-9")
        self.opt_digits.setChecked(True)
        self.opt_symbols = QCheckBox("!@#")
        self.opt_symbols.setChecked(True)
        for c in (self.opt_upper, self.opt_lower, self.opt_digits, self.opt_symbols):
            c.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:11px;")

        gen_opts.addWidget(gen_len_lbl)
        gen_opts.addWidget(self.gen_len)
        gen_opts.addSpacing(6)
        gen_opts.addWidget(self.opt_upper)
        gen_opts.addWidget(self.opt_lower)
        gen_opts.addWidget(self.opt_digits)
        gen_opts.addWidget(self.opt_symbols)
        gen_opts.addStretch()
        form.addLayout(gen_opts)

        self.strength_widget = PasswordStrengthWidget()
        self.pwd_input.textChanged.connect(self.strength_widget.update_strength)
        form.addWidget(self.strength_widget)
        form.addSpacing(8)
        # Category
        cl = QLabel("📁 Catégorie")
        cl.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:14px; background:transparent;")
        self.category_combo = QComboBox()
        self.category_combo.addItems([
            "👤 Personnel",
            "💼 Travail",
            "💳 Finance",
            "🏦 Banque",
            "📚 Étude",
            "🎮 Jeux",
            "📂 Autre",
        ])
        self.category_combo.setMinimumHeight(48)
        self.category_combo.setFont(QFont("Segoe UI", 12))
        self.category_combo.setEditable(False)
        self.category_combo.setStyleSheet(dark_combo)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        form.addWidget(cl)
        form.addWidget(self.category_combo)

        content_layout.addLayout(form)
        content_layout.addSpacing(10)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Buttons
        btns = QHBoxLayout()
        btns.setSpacing(12)
        cancel = QPushButton("? Annuler")
        cancel.setStyleSheet(Styles.get_button_style(primary=False))
        cancel.setMinimumHeight(48)
        cancel.setCursor(Qt.PointingHandCursor)
        save = QPushButton("💾 Enregistrer le mot de passe")
        save.setStyleSheet(Styles.get_button_style(primary=True))
        save.setMinimumHeight(48)
        save.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.on_save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def toggle_password_generation(self, checked):
        self.generate_btn.setVisible(checked)
        if checked:
            self.pwd_input.clear()
            self.pwd_input.setReadOnly(True)
            self.pwd_input.setProperty("readonly", True)
            self.pwd_input.style().unpolish(self.pwd_input)
            self.pwd_input.style().polish(self.pwd_input)
            self.generate_password()
        else:
            self.pwd_input.setReadOnly(False)
            self.pwd_input.setProperty("readonly", False)
            self.pwd_input.style().unpolish(self.pwd_input)
            self.pwd_input.style().polish(self.pwd_input)

    def _on_category_changed(self, text: str):
        if text.startswith("📂 Autre"):
            self.category_combo.setEditable(True)
            le = self.category_combo.lineEdit()
            if le:
                le.setPlaceholderText("Votre catégorie...")
            if text.strip() == "📂 Autre":
                self.category_combo.setEditText("")
        else:
            self.category_combo.setEditable(False)

    def generate_password(self):
        # Generate a password using selected character sets.
        length = int(self.gen_len.value()) if hasattr(self, "gen_len") else 16
        pools = []
        if self.opt_upper.isChecked():
            pools.append(string.ascii_uppercase)
        if self.opt_lower.isChecked():
            pools.append(string.ascii_lowercase)
        if self.opt_digits.isChecked():
            pools.append(string.digits)
        if self.opt_symbols.isChecked():
            pools.append("!@#$%^&*")

        if not pools:
            QMessageBox.warning(self, "Erreur", "Choisissez au moins un type de caractère.")
            return

        pwd_chars = [random.choice(p) for p in pools]
        all_chars = "".join(pools)
        while len(pwd_chars) < length:
            pwd_chars.append(random.choice(all_chars))
        random.shuffle(pwd_chars)
        pwd = "".join(pwd_chars[:length])
        self.pwd_input.setText(pwd)
        self.strength_widget.update_strength(pwd)

    def open_website(self):
        """Open the website URL in default browser"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "URL manquante", "Veuillez saisir l'URL du site web.")
            return

        # Add https:// if no protocol
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        try:
            webbrowser.open(url)
            QMessageBox.information(
                self,
                "Site ouvert",
                "✅ Le site a été ouvert dans votre navigateur.\n\n"
                "Astuce: Après l'enregistrement, vous pourrez utiliser "
                "le bouton 🔗 sur chaque carte pour ouvrir et remplir automatiquement."
            )
        except Exception as e:
            QMessageBox.warning(self, "Erreur", f"Impossible d'ouvrir l'URL: {str(e)}")

    def on_save(self):
        """Save password - Extract site name from URL automatically"""
        url = self.url_input.text().strip()
        user = self.email_input.text().strip()
        pwd = self.pwd_input.text().strip()

        # Validation
        if not url:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir l'URL du site web")
            return
        if not user:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir un email/identifiant")
            return
        if not pwd:
            QMessageBox.warning(self, "Erreur", "Veuillez saisir un mot de passe")
            return
        # Vérification HIBP avec k-anonymity (préfixe SHA1 5 caractères uniquement)
        compromised, breach_count = check_pwned_password(pwd, timeout=3)
        if compromised:
            message = (
                f"⚠️ MOT DE PASSE COMPROMIS !\n\n"
                f"Ce mot de passe a été trouvé dans {breach_count:,} fuites de données.\n\n"
                "Confidentialité préservée (k-anonymity):\n"
                "• Seuls les 5 premiers caractères du hash SHA1 sont envoyés\n"
                "• La comparaison complète est faite localement\n\n"
                "Voulez-vous vraiment utiliser ce mot de passe ?"
            )
            reply = QMessageBox.critical(
                self,
                "ALERTE DE SÉCURITÉ",
                message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

            # Extract site name from URL
        site_name = url
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
            domain = parsed.netloc or parsed.path
            # Remove www. and extract main domain
            if domain.startswith('www.'):
                domain = domain[4:]
            # Take first part before first dot as site name
            site_name = domain.split('.')[0].capitalize() if domain else url
        except:
            site_name = url.split('/')[0].split('.')[0].capitalize()

        # Map display category to backend category
        category_map = {
            "👤 Personnel": "personal",
            "💼 Travail": "work",
            "💳 Finance": "finance",
            "🏦 Banque": "bank",
            "🎮 Jeux": "game",
            "📚 Étude": "study",
            "📂 Autre": "custom",
        }

        display_cat = self.category_combo.currentText().strip()
        category = category_map.get(display_cat, "custom")
        if category == "custom":
            cleaned = re.sub(r"^[^\w]+", "", display_cat).strip()
            if not cleaned:
                QMessageBox.warning(self, "Erreur", "Veuillez saisir une catégorie.")
                return
            if not display_cat.strip().startswith(("📁", "📂", "👤", "💼", "💳", "🏦", "🎮", "📚")):
                display_cat = f"📁 {cleaned}"
            category = re.sub(r"[^\w\s-]", "", cleaned).strip().lower().replace(" ", "_") or "custom"
            if display_cat and display_cat not in [self.category_combo.itemText(i) for i in range(self.category_combo.count())]:
                self.category_combo.addItem(display_cat)
                self.category_combo.setCurrentText(display_cat)


        # Emit with 'password' key instead of 'encrypted_password'
        payload = {
            'site_name': site_name,
            'site_url': url,
            'username': user,
            'password': pwd,  # Corrected key
            'category': category,
            'strength': PasswordStrengthChecker.check_strength(pwd)[0],
        }

        print(f"📤 Emitting password_added with payload: {payload}")
        self.password_added.emit(payload)
        self.accept()
class ViewPasswordModal(QDialog):
    def __init__(self, password_data, api_client=None, parent=None):
        super().__init__(parent)
        self.password_data = password_data or {}
        self.api_client = api_client
        self.setWindowTitle(f"Mot de passe - {self.password_data.get('site_name', '')}")
        self.setFixedSize(480, 400)
        self.setModal(True)
        self._decrypted_pwd = None
        self._is_visible = True
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 20px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        # Header
        head = QHBoxLayout()
        icon = QLabel(self.password_data.get('site_icon', '🔒'))
        icon.setStyleSheet("font-size:36px; background: transparent;")
        title = QLabel(self.password_data.get('site_name', 'Compte'))
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(Styles.get_label_style(20))
        head.addWidget(icon)
        head.addWidget(title)
        head.addStretch()
        layout.addLayout(head)

        # Info section
        info = QVBoxLayout()
        info.setSpacing(18)

        # Username/Email section
        username_section = QVBoxLayout()
        username_section.setSpacing(6)

        # FIXED: Proper label for username
        lbl_id = QLabel("📧 Identifiant / Email")
        lbl_id.setStyleSheet(Styles.get_label_style(12, Styles.TEXT_MUTED) + "; background: transparent;")

        val_id = QLabel(self.password_data.get('username', ''))
        val_id.setStyleSheet(f"""
            color: {Styles.TEXT_PRIMARY};
            font-size: 14px;
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 12px 14px;
        """)
        val_id.setTextInteractionFlags(Qt.TextSelectableByMouse)
        username_section.addWidget(lbl_id)
        username_section.addWidget(val_id)
        info.addLayout(username_section)

        # Password section
        password_section = QVBoxLayout()
        password_section.setSpacing(6)

        # FIXED: Proper label for password
        lbl_pwd = QLabel("🔒 Mot de passe")
        lbl_pwd.setStyleSheet(Styles.get_label_style(12, Styles.TEXT_MUTED) + "; background: transparent;")

        pwd_container = QFrame()
        pwd_container.setStyleSheet("""
            QFrame {
                background: rgba(59, 130, 246, 0.08);
                border: 1px solid rgba(59, 130, 246, 0.3);
                border-radius: 12px;
                padding: 4px;
            }
        """)
        pwd_layout = QHBoxLayout(pwd_container)
        pwd_layout.setContentsMargins(8, 8, 8, 8)
        pwd_layout.setSpacing(10)

        # Get the plain password (already decrypted by backend)
        plain_password = self.password_data.get('encrypted_password', '') or self.password_data.get('password', '')
        self._decrypted_pwd = plain_password

        self.val_pwd = QLabel(self._decrypted_pwd)
        self.val_pwd.setStyleSheet(f"""
            color: {Styles.TEXT_PRIMARY};
            font-size: 15px;
            font-family: 'Courier New';
            font-weight: 600;
            background: transparent;
            padding: 8px;
            letter-spacing: 1px;
        """)
        self.val_pwd.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.val_pwd.setWordWrap(True)
        pwd_layout.addWidget(self.val_pwd, 1)

        # Toggle button
        self.toggle_btn = QPushButton("👁️")
        self.toggle_btn.setFixedSize(40, 40)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(True)
        self.toggle_btn.setToolTip("Masquer/Afficher")
        self.toggle_btn.setCursor(Qt.PointingHandCursor)
        self.toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.1);
                border: none;
                border-radius: 10px;
                font-size: 18px;
            }}
            QPushButton:checked {{
                background: rgba(59, 130, 246, 0.3);
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.4);
            }}
        """)
        self.toggle_btn.toggled.connect(self._set_visibility)
        pwd_layout.addWidget(self.toggle_btn)

        # Copy button
        copy_btn = QPushButton("📋")
        copy_btn.setFixedSize(40, 40)
        copy_btn.setToolTip("Copier le mot de passe")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(Styles.get_button_style(primary=False))
        copy_btn.clicked.connect(self.copy_password)
        pwd_layout.addWidget(copy_btn)

        password_section.addWidget(lbl_pwd)
        password_section.addWidget(pwd_container)
        info.addLayout(password_section)

        layout.addLayout(info)

        # Metadata
        meta = QVBoxLayout()
        meta.setSpacing(10)

        if 'category' in self.password_data:
            category_icons = {
                'personal': '👤 Personnel',
                'work': '💼 Travail',
                'finance': '💳 Finance',
                'game': '🎮 Jeux',
                'study': '📚 Étude'
            }
            cat_text = category_icons.get(self.password_data['category'],
                                          f"📂 {self.password_data['category'].capitalize()}")
            cat_label = QLabel(f"Catégorie: {cat_text}")
            cat_label.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_SECONDARY) + "; background: transparent;")
            meta.addWidget(cat_label)

        if 'strength' in self.password_data:
            strength = self.password_data['strength']
            strength_colors = {
                'strong': (Styles.STRONG_COLOR, '✅ Fort'),
                'medium': (Styles.MEDIUM_COLOR, '⚠️ Moyen'),
                'weak': (Styles.WEAK_COLOR, '❌ Faible')
            }
            color, text = strength_colors.get(strength, (Styles.TEXT_SECONDARY, strength.capitalize()))
            strength_label = QLabel(f"Force: {text}")
            strength_label.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: bold; background: transparent;")
            meta.addWidget(strength_label)

        if 'last_updated' in self.password_data:
            date_label = QLabel(f"🕒 Dernière modification: {self.password_data['last_updated']}")
            date_label.setStyleSheet(Styles.get_label_style(12, Styles.TEXT_MUTED) + "; background: transparent;")
            meta.addWidget(date_label)

        layout.addLayout(meta)
        layout.addStretch()

        # Close button
        close_btn = AnimatedButton("Fermer")
        close_btn.setStyleSheet(Styles.get_button_style(True))
        close_btn.setMinimumHeight(50)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _set_visibility(self, visible: bool):
        """Show decrypted password when visible True, else show bullets"""
        self._is_visible = visible
        if visible:
            self.val_pwd.setText(self._decrypted_pwd)
        else:
            txt = self._decrypted_pwd or ""
            bullets = '•' * min(len(txt), 20) if txt else "•" * 8
            self.val_pwd.setText(bullets)

    def copy_password(self):
        """Copy decrypted password to clipboard"""
        pwd_to_copy = self._decrypted_pwd
        if not pwd_to_copy:
            pwd_to_copy = self.password_data.get('encrypted_password', '') or self.password_data.get('password', '')
        if pwd_to_copy:
            QApplication.clipboard().setText(pwd_to_copy)
            QMessageBox.information(self, "Copié", "📋 Mot de passe copié dans le presse-papier!")


# ==================== EDIT PASSWORD MODAL ====================

class EditPasswordModal(QDialog):
    password_updated = pyqtSignal(int, str, str)

    def __init__(self, password_data, parent=None):
        super().__init__(parent)
        self.password_data = password_data
        self.setWindowTitle(f"Modifier — {password_data.get('site_name', 'Compte')}")
        self.setFixedSize(500, 420)
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1); border-radius: 25px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        title = QLabel("✏️ Modifier le mot de passe")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(Styles.get_label_style(20))
        layout.addWidget(title)

        lbl_old = QLabel("Ancien mot de passe")
        lbl_old.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_SECONDARY) + "; background: transparent;")
        self.in_old = QLineEdit()
        self.in_old.setEchoMode(QLineEdit.Password)
        style_line_edit(self.in_old)
        layout.addWidget(lbl_old)
        layout.addWidget(self.in_old)

        lbl_new = QLabel("Nouveau mot de passe")
        lbl_new.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_SECONDARY) + "; background: transparent;")
        self.in_new = QLineEdit()
        self.in_new.setEchoMode(QLineEdit.Password)
        style_line_edit(self.in_new)
        layout.addWidget(lbl_new)
        layout.addWidget(self.in_new)

        lbl_rep = QLabel("Répéter le nouveau mot de passe")
        lbl_rep.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_SECONDARY) + "; background: transparent;")
        self.in_rep = QLineEdit()
        self.in_rep.setEchoMode(QLineEdit.Password)
        style_line_edit(self.in_rep)
        layout.addWidget(lbl_rep)
        layout.addWidget(self.in_rep)

        self.strength_widget = PasswordStrengthWidget()
        self.in_new.textChanged.connect(self.strength_widget.update_strength)
        layout.addWidget(self.strength_widget)
        layout.addSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(12)
        cancel = AnimatedButton("Annuler")
        cancel.setMinimumHeight(48)
        cancel.setStyleSheet(Styles.get_button_style(False))
        save = AnimatedButton("💾 Mettre à jour")
        save.setMinimumHeight(48)
        save.setStyleSheet(Styles.get_button_style(True))
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.on_save)
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

    def on_save(self):
        old, new, rep = self.in_old.text(), self.in_new.text(), self.in_rep.text()
        if not old or not new or not rep:
            QMessageBox.warning(self, "Champs manquants", "Veuillez remplir tous les champs.")
            return
        current = self.password_data.get('encrypted_password', '') or self.password_data.get('password', '')
        if old != current:
            QMessageBox.warning(self, "Ancien mot de passe", "L'ancien mot de passe est incorrect.")
            return
        if new != rep:
            QMessageBox.warning(self, "Confirmation", "La confirmation ne correspond pas.")
            return
        if PasswordStrengthChecker.check_strength(new)[0] == "weak":
            if QMessageBox.question(self, "Mot de passe faible",
                                    "Le nouveau mot de passe est faible. Continuer quand même ?",
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                return
        last_mod = datetime.now().strftime("Maj. %d/%m/%Y %H:%M")
        self.password_updated.emit(self.password_data['id'], new, last_mod)
        QMessageBox.information(self, "Succès", "Mot de passe mis à jour.")
        self.accept()


# ==================== 2FA MODAL ====================

class TwoFactorModal(QDialog):
    code_verified = pyqtSignal()

    def __init__(self, email, sent_code, parent=None, method: str = "email"):
        super().__init__(parent)
        self.email = email
        self.sent_code = sent_code
        self.method = (method or "email").lower()
        self.setWindowTitle("Vérification en deux étapes")
        self.setFixedSize(400, 250)
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {Styles.PRIMARY_BG};
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 20px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        title = QLabel("📱 Code de vérification")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(Styles.get_label_style(20))
        layout.addWidget(title)

        if self.method == "totp":
            info_text = "Entrez le code à 6 chiffres de votre application d'authentification"
            placeholder = "Code de l'app d'authentification"
        else:
            info_text = f"Un code à 6 chiffres a été envoyé à {self.email}"
            placeholder = "Entrez le code reçu par email"
        info = QLabel(info_text)
        info.setStyleSheet(Styles.get_label_style(13, Styles.TEXT_SECONDARY) + "; background: transparent;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText(placeholder)
        self.code_input.setMaxLength(6)
        self.code_input.setAlignment(Qt.AlignCenter)
        style_line_edit(self.code_input)
        layout.addWidget(self.code_input)

        verify_btn = AnimatedButton("Vérifier")
        verify_btn.setStyleSheet(Styles.get_button_style(primary=True))
        verify_btn.setMinimumHeight(48)
        verify_btn.clicked.connect(self.on_verify_clicked)
        layout.addWidget(verify_btn)

    def on_verify_clicked(self):
        """When verify button is clicked, emit signal to parent"""
        code = self.code_input.text().strip()
        if not code:
            QMessageBox.warning(self, "Code manquant", "Veuillez entrer le code reçu")
            return
        if len(code) != 6:
            QMessageBox.warning(self, "Code invalide", "Le code doit contenir 6 chiffres")
            return

        self.code_verified.emit()


# ==================== FORGOT PASSWORD DIALOG ====================

class ForgotPasswordDialog(QDialog):
    """Multi-step forgot password: email -> code -> new password"""

    COOLDOWN = 60

    def __init__(self, auth_mgr, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mot de passe oublié")
        self.setModal(True)
        self.setFixedSize(520, 600)

        self.auth = auth_mgr
        self.remaining = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)

        self.current_step = 1
        self.email_for_reset = None

        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1); 
                border-radius: 25px;
            }}
        """)

        v = QVBoxLayout(self)
        v.setContentsMargins(40, 40, 40, 40)
        v.setSpacing(20)

        # Header
        header = QVBoxLayout()
        header.setAlignment(Qt.AlignCenter)
        header.setSpacing(10)

        icon = QLabel("🔐")
        icon.setStyleSheet("font-size:46px; background: transparent;")

        self.title_label = QLabel("Étape 1: Adresse e-mail")
        self.title_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.title_label.setStyleSheet(Styles.get_label_style(20))

        header.addWidget(icon)
        header.addWidget(self.title_label)
        v.addLayout(header)

        # Step 1: Email
        self.step1_widget = QFrame()
        self.step1_widget.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        s1_layout = QVBoxLayout(self.step1_widget)
        s1_layout.setSpacing(12)
        s1_layout.setContentsMargins(16, 14, 16, 14)

        lbl_email = QLabel("📧 Adresse e-mail")
        lbl_email.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; background: transparent;")

        self.email = QLineEdit()
        self.email.setMinimumHeight(48)
        self.email.setPlaceholderText("votre@email.com")
        self.email.setStyleSheet(Styles.get_input_style())

        self.btn_send_code = AnimatedButton("📨 Envoyer le code")
        self.btn_send_code.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.BLUE_SECONDARY});
                color: white;
                border: none;
                border-radius: 16px;
                padding: 10px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_SECONDARY}, stop:1 {Styles.BLUE_PRIMARY});
            }}
        """)
        self.btn_send_code.setMinimumHeight(48)
        self.btn_send_code.setCursor(Qt.PointingHandCursor)
        self.btn_send_code.clicked.connect(self._send_code)

        s1_layout.addWidget(lbl_email)
        s1_layout.addWidget(self.email)
        s1_layout.addSpacing(10)
        s1_layout.addWidget(self.btn_send_code)

        v.addWidget(self.step1_widget)

        # Step 2: Code verification
        self.step2_widget = QFrame()
        self.step2_widget.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        self.step2_widget.setVisible(False)
        s2_layout = QVBoxLayout(self.step2_widget)
        s2_layout.setSpacing(12)
        s2_layout.setContentsMargins(16, 14, 16, 14)

        lbl_code = QLabel("🔑 Code de vérification")
        lbl_code.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; background: transparent;")

        self.code = QLineEdit()
        self.code.setMinimumHeight(48)
        self.code.setPlaceholderText("000000")
        self.code.setMaxLength(6)
        self.code.setAlignment(Qt.AlignCenter)
        self.code.setFont(QFont("Courier New", 18, QFont.Bold))
        self.code.setStyleSheet(Styles.get_input_style())

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: rgba(255,255,255,0.60); font-size: 12px; background: transparent;")
        self.status_label.setAlignment(Qt.AlignCenter)

        self.btn_verify_code = AnimatedButton("✅ Vérifier le code")
        self.btn_verify_code.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.BLUE_SECONDARY});
                color: white;
                border: none;
                border-radius: 16px;
                padding: 10px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_SECONDARY}, stop:1 {Styles.BLUE_PRIMARY});
            }}
        """)
        self.btn_verify_code.setMinimumHeight(48)
        self.btn_verify_code.setCursor(Qt.PointingHandCursor)
        self.btn_verify_code.clicked.connect(self._verify_code)

        s2_layout.addWidget(lbl_code)
        s2_layout.addWidget(self.code)
        s2_layout.addWidget(self.status_label)
        s2_layout.addSpacing(10)
        s2_layout.addWidget(self.btn_verify_code)

        v.addWidget(self.step2_widget)

        # Step 3: New password
        self.step3_widget = QFrame()
        self.step3_widget.setStyleSheet("""
            QFrame {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 14px;
            }
        """)
        self.step3_widget.setVisible(False)
        s3_layout = QVBoxLayout(self.step3_widget)
        s3_layout.setSpacing(12)
        s3_layout.setContentsMargins(16, 14, 16, 14)

        lbl_new1 = QLabel("🔒 Nouveau mot de passe")
        lbl_new1.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; background: transparent;")

        self.new1 = QLineEdit()
        self.new1.setMinimumHeight(48)
        self.new1.setPlaceholderText("Créez un mot de passe fort")
        self.new1.setEchoMode(QLineEdit.Password)
        self.new1.setStyleSheet(Styles.get_input_style())

        lbl_new2 = QLabel("✅ Confirmer le mot de passe")
        lbl_new2.setStyleSheet(f"color: {Styles.TEXT_SECONDARY}; font-size: 13px; background: transparent;")

        self.new2 = QLineEdit()
        self.new2.setMinimumHeight(48)
        self.new2.setPlaceholderText("Confirmez votre mot de passe")
        self.new2.setEchoMode(QLineEdit.Password)
        self.new2.setStyleSheet(Styles.get_input_style())

        self.btn_reset_password = AnimatedButton("💾 Réinitialiser le mot de passe")
        self.btn_reset_password.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.BLUE_SECONDARY});
                color: white;
                border: none;
                border-radius: 16px;
                padding: 10px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_SECONDARY}, stop:1 {Styles.BLUE_PRIMARY});
            }}
        """)
        self.btn_reset_password.setMinimumHeight(48)
        self.btn_reset_password.setCursor(Qt.PointingHandCursor)
        self.btn_reset_password.clicked.connect(self._reset_password)

        s3_layout.addWidget(lbl_new1)
        s3_layout.addWidget(self.new1)
        s3_layout.addWidget(lbl_new2)
        s3_layout.addWidget(self.new2)
        s3_layout.addSpacing(10)
        s3_layout.addWidget(self.btn_reset_password)

        v.addWidget(self.step3_widget)

        v.addStretch()

        # Close button
        self.btn_close = AnimatedButton("Fermer")
        self.btn_close.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,0.06);
                color: {Styles.TEXT_PRIMARY};
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 16px;
                padding: 10px 18px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.10);
            }}
        """)
        self.btn_close.setMinimumHeight(46)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.reject)
        v.addWidget(self.btn_close)

    def _send_code(self):
        email = self.email.text().strip()
        if not email:
            QMessageBox.warning(self, "Email manquant", "Veuillez saisir votre e-mail.")
            return

        if '@' not in email or '.' not in email:
            QMessageBox.warning(self, "Email invalide", "Veuillez saisir une adresse e-mail valide.")
            return

        try:
            ok = self.auth.send_reset_code(email)
            if ok:
                self.email_for_reset = email
                QMessageBox.information(self, "Code envoyé",
                                        f"✅ Un code de vérification a été envoyé à:\n{email}\n\n"
                                        "Vérifiez votre boîte mail (et les spams).")
                self._go_to_step(2)
                self._start_cooldown()
            else:
                QMessageBox.warning(self, "Email introuvable",
                                    "Aucun compte trouvé avec cet email.\n\n"
                                    "Vérifiez l'orthographe ou créez un nouveau compte.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'envoyer le code:\n{str(e)}")

    def _verify_code(self):
        code = self.code.text().strip()
        if not code or len(code) != 6:
            QMessageBox.warning(self, "Code invalide", "Veuillez saisir un code à 6 chiffres.")
            return

        try:
            if self.auth.verify_reset_code(self.email_for_reset, code):
                QMessageBox.information(self, "Code vérifié", "✅ Code correct! Créez votre nouveau mot de passe.")
                self._go_to_step(3)
            else:
                QMessageBox.warning(self, "Code invalide",
                                    "Le code saisi est invalide ou a expiré.\n\n"
                                    "Demandez un nouveau code.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur de vérification:\n{str(e)}")

    def _reset_password(self):
        n1 = self.new1.text()
        n2 = self.new2.text()
        code = self.code.text().strip()

        if not n1 or not n2:
            QMessageBox.warning(self, "Champs vides", "Veuillez remplir tous les champs.")
            return

        if n1 != n2:
            QMessageBox.warning(self, "Erreur", "Les mots de passe ne correspondent pas.")
            return

        if len(n1) < 8:
            QMessageBox.warning(self, "Mot de passe trop court",
                                "Le mot de passe doit contenir au moins 8 caractères.")
            return

        try:
            ok = self.auth.update_password_with_code(self.email_for_reset, code, n1)
            if ok:
                QMessageBox.information(
                    self,
                    "Succès",
                    "🎉 Votre mot de passe a été réinitialisé avec succès!\n\n"
                    "Vous pouvez maintenant vous connecter avec votre nouveau mot de passe."
                )
                self.accept()
            else:
                QMessageBox.warning(self, "Erreur",
                                    "Une erreur est survenue lors de la réinitialisation.\n\n"
                                    "Le code a peut-être expiré. Recommencez le processus.")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la réinitialisation:\n{str(e)}")

    def _go_to_step(self, step):
        self.current_step = step

        self.step1_widget.setVisible(False)
        self.step2_widget.setVisible(False)
        self.step3_widget.setVisible(False)

        if step == 1:
            self.title_label.setText("Étape 1: Adresse e-mail")
            self.step1_widget.setVisible(True)
        elif step == 2:
            self.title_label.setText("Étape 2: Vérification du code")
            self.step2_widget.setVisible(True)
            self.code.setFocus()
        elif step == 3:
            self.title_label.setText("Étape 3: Nouveau mot de passe")
            self.step3_widget.setVisible(True)
            self.new1.setFocus()

    def _tick(self):
        self.remaining -= 1
        if self.remaining <= 0:
            self.timer.stop()
            self.btn_send_code.setEnabled(True)
            self.status_label.setText("")
        else:
            self.status_label.setText(f"⏱️ Renvoyer le code dans {self.remaining}s")

    def _start_cooldown(self):
        self.remaining = self.COOLDOWN
        self.btn_send_code.setEnabled(False)
        self.timer.start(1000)


# Also add this AnimatedButton class if it doesn't exist in your modals.py:
class AnimatedButton(QPushButton):
    """Button with hover animation"""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)


# ==================== EDIT PROFILE MODAL (FIXED) ====================

class EditProfileModal(QDialog):
    profile_updated = pyqtSignal(dict)

    def __init__(self, user_data, auth_manager, parent=None):
        super().__init__(parent)
        self.user_data = user_data or {}
        self.auth = auth_manager
        self.api_client = APIClient("http://127.0.0.1:5000")
        self.setWindowTitle("Modifier le profil")
        self.setFixedSize(580, 740)
        self.setModal(True)
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #07111f,
                    stop:0.5 #0b1a2f,
                    stop:1 #122744
                );
                border: 1px solid rgba(148, 163, 184, 0.28);
                border-radius: 22px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
            QPushButton {{
                border-radius: 14px;
                padding: 8px 14px;
            }}
            QFrame#profileHeader {{
                background: rgba(15, 23, 42, 0.58);
                border: 1px solid rgba(96, 165, 250, 0.32);
                border-radius: 16px;
            }}
            QFrame#profileCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30, 41, 59, 0.92),
                    stop:1 rgba(51, 65, 85, 0.90)
                );
                border: 1px solid rgba(148, 163, 184, 0.24);
                border-radius: 16px;
            }}
            QLineEdit {{
                background: rgba(15, 23, 42, 0.76);
                border: 1px solid rgba(96, 165, 250, 0.34);
                border-radius: 12px;
                padding: 10px 12px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(96, 165, 250, 0.78);
                background: rgba(15, 23, 42, 0.95);
            }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)

        profile_header = QFrame()
        profile_header.setObjectName("profileHeader")
        profile_header_l = QVBoxLayout(profile_header)
        profile_header_l.setContentsMargins(14, 12, 14, 12)
        profile_header_l.setSpacing(4)
        title = QLabel("Profil & securite")
        title.setStyleSheet("color:#f8fafc; font-size:20px; font-weight:700;")
        subtitle = QLabel("Mettez a jour votre identite, mot de passe et MFA.")
        subtitle.setStyleSheet("color:#a5b4fc; font-size:12px;")
        profile_header_l.addWidget(title)
        profile_header_l.addWidget(subtitle)
        root.addWidget(profile_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(12)

        info_card = QFrame()
        info_card.setObjectName("profileCard")
        info_l = QVBoxLayout(info_card)
        info_l.setContentsMargins(14, 12, 14, 12)
        info_l.setSpacing(10)
        info_title = QLabel("Informations du compte")
        info_title.setStyleSheet("color:#f8fafc; font-size:14px; font-weight:700;")
        info_l.addWidget(info_title)

        def labeled_input(target_layout, label, placeholder, value="", is_pwd=False):
            lab = QLabel(label)
            lab.setStyleSheet("color:#cbd5e1; font-size:12px;")
            target_layout.addWidget(lab)
            inp = QLineEdit()
            inp.setPlaceholderText(placeholder)
            inp.setText(value or "")
            if is_pwd:
                inp.setEchoMode(QLineEdit.Password)
            inp.setMinimumHeight(44)
            inp.setFont(QFont("Segoe UI", 11))
            target_layout.addWidget(inp)
            return inp

        self.name_input = labeled_input(info_l, "Nom complet", "Votre nom", self.user_data.get('username') or self.user_data.get('name', ''))
        self.email_input = labeled_input(info_l, "Email", "email", self.user_data.get('email', ''))
        self.current_pwd_input = labeled_input(info_l, "Mot de passe actuel", "Mot de passe actuel", "", True)
        self.new_pwd_input = labeled_input(info_l, "Nouveau mot de passe", "Optionnel", "", True)
        self.confirm_pwd_input = labeled_input(info_l, "Confirmer", "Confirmer le mot de passe", "", True)
        content_layout.addWidget(info_card)

        # MFA card
        enabled = bool(self.user_data.get('mfa_enabled'))
        if hasattr(self.auth, "is_mfa_enabled"):
            try:
                enabled = self.auth.is_mfa_enabled(self.user_data.get("email", ""))
            except Exception:
                pass

        mfa_card = QFrame()
        mfa_card.setObjectName("profileCard")
        mfa_layout = QVBoxLayout(mfa_card)
        mfa_layout.setContentsMargins(14, 12, 14, 12)
        mfa_layout.setSpacing(10)

        header = QHBoxLayout()
        sec = QLabel("Securite MFA")
        sec.setStyleSheet("color:#93c5fd; font-size:14px; font-weight:700;")
        header.addWidget(sec)
        header.addStretch()
        self.mfa_status = QLabel("MFA active" if enabled else "MFA desactivee")
        self.mfa_status.setStyleSheet(
            "color:#e2e8f0; font-size:11px; padding:4px 10px; font-weight:600;"
            "background: rgba(59,130,246,0.15); border:1px solid rgba(96,165,250,0.35); border-radius: 10px;"
        )
        header.addWidget(self.mfa_status)
        mfa_layout.addLayout(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        btn_enable = QPushButton("Activer MFA")
        btn_enable.setMinimumHeight(38)
        btn_enable.setStyleSheet(
            Styles.get_button_style(primary=True)
            + "border-radius: 16px; padding: 8px 14px; font-weight: 600;"
        )
        btn_enable.clicked.connect(self._enable_mfa)

        btn_disable = QPushButton("Desactiver MFA")
        btn_disable.setMinimumHeight(38)
        btn_disable.setStyleSheet(
            Styles.get_button_style(primary=False)
            + "border-radius: 16px; padding: 8px 14px;"
        )
        btn_disable.clicked.connect(self._disable_mfa)

        btn_codes = QPushButton("Voir codes")
        btn_codes.setMinimumHeight(34)
        btn_codes.setStyleSheet(
            Styles.get_button_style(primary=False)
            + "border-radius: 14px; padding: 6px 12px;"
        )
        btn_codes.clicked.connect(self._show_recovery_codes)

        btn_gen = QPushButton("Regenerer codes")
        btn_gen.setMinimumHeight(34)
        btn_gen.setStyleSheet(
            Styles.get_button_style(primary=False)
            + "border-radius: 14px; padding: 6px 12px;"
        )
        btn_gen.clicked.connect(self._generate_recovery_codes)

        grid.addWidget(btn_enable, 0, 0)
        grid.addWidget(btn_disable, 0, 1)
        grid.addWidget(btn_codes, 1, 0)
        grid.addWidget(btn_gen, 1, 1)
        mfa_layout.addLayout(grid)

        btn_logout_all = QPushButton("Deconnecter tous les appareils")
        btn_logout_all.setMinimumHeight(38)
        btn_logout_all.setStyleSheet("""
            QPushButton {
                background: rgba(239,68,68,0.12);
                border: 1px solid rgba(239,68,68,0.45);
                color: #fecaca;
                border-radius: 14px;
                padding: 8px 14px;
            }
            QPushButton:hover { background: rgba(239,68,68,0.2); }
        """)
        btn_logout_all.clicked.connect(self._logout_all_devices)
        mfa_layout.addWidget(btn_logout_all)

        content_layout.addWidget(mfa_card)

        self._mfa_available = all(hasattr(self.auth, m) for m in ("enable_totp", "verify_totp", "disable_totp"))
        if not self._mfa_available:
            btn_enable.setToolTip("Fonction MFA indisponible")
            btn_disable.setToolTip("Fonction MFA indisponible")
            btn_codes.setToolTip("Fonction MFA indisponible")
            btn_gen.setToolTip("Fonction MFA indisponible")

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        btn = QPushButton("Enregistrer")
        btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #eff6ff;
                border: 1px solid rgba(147, 197, 253, 0.55);
                border-radius: 14px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        btn.setMinimumHeight(44)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self.on_save)
        root.addWidget(btn)

    def on_save(self):
        name = self.name_input.text().strip()
        email = self.email_input.text().strip().lower()
        current_pwd = self.current_pwd_input.text()
        new_pwd = self.new_pwd_input.text()
        confirm_pwd = self.confirm_pwd_input.text()

        if not name or not email:
            QMessageBox.warning(self, "Erreur", "Nom et email requis")
            return
        if not current_pwd:
            QMessageBox.warning(self, "Erreur", "Mot de passe actuel requis")
            return

        user = self.auth._user_by_email(self.user_data.get('email'))
        if not user:
            QMessageBox.warning(self, "Erreur", "Utilisateur introuvable")
            return
        if not verify_password(user.get('password_hash'), user.get('salt'), current_pwd):
            QMessageBox.warning(self, "Erreur", "Mot de passe actuel incorrect")
            return

        if email != self.user_data.get('email'):
            if self.auth.is_email_taken(email, exclude_user_id=user.get('id')):
                QMessageBox.warning(self, "Erreur", "Email deja utilise")
                return

        if new_pwd or confirm_pwd:
            if new_pwd != confirm_pwd:
                QMessageBox.warning(self, "Erreur", "Les mots de passe ne correspondent pas")
                return
            if len(new_pwd) < 8:
                QMessageBox.warning(self, "Erreur", "Mot de passe trop court")
                return

        ok = self.auth.update_profile(user.get('id'), username=name, email=email)
        if not ok:
            QMessageBox.warning(self, "Erreur", "Mise a jour impossible")
            return
        if new_pwd:
            self.auth.update_master_password(email, new_pwd)

        try:
            log_action(user.get('id'), 'user.profile_updated', 'profile updated')
        except Exception:
            pass

        updated = {
            'id': user.get('id'),
            'username': name,
            'email': email,
            'name': name,
            'initials': (name[:2] or "US").upper(),
            'mfa_enabled': self.user_data.get('mfa_enabled', False),
        }
        self.profile_updated.emit(updated)
        QMessageBox.information(self, "Succes", "Profil mis a jour")
        self.accept()

    def _enable_mfa(self):
        if not self._mfa_available:
            QMessageBox.information(self, "MFA", "Fonction TOTP indisponible.")
            return
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "MFA", "Email requis.")
            return
        res = self.auth.enable_totp(email)
        if res.get("error"):
            QMessageBox.warning(self, "MFA", res.get("error"))
            return
        secret = res.get("secret")
        uri = res.get("uri")
        if not secret:
            QMessageBox.warning(self, "MFA", "Secret TOTP introuvable.")
            return
        self._show_totp_secret(secret, uri)
        code = self._prompt_mfa_code("TOTP", "Code ? 6 chiffres")
        if not code:
            return
        if self.auth.verify_totp(email, code):
            self.user_data['mfa_enabled'] = True
            self.mfa_status.setText("MFA: active")
            QMessageBox.information(self, "MFA", "TOTP activ?")
        else:
            QMessageBox.warning(self, "MFA", "Code invalide ou expir?")

    def _show_totp_secret(self, secret: str, uri: str | None = None):
        dlg = QDialog(self)
        dlg.setWindowTitle("TOTP")
        dlg.setFixedSize(420, 420)
        dlg.setModal(True)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 22px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        info = QLabel("Ajoutez ce compte dans votre application d'authentification.")
        info.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        lay.addWidget(info)

        if uri and _QR_AVAILABLE:
            try:
                qr = qrcode.QRCode(border=2, box_size=6)
                qr.add_data(uri)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                qimage = ImageQt.ImageQt(img)
                pix = QPixmap.fromImage(qimage)
                qr_label = QLabel()
                qr_label.setAlignment(Qt.AlignCenter)
                qr_label.setPixmap(pix)
                lay.addWidget(qr_label)
            except Exception:
                pass

        secret_box = QLineEdit()
        secret_box.setReadOnly(True)
        secret_box.setText(secret)
        secret_box.setStyleSheet(Styles.get_input_style() + "border-radius: 14px;")
        lay.addWidget(secret_box)

        row = QHBoxLayout()
        btn_copy = QPushButton("Copier")
        btn_copy.setStyleSheet(Styles.get_button_style(primary=False) + "border-radius: 16px;")
        btn_copy.setMinimumHeight(36)
        btn_next = QPushButton("Continuer")
        btn_next.setStyleSheet(Styles.get_button_style(primary=True) + "border-radius: 16px;")
        btn_next.setMinimumHeight(36)
        row.addWidget(btn_copy)
        row.addWidget(btn_next)
        lay.addLayout(row)

        def _copy():
            QApplication.clipboard().setText(secret)
            QMessageBox.information(self, "TOTP", "Secret copie dans le presse-papiers")

        btn_copy.clicked.connect(_copy)
        btn_next.clicked.connect(dlg.accept)
        dlg.exec_()

    def _disable_mfa(self):
        if not self._mfa_available:
            QMessageBox.information(self, "MFA", "Fonction TOTP indisponible.")
            return
        email = self.email_input.text().strip()
        if not email:
            QMessageBox.warning(self, "MFA", "Email requis.")
            return
        if self.auth.disable_totp(email):
            self.user_data['mfa_enabled'] = False
            self.mfa_status.setText("MFA: desactive")
            QMessageBox.information(self, "MFA", "TOTP d?sactiv?")
        else:
            QMessageBox.warning(self, "MFA", "Impossible de d?sactiver TOTP")

    def _show_recovery_codes(self):
        if not self._mfa_available:
            QMessageBox.information(self, "Codes", "Fonction MFA indisponible.")
            return
        user_id = self.user_data.get("id")
        if not user_id:
            QMessageBox.warning(self, "Codes", "Utilisateur introuvable")
            return
        try:
            codes = self.auth.list_recovery_codes(int(user_id))
        except Exception:
            QMessageBox.warning(self, "Codes", "Impossible de charger les codes")
            return
        if not codes:
            QMessageBox.information(
                self,
                "Codes",
                "Aucun code disponible. Regenerer pour afficher de nouveaux codes.",
            )
            return
        self._display_recovery_codes(
            codes,
            title="Codes de recuperation",
            subtitle="Conservez ces codes en lieu sur.",
        )

    def _generate_recovery_codes(self):
        if not self._mfa_available:
            QMessageBox.information(self, "Codes", "Fonction MFA indisponible.")
            return
        user_id = self.user_data.get("id")
        if not user_id:
            QMessageBox.warning(self, "Codes", "Utilisateur introuvable")
            return
        confirm = QMessageBox.question(
            self,
            "Codes",
            "Regenerer les codes invalidera les anciens. Continuer ?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            codes = self.auth.generate_recovery_codes(int(user_id))
        except Exception:
            QMessageBox.warning(self, "Codes", "Generation impossible")
            return
        if not codes:
            QMessageBox.warning(self, "Codes", "Generation impossible")
            return
        self._display_recovery_codes(
            codes,
            title="Nouveaux codes",
            subtitle="Ces codes ne seront affiches qu'une seule fois.",
        )

    def _display_recovery_codes(self, codes: list[str], title: str, subtitle: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(420, 360)
        dlg.setModal(True)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 18px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        info = QLabel(subtitle)
        info.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        lay.addWidget(info)

        codes_box = QTextEdit()
        codes_box.setReadOnly(True)
        codes_box.setStyleSheet(Styles.get_input_style())
        codes_box.setText("\n".join(codes))
        lay.addWidget(codes_box, 1)

        row = QHBoxLayout()
        btn_copy = QPushButton("Copier")
        btn_copy.setStyleSheet(Styles.get_button_style(primary=False))
        btn_copy.setMinimumHeight(36)
        btn_close = QPushButton("Fermer")
        btn_close.setStyleSheet(Styles.get_button_style(primary=True))
        btn_close.setMinimumHeight(36)
        row.addWidget(btn_copy)
        row.addWidget(btn_close)
        lay.addLayout(row)

        def _copy():
            QApplication.clipboard().setText("\n".join(codes))
            QMessageBox.information(self, "Codes", "Codes copies dans le presse-papiers")

        btn_copy.clicked.connect(_copy)
        btn_close.clicked.connect(dlg.accept)
        dlg.exec_()

    def _prompt_mfa_code(self, title: str = "MFA", label: str = "Code 6 chiffres") -> str | None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(360, 210)
        dlg.setModal(True)
        dlg.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.PRIMARY_BG}, stop:1 {Styles.SECONDARY_BG});
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 18px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
        """)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)

        title = QLabel(label)
        title.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px;")
        lay.addWidget(title)

        code_input = QLineEdit()
        code_input.setPlaceholderText("000000")
        code_input.setMaxLength(6)
        code_input.setAlignment(Qt.AlignCenter)
        code_input.setStyleSheet(Styles.get_input_style())
        lay.addWidget(code_input)

        row = QHBoxLayout()
        btn_ok = QPushButton("Valider")
        btn_ok.setStyleSheet(Styles.get_button_style(primary=True) + "border-radius: 14px;")
        btn_ok.setMinimumHeight(38)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet(Styles.get_button_style(primary=False) + "border-radius: 14px;")
        btn_cancel.setMinimumHeight(38)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        lay.addLayout(row)

        res = {"code": None}
        def _accept():
            res["code"] = code_input.text().strip()
            dlg.accept()
        btn_ok.clicked.connect(_accept)
        btn_cancel.clicked.connect(dlg.reject)

        dlg.exec_()
        return res["code"]

    def _logout_all_devices(self):
        user_id = self.user_data.get("id")
        if not user_id:
            QMessageBox.warning(self, "Sessions", "Utilisateur introuvable")
            return
        ok, msg, sessions = self.api_client.get_sessions(int(user_id))
        if not ok:
            QMessageBox.warning(self, "Sessions", f"Impossible de charger les sessions: {msg}")
            return
        revoked = 0
        for s in sessions:
            sid = s.get("id")
            if not sid:
                continue
            ok2, _ = self.api_client.revoke_session(int(sid))
            if ok2:
                revoked += 1
        QMessageBox.information(self, "Sessions", f"Sessions révoquées: {revoked}")

class DeviceSessionsModal(QDialog):
    def __init__(self, sessions: list[dict], on_revoke_session, on_revoke_device, parent=None):
        super().__init__(parent)
        self.sessions = self._normalize_sessions(sessions or [])
        self.on_revoke_session = on_revoke_session
        self.on_revoke_device = on_revoke_device
        self.setWindowTitle("Appareils & sessions")
        self.setFixedSize(620, 560)
        self.setModal(True)
        self._build()

    @staticmethod
    def _normalize_sessions(sessions: list[dict]) -> list[dict]:
        normalized = []
        for raw in sessions:
            if not isinstance(raw, dict):
                continue
            device_name = (raw.get("device_name") or raw.get("device_info") or "").strip()
            session_id = raw.get("id")
            ip_address = (raw.get("ip_address") or "").strip()
            last_used = raw.get("last_used") or raw.get("created_at")
            status = (raw.get("status") or "").strip()

            if not device_name:
                device_name = "Appareil inconnu"
            if not status:
                status = "Actif" if session_id else "Historique"

            normalized.append(
                {
                    "device_name": device_name,
                    "ip_address": ip_address or "-",
                    "id": session_id,
                    "status": status,
                    "last_used": last_used,
                }
            )
        return normalized

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #07111f,
                    stop:0.5 #0b1a2f,
                    stop:1 #122744
                );
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 20px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea::viewport {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: rgba(255,255,255,0.03);
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(96, 165, 250, 0.40);
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QFrame#sessionRow {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30, 41, 59, 0.92),
                    stop:1 rgba(51, 65, 85, 0.92)
                );
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 16px;
            }}
            QFrame#headerCard {{
                background: rgba(15, 23, 42, 0.55);
                border: 1px solid rgba(96, 165, 250, 0.30);
                border-radius: 16px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(4)
        title = QLabel("Appareils connectes")
        title.setStyleSheet("color:#f8fafc; font-size:19px; font-weight:700;")
        subtitle = QLabel("Gerez les sessions actives et l'historique de connexion.")
        subtitle.setStyleSheet("color:#a5b4fc; font-size:12px;")
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        layout.addWidget(header)

        list_container = QWidget()
        list_container.setObjectName("devicesList")
        list_container.setStyleSheet("background: transparent;")
        list_container.setAttribute(Qt.WA_StyledBackground, True)
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(10)

        def _format_last_used(value):
            if not value:
                return "Inconnue"
            try:
                return datetime.fromisoformat(str(value)).strftime("%d/%m/%Y %H:%M")
            except Exception:
                return str(value)

        if not self.sessions:
            empty = QFrame()
            empty.setObjectName("sessionRow")
            empty_layout = QVBoxLayout(empty)
            empty_layout.setContentsMargins(16, 16, 16, 16)
            empty_layout.setSpacing(6)
            empty_title = QLabel("Aucun appareil detecte")
            empty_title.setStyleSheet("color:#e2e8f0; font-size:14px; font-weight:600;")
            empty_sub = QLabel("Les prochaines connexions apparaitront ici.")
            empty_sub.setStyleSheet("color:#94a3b8; font-size:12px;")
            empty_layout.addWidget(empty_title)
            empty_layout.addWidget(empty_sub)
            list_layout.addWidget(empty)
        else:
            for sess in self.sessions:
                row = QFrame()
                row.setObjectName("sessionRow")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(14, 12, 14, 12)
                row_layout.setSpacing(12)

                device = sess.get("device_name") or sess.get("device_info") or "Inconnu"
                ip = sess.get("ip_address") or "-"
                status = sess.get("status") or ("Actif" if sess.get("id") else "Historique")
                last_used = sess.get("last_used") or sess.get("created_at")

                left = QVBoxLayout()
                left.setSpacing(4)
                device_lbl = QLabel(device)
                device_lbl.setStyleSheet("color:#f8fafc; font-size:13px; font-weight:700;")
                left.addWidget(device_lbl)

                meta = QLabel(f"IP {ip}  -  Derniere activite: {_format_last_used(last_used)}")
                meta.setStyleSheet("color:#cbd5e1; font-size:11px;")
                left.addWidget(meta)

                left_wrap = QWidget()
                left_wrap.setStyleSheet("background: transparent;")
                left_wrap.setLayout(left)
                row_layout.addWidget(left_wrap, 1)

                status_lbl = QLabel(status)
                is_active = str(status).lower() == "actif"
                status_lbl.setStyleSheet(
                    "font-size:11px; padding:6px 10px; border-radius:12px; font-weight:600; "
                    + (
                        "color:#bbf7d0; background: rgba(22, 163, 74, 0.20); border: 1px solid rgba(22, 163, 74, 0.35);"
                        if is_active
                        else "color:#cbd5e1; background: rgba(148, 163, 184, 0.15); border: 1px solid rgba(148, 163, 184, 0.25);"
                    )
                )
                row_layout.addWidget(status_lbl)

                revoke_btn = QPushButton("Deconnecter")
                revoke_btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(239, 68, 68, 0.16);
                        color: #fecaca;
                        border: 1px solid rgba(248, 113, 113, 0.40);
                        border-radius: 12px;
                        padding: 8px 12px;
                        font-size: 12px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background: rgba(239, 68, 68, 0.25);
                        color: #fee2e2;
                    }
                    QPushButton:disabled {
                        color: rgba(255,255,255,0.45);
                        border-color: rgba(255,255,255,0.10);
                        background: rgba(255,255,255,0.05);
                    }
                """)
                revoke_btn.setMinimumHeight(34)
                revoke_btn.setCursor(Qt.PointingHandCursor)

                session_id = sess.get("id")
                device_name = sess.get("device_name") or sess.get("device_info")
                if session_id:
                    revoke_btn.clicked.connect(
                        lambda _, sid=session_id, w=row: self._revoke_session(sid, w)
                    )
                elif device_name:
                    revoke_btn.clicked.connect(
                        lambda _, dn=device_name, w=row: self._revoke_device(dn, w)
                    )
                else:
                    revoke_btn.setEnabled(False)

                row_layout.addWidget(revoke_btn)
                list_layout.addWidget(row)

        list_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(list_container)
        layout.addWidget(scroll, 1)

        close_btn = QPushButton("Fermer")
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2563eb,
                    stop:1 #3b82f6
                );
                color: #eff6ff;
                border: 1px solid rgba(147, 197, 253, 0.55);
                border-radius: 14px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1d4ed8,
                    stop:1 #2563eb
                );
            }
        """)
        close_btn.setMinimumHeight(42)
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _revoke_session(self, session_id: int, row_widget: QWidget):
        if not session_id:
            QMessageBox.information(self, "Sessions", "Aucune session a revoquer.")
            return
        ok = False
        try:
            ok = self.on_revoke_session(int(session_id))
        except Exception:
            ok = False
        if ok:
            row_widget.setParent(None)
            QMessageBox.information(self, "Sessions", "Session revoquee.")
        else:
            QMessageBox.warning(self, "Erreur", "Impossible de revoquer la session.")

    def _revoke_device(self, device_name: str, row_widget: QWidget):
        if not device_name:
            return
        ok = False
        try:
            ok = self.on_revoke_device(device_name)
        except Exception:
            ok = False
        if ok:
            row_widget.setParent(None)
            QMessageBox.information(self, "Appareils", "Appareil deconnecte.")
        else:
            QMessageBox.warning(self, "Erreur", "Impossible de deconnecter l'appareil.")

class AuditLogModal(QDialog):
    def __init__(self, user_id: int, auth_manager: AuthManager, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.auth = auth_manager
        self.setWindowTitle("Journal")
        self.setFixedSize(760, 560)
        self.setModal(True)
        self._build()

    def _build(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #07111f,
                    stop:0.5 #0b1a2f,
                    stop:1 #122744
                );
                border: 1px solid rgba(148,163,184,0.24);
                border-radius: 20px;
            }}
            QLabel {{ color: {Styles.TEXT_PRIMARY}; background: transparent; }}
            QScrollArea {{ background: transparent; border: none; }}
            QScrollArea::viewport {{ background: transparent; }}
            QFrame#journalHeader {{
                background: rgba(15, 23, 42, 0.58);
                border: 1px solid rgba(96, 165, 250, 0.32);
                border-radius: 16px;
            }}
            QFrame#journalCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(30, 41, 59, 0.92),
                    stop:1 rgba(51, 65, 85, 0.90)
                );
                border: 1px solid rgba(148, 163, 184, 0.24);
                border-radius: 14px;
            }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        header_card = QFrame()
        header_card.setObjectName("journalHeader")
        header = QVBoxLayout(header_card)
        header.setContentsMargins(14, 12, 14, 12)
        header.setSpacing(4)
        title = QLabel("Journal d'audit")
        title.setStyleSheet("color:#f8fafc; font-size:20px; font-weight:700;")
        subtitle = QLabel("Suivez les connexions, modifications et actions sensibles.")
        subtitle.setStyleSheet("color:#a5b4fc; font-size:12px;")
        header.addWidget(title)
        header.addWidget(subtitle)
        root.addWidget(header_card)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        filter_lbl = QLabel("Filtrer")
        filter_lbl.setStyleSheet("color:#cbd5e1; font-size:12px;")
        bar.addWidget(filter_lbl)

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["Tous", "Connexions", "Changements", "Exports", "Echecs"])
        self.filter_combo.setMinimumHeight(34)
        self.filter_combo.setStyleSheet("""
            QComboBox {
                background: rgba(15, 23, 42, 0.76);
                border: 1px solid rgba(96, 165, 250, 0.34);
                border-radius: 10px;
                color: #e2e8f0;
                padding: 6px 10px;
                min-width: 180px;
            }
            QComboBox:focus { border: 1px solid rgba(96, 165, 250, 0.78); }
            QComboBox::drop-down { width: 18px; border: none; }
            QComboBox QAbstractItemView {
                background: #0f1e36;
                color: #e6effb;
                selection-background-color: rgba(59,130,246,0.35);
                border: 1px solid rgba(255,255,255,0.1);
            }
        """)
        self.filter_combo.currentIndexChanged.connect(self._refresh)
        bar.addWidget(self.filter_combo)
        bar.addStretch()
        root.addLayout(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
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
            QScrollBar::handle:vertical:hover { background: rgba(59,130,246,0.85); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        self.list_container = QWidget()
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)
        self.scroll.setWidget(self.list_container)
        root.addWidget(self.scroll, 1)

        close_btn = QPushButton("Fermer")
        close_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2563eb, stop:1 #3b82f6);
                color: #eff6ff;
                border: 1px solid rgba(147, 197, 253, 0.55);
                border-radius: 14px;
                padding: 9px 14px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1d4ed8, stop:1 #2563eb);
            }
        """)
        close_btn.setMinimumHeight(40)
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)

        self._refresh()

    def _filter_key(self):
        return ["all", "login", "password", "vault", "failed"][self.filter_combo.currentIndex()]

    def _refresh(self):
        for i in reversed(range(self.list_layout.count())):
            w = self.list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        def _add_empty_card(message: str):
            card = QFrame()
            card.setObjectName("journalCard")
            l = QVBoxLayout(card)
            l.setContentsMargins(14, 12, 14, 12)
            info = QLabel(message)
            info.setStyleSheet("color:#94a3b8; font-size:12px;")
            l.addWidget(info)
            self.list_layout.addWidget(card)

        if not hasattr(self.auth, "list_audit_logs"):
            _add_empty_card("Journal indisponible.")
            return

        logs = self.auth.list_audit_logs(self.user_id, self._filter_key())
        if not logs:
            _add_empty_card("Aucun journal disponible pour ce filtre.")
            return

        icon_map = {
            "login": "LOG",
            "password": "PWD",
            "vault": "BOX",
            "failed": "ERR",
        }

        for row in logs:
            action = row.get("action", "-")
            when = row.get("created_at")
            ts = when.strftime("%d/%m/%Y %H:%M") if when else "-"
            details = row.get("details") or ""

            kind = "login"
            if "password" in action:
                kind = "password"
            elif "vault" in action or "export" in action:
                kind = "vault"
            elif "failed" in action or "error" in action:
                kind = "failed"

            card = QFrame()
            card.setObjectName("journalCard")
            row_l = QHBoxLayout(card)
            row_l.setContentsMargins(12, 10, 12, 10)
            row_l.setSpacing(12)

            icon = QLabel(icon_map.get(kind, "EVT"))
            icon.setStyleSheet("font-size:11px; font-weight:700; color:#dbeafe;")

            text_col = QVBoxLayout()
            title = QLabel(action.replace(":", " - "))
            title.setStyleSheet("font-weight:700; font-size:13px; color:#f8fafc;")
            details_txt = details if details else "Aucun detail"
            sub = QLabel(f"{ts}  -  {details_txt}")
            sub.setStyleSheet("color:#cbd5e1; font-size:11px;")
            sub.setWordWrap(True)
            text_col.addWidget(title)
            text_col.addWidget(sub)

            row_l.addWidget(icon)
            row_l.addLayout(text_col, 1)
            self.list_layout.addWidget(card)

