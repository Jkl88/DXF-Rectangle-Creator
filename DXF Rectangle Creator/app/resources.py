"""Paths to bundled application resources."""

from __future__ import annotations

import os
import sys


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def logo_path() -> str | None:
    """Return path to splash / default title-block logo, or None if missing."""
    names = ("\u0410\u041a\u041e\u041b\u0415\u0414.jpg", "\u0410\u041a\u041e\u041b\u0415\u0414.png")
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            for name in names:
                candidates.append(os.path.join(meipass, name))
        for name in names:
            candidates.append(os.path.join(os.path.dirname(sys.executable), name))
    root = _project_root()
    for name in names:
        candidates.append(os.path.join(root, name))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None
