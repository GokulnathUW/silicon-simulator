"""Fixtures shared by pipeline tests."""

from pathlib import Path

import pytest

from tests.helpers import apply_simulation_schema


@pytest.fixture
def simulation_db(tmp_path: Path) -> Path:
    """Return a database that already has the simulation tables."""
    path = tmp_path / "sim.db"
    apply_simulation_schema(path)
    return path
