from collections.abc import Sequence
from dataclasses import dataclass

_FALSY_VALUES = frozenset({"false", "0", "no"})


@dataclass(frozen=True)
class UnsupportedFlag:
    """A wrangler flag that pywrangler rejects before proxying."""

    command: str
    names: tuple[str, ...]
    hint: str

    def matches(self, cmd_name: str, args: Sequence[str]) -> bool:
        if cmd_name != self.command:
            return False
        return any(self._is_enabled(arg) for arg in _flag_args(args))

    def _is_enabled(self, arg: str) -> bool:
        # Enabled by `--flag/-f`
        if arg in self.names:
            return True
        # The flag can still be disabled by `--flag=false` so check that part
        name, sep, value = arg.partition("=")
        return bool(sep) and name in self.names and value.lower() not in _FALSY_VALUES

    def error_message(self) -> str:
        return (
            f"`pywrangler {self.command} {self.names[0]}` is not supported "
            f"for Python Workers.\n{self.hint}"
        )


UNSUPPORTED_FLAGS: tuple[UnsupportedFlag, ...] = (
    UnsupportedFlag(
        command="dev",
        names=("--remote", "-r"),
        hint=(
            "Please use remote bindings instead.\n"
            "See https://developers.cloudflare.com/workers/development-testing/#remote-bindings"
        ),
    ),
)


def find_unsupported_flag(
    cmd_name: str,
    args: Sequence[str],
    registry: Sequence[UnsupportedFlag] = UNSUPPORTED_FLAGS,
) -> UnsupportedFlag | None:
    """
    Find an unsupported flag in the given command and arguments.

    Parameters
    ----------
    cmd_name:
        The command name to check.
    args:
        The arguments to check.
    registry:
        The registry of unsupported flags to check against.
        (For testing purposes. Normally not needed.)

    Returns
    -------
        The unsupported flag if found, otherwise None.
    """
    return next((flag for flag in registry if flag.matches(cmd_name, args)), None)


def _flag_args(args: Sequence[str]) -> Sequence[str]:
    return args[: args.index("--")] if "--" in args else args
