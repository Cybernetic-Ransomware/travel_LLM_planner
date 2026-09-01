"""Typed failures for the multi-day trip edit flow.

Every subclass carries a short LLM-safe ``user_message``. The editor raises
before its single write, so nothing here ever reaches persistence.
"""

from __future__ import annotations


class TripEditError(Exception):
    """Base for every recoverable trip-edit failure. ``user_message`` is LLM-safe."""

    user_message = "I couldn't apply the trip changes; nothing was saved."

    def __init__(self, user_message: str | None = None) -> None:
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class TripNotFoundError(TripEditError):
    user_message = "I couldn't find that trip."


class TripDeletedError(TripEditError):
    user_message = "This trip was deleted; there's nothing to update."


class UnsupportedPlanTypeError(TripEditError):
    user_message = "This chat can only edit multi-day trips right now."


class OperationValidationError(TripEditError):
    user_message = "That change isn't valid."


class InvalidDayIndexError(TripEditError):
    user_message = "That day doesn't exist in this trip."


class PlaceNotInTripError(TripEditError):
    user_message = "That place isn't part of this trip."


class TooFewPlacesError(TripEditError):
    user_message = "A trip needs at least 2 places."


class TooManyPlacesError(TripEditError):
    user_message = "A trip can have at most 50 places."


class AccommodationNotFoundError(TripEditError):
    user_message = "There's no such stay in this trip."


class AccommodationSelectorConflictError(TripEditError):
    user_message = (
        "I can't apply two changes to the same stay in one edit — ask me to combine them or split them across two requests."
    )


class TransferNotFoundError(TripEditError):
    user_message = "There's no transfer on that date to change."


class TransferAlreadyExistsError(TripEditError):
    user_message = "There's already a transfer on that date."


class TripEditValidationError(TripEditError):
    """Wraps a Pydantic ``ValidationError`` raised while re-constructing the mutated request."""

    user_message = "Those changes leave the trip in an invalid state; nothing was saved."


class OptimizerFailedError(TripEditError):
    user_message = "I couldn't re-plan the trip with those changes; nothing was saved."


class TripPersistenceError(TripEditError):
    user_message = "I couldn't save the updated trip; please try again."


class TripConcurrencyConflictError(TripEditError):
    """Mirror of ``src.core.exceptions.TripConcurrencyConflictError`` for the chat-tool path."""

    user_message = "This trip changed since we started; nothing was saved. Ask me to try again and I'll re-read it."


class RevisionNotFoundError(TripEditError):
    """Mirror of ``src.core.exceptions.RevisionNotFoundError`` for the chat-tool path."""

    user_message = "There's no such revision to restore."


class RevisionAlreadyCurrentError(TripEditError):
    """Mirror of ``src.core.exceptions.RevisionAlreadyCurrentError`` for the chat-tool path."""

    user_message = "That revision is already the current state — nothing to restore."
