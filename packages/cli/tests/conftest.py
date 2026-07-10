from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CompatConfig:
    compat_date: str
    python_version: str
    extra_compat_flags: list[str] = field(default_factory=list)


COMPAT_CONFIGS: list[CompatConfig] = [
    CompatConfig(
        compat_date="2025-09-01",
        python_version="3.12",
        extra_compat_flags=["enable_python_external_sdk", "python_process_pth_files", "python_request_headers_preserve_commas"],
    ),
    CompatConfig(
        compat_date="2026-01-01",
        python_version="3.13",
        extra_compat_flags=["enable_python_external_sdk", "python_process_pth_files", "python_request_headers_preserve_commas"],
    ),
    CompatConfig(
        compat_date="2026-07-01",
        python_version="3.14",
        # TODO: remove these when 3.14 is stable, and enabled by date
        extra_compat_flags=["python_workers_20260610", "experimental"],
    ),
]


def replace_compat_date(file: Path, compat_date: str) -> None:
    file.write_text(file.read_text().replace("%COMPAT_DATE", compat_date))


def inject_compat_flags(file: Path, extra_flags: list[str]) -> None:
    if not extra_flags:
        return
    content = file.read_text()
    for flag in extra_flags:
        content = content.replace('"python_workers"', f'"python_workers", "{flag}"')
    file.write_text(content)
