# Compat dates used to parametrize workerd and bindings integration tests.
# Each date exercises a different Python version inside the worker runtime:
#   - "2025-09-01" -> Python 3.12 (before the 2025-09-29 cutover)
#   - "2026-01-01" -> Python 3.13 (after the 2025-09-29 cutover)
from pathlib import Path

COMPAT_DATES: list[str] = ["2025-09-01", "2026-01-01"]


def replace_compat_date(file: Path, compat_date: str) -> None:
    file.write_text(file.read_text().replace("%COMPAT_DATE", compat_date))
