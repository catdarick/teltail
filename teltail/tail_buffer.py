"""Rolling tail buffer for sanitized process output.

The buffer stores text and implements a virtual terminal-like behavior for
carriage returns (\\r), ensuring that overwritten lines do not consume
unbounded memory.
"""

from __future__ import annotations

import re
from collections import deque


class TailBuffer:
    """A smart rolling text buffer that handles carriage returns and head preservation.
    
    This buffer acts like a simple terminal:
    - ``\\n`` commits the current line.
    - ``\\r`` returns the cursor to the start of the current line, allowing overwrites.
    
    It maintains a rolling window of the *resultant* lines, keeping total size
    under *max_bytes*. It also preserves the first *head_lines* of output
    indefinitely to keep the context (like startup logs) visible.
    """

    def __init__(self, max_bytes: int = 200_000, head_lines: int = 0) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._max_bytes = max_bytes
        self._head_lines_limit = head_lines
        
        # Buffer state
        self._lines: deque[str] = deque()  # Completed lines (including newline chars)
        self._lines_size_bytes: int = 0    # Total UTF-8 bytes of content in _lines
        
        self._working_chars: list[str] = [] # Current line being built
        self._cursor: int = 0               # Cursor position in _working_chars
        
        # Head preservation
        self._head_lines: list[str] = []   # Frozen head lines
        self._head_frozen = False
        
        # Stats
        self._dropped_bytes: int = 0       # Bytes of *completed lines* dropped from front

    @property
    def max_bytes(self) -> int:
        return self._max_bytes
    
    @property
    def dropped_bytes(self) -> int:
        return self._dropped_bytes

    def append(self, text: str) -> None:
        """Append text, handling newlines and carriage returns."""
        if not text:
            return

        # Fast path: no control characters
        if "\r" not in text and "\n" not in text:
            self._write_chars(text)
            return

        # Split by control characters to process sequentially
        # We use a regex that keeps the delimiters
        parts = re.split(r'(\r|\n)', text)
        
        for part in parts:
            if part == "\r":
                self._cursor = 0
            elif part == "\n":
                self._commit_line()
            elif part:
                self._write_chars(part)

    def _write_chars(self, chars: str) -> None:
        """Write characters to the current working line at the cursor position."""
        needed_len = self._cursor + len(chars)
        current_len = len(self._working_chars)
        
        if needed_len > current_len:
            # Extend the list with placeholders if we are jumping (unlikely with just \r)
            # or just appending
            self._working_chars.extend([""] * (needed_len - current_len))
            
        # Overwrite/Insert
        for i, ch in enumerate(chars):
            self._working_chars[self._cursor + i] = ch
            
        self._cursor += len(chars)

    def _commit_line(self) -> None:
        """Finalize the current working line and push to the buffer."""
        line_str = "".join(self._working_chars) + "\n"
        self._lines.append(line_str)
        
        encoded_len = len(line_str.encode("utf-8", errors="replace"))
        self._lines_size_bytes += encoded_len
        
        # Handle head preservation
        if self._head_lines_limit > 0 and not self._head_frozen:
            self._head_lines.append(line_str)
            if len(self._head_lines) >= self._head_lines_limit:
                self._head_frozen = True
                # Trim excess if we somehow overshot (unlikely with line-by-line)
                self._head_lines = self._head_lines[:self._head_lines_limit]

        # Reset working state
        self._working_chars = []
        self._cursor = 0
        
        self._trim()

    def _trim(self) -> None:
        """Trim old lines if buffer exceeds max_bytes."""
        # We only trim finalized lines. The current working line is always kept.
        while self._lines and self._lines_size_bytes > self._max_bytes:
            dropped_line = self._lines.popleft()
            d_len = len(dropped_line.encode("utf-8", errors="replace"))
            self._lines_size_bytes -= d_len
            self._dropped_bytes += d_len

    def get_full_text(self) -> str:
        """Return the full visible text (tail lines + current working line)."""
        tail = "".join(self._lines)
        current = "".join(self._working_chars)
        return tail + current

    def get_head_text(self) -> str:
        """Return the captured head lines."""
        if self._head_lines_limit <= 0:
            return ""
        return "".join(self._head_lines)
