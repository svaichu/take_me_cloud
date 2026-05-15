
"""Lightning AI studio helpers for take-me-cloud."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
import json
import os
import shlex
import threading
import time

import yaml
from lightning_sdk.api import TeamspaceApi, UserApi
from lightning_sdk.cli.legacy.configure import _download_ssh_keys
from lightning_sdk.cli.legacy.generate import _generate_ssh_config
from lightning_sdk.lightning_cloud.login import Auth
from lightning_sdk.studio import Studio
from tqdm import tqdm


CONFIG_FILENAME = "take_me_cloud_config.yaml"
LIGHTNING_HOSTNAME = "ssh.lightning.ai"
DEFAULT_MACHINE = "CPU"
DEFAULT_CLOUD_PROVIDER = "AWS"
BASH_HISTORY_COMMANDS = [
	"uv venv /home/zeus/venv",
	"source /home/zeus/venv/bin/activate",
	"uv sync --active",
	"uv pip install -e .",
	"uv pip list",
]
REMOTE_VSCODE_EXTENSIONS = [
	"ms-python.python",
	"lfs.vscode-emacs-friendly",
	"ms-toolsai.jupyter",
]


@dataclass(frozen=True, slots=True)
class StudioSummary:
	"""A compact view of a Lightning AI studio."""

	name: str
	teamspace: str
	owner: str
	cluster: str | None = None
	machine_type: str | None = None
	state: str | None = None
	description: str | None = None
	studio_id: str | None = None
	owner_type: str = "user"


def _config_path() -> Path:
	return Path.home() / ".config" / CONFIG_FILENAME


def _split_teamspace_label(teamspace_label: str) -> tuple[str, str]:
	if "/" not in teamspace_label:
		raise ValueError(
			f"Invalid teamspace name '{teamspace_label}'. Expected 'owner/teamspace'."
		)
	owner, teamspace_name = teamspace_label.split("/", 1)
	if not owner or not teamspace_name:
		raise ValueError(
			f"Invalid teamspace name '{teamspace_label}'. Expected 'owner/teamspace'."
		)
	return owner, teamspace_name


def _teamspace_label(owner: str, teamspace_name: str) -> str:
	return f"{owner}/{teamspace_name}"


def _teamspace_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
	entries = config.get("teamspace") or config.get("teamspaces") or []
	if not isinstance(entries, list):
		raise ValueError("Config 'teamspace' must be a list of mappings.")

	teamspace_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("name")]
	if not teamspace_entries:
		raise ValueError("No teamspaces found in configuration.")
	return teamspace_entries


def authenticate_lightning_from_env() -> Auth:
	"""Create a Lightning auth object from the shell environment."""

	api_key = os.getenv("LIGHTNING_API_KEY")
	user_id = os.getenv("LIGHTNING_USER_ID")
	if api_key:
		auth = Auth(user_id=user_id, api_key=api_key) if user_id else Auth(api_key=api_key)
	else:
		auth = Auth()
	auth.authenticate()
	if not auth.api_key:
		raise ValueError("Set LIGHTNING_API_KEY or sign in to Lightning before running take-me-cloud.")
	return auth


def _studio_state(studio: object) -> str | None:
	state = getattr(studio, "state", None)
	if state is None:
		state = getattr(studio, "code_status", None)
	if state is None:
		status = getattr(studio, "status", None)
		if status is not None:
			state = getattr(status, "state", None) or getattr(status, "status", None)
	return str(state) if state is not None else None


def _extract_machine_type(studio: object) -> str | None:
	code_config = getattr(studio, "code_config", None)
	if code_config is not None:
		compute_config = getattr(code_config, "compute_config", None)
		if compute_config is not None:
			instance_type = getattr(compute_config, "instance_type", None)
			if instance_type:
				return str(instance_type)

	machine = getattr(studio, "machine", None)
	if machine is not None:
		machine_name = getattr(machine, "name", None)
		if machine_name:
			return str(machine_name)
		instance_type = getattr(machine, "instance_type", None)
		if instance_type:
			return str(instance_type)

	return None


def _resolve_authed_user() -> tuple[str, str, UserApi]:
	auth = authenticate_lightning_from_env()
	user_api = UserApi()
	username = os.getenv("LIGHTNING_USERNAME")
	if auth.user_id:
		user = user_api._get_user_by_id(auth.user_id)
	elif username:
		user = user_api.get_user(username)
	else:
		raise ValueError(
			"Unable to resolve the Lightning user. Set LIGHTNING_USER_ID or LIGHTNING_USERNAME, or sign in to Lightning."
		)

	user_id_value = getattr(user, "id", None) or getattr(user, "user_id", None)
	user_name_value = getattr(user, "username", None) or getattr(user, "name", None)
	if not user_id_value or not user_name_value:
		raise ValueError("Could not resolve the authenticated Lightning user.")

	return str(user_id_value), str(user_name_value), user_api


def _collect_owned_teamspaces(
	user_id: str,
	user_name: str,
	api: TeamspaceApi,
	user_api: UserApi,
) -> Iterable[tuple[str, str, object]]:
	owner_names: dict[str, tuple[str, str]] = {user_id: (user_name, "user")}
	for organization in user_api._get_organizations_for_authed_user() or []:
		owner_names[getattr(organization, "id", "")] = (getattr(organization, "name", ""), "org")

	for owner_id, (owner_name, owner_type) in owner_names.items():
		if not owner_id:
			continue
		for teamspace in api.list_teamspaces(owner_id=owner_id) or []:
			yield owner_name, owner_type, teamspace


def list_existing_studios() -> list[StudioSummary]:
	"""List all studios accessible to the authenticated Lightning AI user."""

	user_id, user_name, user_api = _resolve_authed_user()
	api = TeamspaceApi()

	studios: list[StudioSummary] = []
	seen_teamspaces: set[str] = set()

	for owner_name, owner_type, teamspace in _collect_owned_teamspaces(user_id, user_name, api, user_api):
		teamspace_id = getattr(teamspace, "id", None)
		teamspace_name = getattr(teamspace, "name", "")
		if not teamspace_id or teamspace_id in seen_teamspaces:
			continue
		seen_teamspaces.add(teamspace_id)

		teamspace_label = _teamspace_label(owner_name, teamspace_name)
		for studio in api.list_studios(teamspace_id=teamspace_id):
			studios.append(
				StudioSummary(
					name=getattr(studio, "name", ""),
					teamspace=teamspace_label,
					owner=owner_name,
					cluster=getattr(studio, "cluster_id", None),
					machine_type=_extract_machine_type(studio),
					state=_studio_state(studio),
					description=getattr(studio, "description", None),
					studio_id=getattr(studio, "id", None),
					owner_type=owner_type,
				)
			)

	return studios


def _normalize_state(state: str | None) -> str:
	if not state:
		return "-"
	return str(state).replace("_", " ").strip().lower()


def format_studios(studios: Iterable[StudioSummary]) -> str:
	"""Render studios grouped by teamspace."""

	rows = list(studios)
	if not rows:
		return "No studios found."

	grouped: dict[str, list[StudioSummary]] = {}
	for row in rows:
		grouped.setdefault(row.teamspace, []).append(row)

	lines: list[str] = []
	for index, teamspace in enumerate(sorted(grouped)):
		if index:
			lines.append("")
		lines.append(f"Teamspace: {teamspace}")

		headers = ["NAME", "OWNER", "MACHINE TYPE", "STATE"]
		teamspace_rows = sorted(grouped[teamspace], key=lambda row: row.name)
		rendered_rows = [
			[row.name, row.owner, row.machine_type or "-", _normalize_state(row.state)]
			for row in teamspace_rows
		]

		widths = [len(header) for header in headers]
		for row in rendered_rows:
			for column_index, value in enumerate(row):
				widths[column_index] = max(widths[column_index], len(value))

		def render(values: list[str]) -> str:
			padded = [value.ljust(widths[column_index]) for column_index, value in enumerate(values)]
			return "  " + "  ".join(padded)

		lines.append(render(headers))
		lines.append("  " + "  ".join("─" * width for width in widths))
		for row in rendered_rows:
			lines.append(render(row))

	return "\n".join(lines)


def _start_with_progress(
	studio: Studio,
	machine: str,
	*,
	label: str = "Starting studio",
	poll_interval: float = 1.0,
	timeout: int = 600,
) -> None:
	"""Start a studio and display a progress bar while waiting."""

	errors: list[BaseException] = []

	def _target() -> None:
		try:
			studio.start(machine=machine)
		except BaseException as exc:  # pragma: no cover - surfaced through errors list
			errors.append(exc)

	thread = threading.Thread(target=_target, daemon=True)
	thread.start()

	elapsed = 0.0
	with tqdm(total=timeout, desc=label, unit="s", leave=True) as progress:
		while thread.is_alive() and elapsed < timeout:
			time.sleep(poll_interval)
			elapsed += poll_interval
			progress.update(min(poll_interval, timeout - progress.n))

		if thread.is_alive():
			raise TimeoutError(f"Timed out while {label.lower()}.")

		thread.join()
		if progress.n < timeout:
			progress.update(timeout - progress.n)

	if errors:
		raise RuntimeError(f"Failed while {label.lower()}.") from errors[0]


def _ensure_lightning_ssh_keys(auth: Auth, ssh_dir: Path) -> Path:
	"""Ensure Lightning SSH key pair exists and return private key path."""

	key_path = ssh_dir / "lightning_rsa"
	pub_path = ssh_dir / "lightning_rsa.pub"
	if key_path.exists() and pub_path.exists():
		return key_path

	_download_ssh_keys(
		api_key=auth.api_key,
		key_id="",
		ssh_home=ssh_dir,
		ssh_key_name="lightning_rsa",
		overwrite=False,
	)
	return key_path


def _split_ssh_config_blocks(lines: list[str]) -> tuple[list[str], list[list[str]]]:
	preamble: list[str] = []
	blocks: list[list[str]] = []
	current: list[str] | None = None

	for line in lines:
		if line.strip().startswith("Host "):
			if current is not None:
				blocks.append(current)
			current = [line]
			continue

		if current is None:
			preamble.append(line)
		else:
			current.append(line)

	if current is not None:
		blocks.append(current)

	return preamble, blocks


def _is_lightning_host_block(block: list[str]) -> bool:
	for line in block:
		stripped = line.strip().lower()
		if stripped.startswith("hostname "):
			hostname = stripped.split(maxsplit=1)[1].strip()
			if hostname == LIGHTNING_HOSTNAME:
				return True
	return False


def _render_lightning_host_block(host: str, studio_id: str, key_path: Path) -> list[str]:
	config = _generate_ssh_config(key_path=str(key_path), host=host, user=f"s_{studio_id}")
	return [line.rstrip() for line in config.strip("\n").splitlines()]


def _ensure_unique_studio_names(studios: Iterable[StudioSummary]) -> None:
	seen: dict[str, StudioSummary] = {}
	duplicates: list[str] = []
	for studio in studios:
		previous = seen.get(studio.name)
		if previous is not None and previous.teamspace != studio.teamspace:
			duplicates.append(studio.name)
		else:
			seen[studio.name] = studio

	if duplicates:
		unique = ", ".join(sorted(set(duplicates)))
		raise ValueError(
			"Studio names must be unique across all teamspaces and organizations. "
			f"Rename these studios before syncing SSH: {unique}."
		)


def lock_lightning_ssh_config(studios: Iterable[StudioSummary]) -> tuple[int, int]:
	"""Sync Lightning hosts in ~/.ssh/config and return counts of preserved and synced hosts."""

	rows = list(studios)
	_ensure_unique_studio_names(rows)

	auth = authenticate_lightning_from_env()
	ssh_dir = Path.home() / ".ssh"
	ssh_dir.mkdir(parents=True, exist_ok=True)

	key_path = _ensure_lightning_ssh_keys(auth, ssh_dir)
	config_path = ssh_dir / "config"

	rows_by_host: dict[str, StudioSummary] = {}
	for row in rows:
		if row.name and row.studio_id:
			rows_by_host[row.name] = row

	existing_lines = []
	if config_path.exists():
		existing_lines = config_path.read_text(encoding="utf-8").splitlines()

	preamble, blocks = _split_ssh_config_blocks(existing_lines)
	non_lightning_blocks = [block for block in blocks if not _is_lightning_host_block(block)]

	out_lines: list[str] = []
	out_lines.extend(preamble)
	if out_lines and out_lines[-1].strip():
		out_lines.append("")

	for index, block in enumerate(non_lightning_blocks):
		if index and out_lines and out_lines[-1].strip():
			out_lines.append("")
		out_lines.extend(block)

	if rows_by_host:
		if out_lines and out_lines[-1].strip():
			out_lines.append("")

		for index, host in enumerate(sorted(rows_by_host)):
			if index and out_lines and out_lines[-1].strip():
				out_lines.append("")
			studio = rows_by_host[host]
			out_lines.extend(_render_lightning_host_block(host, studio.studio_id or "", key_path))

	content = "\n".join(out_lines)
	if content and not content.endswith("\n"):
		content += "\n"
	config_path.write_text(content, encoding="utf-8")

	return len(non_lightning_blocks), len(rows_by_host)


def load_config() -> dict[str, Any]:
	"""Load configuration from ~/.config/take_me_cloud_config.yaml."""

	config_path = _config_path()
	if not config_path.exists():
		raise FileNotFoundError(
			f"Config file not found at {config_path}. Create it before using take-me-cloud."
		)

	with config_path.open("r", encoding="utf-8") as handle:
		config = yaml.safe_load(handle) or {}

	if "Lightning AI" in config and isinstance(config["Lightning AI"], dict):
		return config["Lightning AI"]

	if isinstance(config, dict):
		return config

	raise ValueError("Config file is not valid YAML.")


def get_teamspace_names_from_config(config: dict[str, Any]) -> list[str]:
	return [entry["name"] for entry in _teamspace_entries(config)]


def get_default_machine_for_teamspace(config: dict[str, Any], teamspace_name: str) -> str:
	for entry in _teamspace_entries(config):
		if entry.get("name") == teamspace_name:
			return str(entry.get("machine_default") or config.get("machine_default") or DEFAULT_MACHINE)
	return str(config.get("machine_default") or DEFAULT_MACHINE)


def select_teamspace_interactive(teamspace_names: list[str]) -> str:
	if not teamspace_names:
		raise ValueError("No teamspaces available.")

	if len(teamspace_names) == 1:
		return teamspace_names[0]

	print("Available teamspaces:")
	for index, teamspace_name in enumerate(teamspace_names, start=1):
		print(f"  {index}. {teamspace_name}")

	while True:
		choice = input("Select teamspace (number): ").strip()
		try:
			selection = int(choice) - 1
		except ValueError:
			print("Please enter a valid number.")
			continue

		if 0 <= selection < len(teamspace_names):
			return teamspace_names[selection]

		print(f"Please enter a number between 1 and {len(teamspace_names)}.")


def _get_teamspace_entry(config: dict[str, Any], teamspace_name: str) -> dict[str, Any]:
	for entry in _teamspace_entries(config):
		if entry.get("name") == teamspace_name:
			return entry
	raise ValueError(f"Teamspace '{teamspace_name}' not found in configuration.")


def _resolve_existing_studio(studio_name: str, studios: Iterable[StudioSummary]) -> StudioSummary | None:
	for studio in studios:
		if studio.name == studio_name:
			return studio
	return None


def _delete_existing_studio(studio_name: str, studio: StudioSummary) -> None:
	owner, teamspace_name = _split_teamspace_label(studio.teamspace)
	kwargs: dict[str, Any] = {
		"name": studio_name,
		"teamspace": teamspace_name,
	}
	if studio.owner_type == "org":
		kwargs["org"] = owner
	else:
		kwargs["user"] = owner

	existing = Studio(**kwargs)
	existing.delete()


def _seed_bash_history(studio: Studio) -> None:
	script = "cat >> \"$HOME/.bash_history\" <<'EOF'\n"
	script += "\n".join(BASH_HISTORY_COMMANDS)
	script += "\nEOF"
	studio.run(f"bash -lc {shlex.quote(script)}")


def _install_remote_vscode_extensions(studio: Studio) -> None:
	install_flags = " ".join(f"--install-extension {shlex.quote(extension)}" for extension in REMOTE_VSCODE_EXTENSIONS)
	command = (
		"if command -v code-server >/dev/null 2>&1; then "
		f"code-server {install_flags}; "
		"elif command -v code >/dev/null 2>&1; then "
		f"code {install_flags}; "
		"else echo 'Neither code-server nor code is available on the studio.' >&2; exit 1; fi"
	)
	studio.run(command)


def _prepare_cloned_repo(studio: Studio, repository_name: str) -> None:
	repo_name = repository_name.strip().replace("/", "")
	if not repo_name:
		raise ValueError("Repository name cannot be empty.")

	clone_command = (
		f"cd \"$HOME\" && git clone https://github.com/svaichu/{repo_name}.git \"{repo_name}\""
	)
	studio.run(clone_command)

	settings_json = json.dumps(
		{
			"python.pythonPath": "/home/zeus/venv/bin/python",
			"python.terminal.activateEnvironment": True,
		},
		indent=4,
	)
	settings_command = (
		f"cd \"$HOME/{repo_name}\" && mkdir -p .vscode && cat > .vscode/settings.json <<'EOF'\n"
		f"{settings_json}\nEOF"
	)
	studio.run(settings_command)

	_install_remote_vscode_extensions(studio)


def create_or_replace_studio(studio_name: str) -> Studio:
	"""Create or replace a studio with the given name."""

	config = load_config()
	teamspace_names = get_teamspace_names_from_config(config)
	selected_teamspace_full = select_teamspace_interactive(teamspace_names)
	teamspace_entry = _get_teamspace_entry(config, selected_teamspace_full)

	owner, teamspace_name = _split_teamspace_label(selected_teamspace_full)
	owner_type = str(teamspace_entry.get("owner_type") or "user").lower()
	if owner_type not in {"user", "org"}:
		raise ValueError(
			f"Invalid owner_type '{owner_type}' for teamspace '{selected_teamspace_full}'."
		)

	machine_type = get_default_machine_for_teamspace(config, selected_teamspace_full)
	cloud_provider = str(config.get("cloud_provider") or DEFAULT_CLOUD_PROVIDER)

	existing_studio = _resolve_existing_studio(studio_name, list_existing_studios())
	if existing_studio is not None:
		_delete_existing_studio(studio_name, existing_studio)

	studio_kwargs: dict[str, Any] = {
		"name": studio_name,
		"teamspace": teamspace_name,
		"create_ok": True,
		"cloud_provider": cloud_provider,
	}
	if owner_type == "org":
		studio_kwargs["org"] = owner
	else:
		studio_kwargs["user"] = owner

	studio = Studio(**studio_kwargs)
	_start_with_progress(studio, machine=machine_type)
	_seed_bash_history(studio)
	return studio


def go_studio(studio_name: str) -> Studio:
	"""Create or replace a studio, then clone the matching repository and install editor tooling."""

	normalized_name = studio_name.strip().replace("/", "")
	if not normalized_name:
		raise ValueError("Studio name cannot be empty.")

	studio = create_or_replace_studio(normalized_name)
	_prepare_cloned_repo(studio, normalized_name)
	return studio


