# -*- coding: utf-8 -*-
# src/gui/components/password_list.py

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QLineEdit, QMenu, QAction, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QClipboard
from PyQt5.QtWidgets import QApplication
import webbrowser


def hex_to_rgba_qt(hex_color: str, alpha: float) -> str:
    """Convert hex to rgba for Qt stylesheets"""
    hex_color = hex_color.strip()
    if hex_color.startswith('#'):
        hex_color = hex_color[1:]
    if len(hex_color) == 3:
        hex_color = ''.join([c * 2 for c in hex_color])
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


class PasswordCard(QFrame):
    """Modern password card with Auto-fill capabilities"""
    copy_clicked = pyqtSignal(dict)
    view_clicked = pyqtSignal(dict)
    edit_clicked = pyqtSignal(int)
    delete_clicked = pyqtSignal(int)
    restore_clicked = pyqtSignal(int)
    favorite_clicked = pyqtSignal(int)
    autofill_clicked = pyqtSignal(dict)
    
    request_2fa_for_copy = pyqtSignal(dict)
    request_2fa_for_view = pyqtSignal(dict)

    def __init__(self, password_data, parent=None):
        super().__init__(parent)
        self.password_data = password_data
        self._build()

    def _build(self):
        from src.gui.styles.styles import Styles

        self.setFixedWidth(650)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30, 48, 80, 0.85),
                    stop:1 rgba(20, 35, 60, 0.85)
                );
                border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.25)};
                border-radius: 20px;
                padding: 20px;
            }}
            QFrame:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(40, 60, 95, 0.9),
                    stop:1 rgba(25, 40, 70, 0.9)
                );
                border: 1px solid {Styles.BLUE_PRIMARY};
            }}
        """)

        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(0, 0, 0, 0)

        # ---------- Header ----------
        header = QHBoxLayout()
        header.setSpacing(12)

        # Icon
        icon_frame = QFrame()
        icon_frame.setFixedSize(50, 50)
        icon_frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.PURPLE});
                border-radius: 14px;
                border: none;
            }}
        """)
        il = QVBoxLayout(icon_frame)
        il.setContentsMargins(0, 0, 0, 0)
        icon = QLabel(self.password_data.get('site_icon', '🔒'))
        icon.setStyleSheet("font-size: 24px; background: transparent; color: white;")
        icon.setAlignment(Qt.AlignCenter)
        il.addWidget(icon)
        header.addWidget(icon_frame)

        # Site info
        info = QVBoxLayout()
        info.setSpacing(4)

        site = QLabel(self.password_data.get('site_name', 'Site'))
        site.setFont(QFont("Segoe UI", 14, QFont.Bold))
        site.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; background:transparent;")
        info.addWidget(site)

        user = QLabel(self.password_data.get('username', ''))
        user.setWordWrap(True)
        user.setStyleSheet(f"color:{Styles.TEXT_SECONDARY}; font-size:12px; background:transparent;")
        info.addWidget(user)

        # Show URL if available
        site_url = self.password_data.get('site_url', '')
        if site_url:
            url_label = QLabel(f"🔗 {site_url[:35]}..." if len(site_url) > 35 else f"🔗 {site_url}")
            url_label.setStyleSheet(f"color:{Styles.BLUE_SECONDARY}; font-size:10px; background:transparent;")
            info.addWidget(url_label)

        header.addLayout(info, 1)

        # Action buttons
        cat = self.password_data.get('category', 'personal')
        is_trash = cat == "trash"
        actions = QHBoxLayout()
        actions.setSpacing(6)

        # Auto-fill button (if URL exists)
        if site_url:
            autofill_btn = QPushButton("🚀")
            autofill_btn.setFixedSize(34, 34)
            autofill_btn.setCursor(Qt.PointingHandCursor)
            autofill_btn.setToolTip("Ouvrir et remplir automatiquement")
            autofill_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {hex_to_rgba_qt(Styles.STRONG_COLOR, 0.15)};
                    border: 1px solid {hex_to_rgba_qt(Styles.STRONG_COLOR, 0.30)};
                    border-radius: 10px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background: {hex_to_rgba_qt(Styles.STRONG_COLOR, 0.30)};
                    border: 1px solid {hex_to_rgba_qt(Styles.STRONG_COLOR, 0.50)};
                }}
            """)
            autofill_btn.clicked.connect(lambda: self._handle_autofill())
            actions.addWidget(autofill_btn)

        view_btn = QPushButton("👁️")
        edit_btn = QPushButton("✏️")
        delete_btn = QPushButton("🗑️")
        restore_btn = QPushButton("↩")

        for b in (view_btn, edit_btn, delete_btn, restore_btn):
            b.setFixedSize(34, 34)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {hex_to_rgba_qt("#FFFFFF", 0.08)};
                    border: 1px solid {hex_to_rgba_qt("#FFFFFF", 0.15)};
                    border-radius: 10px;
                    font-size: 14px;
                }}
                QPushButton:hover {{
                    background: {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.30)};
                    border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.50)};
                }}
            """)

        view_btn.setToolTip("Voir le mot de passe")
        edit_btn.setToolTip("Modifier")
        delete_btn.setToolTip("Supprimer")
        restore_btn.setToolTip("Restaurer")

        view_btn.clicked.connect(lambda: self.view_clicked.emit(self.password_data))
        edit_btn.clicked.connect(lambda: self.edit_clicked.emit(self.password_data['id']))
        delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.password_data['id']))
        restore_btn.clicked.connect(lambda: self.restore_clicked.emit(self.password_data['id']))

        if is_trash:
            actions.addWidget(restore_btn)
            actions.addWidget(delete_btn)
            delete_btn.setToolTip("Supprimer d?finitivement")
        else:
            actions.addWidget(view_btn)
            actions.addWidget(edit_btn)
            actions.addWidget(delete_btn)
        header.addLayout(actions)

        root.addLayout(header)

        # ---------- Password masked + copy ----------
        pwd_wrap = QFrame()
        pwd_wrap.setStyleSheet(f"""
            QFrame {{
                background: {hex_to_rgba_qt("#0F2238", 0.70)};
                border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.25)};
                border-radius: 12px;
                padding: 12px 14px;
            }}
        """)
        pwl = QHBoxLayout(pwd_wrap)
        pwl.setContentsMargins(0, 0, 0, 0)
        pwl.setSpacing(10)

        dots = QLabel("• • • • • • • • • •")
        dots.setStyleSheet(f"""
            color: {Styles.BLUE_SECONDARY};
           font-size: 16px;
           font-family: 'Courier New', monospace;
            letter-spacing: 3px;
           font-weight: bold;
            background: transparent;
        """)
        pwl.addWidget(dots)
        pwl.addStretch()

        copy_btn = QPushButton("📋 Copier")
        copy_btn.setFixedHeight(36)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setToolTip("Copier le mot de passe")
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_PRIMARY}, stop:1 {Styles.BLUE_SECONDARY});
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 12px;
                font-weight: bold;
                padding: 0px 16px;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {Styles.BLUE_SECONDARY}, stop:1 {Styles.BLUE_PRIMARY});
            }}
        """)
        copy_btn.clicked.connect(lambda: self.copy_clicked.emit(self.password_data))
        pwl.addWidget(copy_btn)

        root.addWidget(pwd_wrap)

        # ---------- Footer ----------
        footer = QHBoxLayout()
        footer.setSpacing(10)

        # Strength
        strength = self.password_data.get('strength', 'medium')
        palette = {
            'strong': (Styles.STRONG_COLOR, 'Fort'),
            'medium': (Styles.MEDIUM_COLOR, 'Moyen'),
            'weak': (Styles.WEAK_COLOR, 'Faible')
        }
        color_hex, label_txt = palette.get(strength, (Styles.TEXT_MUTED, 'Inconnu'))

        pill = QFrame()
        pill.setStyleSheet(f"""
            QFrame {{
                background: {hex_to_rgba_qt(color_hex, 0.10)};
                border: 1px solid {hex_to_rgba_qt(color_hex, 0.20)};
                border-radius: 8px;
                padding: 5px 10px;
            }}
        """)
        pl = QHBoxLayout(pill)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        t = QLabel(f"● {label_txt}")
        t.setStyleSheet(f"color:{color_hex}; font-size:10px; font-weight:700; background:transparent;")
        pl.addWidget(t)
        footer.addWidget(pill)

        # Category
        cat = self.password_data.get('category', 'personal')
        icons = {'personal': '👤', 'work': '💼', 'finance': '💳', 'game': '🎮', 'study': '📚', 'trash': '🗑️'}
        cat_labels = {'personal': 'Personnel', 'work': 'Travail', 'finance': 'Finance', 'game': 'Jeux', 'study': 'Étude'}
        cat_lbl = QLabel(f"{icons.get(cat, '🔒')} {cat_labels.get(cat, cat.capitalize())}")
        cat_lbl.setStyleSheet(f"color:{Styles.TEXT_MUTED}; font-size:10px; background:transparent;")
        footer.addWidget(cat_lbl)
        
        

        # Date
        last_updated = self.password_data.get('last_updated', '')
        if last_updated:
            date_lbl = QLabel(f"🕒 {last_updated}")
            date_lbl.setStyleSheet(f"color:{Styles.TEXT_MUTED}; font-size:10px; background:transparent;")
            footer.addWidget(date_lbl)

        footer.addStretch()

        # Favorite
        is_fav = bool(self.password_data.get('favorite', False))
        fav_btn = QPushButton("⭐" if is_fav else "☆")
        fav_btn.setFixedSize(30, 30)
        fav_btn.setCursor(Qt.PointingHandCursor)
        fav_btn.setToolTip("Retirer des favoris" if is_fav else "Ajouter aux favoris")
        fav_btn.setStyleSheet(f"""
            QPushButton {{
                background: {hex_to_rgba_qt('#FFC107', 0.20) if is_fav else hex_to_rgba_qt('#FFFFFF', 0.08)};
                border: 1px solid {hex_to_rgba_qt('#FFC107', 0.40) if is_fav else hex_to_rgba_qt('#FFFFFF', 0.15)};
                border-radius: 8px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: {hex_to_rgba_qt('#FFC107', 0.30)};
                border: 1px solid {hex_to_rgba_qt('#FFC107', 0.50)};
            }}
        """)
        fav_btn.clicked.connect(lambda: self.favorite_clicked.emit(self.password_data['id']))
        footer.addWidget(fav_btn)

        root.addLayout(footer)

    def _handle_autofill(self):
        """Handle auto-fill: Emit signal to main window for 2FA verification"""
        self.autofill_clicked.emit(self.password_data)


class PasswordList(QWidget):
    copy_password = pyqtSignal(str)
    view_password = pyqtSignal(dict)
    edit_password = pyqtSignal(int)
    delete_password = pyqtSignal(int)
    favorite_password = pyqtSignal(int)
    restore_password = pyqtSignal(int)
    auto_login_clicked = pyqtSignal(dict)  # For autofill

    # 2FA signals (forwarded to MainWindow)
    request_2fa_for_copy = pyqtSignal(str)
    request_2fa_for_view = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.passwords = []
        self.filtered_passwords = []
        self.current_filter = 'all'
        self.setStyleSheet("QWidget { background: transparent; }")
        self._build()

    def _build(self):
        from src.gui.styles.styles import Styles

        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(20)

        header = QHBoxLayout()
        header.setSpacing(20)

        title = QLabel("Mes Mots de Passe")
        title.setFont(QFont("Segoe UI", 20, QFont.Bold))
        title.setStyleSheet(f"color:{Styles.TEXT_PRIMARY};")
        header.addWidget(title)

        # Search
        search_wrap = QFrame()
        search_wrap.setFixedWidth(400)
        search_wrap.setStyleSheet("QFrame { background: transparent; border: none; }")
        sh = QHBoxLayout(search_wrap)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher...")
        self.search_input.setFrame(False)
        self.search_input.setMinimumHeight(44)
        self.search_input.setFont(QFont("Segoe UI", 13))
        self.search_input.setTextMargins(16, 0, 16, 0)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {hex_to_rgba_qt('#1A2942', 0.80)};
                border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.25)};
                border-radius: 22px;
                padding: 10px 16px;
                color: {Styles.TEXT_PRIMARY};
                selection-background-color: {Styles.BLUE_PRIMARY};
                selection-color: white;
                font-size: 14px;
            }}
            QLineEdit::placeholder {{ color: {Styles.TEXT_MUTED}; }}
            QLineEdit:focus {{
                border: 1px solid {Styles.BLUE_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self.on_search)
        sh.addWidget(self.search_input, 1)

        self.filter_btn = QPushButton("🔍")
        self.filter_btn.setFixedSize(44, 44)
        self.filter_btn.setCursor(Qt.PointingHandCursor)
        self.filter_btn.setStyleSheet(f"""
            QPushButton {{
                background: {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.15)};
                border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.30)};
                border-radius: 22px;
                font-size: 16px;
                color: {Styles.BLUE_SECONDARY};
            }}
            QPushButton:hover {{
                background: {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.25)};
                border: 1px solid {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.50)};
            }}
        """)
        self.filter_btn.clicked.connect(self.show_filter_menu)
        sh.addWidget(self.filter_btn)

        header.addWidget(search_wrap)
        main.addLayout(header)

        # Scroll area 
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.03);
                width: 10px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: rgba(96, 165, 250, 0.3);
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(96, 165, 250, 0.5);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.column = QWidget()
        self.col_layout = QVBoxLayout(self.column)
        self.col_layout.setSpacing(16)
        self.col_layout.setContentsMargins(5, 5, 5, 5)
        self.col_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.column)
        main.addWidget(scroll)

    def show_filter_menu(self):
        from src.gui.styles.styles import Styles

        m = QMenu(self)
        m.setStyleSheet(f"""
            QMenu {{
                background: {Styles.PRIMARY_BG};
                border: 1px solid {hex_to_rgba_qt('#FFFFFF', 0.20)};
                border-radius: 12px;
                padding: 10px;
            }}
            QMenu::item {{
                padding: 10px 20px;
                border-radius: 8px;
                color: {Styles.TEXT_PRIMARY};
                font-size: 13px;
            }}
            QMenu::item:selected {{
                background: {hex_to_rgba_qt(Styles.BLUE_PRIMARY, 0.20)};
            }}
        """)
        filters = [
            ("📋 Tous les mots de passe", 'all'),
            ("🔒 Forts seulement", 'strong'),
            ("⚠️ Moyens seulement", 'medium'),
            ("💔 Faibles seulement", 'weak'),
            ("⭐ Favoris", 'favorites'),
            ("💼 Travail", 'work'),
            ("👤 Personnel", 'personal'),
            ("💳 Finance", 'finance'),
            ("🎮 Jeux", 'game'),
            ("📚 Étude", 'study'),
        ]
        for text, tag in filters:
            act = QAction(text, self)
            act.triggered.connect(lambda _, f=tag: self.apply_filter(f))
            m.addAction(act)
        m.exec_(self.filter_btn.mapToGlobal(self.filter_btn.rect().bottomLeft()))

    def apply_filter(self, ftype: str):
        self.current_filter = ftype
        if ftype == 'all':
            filtered = self.passwords
        elif ftype in ('strong', 'medium', 'weak'):
            filtered = [p for p in self.passwords if p.get('strength') == ftype]
        elif ftype == 'favorites':
            filtered = [p for p in self.passwords if p.get('favorite')]
        else:
            filtered = [p for p in self.passwords if p.get('category') == ftype]
        self.load_passwords(filtered)

    def load_passwords(self, passwords):
        """Single column layout (vertical only, centered cards)."""
        self.passwords = passwords
        self.filtered_passwords = passwords[:]

        # clear
        for i in reversed(range(self.col_layout.count())):
            w = self.col_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        if not passwords:
            from src.gui.styles.styles import Styles

            wrap = QFrame()
            wrap.setStyleSheet("background: transparent; border: none;")
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 80, 0, 80)
            wl.setSpacing(20)
            wl.setAlignment(Qt.AlignCenter)

            ic = QLabel("🔒")
            ic.setStyleSheet("font-size: 80px; background: transparent;")
            ic.setAlignment(Qt.AlignCenter)
            wl.addWidget(ic)

            t = QLabel("Aucun mot de passe")
            t.setAlignment(Qt.AlignCenter)
            t.setStyleSheet(f"color:{Styles.TEXT_PRIMARY}; font-size:22px; font-weight:bold; background:transparent;")
            wl.addWidget(t)

            d = QLabel("Cliquez sur 'Nouveau Mot de Passe' pour commencer à sécuriser vos comptes")
            d.setAlignment(Qt.AlignCenter)
            d.setWordWrap(True)
            d.setMaximumWidth(420)
            d.setStyleSheet(f"color:{Styles.TEXT_MUTED}; font-size:14px; background:transparent;")
            wl.addWidget(d)

            self.col_layout.addWidget(wrap)
            return

        # build cards
        for pwd in self.filtered_passwords:
            card = PasswordCard(pwd)
            # 2FA signals forwarded upstream
            card.request_2fa_for_copy.connect(self.request_2fa_for_copy.emit)
            card.request_2fa_for_view.connect(self.request_2fa_for_view.emit)
            # regular signals
            card.copy_clicked.connect(self.copy_password.emit)
            card.view_clicked.connect(self.view_password.emit)
            card.edit_clicked.connect(self.edit_password.emit)
            card.delete_clicked.connect(self.delete_password.emit)
            card.restore_clicked.connect(self.restore_password.emit)
            card.favorite_clicked.connect(self.favorite_password.emit)
            card.autofill_clicked.connect(self.auto_login_clicked.emit)

            # center card horizontally
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addStretch()
            rl.addWidget(card)
            rl.addStretch()
            self.col_layout.addWidget(row)

        self.col_layout.addStretch()

    def on_search(self, text: str):
        t = text.strip().lower()
        if not t:
            self.apply_filter(self.current_filter)
            return
        filtered = [
            p for p in self.passwords
            if (t in p.get('site_name', '').lower()
                or t in p.get('username', '').lower()
                or t in p.get('category', '').lower())
        ]
        self.load_passwords(filtered)
