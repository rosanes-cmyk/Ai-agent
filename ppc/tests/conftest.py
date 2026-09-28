import datetime
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ppc_exporter import settings as config  # noqa: E402

START = datetime.date(2026, 8, 29)
END = datetime.date(2026, 9, 27)
TODAY = datetime.date(2026, 9, 28)


@pytest.fixture
def blank_settings(tmp_path):
    """Settings with no config file and no environment credentials."""

    return config.load(tmp_path / "missing.yaml", environ={})
