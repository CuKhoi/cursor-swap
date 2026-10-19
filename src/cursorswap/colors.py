"""The Bash palette, with plain text padded before applying color."""
import os
import sys

CODES = {
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
    "accent": "\033[38;5;173m", "muted": "\033[38;5;250m",
    "red": "\033[31m", "yellow": "\033[33m",
    "ok": "\033[38;5;108m", "warn": "\033[38;5;179m", "crit": "\033[38;5;167m",
}


def supports_color():
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return sys.stdout.isatty() and os.environ.get("TERM") != "dumb"


def code(name):
    return CODES[name] if supports_color() else ""


def paint(text, *styles):
    return "".join(code(style) for style in styles) + str(text) + code("reset")


def accent(text):
    return paint(text, "accent")


def muted(text):
    return paint(text, "muted")


def bold(text):
    return paint(text, "bold")


def bold_accent(text):
    return paint(text, "bold", "accent")


def sev_pct(value):
    return paint(f"{value}%", "crit" if float(value) >= 90 else "warn" if float(value) >= 70 else "ok")
