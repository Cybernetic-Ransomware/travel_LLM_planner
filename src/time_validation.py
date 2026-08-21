from __future__ import annotations

from datetime import time
from typing import Annotated

from pydantic import AfterValidator

# Lives at src/ top level, not src/core/: importing src.core.* from a leaf domain model triggers a circular import.


def _reject_aware_time(value: time) -> time:
    if value.tzinfo is not None:
        raise ValueError("must be a naive local wall-clock time, not timezone/UTC-offset-aware")
    return value


NaiveTime = Annotated[time, AfterValidator(_reject_aware_time)]
