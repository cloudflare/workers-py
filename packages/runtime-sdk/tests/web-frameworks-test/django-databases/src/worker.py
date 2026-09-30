# pyright: reportMissingImports=false

"""Django database backend test worker."""

from testlib.entrypoint import TestRunnerEntrypoint


class Default(TestRunnerEntrypoint):
    pass
