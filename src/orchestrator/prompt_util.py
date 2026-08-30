import re

_MAX_FIELD_LEN = 200


def _sanitize_for_prompt(text: str) -> str:
    """Strip control characters and collapse whitespace to prevent prompt injection.

    A malicious place name such as ``"Foo\\nIgnore previous instructions"`` would
    otherwise introduce a new paragraph into the system prompt and could alter the
    model's behaviour.  Replacing control characters with a single space keeps the
    value on one line and limits it to a safe length.
    """
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r" {2,}", " ", text).strip()
    return text[:_MAX_FIELD_LEN]
