"""String manipulation utilities for teltail."""

from __future__ import annotations

import re


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*.

    This removes CSI sequences (like colors and cursor movements) but preserves
    standard control characters like \\n and \\r.
    """
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def resolve_carriage_returns(text: str) -> str:
    """Resolve carriage returns in *text* to simulate terminal output.

    This interprets ``\\r`` as moving the cursor to the start of the line,
    causing subsequent characters to overwrite existing ones. ``\\n`` moves
    to the next line.

    Example:
        >>> resolve_carriage_returns("Loading\\rDone   \\n")
        'Done   \\n'
        >>> resolve_carriage_returns("Longer\\rShort")
        'Shortr'
    """
    if "\r" not in text:
        return text

    lines = text.splitlines(keepends=True)
    out_lines: list[str] = []
    current_line: list[str] = []

    def commit_line(newline_char: str = "") -> None:
        # Join the current line segments (simulating overwrite)
        # This is slightly more complex than string slicing if we want to accept
        # that we processed segments incrementally.
        # But actually, my logic below constructs `current_visual` as a string.
        # Let's change current_line to be the string content.
        pass

    current_visual = ""

    for chunk in lines:
        # Identify the line ending
        if chunk.endswith("\r\n"):
            ending = "\r\n"
            content = chunk[:-2]
            is_newline = True
        elif chunk.endswith("\n"):
            ending = "\n"
            content = chunk[:-1]
            is_newline = True
        elif chunk.endswith("\r"):
            ending = "\r"
            content = chunk[:-1]
            is_newline = False
        else:
            ending = ""
            content = chunk
            is_newline = False  # End of string

        # Apply overwrite logic: content overwrites current_visual from start
        if len(content) >= len(current_visual):
            current_visual = content
        else:
            current_visual = content + current_visual[len(content) :]

        if is_newline:
            out_lines.append(current_visual + ending)
            current_visual = ""
    
    if current_visual:
        out_lines.append(current_visual)

    return "".join(out_lines)

