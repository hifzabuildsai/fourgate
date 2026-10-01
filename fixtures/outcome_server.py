#!/usr/bin/env python3
"""Shim: runs the packaged demo server (fourgate/demo/server.py) without installing the package."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent.parent / "fourgate" / "demo" / "server.py"), run_name="__main__")
