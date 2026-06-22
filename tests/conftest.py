"""Shared pytest setup: build the synthetic fixtures once per session.

make_fixtures.py writes six stand-in PDFs into this directory (an XFA array form, a
single-stream XDP, an AcroForm-only form, a no-form PDF, an empty XFA, and a corrupt XFA).
They are git-ignored and regenerated on every run.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # so `import make_fixtures` works under any pytest import mode

import make_fixtures  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def fixtures():
    make_fixtures.main()
    yield
