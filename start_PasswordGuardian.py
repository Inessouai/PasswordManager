
import os, sys, types, traceback
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel
from PyQt5.QtCore import Qt

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
GUI_DIR = os.path.join(SRC_DIR, "gui")

for p in (PROJECT_ROOT, SRC_DIR, GUI_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

if "gui" not in sys.modules:
    gui_pkg = types.ModuleType("gui")
    gui_pkg.__path__ = [GUI_DIR]
    sys.modules["gui"] = gui_pkg

# print hard crashes
def _install_crash_printer():
    import faulthandler
    faulthandler.enable()
    def excepthook(tp, value, tb):
        import traceback as _tb
        _tb.print_exception(tp, value, tb)
    sys.excepthook = excepthook
_install_crash_printer()

def load_mainwindow():
    try:
        from src.gui.main_window import MainWindow
        return MainWindow
    except Exception:
        try:
            from gui.main_window import MainWindow  # alias
            return MainWindow
        except Exception:
            print(" Failed to import MainWindow (both src.gui and gui). Traceback:")
            traceback.print_exc()
            class Placeholder(QMainWindow):
                def __init__(self):
                    super().__init__()
                    self.setWindowTitle("SecureVault")
                    self.setMinimumSize(900, 600)
                    lbl = QLabel("MainWindow not found.\nFix imports or keep alias.")
                    lbl.setAlignment(Qt.AlignCenter)
                    self.setCentralWidget(lbl)
            return Placeholder

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # Ensure DB schema exists for local SQLite usage
    try:
        from database.engine import init_db
        init_db()
    except Exception:
        print("Failed to initialize database schema.")
        traceback.print_exc()

    app = QApplication(sys.argv)
    MainWindow = load_mainwindow()
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
