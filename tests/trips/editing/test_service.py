from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import TripConcurrencyConflictError as HTTPConflict
from src.trips.editing.errors import (
    OptimizerFailedError,
    TripConcurrencyConflictError,
    TripDeletedError,
    TripNotFoundError,
    UnsupportedPlanTypeError,
)
from src.trips.editing.operations import SetPlacePinnedOp
from src.trips.editing.service import MultiDayTripEditor
from src.trips.models import MultiDayTripDetailOut

pytestmark = pytest.mark.unit


def _detail(request, revision: int = 0) -> MultiDayTripDetailOut:
    dates = [d.date for d in request.days]
    return MultiDayTripDetailOut(
        id="507f1f77bcf86cd799439011",
        name="Trip",
        created_at="2026-01-01T00:00:00",
        revision=revision,
        start_date=str(min(dates)),
        end_date=str(max(dates)),
        num_days=len(request.days),
        transport_mode=request.transport_mode,
        multi_day_request=request,
        multi_day_response={"days": [], "transport_mode": request.transport_mode, "unassigned": []},
    )


@pytest.fixture
def op():
    return [SetPlacePinnedOp(op="set_place_pinned", place_id="p1", day_index=2)]


class TestMultiDayTripEditor:
    async def test_happy_path_persists_via_shared_update(self, base_request, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=_detail(base_request, revision=3))
        trips.update = AsyncMock(return_value=_detail(base_request, revision=4))
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())

        response_stub = _detail(base_request).multi_day_response
        with patch("src.trips.editing.service.optimize_trip", new=AsyncMock(return_value=response_stub)):
            result = await editor.apply("507f1f77bcf86cd799439011", op, expected_revision=3)

        assert result.revision == 4
        save_request = trips.update.call_args[0][1]
        assert save_request.expected_revision == 3
        assert save_request.plan_type == "MULTI_DAY"

    async def test_trip_not_found(self, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=None)
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        with pytest.raises(TripNotFoundError):
            await editor.apply("x", op, expected_revision=0)

    async def test_single_day_trip_rejected(self, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=MagicMock(spec=[]))  # not a MultiDayTripDetailOut
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        with pytest.raises(UnsupportedPlanTypeError):
            await editor.apply("x", op, expected_revision=0)

    async def test_early_revision_mismatch(self, base_request, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=_detail(base_request, revision=5))
        trips.update = AsyncMock()
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        with pytest.raises(TripConcurrencyConflictError):
            await editor.apply("x", op, expected_revision=2)
        trips.update.assert_not_called()

    async def test_optimizer_failure_is_wrapped_and_nothing_persisted(self, base_request, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=_detail(base_request, revision=0))
        trips.update = AsyncMock()
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        with (
            patch("src.trips.editing.service.optimize_trip", new=AsyncMock(side_effect=ValueError("boom"))),
            pytest.raises(OptimizerFailedError),
        ):
            await editor.apply("x", op, expected_revision=0)
        trips.update.assert_not_called()

    async def test_cas_conflict_at_persist_is_wrapped(self, base_request, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=_detail(base_request, revision=0))
        trips.update = AsyncMock(side_effect=HTTPConflict("x", expected=0))
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        response_stub = _detail(base_request).multi_day_response
        with (
            patch("src.trips.editing.service.optimize_trip", new=AsyncMock(return_value=response_stub)),
            pytest.raises(TripConcurrencyConflictError),
        ):
            await editor.apply("x", op, expected_revision=0)

    async def test_deleted_between_read_and_write(self, base_request, op):
        trips = MagicMock()
        trips.find_by_id = AsyncMock(return_value=_detail(base_request, revision=0))
        trips.update = AsyncMock(return_value=None)
        editor = MultiDayTripEditor(MagicMock(), trips, MagicMock())
        response_stub = _detail(base_request).multi_day_response
        with (
            patch("src.trips.editing.service.optimize_trip", new=AsyncMock(return_value=response_stub)),
            pytest.raises(TripDeletedError),
        ):
            await editor.apply("x", op, expected_revision=0)
