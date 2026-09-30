#!/usr/bin/env python3
"""Run isolated skip/API tests before restarting the production service."""
import runpy
from pathlib import Path
runpy.run_path(str(Path(__file__).with_name("test_skip_markers.py")), run_name="__main__")
