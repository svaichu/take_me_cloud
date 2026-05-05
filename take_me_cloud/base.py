
"""Lightning AI studio listing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from lightning_sdk.api import TeamspaceApi, UserApi
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


