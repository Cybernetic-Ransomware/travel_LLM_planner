"""User-facing messages for the panel UI. Centralised for future i18n / framework migration."""

ERR_API_UNREACHABLE = "Cannot connect to the backend API."
ERR_UNEXPECTED = "Something went wrong. Please try again."

ERR_MATRIX_UNAVAILABLE = "The route distance service is temporarily unavailable. Please try again later."
ERR_ORCHESTRATOR_UNAVAILABLE = "The AI assistant is not configured. Please contact the administrator."
ERR_NOT_IMPLEMENTED = "This feature is not yet available."

ERR_IMPORT_FAILED = "Import failed: {detail}"
ERR_ENRICHMENT_FAILED = "Enrichment failed: {detail}"
ERR_OPTIMIZATION_FAILED = "Route optimization failed: {detail}"
ERR_TRIP_FAILED = "Trip optimization failed: {detail}"
ERR_CHAT_UNAVAILABLE = "Could not reach the AI assistant. Please try again later."
ERR_CHAT_INTERRUPTED = "The AI response was interrupted. Please try again."

ERR_PLACE_COUNT = "Could not load place count."

SKIP_REASON: dict[str, str] = {
    "NO_COORDINATES": "Missing coordinates",
    "TIME_WINDOW_INFEASIBLE": "Closed or outside preferred hours on this day",
    "NO_MATRIX_ENTRY": "No route data available",
}

FRIENDLY_BY_STATUS: dict[int, str] = {
    501: ERR_NOT_IMPLEMENTED,
    502: ERR_MATRIX_UNAVAILABLE,
    503: ERR_ORCHESTRATOR_UNAVAILABLE,
}
