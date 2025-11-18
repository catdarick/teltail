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

    def build_live_text(self, status: Status, command_argv: list[str], buffer_text: str) -> str:
        header_builder = HeaderBuilder(self.defaults)
        header = header_builder.build_header(status, command_argv, self.defaults.max_message_length)
        header_len = tg_len(header) + tg_len("\n")
        available_for_body = max(0, self.defaults.max_message_length - header_len)

        if available_for_body <= 0 or not buffer_text:
            return header

        tail_units = min(tg_len(buffer_text), self.defaults.tail_length, available_for_body)
        body_tail = tg_slice_tail(buffer_text, tail_units)
        if tail_units > 0:
            return header + "\n" + body_tail
        return header


@dataclass
class SummaryBuilder:
    defaults: DefaultsConfig

    def build_summary(self, status: Status, command_argv: list[str], exit_code: int, duration_secs: float | None) -> str:
        header_builder = HeaderBuilder(self.defaults)
        header = header_builder.build_header(status, command_argv, self.defaults.max_message_length)
        status_word = "Finished" if status == "success" else "Failed"
        base = f"{header}\n{status_word} with exit code {exit_code}"
        if duration_secs is not None:
            base += f" in {duration_secs:.1f}s"
        if tg_len(base) > self.defaults.max_message_length:
            base = tg_truncate_middle(base, self.defaults.max_message_length)
        return base
