"""Crash logging and problem reports for beta testers."""
from __future__ import annotations

import logging
import platform
import sys
import traceback
import urllib.parse
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from .model import APP_NAME, APP_VERSION

# Where testers send reports. Set this before you build a release.
FEEDBACK_EMAIL = "splattervhs@gmail.com"
BETA = True

log = logging.getLogger("goredraft")


def log_dir() -> Path:
    d = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def system_info() -> str:
    try:
        from PySide6 import __version__ as pyside
    except ImportError:
        pyside = "?"
    return (f"{APP_NAME} {APP_VERSION}{' beta' if BETA else ''} · {platform.system()} {platform.release()} "
            f"({platform.machine()}) · Python {platform.python_version()} · Qt {pyside}")


def setup_logging():
    h = RotatingFileHandler(log_dir() / "goredraft.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    log.info("start · %s", system_info())

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        log.error("crash\n%s", text)
        app = QApplication.instance()
        if app is None:
            sys.__excepthook__(exc_type, exc, tb)
            return
        box = QMessageBox(QMessageBox.Critical, "Something broke",
                          "GORE DRAFT hit an error. Your work is probably fine; save now to be safe.\n\n"
                          f"{exc_type.__name__}: {exc}\n\n"
                          "Use Help → Report a Problem to send the details.")
        box.setDetailedText(text)
        report = box.addButton("Report a Problem", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() is report:
            report_problem(None, text)
    sys.excepthook = hook


def open_log_folder():
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir())))


def report_problem(parent, extra: str = ""):
    """Open an email with version info and the end of the log."""
    try:
        tail = (log_dir() / "goredraft.log").read_text(encoding="utf-8")[-3000:]
    except OSError:
        tail = ""
    body = (f"What were you doing when it happened?\n\n\n\nWhat did you expect?\n\n\n"
            f"---\n{system_info()}\n\n{extra[-1500:]}\n{tail}")
    if FEEDBACK_EMAIL:
        url = f"mailto:{FEEDBACK_EMAIL}?subject={urllib.parse.quote(f'GORE DRAFT {APP_VERSION} problem')}" \
              f"&body={urllib.parse.quote(body[:6000])}"
        if QDesktopServices.openUrl(QUrl(url)):
            return
    QApplication.clipboard().setText(body)
    QMessageBox.information(parent, "Report a problem",
                            "The details have been copied to your clipboard. Paste them into a message to "
                            "whoever gave you GORE DRAFT.\n\nThe full log is in the folder that opens next.")
    open_log_folder()
