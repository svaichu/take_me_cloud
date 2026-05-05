# take-me-cloud

A CLI tool for seamless Lightning AI studio management and SSH configuration. Easily list all your accessible studios and automatically synchronize them with your `.ssh/config` file for quick SSH access.

## Introduction

`take-me-cloud` simplifies working with Lightning AI studios by providing a unified command-line interface to:
- List all studios across your teamspaces and organizations
- View studio status and cluster information
- Automatically configure SSH access to your studios
- Preserve non-Lightning SSH hosts while keeping Lightning entries in sync

## Features

1. **Studio Discovery**: Connect to Lightning AI and discover all studios you have access to across teamspaces and organizations.
2. **Studio Listing**: Display a formatted table of all accessible studios with their status, cluster, and metadata.
3. **SSH Configuration**: Synchronize your Lightning studios with `~/.ssh/config`, enabling direct SSH access by studio name while preserving existing non-Lightning hosts.

## Installation

### Using `uv` (Recommended)

```bash
uv env create --python 3.13
uv sync
uv run take-me-cloud --help
```

### Using `pip`

```bash
pip install -e .
take-me-cloud --help
```

## Requirements

- Python >= 3.13
- `lightning-sdk >= 2026.4.23`

Set the following environment variables before using the CLI:
- `LIGHTNING_API_KEY`: Your Lightning AI API key
- `LIGHTNING_USER_ID`: Your Lightning AI user ID

## Usage

### List all accessible studios

```bash
take-me-cloud --list
# or
take-me-cloud -ls
```

Output:
```
Studio                  Teamspace        Owner          Cluster                    State
----------------------  ---------------  -------------  -------------------------  -----------------------
modern-amaranth-ou1r    myml             vaishnavahari  lightning-public-prod      CLOUD_SPACE_STATE_READY
husky-coffee-72g7       myml             vaishnavahari  lightning-public-prod      CLOUD_SPACE_STATE_READY
```

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

## SSH Configuration Details

Once `--lock-ssh` is run, you can SSH directly to any of your studios by name:

```bash
ssh modern-amaranth-ou1r
ssh husky-coffee-72g7
```

The SSH config uses:
- Lightning AI's standard SSH gateway: `ssh.lightning.ai`
- Automatic key-based authentication
- Studio-specific user credentials

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
