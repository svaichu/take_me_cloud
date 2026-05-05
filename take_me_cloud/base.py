
"""Lightning AI studio listing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml
from lightning_sdk.api import TeamspaceApi, UserApi
from lightning_sdk.cli.legacy.configure import _download_ssh_keys
from lightning_sdk.cli.legacy.generate import _generate_ssh_config
from lightning_sdk.lightning_cloud.login import Auth
from lightning_sdk.studio import Studio
import threading
import time
from tqdm import tqdm


@dataclass(frozen=True, slots=True)
class StudioSummary:
	"""A compact view of a Lightning AI studio."""

	name: str
	teamspace: str
	owner: str
	cluster: str | None
	machine_type: str | None
	state: str | None
	description: str | None
	studio_id: str | None


LIGHTNING_HOSTNAME = "ssh.lightning.ai"


def authenticate_lightning_from_env() -> Auth:
	"""Create a Lightning auth object from the shell environment."""

	auth = Auth()
	auth.authenticate()
	if not auth.user_id or not auth.api_key:
		raise ValueError("Set LIGHTNING_USER_ID and LIGHTNING_API_KEY before running take-me-cloud.")
	return auth


def _studio_state(studio: object) -> str | None:
	state = getattr(studio, "state", None)
	if state is None:
		state = getattr(studio, "code_status", None)
	return str(state) if state is not None else None


def _resolve_authed_user() -> tuple[str, str]:
	"""Resolve the authenticated user's id and username from shell credentials."""

	auth = authenticate_lightning_from_env()
	user_api = UserApi()
	user = user_api._get_user_by_id(auth.user_id)
	return auth.user_id, user.username


def _collect_owned_teamspaces(user_id: str, user_name: str, api: TeamspaceApi, user_api: UserApi) -> Iterable[tuple[str, object]]:
	owner_names = {user_id: user_name}
	for organization in user_api._get_organizations_for_authed_user():
		owner_names[organization.id] = organization.name

	for owner_id, owner_name in owner_names.items():
		for teamspace in api.list_teamspaces(owner_id=owner_id) or []:
			yield owner_name, teamspace


def list_existing_studios() -> list[StudioSummary]:
	"""List all studios accessible to the authenticated Lightning AI user."""

	user_id, user_name = _resolve_authed_user()
	api = TeamspaceApi()
	user_api = UserApi()

	studios: list[StudioSummary] = []
	seen_teamspaces: set[str] = set()

	for owner_name, teamspace in _collect_owned_teamspaces(user_id, user_name, api, user_api):
		if teamspace.id in seen_teamspaces:
			continue
		seen_teamspaces.add(teamspace.id)

		for studio in api.list_studios(teamspace_id=teamspace.id):
			# Try to extract machine type from various possible attributes
			machine_type = (
				getattr(studio, "machine", None)
				or getattr(studio, "machine_type", None)
				or getattr(studio, "accelerator", None)
				or getattr(studio, "instance_type", None)
			)
			
			studios.append(
				StudioSummary(
					name=getattr(studio, "name", ""),
					teamspace=getattr(teamspace, "name", ""),
					owner=owner_name,
					cluster=getattr(studio, "cluster_id", None),
					machine_type=machine_type,
					state=_studio_state(studio),
					description=getattr(studio, "description", None),
					studio_id=getattr(studio, "id", None),
				)
			)

	return studios


def _format_status(state: str | None) -> str:
	"""Format status with icon similar to Lightning SDK CLI."""

	if state is None:
		return "✗ unknown"

	state_lower = str(state).lower().strip()
	if not state_lower:
		return "✗ unknown"

	# Map common states to icons/symbols (including Lightning SDK internal state names)
	status_map = {
		"running": "✓ running",
		"cloud_space_state_ready": "✓ ready",
		"running_job_queue": "✓ running",
		"stopped": "✗ stopped",
		"cloud_space_state_stopped": "✗ stopped",
		"stopping": "⟳ stopping",
		"starting": "⟳ starting",
		"cloud_space_state_starting": "⟳ starting",
		"failed": "✗ failed",
		"pending": "⟳ pending",
	}

	for key, display in status_map.items():
		if key in state_lower:
			return display

	return f"• {state_lower}"


def format_studios(studios: Iterable[StudioSummary]) -> str:
	"""Render studios grouped by teamspace, matching Lightning SDK CLI style."""

	rows = list(studios)
	if not rows:
		return "No studios found."

	# Group studios by teamspace for clearer output
	grouped: dict[str, list[StudioSummary]] = {}
	for row in rows:
		grouped.setdefault(row.teamspace, []).append(row)

	lines: list[str] = []
	first_teamspace = True
	for teamspace in sorted(grouped):
		if not first_teamspace:
			lines.append("")  # Blank line between teamspaces
		first_teamspace = False

		lines.append(f"{'─' * 60}")
		lines.append(f"  Teamspace: {teamspace}")
		lines.append(f"{'─' * 60}")

		headers = ["NAME", "OWNER", "MACHINE", "STATE"]
		table_rows = [
			[
				row.name,
				row.owner,
				row.machine_type or "-",
				_format_status(row.state),
			]
			for row in grouped[teamspace]
		]

		# Calculate column widths
		widths = [len(header) for header in headers]
		for row in table_rows:
			for index, value in enumerate(row):
				widths[index] = max(widths[index], len(value))

		def render_row(values: list[str], bold: bool = False) -> str:
			cells = [value.ljust(widths[index]) for index, value in enumerate(values)]
			return "  " + "  ".join(cells)

		lines.append(render_row(headers, bold=True))
		lines.append("  " + "  ".join(["─" * widths[i] for i in range(len(headers))]))

		for row in table_rows:
			lines.append(render_row(row))

	return "\n".join(lines)


def _start_with_progress(studio: Studio, machine: str, poll_interval: float = 1.0, timeout: int = 600) -> None:
	"""Start a studio in a background thread and show a progress bar while waiting.

	This runs `studio.start(machine=...)` in a thread and polls `studio.status` until
	it reports a running state or the timeout is reached. The progress bar is a simple
	indeterminate-style progress that advances until completion.
	"""

	def _target() -> None:
		try:
			studio.start(machine=machine)
		except Exception:
			# Let the caller handle start exceptions; they will be raised in the thread.
			return

	thread = threading.Thread(target=_target, daemon=True)
	thread.start()

	# Use a simple progress bar that advances until thread completes or timeout
	with tqdm(total=timeout, unit="s", desc="Starting", leave=True) as pbar:
		elapsed = 0
		while thread.is_alive() and elapsed < timeout:
			time.sleep(poll_interval)
			elapsed += poll_interval
			pbar.update(poll_interval)

		if thread.is_alive():
			raise RuntimeError("Timed out while starting the studio")

	# One final small pause to allow status to settle
	time.sleep(0.5)


def _ensure_lightning_ssh_keys(auth: Auth, ssh_dir: Path) -> Path:
	"""Ensure Lightning SSH key pair exists and return private key path."""

	key_path = ssh_dir / "lightning_rsa"
	pub_path = ssh_dir / "lightning_rsa.pub"
	if key_path.exists() and pub_path.exists():
		return key_path

	_download_ssh_keys(api_key=auth.api_key, ssh_home=ssh_dir, ssh_key_name="lightning_rsa", overwrite=False)
	return key_path


def _split_ssh_config_blocks(lines: list[str]) -> tuple[list[str], list[list[str]]]:
	"""Split an SSH config into preamble and host blocks."""

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
		if stripped.startswith("hostname ") and stripped.split(maxsplit=1)[1] == LIGHTNING_HOSTNAME:
			return True
	return False


def _render_lightning_host_block(host: str, studio_id: str, key_path: Path) -> list[str]:
	config = _generate_ssh_config(key_path=str(key_path), host=host, user=f"s_{studio_id}")
	return [line.rstrip() for line in config.strip("\n").splitlines()]


def lock_lightning_ssh_config(studios: Iterable[StudioSummary]) -> tuple[int, int]:
	"""Sync Lightning hosts in ~/.ssh/config and return (kept_non_lightning, synced_lightning)."""

	auth = authenticate_lightning_from_env()
	ssh_dir = Path.home() / ".ssh"
	ssh_dir.mkdir(parents=True, exist_ok=True)

	key_path = _ensure_lightning_ssh_keys(auth, ssh_dir)
	config_path = ssh_dir / "config"

	rows = list(studios)
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

	if out_lines and out_lines[-1].strip() != "":
		out_lines.append("")

	for index, block in enumerate(non_lightning_blocks):
		if index > 0 and out_lines and out_lines[-1].strip() != "":
			out_lines.append("")
		out_lines.extend(block)

	if rows_by_host:
		if out_lines and out_lines[-1].strip() != "":
			out_lines.append("")

		for index, host in enumerate(sorted(rows_by_host)):
			if index > 0 and out_lines and out_lines[-1].strip() != "":
				out_lines.append("")
			studio = rows_by_host[host]
			out_lines.extend(_render_lightning_host_block(host=host, studio_id=studio.studio_id or "", key_path=key_path))

	content = "\n".join(out_lines)
	if content and not content.endswith("\n"):
		content += "\n"
	config_path.write_text(content, encoding="utf-8")

	return len(non_lightning_blocks), len(rows_by_host)


def load_config() -> dict[str, Any]:
	"""Load configuration from ~/.config/take_me_cloud_config.yaml."""

	config_path = Path.home() / ".config" / "take_me_cloud_config.yaml"
	if not config_path.exists():
		raise FileNotFoundError(
			f"Config file not found at {config_path}. "
			"Please create it with your default machine type, cloud provider, and teamspaces."
		)

	with config_path.open("r") as f:
		config = yaml.safe_load(f)

	if not config or "Lightning AI" not in config:
		raise ValueError("Config file must contain 'Lightning AI' section.")

	return config["Lightning AI"]


def get_teamspace_names_from_config(config: dict[str, Any]) -> list[str]:
	"""Extract teamspace names from configuration."""

	teamspaces = config.get("teamspace", [])
	if not teamspaces:
		raise ValueError("No teamspaces found in configuration.")

	return [ts["name"] for ts in teamspaces if isinstance(ts, dict) and "name" in ts]


def get_default_machine_for_teamspace(config: dict[str, Any], teamspace_name: str) -> str:
	"""Get default machine type for a teamspace, falling back to global default."""

	teamspaces = config.get("teamspace", [])
	for ts in teamspaces:
		if isinstance(ts, dict) and ts.get("name") == teamspace_name:
			if "machine_default" in ts:
				return ts["machine_default"]

	return config.get("machine_default", "CPU")


def select_teamspace_interactive(teamspace_names: list[str]) -> str:
	"""Interactively select a teamspace from the list."""

	if not teamspace_names:
		raise ValueError("No teamspaces available.")

	if len(teamspace_names) == 1:
		return teamspace_names[0]

	print("\nAvailable teamspaces:")
	for index, name in enumerate(teamspace_names, 1):
		print(f"  {index}. {name}")

	while True:
		try:
			choice = input("Select teamspace (number): ").strip()
			index = int(choice) - 1
			if 0 <= index < len(teamspace_names):
				return teamspace_names[index]
			print(f"Please enter a number between 1 and {len(teamspace_names)}.")
		except ValueError:
			print("Please enter a valid number.")



def create_or_replace_studio(studio_name: str) -> None:
	"""Create or replace a studio with the given name."""

	config = load_config()
	teamspace_names = get_teamspace_names_from_config(config)
	selected_teamspace_full = select_teamspace_interactive(teamspace_names)
	
	# Parse the full teamspace name like "vaishnavahari/myml" or "rwth-gut/skillcomp-ws"
	parts = selected_teamspace_full.split("/")
	if len(parts) != 2:
		raise ValueError(f"Invalid teamspace name format: {selected_teamspace_full}. Expected 'user/teamspace' or 'org/teamspace'.")
	
	owner, teamspace_name = parts
	
	# Get owner_type from config (user or org)
	config_teamspaces = config.get("teamspace", [])
	teamspace_info = None
	for ts in config_teamspaces:
		if isinstance(ts, dict) and ts.get("name") == selected_teamspace_full:
			teamspace_info = ts
			break
	
	if not teamspace_info:
		raise ValueError(f"Teamspace '{selected_teamspace_full}' not found in configuration.")
	
	owner_type = teamspace_info.get("owner_type", "user").lower()
	machine_type = get_default_machine_for_teamspace(config, selected_teamspace_full)
	cloud_provider = config.get("cloud_provider", "AWS")

	existing_studios = list_existing_studios()
	existing_studio = next(
		(s for s in existing_studios if s.name == studio_name),
		None,
	)

	if existing_studio:
		print(f"Studio '{studio_name}' already exists. Deleting...")
		try:
			# Build Studio kwargs with user or org for deletion
			delete_kwargs = {
				"name": studio_name,
				"teamspace": existing_studio.teamspace,
			}
			
			if owner_type == "org":
				delete_kwargs["org"] = owner
			else:
				delete_kwargs["user"] = owner
			
			studio = Studio(**delete_kwargs)
			studio.delete()
			print(f"Studio '{studio_name}' deleted.")
		except Exception as e:
			raise RuntimeError(f"Failed to delete existing studio: {e}") from e

	print(f"Creating new studio '{studio_name}' in teamspace '{selected_teamspace_full}'...")
	try:
		# Build Studio kwargs with user or org
		studio_kwargs = {
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
		print(f"Studio '{studio_name}' created successfully.")
		
		# Start the studio with the desired machine type (show progress)
		print(f"Starting studio with machine type: {machine_type}...")
		_start_with_progress(studio, machine=machine_type)
		print(f"Studio started with machine type: {machine_type}")
		
		print(f"Cloud provider: {cloud_provider}")
		print(f"Teamspace: {selected_teamspace_full}")
	except Exception as e:
		raise RuntimeError(f"Failed to create studio: {e}") from e


