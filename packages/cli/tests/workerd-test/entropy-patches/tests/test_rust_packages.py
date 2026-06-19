"""Tests for Rust package entropy patches.

Rust packages that use HashMap need one entropy call at init time for the hash
seed. The entropy patch allows this call during snapshotting. Only the first Rust
package imported makes the call -- subsequent ones reuse the seed.

This file tests that importing multiple Rust packages in various orderings works
correctly through the snapshot cycle.
"""

import itertools

import jiter
import pytest
import tiktoken._tiktoken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.hashes import SHA256

RUST_PACKAGES = ["tiktoken._tiktoken", "cryptography.exceptions", "jiter"]


@pytest.mark.parametrize(
    "order",
    list(itertools.permutations(RUST_PACKAGES)),
    ids=[
        "->".join(m.split(".")[0] for m in perm)
        for perm in itertools.permutations(RUST_PACKAGES)
    ],
)
def test_rust_import_permutations(order):
    for module_name in order:
        __import__(module_name)


def test_tiktoken_import():
    assert tiktoken._tiktoken is not None


def test_cryptography_hashing():
    digest = hashes.Hash(SHA256())
    digest.update(b"test data")
    result = digest.finalize()
    assert len(result) == 32


def test_jiter_parse():
    result = jiter.from_json(b'{"key": "value", "num": 42}')
    assert result == {"key": "value", "num": 42}
