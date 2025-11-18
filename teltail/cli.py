"""Command line interface for teltail."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .config import ConfigError, load_config, run_configure
from .runner import run_with_notifications


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="teltail", add_help=True)
    parser.add_argument("--configure", action="store_true", help="run interactive configuration and exit")
    parser.add_argument("--config", type=str, help="path to configuration file", default=None)
    parser.add_argument("--chat-id", type=str, help="override Telegram chat id")
    parser.add_argument("--max-message-length", type=int, help="override max message length")
    parser.add_argument("--max-header-length", type=int, help="override max header length")
    parser.add_argument("--tail-length", type=int, help="override tail length (in UTF-16 units)")
    parser.add_argument("--update-interval", type=float, help="override update interval in seconds")
    parser.add_argument("--merge-stderr", action="store_true", help="merge stderr into stdout stream")
    parser.add_argument("--no-merge-stderr", action="store_true", help="do not merge stderr into stdout stream")
    parser.add_argument("--strip-ansi", action="store_true", help="strip ANSI escape codes from Telegram output")
    parser.add_argument("--no-strip-ansi", action="store_true", help="do not strip ANSI escape codes")
    parser.add_argument("--emoji-running", type=str, help="emoji for running state")
    parser.add_argument("--emoji-ok", type=str, help="emoji for success state")
    parser.add_argument("--emoji-error", type=str, help="emoji for error state")
    # Remainder positional: everything after "--" is treated as the command and its args.
    parser.add_argument("cmd", nargs=argparse.REMAINDER, help="command to run")
    return parser


def _apply_overrides(cfg, args) -> None:
    # Telegram overrides
    if args.chat_id:
        cfg.telegram.chat_id = args.chat_id

    # Defaults overrides
    d = cfg.defaults
    if args.max_message_length is not None:
        d.max_message_length = args.max_message_length
    if args.max_header_length is not None:
        d.max_header_length = args.max_header_length
    if args.tail_length is not None:
        d.tail_length = args.tail_length
    if args.update_interval is not None:
        d.update_interval_secs = args.update_interval

    if args.merge_stderr and args.no_merge_stderr:
        print("[teltail] cannot specify both --merge-stderr and --no-merge-stderr", file=sys.stderr)
    elif args.merge_stderr:
        d.merge_stderr = True
    elif args.no_merge_stderr:
        d.merge_stderr = False

    if args.strip_ansi and args.no_strip_ansi:
        print("[teltail] cannot specify both --strip-ansi and --no-strip-ansi", file=sys.stderr)
    elif args.strip_ansi:
        d.strip_ansi = True
    elif args.no_strip_ansi:
        d.strip_ansi = False

    if args.emoji_running is not None:
        d.emoji_running = args.emoji_running
    if args.emoji_ok is not None:
        d.emoji_ok = args.emoji_ok
    if args.emoji_error is not None:
        d.emoji_error = args.emoji_error


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.configure:
        # Interactive mode, no child process.
        config_path = Path(args.config) if args.config else None
        if config_path is None:
            from .config import DEFAULT_CONFIG_PATH

            run_configure(DEFAULT_CONFIG_PATH)
        else:
            run_configure(config_path)
        return 0

    # Normal run: load config first.
    config_path = Path(args.config) if args.config else None
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        path_str = str(config_path or "~/.config/teltail/config.toml")
        print(f"[teltail] config not found/invalid at {path_str}: {exc}", file=sys.stderr)
        print("[teltail] run 'teltail --configure' to create or fix the config", file=sys.stderr)
        return 1

    _apply_overrides(cfg, args)

    cmd = args.cmd
    if not cmd:
        print("[teltail] usage: teltail [options] -- <command> [args...]", file=sys.stderr)
        return 1

    return asyncio.run(run_with_notifications(cfg, cmd))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
