import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.styles import APP_STYLESHEET
from app.ui.main_window import MainWindow


def resource_path(relative_path: str) -> str:
    """Works both in dev and inside a PyInstaller-frozen exe (where bundled files
    extract to sys._MEIPASS at runtime)."""
    base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return str(base_path / relative_path)


def _set_windows_app_user_model_id():
    """Windows groups/identifies a running window's Taskbar button by its
    AppUserModelID, not just its own HICON -- without a unique one set, a frozen
    PyInstaller app can get lumped in under a generic/python default identity, which
    is a known real cause of the Taskbar showing a generic icon even though the
    window's own icon (set via setWindowIcon below) is perfectly valid. Windows-only;
    a no-op (silently skipped) on any other platform."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('JobFinder.App')
    except Exception:
        pass  # best-effort -- worst case the Taskbar identity/icon falls back to default


def _enable_crash_log():
    """A native crash (Qt, access violation) kills the process with no Python traceback and, in the
    frozen exe, no console. faulthandler writes the Python stack of every thread to crash.log, so
    the next one says which line was running. Best-effort: never stops the app starting."""
    try:
        import faulthandler
        import os
        folder = Path(os.environ.get('APPDATA', str(Path.home()))) / 'JobDesk'
        folder.mkdir(parents=True, exist_ok=True)
        global _CRASH_LOG
        _CRASH_LOG = open(folder / 'crash.log', 'a', buffering=1)
        faulthandler.enable(file=_CRASH_LOG, all_threads=True)
    except Exception:
        pass


def main():
    _enable_crash_log()
    _set_windows_app_user_model_id()

    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    app_icon = QIcon(resource_path('Icon.ico'))
    app.setWindowIcon(app_icon)

    window = MainWindow()
    # Also set directly on the window itself, not just QApplication -- a real,
    # commonly-reported Windows+Qt gotcha: the Taskbar button icon is tied to the
    # top-level window's own icon, and doesn't always reliably inherit the
    # QApplication-level one alone in a frozen build.
    window.setWindowIcon(app_icon)
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
