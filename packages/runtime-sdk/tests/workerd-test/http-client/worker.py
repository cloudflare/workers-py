import os

import pytest

from workers import WorkerEntrypoint


class Default(WorkerEntrypoint):
    def test(self):
        os.chdir("/session/metadata/tests")
        args = [".", "-vv"]
        if self.env.color:
            args.append("--color=yes")
        assert pytest.main(args) == 0
