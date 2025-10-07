from typing import Literal, NamedTuple
from datetime import datetime


class PythonCompatVersion(NamedTuple):
    version: Literal["3.12", "3.13"]
    compat_flag: str
    compat_date: datetime | None


PYTHON_COMPAT_VERSIONS = [
    PythonCompatVersion(
        "3.13", "python_workers_20250116", datetime.strptime("2025-09-29", "%Y-%m-%d")
    ),
    PythonCompatVersion("3.12", "python_workers", None),
]
