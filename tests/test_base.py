from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from take_me_cloud.base import StudioSummary, authenticate_lightning_from_env, lock_lightning_ssh_config, list_existing_studios


class TestAuthentication(TestCase):
    @patch("take_me_cloud.base.Auth")
    def test_authenticate_lightning_from_env_success(self, auth_cls: Mock) -> None:
        auth = auth_cls.return_value
        auth.user_id = "user-123"
        auth.api_key = "api-123"

        resolved = authenticate_lightning_from_env()

        auth.authenticate.assert_called_once_with()
        self.assertIs(resolved, auth)


class TestStudioListing(TestCase):
    @patch("take_me_cloud.base._collect_owned_teamspaces")
    @patch("take_me_cloud.base.UserApi")
    @patch("take_me_cloud.base.TeamspaceApi")
    @patch("take_me_cloud.base._resolve_authed_user")
    def test_list_existing_studios_success(
        self,
        resolve_authed_user: Mock,
        teamspace_api_cls: Mock,
        user_api_cls: Mock,
        collect_owned_teamspaces: Mock,
    ) -> None:
        resolve_authed_user.return_value = ("user-123", "vaishnav")
        teamspace_api = teamspace_api_cls.return_value
        user_api = user_api_cls.return_value

        ts1 = SimpleNamespace(id="ts-1", name="teamspace-one")
        ts2 = SimpleNamespace(id="ts-2", name="teamspace-two")
        collect_owned_teamspaces.return_value = [
            ("vaishnav", ts1),
            ("org-x", ts2),
        ]

        studio1 = SimpleNamespace(
            name="studio-a",
            cluster_id="cluster-a",
            state="RUNNING",
            description="primary",
            id="st-1",
        )
        studio2 = SimpleNamespace(
            name="studio-b",
            cluster_id="cluster-b",
            code_status="STOPPED",
            description="secondary",
            id="st-2",
        )

        def list_studios_side_effect(teamspace_id: str):
            if teamspace_id == "ts-1":
                return [studio1]
            if teamspace_id == "ts-2":
                return [studio2]
            return []

        teamspace_api.list_studios.side_effect = list_studios_side_effect

        studios = list_existing_studios()

        collect_owned_teamspaces.assert_called_once_with("user-123", "vaishnav", teamspace_api, user_api)
        self.assertEqual(
            studios,
            [
                StudioSummary(
                    name="studio-a",
                    teamspace="teamspace-one",
                    owner="vaishnav",
                    cluster="cluster-a",
                    state="RUNNING",
                    description="primary",
                    studio_id="st-1",
                ),
                StudioSummary(
                    name="studio-b",
                    teamspace="teamspace-two",
                    owner="org-x",
                    cluster="cluster-b",
                    state="STOPPED",
                    description="secondary",
                    studio_id="st-2",
                ),
            ],
        )


class TestLockSsh(TestCase):
    @patch("take_me_cloud.base._render_lightning_host_block")
    @patch("take_me_cloud.base._ensure_lightning_ssh_keys")
    @patch("take_me_cloud.base.authenticate_lightning_from_env")
    def test_lock_lightning_ssh_config_replaces_only_lightning_hosts(
        self,
        authenticate_lightning_from_env: Mock,
        ensure_lightning_ssh_keys: Mock,
        render_lightning_host_block: Mock,
    ) -> None:
        authenticate_lightning_from_env.return_value = SimpleNamespace(api_key="api-123", user_id="user-123")

        def render_side_effect(host: str, studio_id: str, key_path: Path) -> list[str]:
            return [
                f"Host {host}",
                f"  User s_{studio_id}",
                "  Hostname ssh.lightning.ai",
                f"  IdentityFile {key_path}",
            ]

        render_lightning_host_block.side_effect = render_side_effect

        studios = [
            StudioSummary(
                name="studio-new",
                teamspace="ts",
                owner="owner",
                cluster="cluster",
                state="RUNNING",
                description="desc",
                studio_id="st-new",
            )
        ]

        with TemporaryDirectory() as temp_home:
            ssh_dir = Path(temp_home) / ".ssh"
            ssh_dir.mkdir(parents=True, exist_ok=True)
            config_path = ssh_dir / "config"
            config_path.write_text(
                "\n".join(
                    [
                        "Host github.com",
                        "  Hostname github.com",
                        "  User git",
                        "",
                        "Host old-lightning",
                        "  User s_old",
                        "  Hostname ssh.lightning.ai",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            ensure_lightning_ssh_keys.return_value = ssh_dir / "lightning_rsa"

            with patch("take_me_cloud.base.Path.home", return_value=Path(temp_home)):
                kept_non_lightning, synced_lightning = lock_lightning_ssh_config(studios)

            updated = config_path.read_text(encoding="utf-8")

        self.assertEqual(kept_non_lightning, 1)
        self.assertEqual(synced_lightning, 1)
        self.assertIn("Host github.com", updated)
        self.assertIn("Host studio-new", updated)
        self.assertNotIn("Host old-lightning", updated)
