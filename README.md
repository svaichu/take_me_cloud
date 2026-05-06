# take-me-cloud

A CLI tool for seamless Lightning AI studio management and SSH configuration. Easily list all your accessible studios and automatically synchronize them with your `.ssh/config` file for quick SSH access.

## Introduction

`take-me-cloud` simplifies working with Lightning AI studios by providing a unified command-line interface to:
- List all studios across your teamspaces and organizations
- View studio status and cluster information
- Automatically configure SSH access to your studios
- Preserve non-Lightning SSH hosts while keeping Lightning entries in sync

## Features

1. **`--list` / `-ls`**: List all accessible studios across teamspaces and organizations with their status, owner, machine type, and state.
2. **`--lock-ssh`**: Synchronize your Lightning studios with `~/.ssh/config`, enabling direct SSH access while preserving non-Lightning hosts. Automatically removes stale Lightning entries.
3. **`--create-replace`**: Create a new studio with default machine type and cloud provider from config. Automatically deletes any existing studio with the same name.

## Installation

### Using `uv`

```bash
uv tool install take-me-cloud
```

### Using `pip`

```bash
pip install take-me-cloud
```

### Development (Editable Mode)

```bash
pip install -e .
```

Or with `uv`:

```bash
uv sync
```

## Requirements

- Python >= 3.13
- `lightning-sdk >= 2026.4.23`

Set the following environment variables before using the CLI:
- `LIGHTNING_API_KEY`: Your Lightning AI API key
- `LIGHTNING_USER_ID`: Your Lightning AI user ID

## Usage

### Configuration

Before using `take-me-cloud`, create a configuration file at `~/.config/take_me_cloud_config.yaml`:

```yaml
default_machine_type: T4
cloud_provider: AWS
teamspaces:
  - rwth-gut/skillcomp
  - your-teamspace/name
```

### List all accessible studios

```bash
take-me-cloud --list
# or
take-me-cloud -ls
```

Output:
```
Studio                  Teamspace            Owner          Machine Type    State
----------------------  -------------------  -------------  --------------  -----------------------
modern-amaranth-ou1r    rwth-gut/skillcomp   vaishnavahari  T4              CLOUD_SPACE_STATE_READY
husky-coffee-72g7       rwth-gut/skillcomp   vaishnavahari  CPU             CLOUD_SPACE_STATE_READY
```

### Create a new studio

```bash
take-me-cloud --create-replace my-studio
```

This command will:
- Prompt you to select a teamspace from your config file
- Create a new studio named `my-studio` with the default machine type and cloud provider
- Delete any existing studio with the same name
- Show a progress bar during creation

### Synchronize SSH configuration

```bash
take-me-cloud --lock-ssh
```

This command will:
- Ensure Lightning SSH keys exist in `~/.ssh/`
- Add all currently accessible studios to `~/.ssh/config` with proper SSH configuration
- Remove stale Lightning studio entries that are no longer accessible
- Preserve all non-Lightning hosts

Output:
```
SSH config synchronized (lightning_hosts=12, non_lightning_hosts_preserved=1).
```

### SSH Access

Once `--lock-ssh` is run, you can SSH directly to any of your studios by name:

```bash
ssh modern-amaranth-ou1r
ssh husky-coffee-72g7
```

## Development

### Run tests

```bash
uv run python -m unittest discover -s tests -v
```

### Project structure

```
take-me-cloud/
├── take_me_cloud/
│   ├── __init__.py
│   ├── base.py          # Core functionality (listing, SSH config)
│   ├── cli.py           # CLI entry point and argument parsing
├── tests/
│   ├── test_base.py     # Core functionality tests
│   ├── test_cli.py      # CLI tests
├── doc/
│   ├── AGENT.md         # Agent instructions
│   ├── FEATURES.md      # Feature specifications
│   ├── TESTING.md       # Testing requirements
├── README.md
└── pyproject.toml
```

## License

MIT
