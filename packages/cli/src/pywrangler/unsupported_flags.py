from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class UnsupportedFlag:
    """A wrangler flag that pywrangler rejects before proxying."""

    command: str
    names: tuple[str, ...]
    hint: str

    def matches(self, cmd_name: str, args: Sequence[str]) -> bool:
        if cmd_name != self.command:
            return False
        flag_args = _flag_args(args)
        return any(
            self._is_enabled(arg, flag_args[i + 1] if i + 1 < len(flag_args) else None)
            for i, arg in enumerate(flag_args)
        )

    def _is_enabled(self, arg: str, next_arg: str | None) -> bool:
        # Enabled by `--flag/-f`, unless followed by a separate `false` value
        if arg in self.names:
            return next_arg != "false"
        # With `--flag=value`, enables the flag only for a literal `true`
        # instestingly, wrangler ignores all other values other than `true/false`,
        # so things like --flag=1 is the same as --flag=False
        name, sep, value = arg.partition("=")
        return bool(sep) and name in self.names and value == "true"

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
