# pyright: reportMissingImports=false
import uuid


def unique_table_name() -> str:
    """Unique per call"""
    return f"test_{uuid.uuid4().hex[:10]}"
