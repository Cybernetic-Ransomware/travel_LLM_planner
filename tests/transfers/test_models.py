"""Unit tests for TransferBlock."""

from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from src.transfers.models import TransferBlock


def _transfer(departure: time = time(10, 0), arrival: time = time(15, 0), **kwargs) -> TransferBlock:
    return TransferBlock(date=date(2026, 10, 10), departure_time=departure, arrival_time=arrival, **kwargs)


@pytest.mark.unit
class TestTransferBlockValidation:
    def test_valid_transfer_constructs(self):
        transfer = _transfer()
        assert transfer.departure_time == time(10, 0)
        assert transfer.arrival_time == time(15, 0)

    def test_label_defaults_to_none(self):
        assert _transfer().label is None

    def test_label_accepted(self):
        transfer = _transfer(label="Shinkansen Nozomi 15")
        assert transfer.label == "Shinkansen Nozomi 15"

    def test_arrival_equal_departure_rejected(self):
        with pytest.raises(ValidationError, match="arrival_time must be after departure_time"):
            _transfer(departure=time(10, 0), arrival=time(10, 0))

    def test_arrival_before_departure_rejected(self):
        with pytest.raises(ValidationError, match="arrival_time must be after departure_time"):
            _transfer(departure=time(15, 0), arrival=time(10, 0))

    def test_overnight_transfer_rejected(self):
        """22:00 -> 06:00 next day is out of scope for this slice — see ADR-16."""
        with pytest.raises(ValidationError, match="overnight transfers are not supported"):
            _transfer(departure=time(22, 0), arrival=time(6, 0))
