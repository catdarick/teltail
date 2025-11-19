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

    def build_live_text(self, status: Status, command_argv: list[str], buffer_text: str, dropped_bytes: int = 0) -> str:
        # Note: buffer_text contains the rolling tail of the output (TailBuffer).
        # We simply want to show the last X symbols/lines of buffer_text.
        
        header_builder = HeaderBuilder(self.defaults)
        emoji = header_builder._emoji_for_status(status)
        status_word = "Running" if status == "running" else "Finished" if status == "success" else "Failed"
        header = f"{emoji} {status_word}"
        command_line = " ".join(command_argv)
        cmd_block_text = "```bash\n" + command_line + "\n```"
        
        prefix = (
            header
            + "\n"
            + cmd_block_text
            + "\n\nTail ("
        )

        # Calculate available budget for the body
        fixed_overhead = tg_len(prefix) + tg_len("):\n") + tg_len("```\n") + tg_len("\n```")
        available_for_body = max(0, self.defaults.max_message_length - fixed_overhead)
        
        # Also constrained by tail_length
        body_budget = min(available_for_body, self.defaults.tail_length)
        
        shown_body = ""
        if body_budget > 0:
             # Just take the very end of the buffer that fits budget
             shown_body = tg_slice_tail(buffer_text, body_budget)
        
        # Stats logic
        # Total lines tracked by buffer so far is tricky because buffer rolls.
        # We know dropped_bytes.
        # Let's just report "skipped X bytes" if we cut anything.
        
        # "skipped" = (total_buffer_bytes + dropped_bytes) - shown_bytes
        total_buffer_bytes = len(buffer_text.encode("utf-8", errors="replace"))
        shown_bytes = len(shown_body.encode("utf-8", errors="replace"))
        
        total_avail_bytes = total_buffer_bytes + dropped_bytes
        skipped_bytes = max(0, total_avail_bytes - shown_bytes)
        
        # To report "skipped lines" we need to know how many lines we dropped/skipped.
        # buffer_text has N lines. dropped_bytes corresponds to unknown lines.
        # But user requested "skipped 51 lines" example.
        # If we don't track dropped lines, we can't report them accurately.
        # Let's stick to bytes/KB if lines are unknown, or just bytes.
        # OR we can count lines in buffer_text vs shown_body for the visible part, 
        # but for dropped part we only know bytes.
        # For simplicity and accuracy, let's just show bytes/KB if we have drops.
        
        stats_parts = []
        if skipped_bytes > 0:
             # Try to be helpful with lines if possible (e.g. no drops, just tail cut)
             if dropped_bytes == 0:
                 total_lines = buffer_text.count("\n")
                 shown_lines = shown_body.count("\n")
                 skipped_lines = max(0, total_lines - shown_lines)
                 if skipped_lines > 0:
                     unit = "line" if skipped_lines == 1 else "lines"
                     stats_parts.append(f"{skipped_lines} {unit}")
             
             if skipped_bytes >= 2048:
                kb = skipped_bytes / 1024.0
                stats_parts.append(f"{kb:.1f} KB skipped")
             else:
                stats_parts.append(f"{skipped_bytes} bytes skipped")
        else:
             # If showing everything (including start), show total lines
             total_lines = buffer_text.count("\n")
             unit = "line" if total_lines == 1 else "lines"
             stats_parts.append(f"total {total_lines} {unit}")

        tail_stats = ", ".join(stats_parts)
        if not tail_stats:
            tail_stats = "showing all"

        # Assemble Final
        final_msg = (
            prefix 
            + tail_stats 
            + "):\n"
            + "```\n" 
            + shown_body 
            + "\n```"
        )
        
        if tg_len(final_msg) > self.defaults.max_message_length:
             final_msg = tg_truncate_middle(final_msg, self.defaults.max_message_length)
             
        return final_msg


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
