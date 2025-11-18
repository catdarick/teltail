"""Orchestration logic for running a child process and updating Telegram."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from asyncio.subprocess import PIPE
from typing import Iterable, Optional

from .config import Config
from .notifier import HeaderBuilder, LiveMessageBuilder, SummaryBuilder
from .string_utils import strip_ansi
from .tail_buffer import TailBuffer
from .telegram_client import TelegramClient, TelegramError, TelegramMessage


async def _read_stream(stream: asyncio.StreamReader, buffer: TailBuffer, is_stderr: bool, do_strip_ansi: bool) -> None:
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        text = chunk.decode("utf-8", errors="replace")
        if do_strip_ansi:
            text = strip_ansi(text)
        # Echo to local terminal.
        target = sys.stderr if is_stderr else sys.stdout
        target.write(text)
        target.flush()
        buffer.append(text)


async def run_with_notifications(config: Config, argv: Iterable[str]) -> int:
    command_argv = list(argv)
    if not command_argv:
        print("[teltail] no command given", file=sys.stderr)
        return 1

    defaults = config.defaults
    header_builder = HeaderBuilder(defaults)
    live_builder = LiveMessageBuilder(defaults)
    summary_builder = SummaryBuilder(defaults)

    client = TelegramClient(config.telegram.bot_token)

    # Initial message send. Child must not start if this fails.
    # Use the same layout as live messages, but with an empty tail.
    from .length_utils import tg_len, tg_truncate_middle

    initial_text = LiveMessageBuilder(defaults).build_live_text("running", command_argv, buffer_text="")

    if tg_len(initial_text) > defaults.max_message_length:
        initial_text = tg_truncate_middle(initial_text, defaults.max_message_length)

    try:
        message = client.send_message(config.telegram.chat_id, initial_text, parse_mode="Markdown")
    except TelegramError as exc:
        print(f"[teltail] failed to send initial Telegram message: {exc}", file=sys.stderr)
        print("[teltail] check your configuration or run 'teltail --configure'", file=sys.stderr)
        return 1

    # Only now start the child process.
    # If merge_stderr is enabled, forward stderr into stdout so we only
    # have a single combined stream to read from.
    if defaults.merge_stderr:
        stderr_opt = asyncio.subprocess.STDOUT
    else:
        stderr_opt = PIPE

    # Child environment: by default we set PYTHONUNBUFFERED=1 so that
    # Python processes behave as if run with -u, which makes streaming
    # output through teltail much more responsive. Users can disable this
    # via the python_unbuffered default or by explicitly setting
    # PYTHONUNBUFFERED in their environment.
    env = os.environ.copy()
    if defaults.python_unbuffered and "PYTHONUNBUFFERED" not in env:
        env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = await asyncio.create_subprocess_exec(
            *command_argv,
            stdout=PIPE,
            stderr=stderr_opt,
            env=env,
        )
    except Exception as exc:
        print(f"[teltail] failed to start child process: {exc}", file=sys.stderr)
        # We already sent the initial message; we can update it once more to failed.
        try:
            failed_header = header_builder.build_header("error", command_argv, defaults.max_message_length)
            client.edit_message(message, failed_header + "\nFailed to start child process.")
        except Exception:
            pass
        return 1

    tail_buffer = TailBuffer(head_lines=defaults.head_lines)

    loop = asyncio.get_running_loop()

    # Signal forwarding: on SIGINT/SIGTERM, forward to child.
    def _handle_signal(signum: int) -> None:
        if proc.returncode is None and proc.pid is not None:
            try:
                os.kill(proc.pid, signum)
            except ProcessLookupError:
                pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal, sig)
        except NotImplementedError:  # pragma: no cover - Windows
            pass

    start_time = time.time()

    async def _update_loop() -> None:
        last_sent_text: Optional[str] = None
        while True:
            await asyncio.sleep(defaults.update_interval_secs)
            if proc.returncode is not None:
                # Child finished; final update done outside.
                break
            try:
                buffer_text = tail_buffer.get_full_text()
                head_text = tail_buffer.get_head_text()
                dropped_bytes = tail_buffer.dropped_bytes
                
                text = live_builder.build_live_text(
                    "running", 
                    command_argv, 
                    buffer_text,
                    head_text=head_text,
                    dropped_bytes=dropped_bytes
                )
                if text != last_sent_text:
                    client.edit_message(message, text, parse_mode="Markdown")
                    last_sent_text = text
            except TelegramError as exc:
                print(f"[teltail] update loop error: {exc}", file=sys.stderr)
                break
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[teltail] unexpected update loop error: {exc}", file=sys.stderr)
                break

    # Reader tasks. When stderr is merged into stdout we only need to read
    # a single combined stream.
    stdout_task = asyncio.create_task(
        _read_stream(proc.stdout, tail_buffer, is_stderr=False, do_strip_ansi=defaults.strip_ansi)  # type: ignore[arg-type]
    )
    if defaults.merge_stderr:
        stderr_task = None
    else:
        stderr_task = asyncio.create_task(
            _read_stream(proc.stderr, tail_buffer, is_stderr=True, do_strip_ansi=defaults.strip_ansi)  # type: ignore[arg-type]
        )

    update_task = asyncio.create_task(_update_loop())

    # Wait for process completion.
    await proc.wait()
    await stdout_task
    if stderr_task is not None:
        await stderr_task

    # Determine final status and edit live message.
    status = "success" if proc.returncode == 0 else "error"
    try:
        buffer_text = tail_buffer.get_full_text()
        head_text = tail_buffer.get_head_text()
        dropped_bytes = tail_buffer.dropped_bytes
        
        final_text = live_builder.build_live_text(
            status, 
            command_argv, 
            buffer_text,
            head_text=head_text,
            dropped_bytes=dropped_bytes
        )
        client.edit_message(message, final_text, parse_mode="Markdown")
    except TelegramError as exc:
        print(f"[teltail] failed to update final live message: {exc}", file=sys.stderr)

    # Final summary message.
    duration = time.time() - start_time
    try:
        summary = summary_builder.build_summary(status, command_argv, proc.returncode or 0, duration)
        client.send_message(config.telegram.chat_id, summary, parse_mode="Markdown")
    except TelegramError as exc:
        print(f"[teltail] failed to send summary message: {exc}", file=sys.stderr)

    # Ensure update loop stops.
    try:
        update_task.cancel()
    except Exception:
        pass
    return proc.returncode or 0
