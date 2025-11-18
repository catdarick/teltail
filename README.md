# teltail

`teltail` is a small CLI tool that runs a command, streams its output to your
terminal, and maintains a single live Telegram message with the header and tail
of the output. When the command finishes, it edits the live message with the
final status and sends a separate summary message.

## Installation

You can install `teltail` either globally for your user or in a project-local
virtual environment.

### User-level installation (recommended)

Install into your default Python environment so `teltail` is available on your
PATH:

```bash
cd /path/to/teltail
python3 -m pip install .
```

After that, you can run `teltail` from any shell:

```bash
teltail --help
```

If you prefer an isolated user-level install, you can use `pipx` instead:

```bash
cd /path/to/teltail
pipx install .
```

### Project-local development install

For hacking on `teltail` itself, it can be convenient to use a virtual
environment inside the repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .
```

## Configuration

Before the first use you need to configure your Telegram bot token and chat id:

```bash
teltail --configure
```

This writes `~/.config/teltail/config.toml`. You can
also create a project-local `.teltail.toml` that will be merged on top of the
user config.

## Usage

Run a command and mirror its output to Telegram:

```bash
teltail -- python -m this
```

Options are available to override configuration values for a single run. Run
`teltail -h` for the full list.

## Development

The core modules live under the `teltail` package:

- `config` – configuration loading and `--configure` implementation.
- `length_utils` – UTF‑16 based Telegram length utilities.
- `tail_buffer` – rolling tail buffer for process output.
- `telegram_client` – minimal Telegram Bot API client.
- `notifier` – header, live message and summary construction.
- `runner` – main orchestration of subprocess and Telegram updates.
- `cli` – argument parsing and entrypoint.

To run the CLI from a checkout:

```bash
python -m teltail.cli -- echo "hello from teltail"
```
