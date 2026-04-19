"""Tests for TaskProcessor utilities."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import pytest

from task_processor.utils import calculate_retry_delay


def test_retry_delay_first():
    assert calculate_retry_delay(1) == 60


def test_retry_delay_second():
    assert calculate_retry_delay(2) == 300


def test_retry_delay_third():
    assert calculate_retry_delay(3) == 600


def test_retry_delay_fourth():
    assert calculate_retry_delay(4) == 1800


def test_retry_delay_fifth():
    assert calculate_retry_delay(5) == 3600


def test_retry_delay_sixth():
    assert calculate_retry_delay(6) == 3600


def test_retry_delay_tenth():
    assert calculate_retry_delay(10) == 3600


def test_retry_delay_zero():
    assert calculate_retry_delay(0) == 0


def test_retry_delay_negative():
    assert calculate_retry_delay(-1) == 0
