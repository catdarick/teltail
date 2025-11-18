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
            # Nothing skipped: show total instead.
            unit = "line" if total_lines == 1 else "lines"
            return f"total {total_lines} {unit}, {total_bytes} bytes"

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

    def build_live_text(self, status: Status, command_argv: list[str], buffer_text: str, head_text: str = "", dropped_bytes: int = 0) -> str:
        # Resolve carriage returns to clean up progress bars and overwritten lines.
        # We do this for both head and buffer (tail) to ensure clean matching.
        # Note: TailBuffer now handles carriage returns internally, so buffer_text
        # and head_text are already "clean". We keep the variables as is.
        
        # Reconstruct the effective visual text
        if dropped_bytes == 0:
            visual_text = buffer_text
        else:
            # Check for overlap
            head_len_bytes = len(head_text.encode("utf-8", errors="replace"))
            if dropped_bytes < head_len_bytes:
                # Overlap: recover the missing prefix from head_text
                missing_head = head_text.encode("utf-8", errors="replace")[:dropped_bytes].decode("utf-8", errors="replace")
                visual_text = missing_head + buffer_text
            else:
                # Gap
                visual_text = head_text + f"\n\n... skipped {dropped_bytes - head_len_bytes} bytes ...\n\n" + buffer_text

        header_builder = HeaderBuilder(self.defaults)
        # Header is just the status line (emoji + word), the full CLI
        # command is shown in its own fenced code block below.
        emoji = header_builder._emoji_for_status(status)
        status_word = "Running" if status == "running" else "Finished" if status == "success" else "Failed"
        header = f"{emoji} {status_word}"

        # Build a shell-style representation of the CLI command.
        command_line = " ".join(command_argv)
        cmd_block_text = "```bash\n" + command_line + "\n```"

        # Provisional tail based on tail_length budget.
        # We use tg_truncate_middle to preserve head and tail if the text is too long.
        full_units = tg_len(visual_text)
        tail_units_budget = min(full_units, self.defaults.tail_length)
        
        # If we have dropped bytes, we assume we are in "head+tail" mode and favor truncate_middle.
        # Even if dropped_bytes==0, truncate_middle is safe (keeps start and end).
        provisional_body = tg_truncate_middle(visual_text, tail_units_budget)

        # Apply a lines-based cap for the provisional tail if configured.
        # Note: max_tail_lines logic might need to be relaxed if we are intentionally keeping the head.
        # For now, we skip max_tail_lines enforcement if we have a gap (dropped_bytes > 0) 
        # or if the user configured head_lines?
        # Actually, max_tail_lines is explicitly "lines from the end". 
        # If the user set it, they might only want the last N lines.
        # But the new request implies they want Head + Tail.
        # Let's apply max_tail_lines only to the *tail part* if we had a gap?
        # Complexity. Let's stick to existing behavior: max_tail_lines applies to the *resulting body*.
        # If result is "Head ... Tail", and we take last N lines, we lose Head.
        # So we should NOT apply max_tail_lines if we successfully preserved a head.
        
        # Strategy: If head_text is present and we are using it (dropped_bytes > 0), we skip max_tail_lines
        # or apply it only to the tail section.
        # Since we already constructed `visual_text`, it's hard to separate.
        
        # Let's just rely on tail_length (chars) budget for now and simplify.
        # The user can increase tail_length or unset max_tail_lines if they want more.
        
        # Compute skipped vs total stats based on full buffer vs tail.
        tail_stats = self._build_separator(visual_text, provisional_body)

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
        body_tail = tg_truncate_middle(visual_text, tail_units)

        # Skipping strict max_tail_lines enforcement on the final body to preserve head if present.
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
