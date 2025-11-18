"""Telegram length and truncation helpers using UTF-16 code unit semantics.

These helpers implement an approximation of Telegram's message length model,
where the length of a message is defined as the number of UTF-16 code units
in its text.
"""

from __future__ import annotations

from typing import Final

ELLIPSIS: Final[str] = "..."


def _to_utf16_units(text: str) -> list[int]:
    """Return list of UTF-16 code units for *text*.

    We use Python's UTF-16-LE codec and ignore the BOM.
    """

    if not text:
        return []
    # Encode to UTF-16-LE so that every code unit is 2 bytes; then interpret
    # each pair of bytes as one code unit.
    data = text.encode("utf-16-le", errors="surrogatepass")
    # len(data) is always even; each code unit is 2 bytes.
    return [data[i] | (data[i + 1] << 8) for i in range(0, len(data), 2)]


def tg_len(text: str) -> int:
    """Return the length of *text* in UTF-16 code units.

    This is the metric used for enforcing Telegram message limits.
    """

    return len(_to_utf16_units(text))


def tg_slice_head(text: str, max_units: int) -> str:
    """Return the prefix of *text* whose UTF-16 length is at most *max_units*.

    If *max_units* is greater than or equal to the length, return *text*
    unchanged.
    """

    if max_units <= 0 or not text:
        return ""
    units = _to_utf16_units(text)
    if max_units >= len(units):
        return text
    # Walk the original string until we have consumed max_units UTF-16 units.
    out_chars = []
    used = 0
    for ch in text:
        needed = tg_len(ch)
        if used + needed > max_units:
            break
        out_chars.append(ch)
        used += needed
    return "".join(out_chars)


def tg_slice_tail(text: str, max_units: int) -> str:
    """Return the suffix of *text* whose UTF-16 length is at most *max_units*.

    If *max_units* is greater than or equal to the length, return *text*
    unchanged.
    """

    if max_units <= 0 or not text:
        return ""
    units = _to_utf16_units(text)
    if max_units >= len(units):
        return text
    # Walk the original string from the end until we have consumed max_units
    # UTF-16 units.
    out_chars = []
    used = 0
    for ch in reversed(text):
        needed = tg_len(ch)
        if used + needed > max_units:
            break
        out_chars.append(ch)
        used += needed
    return "".join(reversed(out_chars))


def tg_truncate_middle(text: str, max_units: int, ellipsis: str = ELLIPSIS) -> str:
    """Truncate *text* in the middle so its UTF-16 length is at most
    *max_units*.

    Keeps a head and a tail with *ellipsis* in the center. If the text already
    fits, it is returned unchanged. If *max_units* is too small to even fit the
    ellipsis, a sliced ellipsis is returned.
    """

    if max_units <= 0:
        return ""
    if not text:
        return ""

    total = tg_len(text)
    if total <= max_units:
        return text

    ellipsis_units = tg_len(ellipsis)
    if ellipsis_units >= max_units:
        # Not enough room for head+tail; return truncated ellipsis.
        return tg_slice_head(ellipsis, max_units)

    remaining = max_units - ellipsis_units
    # Split remaining budget roughly equally between head and tail.
    head_units = remaining // 2
    tail_units = remaining - head_units

    head = tg_slice_head(text, head_units)
    tail = tg_slice_tail(text, tail_units)
    return head + ellipsis + tail
