"""Verify that sdk.mjs is up to date with the TypeScript source."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RUNTIME_SDK_DIR = Path(__file__).resolve().parent.parent
COMPILE_SCRIPT = RUNTIME_SDK_DIR / "scripts" / "compile_js_sdk.py"


def test_sdk_mjs_up_to_date() -> None:
    """sdk.mjs must match the output of compiling ts/sdk.ts.

    If this test fails, run:
        python scripts/compile_js_sdk.py
    """
    result = subprocess.run(
        [sys.executable, str(COMPILE_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=str(RUNTIME_SDK_DIR),
        check=False,
    )
    assert result.returncode == 0, (
        f"sdk.mjs is out of date. Run: python scripts/compile_js_sdk.py\n{result.stderr}"
    )
