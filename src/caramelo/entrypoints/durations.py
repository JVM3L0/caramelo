import re
from datetime import timedelta

_PART = re.compile(r"(\d+)([mhd])")
_UNITS = {"m": "minutes", "h": "hours", "d": "days"}


def parse_duration(text: str) -> timedelta:
    """Parses values like 30m, 2h, 1d or 1h30m."""
    parts = _PART.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        raise ValueError(f"invalid duration {text!r} (use e.g. 30m, 2h, 1d)")
    return sum((timedelta(**{_UNITS[u]: int(n)}) for n, u in parts), timedelta())
