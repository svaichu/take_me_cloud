
"""Lightning AI studio listing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lightning_sdk.api import TeamspaceApi, UserApi
from lightning_sdk.cli.legacy.configure import _download_ssh_keys
from lightning_sdk.cli.legacy.generate import _generate_ssh_config
from lightning_sdk.lightning_cloud.login import Auth


@dataclass(frozen=True, slots=True)
class StudioSummary:
	"""A compact view of a Lightning AI studio."""

	name: str
	teamspace: str
	owner: str
	cluster: str | None
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
			studios.append(
				StudioSummary(
					name=getattr(studio, "name", ""),
					teamspace=getattr(teamspace, "name", ""),
					owner=owner_name,
					cluster=getattr(studio, "cluster_id", None),
					state=_studio_state(studio),
					description=getattr(studio, "description", None),
					studio_id=getattr(studio, "id", None),
				)
			)

	return studios


def format_studios(studios: Iterable[StudioSummary]) -> str:
	"""Render studios as a compact plain-text table."""

	rows = list(studios)
	if not rows:
		return "No studios found."

	headers = ["Studio", "Teamspace", "Owner", "Cluster", "State"]
	table_rows = [
		[row.name, row.teamspace, row.owner, row.cluster or "-", row.state or "-"] for row in rows
	]

	widths = [len(header) for header in headers]
	for row in table_rows:
		for index, value in enumerate(row):
			widths[index] = max(widths[index], len(value))

	def render_row(values: list[str]) -> str:
		return "  ".join(value.ljust(widths[index]) for index, value in enumerate(values))

	lines = [render_row(headers), render_row(["-" * width for width in widths])]
	lines.extend(render_row(row) for row in table_rows)
	return "\n".join(lines)


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


