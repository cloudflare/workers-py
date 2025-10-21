import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from .utils import WRANGLER_COMMAND, run_command

logger = logging.getLogger(__name__)

TSCONFIG = """
{
  "compilerOptions": {
    "target": "esnext",
    "module": "esnext",
    "moduleResolution": "nodenext",
    "lib": ["esnext"]
  },
  "include": ["worker-configuration.d.ts"]
}
"""

PACKAGE_JSON = """
{
  "dependencies": {
    "typescript": "^5.3.2"
  }
}
"""


def wrangler_types(outdir_arg: str | None, config: str | None, /) -> None:
    args = ["types"]
    if config:
        args += ["--config", config]
    if outdir_arg is None:
        outdir = Path("src")
    else:
        outdir = Path(outdir_arg)
    stubs_dir = outdir / "js-stubs"
    stubs_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        run_command(WRANGLER_COMMAND + args + [tmp / "worker-configuration.d.ts"])
        (tmp / "tsconfig.json").write_text(TSCONFIG)
        (tmp / "package.json").write_text(PACKAGE_JSON)
        run_command(["npm", "-C", tmp, "install"])
        run_command(["npx", "@pyodide/ts-to-python", tmp, stubs_dir / "__init__.pyi"])
