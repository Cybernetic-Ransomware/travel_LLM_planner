import re

_MAX_FIELD_LEN = 200


def _sanitize_for_prompt(text: str) -> str:
    """Collapse control chars/whitespace and cap length so a hostile field can't inject a prompt line."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r" {2,}", " ", text).strip()
    return text[:_MAX_FIELD_LEN]
