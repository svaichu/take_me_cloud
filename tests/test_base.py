from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from take_me_cloud.base import (
    StudioSummary,
    authenticate_lightning_from_env,
    create_or_replace_studio,
    format_studios,
    get_default_machine_for_teamspace,
    get_teamspace_names_from_config,
    go_studio,
    list_existing_studios,
    load_config,
    lock_lightning_ssh_config,
    _resolve_authed_user,
    _prepare_cloned_repo,
)


class TestAuthentication(TestCase):
    @patch.dict("os.environ", {"LIGHTNING_API_KEY": "api-123", "LIGHTNING_USER_ID": "user-123"})
    @patch("take_me_cloud.base.Auth")
    def test_authenticate_lightning_from_env_success(self, auth_cls: Mock) -> None:
        auth = auth_cls.return_value
        auth.user_id = "user-123"
        auth.api_key = "api-123"

        resolved = authenticate_lightning_from_env()

        auth_cls.assert_called_once_with(user_id="user-123", api_key="api-123")
        auth.authenticate.assert_called_once_with()
        self.assertIs(resolved, auth)

    @patch.dict("os.environ", {}, clear=True)
    @patch("take_me_cloud.base.Auth")
    def test_authenticate_lightning_from_env_uses_cached_session(self, auth_cls: Mock) -> None:
        auth = auth_cls.return_value
        auth.api_key = "api-123"
        auth.user_id = "user-123"

        resolved = authenticate_lightning_from_env()

        auth_cls.assert_called_once_with()
        auth.authenticate.assert_called_once_with()
        self.assertIs(resolved, auth)

    @patch.dict("os.environ", {"LIGHTNING_API_KEY": "api-123", "LIGHTNING_USERNAME": "vaishnav"})
    @patch("take_me_cloud.base.Auth")
    def test_authenticate_lightning_from_env_username_fallback(self, auth_cls: Mock) -> None:
        auth = auth_cls.return_value
        auth.user_id = None
        auth.api_key = "api-123"

        resolved = authenticate_lightning_from_env()

        auth_cls.assert_called_once_with(api_key="api-123")
        auth.authenticate.assert_called_once_with()
        self.assertIs(resolved, auth)


class TestStudioListing(TestCase):
    @patch.dict("os.environ", {}, clear=True)
    @patch("take_me_cloud.base.UserApi")
    @patch("take_me_cloud.base.authenticate_lightning_from_env")
    def test_resolve_authed_user_uses_session_user_id(
        self,
        authenticate_lightning_from_env_mock: Mock,
        user_api_cls: Mock,
    ) -> None:
        authenticate_lightning_from_env_mock.return_value = SimpleNamespace(api_key="api-123", user_id="user-123")
        user_api = user_api_cls.return_value
        user_api._get_user_by_id.return_value = SimpleNamespace(id="user-123", username="vaishnav")

        user_id, user_name, returned_user_api = _resolve_authed_user()

        self.assertEqual(user_id, "user-123")
        self.assertEqual(user_name, "vaishnav")
        self.assertIs(returned_user_api, user_api)
        user_api._get_user_by_id.assert_called_once_with("user-123")

    @patch.dict("os.environ", {"LIGHTNING_API_KEY": "api-123", "LIGHTNING_USERNAME": "vaishnav"})
    @patch("take_me_cloud.base.UserApi")
    @patch("take_me_cloud.base.authenticate_lightning_from_env")
    def test_resolve_authed_user_username_fallback(
        self,
        authenticate_lightning_from_env_mock: Mock,
        user_api_cls: Mock,
    ) -> None:
        authenticate_lightning_from_env_mock.return_value = SimpleNamespace(api_key="api-123", user_id=None)
        user_api = user_api_cls.return_value
        user_api.get_user.return_value = SimpleNamespace(id="user-123", username="vaishnav")

        user_id, user_name, returned_user_api = _resolve_authed_user()

        self.assertEqual(user_id, "user-123")
        self.assertEqual(user_name, "vaishnav")
        self.assertIs(returned_user_api, user_api)
        user_api.get_user.assert_called_once_with("vaishnav")

    @patch("take_me_cloud.base._collect_owned_teamspaces")
    @patch("take_me_cloud.base.TeamspaceApi")
    @patch("take_me_cloud.base._resolve_authed_user")
    def test_list_existing_studios_success(
        self,
        resolve_authed_user: Mock,
        teamspace_api_cls: Mock,
        collect_owned_teamspaces: Mock,
    ) -> None:
        resolve_authed_user.return_value = ("user-123", "vaishnav", Mock())
        teamspace_api = teamspace_api_cls.return_value

        ts1 = SimpleNamespace(id="ts-1", name="teamspace-one")
        ts2 = SimpleNamespace(id="ts-2", name="teamspace-two")
        collect_owned_teamspaces.return_value = [
            ("vaishnav", "user", ts1),
            ("org-x", "org", ts2),
        ]

        studio1 = SimpleNamespace(
            name="studio-a",
            cluster_id="cluster-a",
            code_config=SimpleNamespace(compute_config=SimpleNamespace(instance_type="cpu")),
            state="RUNNING",
            description="primary",
            id="st-1",
        )
        studio2 = SimpleNamespace(
            name="studio-b",
            cluster_id="cluster-b",
            code_config=SimpleNamespace(compute_config=SimpleNamespace(instance_type="gpu-t4")),
            code_status="STOPPED",
            description="secondary",
            id="st-2",
        )
        teamspace_api.list_studios.side_effect = lambda teamspace_id: [studio1] if teamspace_id == "ts-1" else [studio2]

        studios = list_existing_studios()

        self.assertEqual(
            studios,
            [
                StudioSummary(
                    name="studio-a",
                    teamspace="vaishnav/teamspace-one",
                    owner="vaishnav",
                    cluster="cluster-a",
                    machine_type="cpu",
                    state="RUNNING",
                    description="primary",
                    studio_id="st-1",
                    owner_type="user",
                ),
                StudioSummary(
                    name="studio-b",
                    teamspace="org-x/teamspace-two",
                    owner="org-x",
                    cluster="cluster-b",
                    machine_type="gpu-t4",
                    state="STOPPED",
                    description="secondary",
                    studio_id="st-2",
                    owner_type="org",
                ),
            ],
        )


class TestFormatting(TestCase):
    def test_format_studios_groups_by_teamspace(self) -> None:
        output = format_studios(
            [
                StudioSummary(
                    name="studio-a",
                    teamspace="org-x/teamspace-two",
                    owner="org-x",
                    machine_type="T4",
                    state="RUNNING",
                    studio_id="st-1",
                    owner_type="org",
                ),
                StudioSummary(
                    name="studio-b",
                    teamspace="vaishnav/teamspace-one",
                    owner="vaishnav",
                    machine_type="CPU",
                    state="STOPPED",
                    studio_id="st-2",
                ),
            ]
        )

        self.assertIn("Teamspace: org-x/teamspace-two", output)
        self.assertIn("Teamspace: vaishnav/teamspace-one", output)
        self.assertIn("studio-a", output)
        self.assertIn("studio-b", output)


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

        render_lightning_host_block.side_effect = lambda host, studio_id, key_path: [
            f"Host {host}",
            f"  User s_{studio_id}",
            "  Hostname ssh.lightning.ai",
            f"  IdentityFile {key_path}",
        ]

        studios = [
            StudioSummary(
                name="studio-new",
                teamspace="vaishnav/teamspace-one",
                owner="vaishnav",
                machine_type="T4",
                state="RUNNING",
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

    def test_lock_lightning_ssh_config_rejects_duplicate_names(self) -> None:
        studios = [
            StudioSummary(name="studio-a", teamspace="org-a/ts-a", owner="org-a", studio_id="1"),
            StudioSummary(name="studio-a", teamspace="org-b/ts-b", owner="org-b", studio_id="2"),
        ]

        with self.assertRaises(ValueError):
            lock_lightning_ssh_config(studios)


class TestConfig(TestCase):
    def test_load_config_missing_file(self) -> None:
        with patch("take_me_cloud.base.Path.home", return_value=Path("/nonexistent")):
            with self.assertRaises(FileNotFoundError):
                load_config()

    def test_get_teamspace_names_from_config(self) -> None:
        config = {
            "machine_default": "CPU",
            "teamspace": [
                {"name": "org1/ts1", "machine_default": "T4"},
                {"name": "org2/ts2"},
            ],
        }
        self.assertEqual(get_teamspace_names_from_config(config), ["org1/ts1", "org2/ts2"])

    def test_get_default_machine_for_teamspace_override(self) -> None:
        config = {
            "machine_default": "CPU",
            "teamspace": [
                {"name": "org1/ts1", "machine_default": "T4"},
                {"name": "org2/ts2"},
            ],
        }
        self.assertEqual(get_default_machine_for_teamspace(config, "org1/ts1"), "T4")

    def test_get_default_machine_for_teamspace_global_default(self) -> None:
        config = {
            "machine_default": "CPU",
            "teamspace": [
                {"name": "org1/ts1"},
                {"name": "org2/ts2"},
            ],
        }
        self.assertEqual(get_default_machine_for_teamspace(config, "org2/ts2"), "CPU")


class TestCreateReplaceStudio(TestCase):
    @patch("take_me_cloud.base._seed_bash_history")
    @patch("take_me_cloud.base._start_with_progress")
    @patch("take_me_cloud.base.Studio")
    @patch("take_me_cloud.base.list_existing_studios")
    @patch("take_me_cloud.base.load_config")
    @patch("take_me_cloud.base.select_teamspace_interactive")
    def test_create_or_replace_studio_creates_new_studio(
        self,
        select_teamspace_interactive_mock: Mock,
        load_config_mock: Mock,
        list_existing_studios_mock: Mock,
        studio_cls: Mock,
        start_with_progress_mock: Mock,
        seed_bash_history_mock: Mock,
    ) -> None:
        load_config_mock.return_value = {
            "machine_default": "CPU",
            "cloud_provider": "AWS",
            "teamspace": [
                {"name": "vaishnavahari/myml", "owner_type": "user", "machine_default": "T4"},
            ],
        }
        list_existing_studios_mock.return_value = []
        select_teamspace_interactive_mock.return_value = "vaishnavahari/myml"

        studio_instance = Mock()
        studio_cls.return_value = studio_instance

        create_or_replace_studio("new-studio")

        studio_cls.assert_called_once_with(
            name="new-studio",
            teamspace="myml",
            user="vaishnavahari",
            create_ok=True,
            cloud_provider="AWS",
        )
        start_with_progress_mock.assert_called_once_with(studio_instance, machine="T4")
        seed_bash_history_mock.assert_called_once_with(studio_instance)

    @patch("take_me_cloud.base._seed_bash_history")
    @patch("take_me_cloud.base._start_with_progress")
    @patch("take_me_cloud.base.Studio")
    @patch("take_me_cloud.base.list_existing_studios")
    @patch("take_me_cloud.base.load_config")
    @patch("take_me_cloud.base.select_teamspace_interactive")
    def test_create_or_replace_studio_deletes_existing(
        self,
        select_teamspace_interactive_mock: Mock,
        load_config_mock: Mock,
        list_existing_studios_mock: Mock,
        studio_cls: Mock,
        start_with_progress_mock: Mock,
        seed_bash_history_mock: Mock,
    ) -> None:
        load_config_mock.return_value = {
            "machine_default": "CPU",
            "cloud_provider": "AWS",
            "teamspace": [
                {"name": "vaishnavahari/myml", "owner_type": "user", "machine_default": "T4"},
            ],
        }
        select_teamspace_interactive_mock.return_value = "vaishnavahari/myml"
        list_existing_studios_mock.return_value = [
            StudioSummary(
                name="existing-studio",
                teamspace="vaishnavahari/myml",
                owner="vaishnavahari",
                cluster="cluster-1",
                machine_type="CPU",
                state="RUNNING",
                description="existing",
                studio_id="st-existing",
            )
        ]

        studio_instance_delete = Mock()
        studio_instance_create = Mock()
        studio_cls.side_effect = [studio_instance_delete, studio_instance_create]

        create_or_replace_studio("existing-studio")

        self.assertEqual(studio_cls.call_count, 2)
        self.assertEqual(
            studio_cls.call_args_list[0],
            (
                (),
                {
                    "name": "existing-studio",
                    "teamspace": "myml",
                    "user": "vaishnavahari",
                },
            ),
        )
        studio_instance_delete.delete.assert_called_once_with()
        self.assertEqual(
            studio_cls.call_args_list[1],
            (
                (),
                {
                    "name": "existing-studio",
                    "teamspace": "myml",
                    "user": "vaishnavahari",
                    "create_ok": True,
                    "cloud_provider": "AWS",
                },
            ),
        )
        start_with_progress_mock.assert_called_once_with(studio_instance_create, machine="T4")
        seed_bash_history_mock.assert_called_once_with(studio_instance_create)


class TestGoStudio(TestCase):
    @patch("take_me_cloud.base._prepare_cloned_repo")
    @patch("take_me_cloud.base.create_or_replace_studio")
    def test_go_studio_normalizes_name_and_prepares_repo(
        self,
        create_or_replace_studio_mock: Mock,
        prepare_cloned_repo_mock: Mock,
    ) -> None:
        studio = Mock()
        create_or_replace_studio_mock.return_value = studio

        resolved = go_studio("repo/name")

        self.assertIs(resolved, studio)
        create_or_replace_studio_mock.assert_called_once_with("reponame")
        prepare_cloned_repo_mock.assert_called_once_with(studio, "reponame")

    def test_prepare_cloned_repo_builds_expected_commands(self) -> None:
        studio = Mock()

        _prepare_cloned_repo(studio, "my-repo")

        self.assertGreaterEqual(studio.run.call_count, 3)
        clone_command = studio.run.call_args_list[0].args[0]
        settings_command = studio.run.call_args_list[1].args[0]
        extensions_command = studio.run.call_args_list[2].args[0]

        self.assertIn("git clone https://github.com/svaichu/my-repo.git", clone_command)
        self.assertIn(".vscode/settings.json", settings_command)
        self.assertIn("python.pythonPath", settings_command)
        self.assertIn("code-server", extensions_command)
        self.assertIn("ms-python.python", extensions_command)
