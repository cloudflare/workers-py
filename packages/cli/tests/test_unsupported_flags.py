import pytest

from pywrangler.unsupported_flags import (
    UNSUPPORTED_FLAGS,
    UnsupportedFlag,
    find_unsupported_flag,
)

FLAG = UnsupportedFlag(command="dev", names=("--foo", "-f"), hint="Do X instead.")
REGISTRY = (FLAG,)


@pytest.mark.parametrize(
    "args",
    [
        ["--foo"],
        ["-f"],
        ["--port", "8787", "--foo"],
        ["--foo=true"],
        ["-f=true"],
        ["--foo", "true"],
        ["--foo", "--port", "8787"],
    ],
)
def test_enabled_flag_is_found(args):
    assert find_unsupported_flag("dev", args, REGISTRY) is FLAG


@pytest.mark.parametrize(
    "args",
    [
        [],
        ["--foobar"],
        ["--foo=false"],
        ["--foo=0"],
        ["--foo=No"],
        ["--foo=1"],
        ["--foo=yes"],
        ["--foo=TRUE"],
        ["--foo="],
        ["-f=0"],
        ["--foo", "false"],
        ["-f", "false"],
        ["--foo", "false", "--port", "8787"],
        ["--", "--foo"],
    ],
)
def test_disabled_or_absent_flag_is_ignored(args):
    assert find_unsupported_flag("dev", args, REGISTRY) is None


def test_flag_is_scoped_to_its_command():
    assert find_unsupported_flag("deploy", ["--foo"], REGISTRY) is None


def test_error_message():
    assert FLAG.error_message() == (
        "`pywrangler dev --foo` is not supported for Python Workers.\nDo X instead."
    )


@pytest.mark.parametrize("args", [["--remote"], ["-r"], ["--remote=true"]])
def test_default_registry_rejects_dev_remote(args):
    flag = find_unsupported_flag("dev", args, UNSUPPORTED_FLAGS)
    assert flag is not None
    assert "remote bindings" in flag.error_message()


def test_default_registry_allows_remote_for_other_commands():
    assert find_unsupported_flag("d1", ["execute", "db", "--remote"]) is None
