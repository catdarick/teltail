"""Configuration loading and interactive --configure mode for teltail.

This module is responsible for:
- Discovering and loading TOML configuration from the default and project
  override locations.
- Validating required settings.
- Implementing the interactive ``--configure`` flow.
"""

from __future__ import annotations

import getpass
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "teltail" / "config.toml"
PROJECT_OVERRIDE_PATH = Path(".teltail.toml")


@dataclass
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass
class DefaultsConfig:
    max_message_length: int = 4096
    max_header_length: int = 256
    max_tail_lines: int = 200
    tail_length: int = 3000
    update_interval_secs: float = 3.0
    merge_stderr: bool = True
    strip_ansi: bool = True
    emoji_running: str = "⏳"
    emoji_ok: str = "✅"
    emoji_error: str = "❌"
    python_unbuffered: bool = True


@dataclass
class Config:
    telegram: TelegramConfig
    defaults: DefaultsConfig


class ConfigError(Exception):
    pass


def _load_toml(path: Path) -> Dict[str, Any]:
    with path.open("rb") as f:
        return tomllib.load(f)


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* onto *base* without mutating inputs."""

    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge_dicts(result[k], v)
        else:
            result[k] = v
    return result


def load_config(explicit_path: Optional[Path] = None) -> Config:
    """Load and validate configuration.

    Search order:
    - explicit_path if provided
    - default config path
    - project override ``.teltail.toml`` is merged on top of the base config

    Raises ``ConfigError`` on any issue.
    """

    base_path = explicit_path or DEFAULT_CONFIG_PATH
    if not base_path.exists():
        raise ConfigError(
            f"config not found at {base_path}. Run 'teltail --configure' to create it."
        )

    try:
        base_data = _load_toml(base_path)
    except Exception as exc:
        raise ConfigError(f"failed to parse config at {base_path}: {exc}") from exc

    data: Dict[str, Any] = base_data

    if PROJECT_OVERRIDE_PATH.exists():
        try:
            override_data = _load_toml(PROJECT_OVERRIDE_PATH)
            data = _merge_dicts(data, override_data)
        except Exception as exc:
            raise ConfigError(f"failed to parse project override at {PROJECT_OVERRIDE_PATH}: {exc}") from exc

    telegram = data.get("telegram") or {}
    if not isinstance(telegram, dict):
        raise ConfigError("[telegram] section must be a table")

    bot_token = telegram.get("bot_token")
    chat_id = telegram.get("chat_id")
    if not bot_token or not isinstance(bot_token, str):
        raise ConfigError("telegram.bot_token is required and must be a string")
    if not chat_id or not isinstance(chat_id, (str, int)):
        raise ConfigError("telegram.chat_id is required and must be a string or int")

    defaults_data = data.get("defaults") or {}
    if not isinstance(defaults_data, dict):
        raise ConfigError("[defaults] section must be a table if present")

    def _get_int(key: str, default: int) -> int:
        v = defaults_data.get(key, default)
        if isinstance(v, bool):
            raise ConfigError(f"defaults.{key} must be an integer, not bool")
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ConfigError(f"defaults.{key} must be an integer")
        if iv <= 0:
            raise ConfigError(f"defaults.{key} must be positive")
        return iv

    def _get_float(key: str, default: float) -> float:
        v = defaults_data.get(key, default)
        try:
            fv = float(v)
        except (TypeError, ValueError):
            raise ConfigError(f"defaults.{key} must be a number")
        if fv <= 0:
            raise ConfigError(f"defaults.{key} must be positive")
        return fv

    def _get_bool(key: str, default: bool) -> bool:
        v = defaults_data.get(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            if lowered in {"1", "true", "yes", "y", "on"}:
                return True
            if lowered in {"0", "false", "no", "n", "off"}:
                return False
        raise ConfigError(f"defaults.{key} must be a boolean")

    def _get_str(key: str, default: str) -> str:
        v = defaults_data.get(key, default)
        if not isinstance(v, str):
            raise ConfigError(f"defaults.{key} must be a string")
        return v

    defaults = DefaultsConfig(
        max_message_length=_get_int("max_message_length", DefaultsConfig.max_message_length),
        max_header_length=_get_int("max_header_length", DefaultsConfig.max_header_length),
        max_tail_lines=_get_int("max_tail_lines", DefaultsConfig.max_tail_lines),
        tail_length=_get_int("tail_length", DefaultsConfig.tail_length),
        update_interval_secs=_get_float("update_interval_secs", DefaultsConfig.update_interval_secs),
        merge_stderr=_get_bool("merge_stderr", DefaultsConfig.merge_stderr),
        strip_ansi=_get_bool("strip_ansi", DefaultsConfig.strip_ansi),
        emoji_running=_get_str("emoji_running", DefaultsConfig.emoji_running),
        emoji_ok=_get_str("emoji_ok", DefaultsConfig.emoji_ok),
    emoji_error=_get_str("emoji_error", DefaultsConfig.emoji_error),
    python_unbuffered=_get_bool("python_unbuffered", DefaultsConfig.python_unbuffered),
    )

    tg_cfg = TelegramConfig(bot_token=str(bot_token), chat_id=str(chat_id))
    return Config(telegram=tg_cfg, defaults=defaults)


def _prompt(prompt: str, default: Optional[str] = None, secret: bool = False) -> str:
    if default is not None:
        full = f"{prompt} [{default}]: "
    else:
        full = f"{prompt}: "
    if secret:
        value = getpass.getpass(full)
    else:
        value = input(full)
    if not value and default is not None:
        return default
    return value


def run_configure(path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Interactive configuration writer for ``teltail --configure``."""

    print(f"[teltail] configuring teltail at {path}")

    # Base defaults from our DefaultsConfig dataclass.
    defaults = DefaultsConfig()

    bot_token = _prompt("Telegram bot token", secret=True)
    chat_id = _prompt("Telegram chat id")

    def _prompt_int(name: str, current: int) -> int:
        raw = _prompt(name, default=str(current))
        try:
            value = int(raw)
        except ValueError:
            print(f"[teltail] invalid integer for {name}, keeping default {current}")
            return current
        if value <= 0:
            print(f"[teltail] {name} must be positive, keeping default {current}")
            return current
        return value

    def _prompt_float(name: str, current: float) -> float:
        raw = _prompt(name, default=str(current))
        try:
            value = float(raw)
        except ValueError:
            print(f"[teltail] invalid number for {name}, keeping default {current}")
            return current
        if value <= 0:
            print(f"[teltail] {name} must be positive, keeping default {current}")
            return current
        return value

    def _prompt_bool(name: str, current: bool) -> bool:
        default_str = "yes" if current else "no"
        raw = _prompt(name + " (yes/no)", default=default_str)
        lowered = raw.strip().lower()
        if lowered in {"", "y", "yes", "true", "1"}:
            return True
        if lowered in {"n", "no", "false", "0"}:
            return False
        print(f"[teltail] invalid boolean for {name}, keeping default {current}")
        return current

    max_message_length = _prompt_int("max_message_length", defaults.max_message_length)
    max_header_length = _prompt_int("max_header_length", defaults.max_header_length)
    tail_length = _prompt_int("tail_length", defaults.tail_length)
    max_tail_lines = _prompt_int("max_tail_lines", defaults.max_tail_lines)
    update_interval_secs = _prompt_float("update_interval_secs", defaults.update_interval_secs)
    merge_stderr = _prompt_bool("merge_stderr", defaults.merge_stderr)
    strip_ansi = _prompt_bool("strip_ansi", defaults.strip_ansi)

    emoji_running = _prompt("emoji_running", default=defaults.emoji_running)
    emoji_ok = _prompt("emoji_ok", default=defaults.emoji_ok)
    emoji_error = _prompt("emoji_error", default=defaults.emoji_error)
    python_unbuffered = _prompt_bool("python_unbuffered", defaults.python_unbuffered)

    config_dir = path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    content = """[telegram]
"""
    content += f"bot_token = \"{bot_token}\"\n"
    content += f"chat_id = \"{chat_id}\"\n\n"

    content += """[defaults]
"""
    content += f"max_message_length = {max_message_length}\n"
    content += f"max_header_length = {max_header_length}\n"
    content += f"tail_length = {tail_length}\n"
    content += f"max_tail_lines = {max_tail_lines}\n"
    content += f"update_interval_secs = {update_interval_secs}\n"
    content += f"merge_stderr = {str(merge_stderr).lower()}\n"
    content += f"strip_ansi = {str(strip_ansi).lower()}\n"
    content += f"emoji_running = \"{emoji_running}\"\n"
    content += f"emoji_ok = \"{emoji_ok}\"\n"
    content += f"emoji_error = \"{emoji_error}\"\n"
    content += f"python_unbuffered = {str(python_unbuffered).lower()}\n"

    # Write with 0600 permissions.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        f.write(content)

    # Ensure permissions are 0600 on platforms that support chmod.
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except PermissionError:
        # Best-effort; continue.
        pass

    print(f"[teltail] configuration saved to {path}")
