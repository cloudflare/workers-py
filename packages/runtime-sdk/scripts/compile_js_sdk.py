"""
Compile ts/sdk.ts -> src/workers/sdk.mjs using esbuild.

Usage:
    python scripts/compile_js_sdk.py          # compile and write
    python scripts/compile_js_sdk.py --check  # verify sdk.mjs is up to date
"""

import shutil
import subprocess
import sys
from pathlib import Path

RUNTIME_SDK_DIR = Path(__file__).resolve().parent.parent
TS_SOURCE = RUNTIME_SDK_DIR / "ts" / "sdk.ts"
MJS_OUTPUT = RUNTIME_SDK_DIR / "src" / "workers" / "sdk.mjs"

HEADER = """\
// AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
// Source: ts/sdk.ts
// Regenerate: python scripts/compile_js_sdk.py
"""


def compile_ts() -> str:
    """Compile ts/sdk.ts to JavaScript and return the output string (with header)."""
    npx = shutil.which("npx")
    if npx is None:
        print(
            "error: npx not found. Install Node.js to compile TypeScript.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = subprocess.run(
        [
            npx,
            "--yes",
            "esbuild@0.28.0",
            str(TS_SOURCE),
            "--format=esm",
            "--log-level=error",
        ],
        capture_output=True,
        text=True,
        cwd=str(RUNTIME_SDK_DIR),
        check=False,
    )

    if result.returncode != 0:
        print(f"esbuild failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(result.returncode)

    return HEADER + result.stdout


def main() -> None:
    compiled = compile_ts()

    if "--check" in sys.argv:
        if not MJS_OUTPUT.exists():
            print(
                f"error: {MJS_OUTPUT.relative_to(RUNTIME_SDK_DIR)} does not exist.",
                file=sys.stderr,
            )
            print("Run: python scripts/compile_js_sdk.py", file=sys.stderr)
            sys.exit(1)

        current = MJS_OUTPUT.read_text()
        if current != compiled:
            print(
                f"error: {MJS_OUTPUT.relative_to(RUNTIME_SDK_DIR)} is out of date.",
                file=sys.stderr,
            )
            print("Run: python scripts/compile_js_sdk.py", file=sys.stderr)
            sys.exit(1)

        print(f"{MJS_OUTPUT.relative_to(RUNTIME_SDK_DIR)} is up to date.")
    else:
        MJS_OUTPUT.write_text(compiled)
        print(
            f"Compiled {TS_SOURCE.relative_to(RUNTIME_SDK_DIR)} -> {MJS_OUTPUT.relative_to(RUNTIME_SDK_DIR)}"
        )


if __name__ == "__main__":
    main()
