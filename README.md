# teltail

`teltail` is a small CLI tool that runs a command, streams its output to your
terminal, and maintains a single live Telegram message with the header and tail
of the output. When the command finishes, it edits the live message with the
final status and sends a separate summary message.

It's particularly useful for monitoring long-running tasks like model training,
data processing, builds, or any other processes where you want to track progress
remotely without staying connected to your terminal.

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

Before the first use, you need to create a Telegram bot and get your chat ID.
You can follow [this guide](https://gist.github.com/nafiesl/4ad622f344cd1dc3bb1ecbe468ff9f8a)
to learn how to get your bot API token and chat ID.

Once you have those, configure `teltail`:

```bash
teltail --configure
```

This writes `~/.config/teltail/config.toml`. You can
also create a project-local `.teltail.toml` that will be merged on top of the
user config.

## Usage

Run a command and mirror its output to Telegram:

```bash
teltail -- echo "hello from teltail"

# or without the '--'
teltail echo "hello from teltail"
```

Options are available to override configuration values for a single run. 

Example: limit the number of lines shown in the Telegram tail section for a noisy command:

```bash
teltail --max-tail-lines 20 -- find /var/log -type f -name "*.log"
```
Run `teltail -h` for the full options list.

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
