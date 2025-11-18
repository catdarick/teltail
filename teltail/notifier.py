"""High-level message construction helpers for teltail.

This module builds headers and full Telegram message texts from a command and
output tail, enforcing the configured length limits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .config import DefaultsConfig
from .length_utils import tg_len, tg_slice_tail, tg_truncate_middle


Status = Literal["running", "success", "error"]


@dataclass
class HeaderBuilder:
    defaults: DefaultsConfig

    def build_command_display(self, command_argv: list[str]) -> str:
        raw = " ".join(command_argv)
        if tg_len(raw) <= self.defaults.max_header_length:
            return raw
        return tg_truncate_middle(raw, self.defaults.max_header_length)

    def _emoji_for_status(self, status: Status) -> str:
        if status == "running":
            return self.defaults.emoji_running
        if status == "success":
            return self.defaults.emoji_ok
        return self.defaults.emoji_error

    def build_header(self, status: Status, command_argv: list[str], max_message_length: int | None = None) -> str:
        command_display = self.build_command_display(command_argv)
        emoji = self._emoji_for_status(status)
        header = f"{emoji} {'Running' if status == 'running' else 'Finished' if status == 'success' else 'Failed'}: {command_display}"
        limit = max_message_length or self.defaults.max_message_length
        if tg_len(header) > limit:
            header = tg_truncate_middle(header, limit)
        return header


@dataclass
class LiveMessageBuilder:
    defaults: DefaultsConfig

    def _build_separator(self, full_text: str, tail_text: str) -> str:
        """Build a separator line, optionally including skipped lines/bytes info.

        ``full_text`` is the entire buffered output, ``tail_text`` is the part
        that will actually be shown as the body. Both are plain text (after any
        ANSI stripping) and may be empty.
        """

        total_lines = full_text.count("\n")
        shown_lines = tail_text.count("\n")
        skipped_lines = max(0, total_lines - shown_lines)

        total_bytes = len(full_text.encode("utf-8", errors="replace"))
        shown_bytes = len(tail_text.encode("utf-8", errors="replace"))
        skipped_bytes = max(0, total_bytes - shown_bytes)

        if skipped_lines <= 0 and skipped_bytes <= 0:
            return "--- tail ---"

        parts: list[str] = []
        if skipped_lines > 0:
            unit = "line" if skipped_lines == 1 else "lines"
            parts.append(f"{skipped_lines} {unit}")
        if skipped_bytes > 0:
            # Show as KB when reasonably large to keep the separator compact.
            if skipped_bytes >= 2048:
                kb = skipped_bytes / 1024.0
                parts.append(f"{kb:.1f} KB")
            else:
                parts.append(f"{skipped_bytes} bytes")
        info = ", ".join(parts)
        return f"skipped {info}"

    def build_live_text(self, status: Status, command_argv: list[str], buffer_text: str) -> str:
        header_builder = HeaderBuilder(self.defaults)
        # Header is just the status line (emoji + word), the full CLI
        # command is shown in its own fenced code block below.
        emoji = header_builder._emoji_for_status(status)
        status_word = "Running" if status == "running" else "Finished" if status == "success" else "Failed"
        header = f"{emoji} {status_word}"

        # Build a shell-style representation of the CLI command.
        command_line = " ".join(command_argv)
        cmd_block_text = "```bash\n" + command_line + "\n```"

        # Provisional tail: we may adjust it after accounting for the
        # information that we will place in the <pre> opening tag.
        full_units = tg_len(buffer_text)
        tail_units_budget = min(full_units, self.defaults.tail_length)
        provisional_tail = tg_slice_tail(buffer_text, tail_units_budget)

    # Compute skipped vs total stats based on full buffer vs tail.
        total_lines = buffer_text.count("\n")
        shown_lines = provisional_tail.count("\n")
        skipped_lines = max(0, total_lines - shown_lines)

        total_bytes = len(buffer_text.encode("utf-8", errors="replace"))
        shown_bytes = len(provisional_tail.encode("utf-8", errors="replace"))
        skipped_bytes = max(0, total_bytes - shown_bytes)

        if skipped_lines > 0 or skipped_bytes > 0:
            # Include how much was skipped.
            parts: list[str] = []
            if skipped_lines > 0:
                unit = "line" if skipped_lines == 1 else "lines"
                parts.append(f"{skipped_lines} {unit}")
            if skipped_bytes > 0:
                parts.append(f"{skipped_bytes} bytes")
            tail_stats = "skipped " + ", ".join(parts)
        else:
            # Nothing skipped: show total instead.
            unit = "line" if total_lines == 1 else "lines"
            tail_stats = f"total {total_lines} {unit}, {total_bytes} bytes"

        # Common prefix for all messages:
        #   ⏳ Running
        #   ```bash
        #   {cli_command}
        #   ```
        #
        #   Tail ({tail_stats}):
        #   ```
        #   {tail}
        #   ```

        # Base header + command block and "Tail (..):" line; we add the
        # tail body and its fences only if there is output.
        prefix = (
            header
            + "\n"  # newline after header
            + cmd_block_text
            + "\n\nTail ("
            + tail_stats
            + "):\n"
        )

        # If there's no buffer_text (should have been handled above) or the
        # tail is empty, just return the prefix.
        if not buffer_text:
            base = prefix
            if tg_len(base) > self.defaults.max_message_length:
                base = tg_truncate_middle(base, self.defaults.max_message_length)
            return base

        # Account for prefix plus opening/closing fences around the tail.
        fixed_overhead = tg_len(prefix) + tg_len("```\n") + tg_len("\n```")
        available_for_body = max(0, self.defaults.max_message_length - fixed_overhead)

        if available_for_body <= 0:
            # No room for tail body; show just the prefix without the fenced
            # block.
            base = prefix.rstrip("\n")
            if tg_len(base) > self.defaults.max_message_length:
                base = tg_truncate_middle(base, self.defaults.max_message_length)
            return base

        tail_units = min(full_units, self.defaults.tail_length, available_for_body)
        body_tail = tg_slice_tail(buffer_text, tail_units)
        if tail_units > 0:
            return prefix + "```\n" + body_tail + "\n```"

        # If we somehow ended up with no tail units, return only the prefix.
        base = prefix.rstrip("\n")
        if tg_len(base) > self.defaults.max_message_length:
            base = tg_truncate_middle(base, self.defaults.max_message_length)
        return base


@dataclass
class SummaryBuilder:
    defaults: DefaultsConfig

    def build_summary(self, status: Status, command_argv: list[str], exit_code: int, duration_secs: float | None) -> str:
        """Build a final summary message in the same shape as live messages.

        Format:

            {emoji} Finished/Failed
            ```bash
            {cli_command}
            ```
            
            Status: {status_word} with exit code {exit_code} in {duration}s
        """

        header_builder = HeaderBuilder(self.defaults)
        emoji = header_builder._emoji_for_status(status)
        status_word = "Finished" if status == "success" else "Failed"
        header = f"{emoji} {status_word}"

        command_line = " ".join(command_argv)
        cmd_block_text = "```bash\n" + command_line + "\n```"

        status_line = f"Status: {status_word} with exit code {exit_code}"
        if duration_secs is not None:
            status_line += f" in {duration_secs:.1f}s"

        base = header + "\n" + cmd_block_text + "\n\n" + status_line
        if tg_len(base) > self.defaults.max_message_length:
            base = tg_truncate_middle(base, self.defaults.max_message_length)
        return base
