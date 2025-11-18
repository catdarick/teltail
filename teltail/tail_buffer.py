"""Rolling tail buffer for sanitized process output.

The buffer stores text (typically UTF-8 decoded, ANSI-stripped output) and
keeps at most *max_bytes* of data in memory.
"""

from __future__ import annotations

from collections import deque


class TailBuffer:
    """A bounded rolling text buffer with byte-based trimming.

    The public API operates on Python ``str`` objects. Internally, we track the
    UTF-8 encoded byte length and drop from the front when the limit is
    exceeded. This keeps memory usage bounded while preserving recent output.
    """

    def __init__(self, max_bytes: int = 200_000) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes
        self._chunks: deque[str] = deque()
        self._size_bytes: int = 0

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def append(self, text: str) -> None:
        """Append *text* to the buffer and trim if necessary."""

        if not text:
            return
        self._chunks.append(text)
        self._size_bytes += len(text.encode("utf-8", errors="replace"))
        self._trim()

    def _trim(self) -> None:
        """Trim from the front until the buffer fits into *max_bytes*."""

        while self._chunks and self._size_bytes > self._max_bytes:
            oldest = self._chunks.popleft()
            self._size_bytes -= len(oldest.encode("utf-8", errors="replace"))

    def get_full_text(self) -> str:
        """Return the full buffered text."""

        return "".join(self._chunks)
