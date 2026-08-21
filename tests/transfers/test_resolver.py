"""Unit tests for resolve_day_transfer — mirrors tests/accommodations/test_resolver.py."""

from __future__ import annotations

from datetime import date, time

import pytest

from src.transfers.models import TransferBlock
from src.transfers.resolver import resolve_day_transfer


def _transfer(day: date) -> TransferBlock:
    return TransferBlock(date=day, departure_time=time(10, 0), arrival_time=time(15, 0))


@pytest.mark.unit
class TestResolveDayTransfer:
    def test_day_with_transfer_resolves_it(self):
        transfer = _transfer(date(2026, 10, 10))
        [result] = resolve_day_transfer([date(2026, 10, 10)], [transfer])
        assert result is transfer

    def test_day_without_transfer_resolves_to_none(self):
        transfer = _transfer(date(2026, 10, 10))
        [result] = resolve_day_transfer([date(2026, 10, 11)], [transfer])
        assert result is None

    def test_no_transfers_resolves_all_days_to_none(self):
        results = resolve_day_transfer([date(2026, 10, d) for d in range(5, 10)], [])
        assert all(r is None for r in results)

    def test_multiple_days_each_resolve_independently(self):
        transfer = _transfer(date(2026, 10, 10))
        dates = [date(2026, 10, 9), date(2026, 10, 10), date(2026, 10, 11)]
        results = resolve_day_transfer(dates, [transfer])
        assert results == [None, transfer, None]
