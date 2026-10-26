def normalize_optional_email(value: str | None) -> str | None:
    """Remove transport whitespace without inventing or silently fixing an address."""
    if value is None:
        return None
    return value.strip() or None
