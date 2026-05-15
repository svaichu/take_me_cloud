# take-me-cloud

`take-me-cloud` is a CLI for working with Lightning AI studios from your shell. It can list every studio you can access, sync Lightning SSH entries into `~/.ssh/config`, create or replace studios from a local config file, and bootstrap a fresh studio for repository work.

## Introduction

The CLI authenticates with Lightning AI through `LIGHTNING_API_KEY` and `LIGHTNING_USER_ID`. It uses those credentials to discover your organizations, teamspaces, and studios.

## Installation

```bash
pip install take_me_cloud
```

```bash
uv tool install take_me_cloud
```

For development:

```bash
pip install -e .
```

## Configuration

Create `~/.config/take_me_cloud_config.yaml` with a `Lightning AI` section:

```yaml
Lightning AI:
  machine_default: T4
  cloud_provider: AWS
  teamspace:
    - name: rwth-gut/skillcomp
      owner_type: org
    - name: vaishnavahari/myml
      owner_type: user
      machine_default: CPU
```

`teamspace` entries are shown interactively when you create a studio. Each entry must use `owner/teamspace` naming.

## Usage

### List studios

```bash
take-me-cloud --list
take-me-cloud -ls
```

The output is grouped by teamspace and shows the studio name, owner, machine type, and current state.

### Sync SSH config

```bash
take-me-cloud --lock-ssh
```

This preserves non-Lightning SSH hosts, removes stale Lightning entries, and writes the current accessible studios into `~/.ssh/config`.

### Create or replace a studio

```bash
take-me-cloud --create-replace my-studio
```

The CLI prompts for a teamspace from the config file, deletes any existing studio with the same name, starts the replacement with the configured machine type, and seeds the zsh history with common setup commands.

### Go studio

```bash
take-me-cloud --go-studio my-repo
```

This creates or replaces a studio, clones `svaichu/my-repo` into the studio home directory, writes `.vscode/settings.json`, and installs the requested VS Code extensions on the remote environment.

### Version

```bash
take-me-cloud --version
take-me-cloud -v
```

## Development

Run the tests with:

```bash
uv run python -m unittest discover -s tests -v
```

## Project Layout

- `take_me_cloud/base.py`: Lightning helpers and SSH/config logic
- `take_me_cloud/cli.py`: Argument parsing and command dispatch
- `tests/`: Unit tests for the core flows
