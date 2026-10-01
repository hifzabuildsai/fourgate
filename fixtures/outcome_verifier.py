#!/usr/bin/env python3
"""Shim: runs the packaged demo verifier (fourgate/demo/verifier.py) without installing the package."""
import runpy
from pathlib import Path

# verifier.py ends with `raise SystemExit(main())`, so its exit code propagates through run_path.
runpy.run_path(str(Path(__file__).resolve().parent.parent / "fourgate" / "demo" / "verifier.py"), run_name="__main__")
