from contextlib import chdir
from subprocess import run

# Import the full module so we can patch constants
from pywrangler.types import wrangler_types

WRANGLER_TOML = """
compatibility_date = "2025-08-14"

kv_namespaces = [
    { binding = "FOO", id = "<YOUR_KV_NAMESPACE_ID>" }
]
"""

PYPROJECT_TOML = """
[dependency-groups]
dev = [
    "mypy>=1.17.1",
    "pyodide-py",
]

[tool.mypy]
files = [
    "src",
]
"""

WORKER = """
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from js import Env

class Default:
    env: "Env"
    async def fetch(self) -> None:
        reveal_type(self.env.FOO) # Revealed type is "js.KVNamespace_iface"
        bar = await self.env.FOO.get("bar")
        reveal_type(bar) # Revealed type is "builtins.str | None"
"""


def test_types(tmp_path):
    config_path = tmp_path / "wrangler.toml"
    pyproject_path = tmp_path / "pyproject.toml"
    worker_dir = tmp_path / "src/worker"
    worker_path = worker_dir / "entry.py"

    worker_dir.mkdir(parents=True)
    worker_path.write_text(WORKER)
    config_path.write_text(WRANGLER_TOML)
    pyproject_path.write_text(PYPROJECT_TOML)

    with chdir(tmp_path):
        wrangler_types(None, None)
        result = run(["uv", "run", "mypy"], capture_output=True, text=True, check=False)

        assert 'Revealed type is "js.KVNamespace_iface"' in result.stdout
        assert 'Revealed type is "builtins.str | None"' in result.stdout
        assert "Success: no issues found" in result.stdout
