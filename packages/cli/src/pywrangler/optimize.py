import logging
from pathlib import Path
from typing import TypedDict

from wheel_optimizer import OptimizerConfig, OptimizerPipeline

from .utils import read_pyproject_toml

# Note: When adding a new optimizer, make sure to update the following:
# - _ALL_OPTIMIZER_FIELDS
# - DEFAULT_ON_OPTIMIZERS
# - OptimizeConfig


class OptimizeConfig(TypedDict, total=False):
    disable_all: bool
    remove_docstrings: bool
    remove_type_annotations: bool
    remove_assertions: bool
    remove_comments: bool
    remove_tests: bool
    remove_typestubs: bool
    remove_pycache: bool
    remove_c_source: bool
    remove_cython_source: bool
    minify_whitespace: bool
    compile_pyc: bool


logger = logging.getLogger(__name__)
# Disable wheel_optimizer logging, we have our own logging
logging.getLogger("wheel_optimizer").setLevel(logging.CRITICAL)

DEFAULT_ON_OPTIMIZERS: frozenset[str] = frozenset(
    {
        "remove_docstrings",
        "remove_pycache",
        "remove_comments",
        "minify_whitespace",
    }
)

_ALL_OPTIMIZER_FIELDS: frozenset[str] = frozenset(
    {
        "remove_docstrings",
        "remove_type_annotations",
        "remove_assertions",
        "remove_comments",
        "remove_tests",
        "remove_typestubs",
        "remove_pycache",
        "remove_c_source",
        "remove_cython_source",
        "minify_whitespace",
        "compile_pyc",
    }
)


def _read_optimize_section() -> OptimizeConfig:
    data = read_pyproject_toml()
    tool = data.get("tool", {})
    pywrangler = tool.get("pywrangler", {}) if isinstance(tool, dict) else {}
    optimize = pywrangler.get("optimize", {}) if isinstance(pywrangler, dict) else {}
    result: OptimizeConfig = {}
    if isinstance(optimize, dict):
        result.update(optimize)  # type: ignore[typeddict-item]
    return result


def get_optimize_config() -> OptimizerConfig:
    user_config = _read_optimize_section()

    if user_config.get("disable_all", False):
        return OptimizerConfig(disable_all=True)

    kwargs: dict[str, bool] = {}
    for field in _ALL_OPTIMIZER_FIELDS:
        user_value = user_config.get(field)
        if user_value is not None:
            kwargs[field] = bool(user_value)
        else:
            kwargs[field] = field in DEFAULT_ON_OPTIMIZERS

    return OptimizerConfig(**kwargs)


def optimize_packages(vendor_path: Path) -> None:
    config = get_optimize_config()

    if config.disable_all:
        logger.debug("Bundle optimization disabled via disable_all = true")
        return

    pipeline = OptimizerPipeline(config)

    if not pipeline.optimizers:
        logger.debug("No optimizers enabled, skipping optimization")
        return

    names = [opt.name for opt in pipeline.optimizers]
    logger.info(
        f"Optimizing vendor packages ({', '.join(names)})...",
    )
    pipeline.run(vendor_path)
    logger.debug("Bundle optimization complete.")
