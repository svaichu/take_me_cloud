from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch, mock_open

from take_me_cloud.base import (
    StudioSummary,
    authenticate_lightning_from_env,
    list_existing_studios,
    load_config,
    lock_lightning_ssh_config,
    get_teamspace_names_from_config,
    get_default_machine_for_teamspace,
    create_or_replace_studio,
)


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
            machine="CPU",
            state="RUNNING",
            description="primary",
            id="st-1",
        )
        studio2 = SimpleNamespace(
            name="studio-b",
            cluster_id="cluster-b",
            machine="T4",
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
                    machine_type="CPU",
                    state="RUNNING",
                    description="primary",
                    studio_id="st-1",
                ),
                StudioSummary(
                    name="studio-b",
                    teamspace="teamspace-two",
                    owner="org-x",
                    cluster="cluster-b",
                    machine_type="T4",
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
                machine_type="T4",
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
        names = get_teamspace_names_from_config(config)
        self.assertEqual(names, ["org1/ts1", "org2/ts2"])

    def test_get_default_machine_for_teamspace_override(self) -> None:
        config = {
            "machine_default": "CPU",
            "teamspace": [
                {"name": "org1/ts1", "machine_default": "T4"},
                {"name": "org2/ts2"},
            ],
        }
        machine = get_default_machine_for_teamspace(config, "org1/ts1")
        self.assertEqual(machine, "T4")

    def test_get_default_machine_for_teamspace_global_default(self) -> None:
        config = {
            "machine_default": "CPU",
            "teamspace": [
                {"name": "org1/ts1"},
                {"name": "org2/ts2"},
            ],
        }
        machine = get_default_machine_for_teamspace(config, "org2/ts2")
        self.assertEqual(machine, "CPU")


class TestCreateReplaceStudio(TestCase):
    @patch("take_me_cloud.base.input")
    @patch("take_me_cloud.base.Studio")
    @patch("take_me_cloud.base.list_existing_studios")
    @patch("take_me_cloud.base.load_config")
    def test_create_or_replace_studio_creates_new_studio(
        self,
        load_config_mock: Mock,
        list_existing_studios_mock: Mock,
        studio_cls: Mock,
        input_mock: Mock,
    ) -> None:
        # Setup config mock
        load_config_mock.return_value = {
            "machine_default": "CPU",
            "cloud_provider": "AWS",
            "teamspace": [
                {"name": "vaishnavahari/myml", "owner_type": "user", "machine_default": "T4"},
            ],
        }

        # No existing studios
        list_existing_studios_mock.return_value = []

        # Mock the Studio instance
        studio_instance = Mock()
        studio_cls.return_value = studio_instance
        input_mock.return_value = "1"  # Select first (only) teamspace

        # Call the function
        create_or_replace_studio("new-studio")

        # Verify Studio was created with correct params (user-owned teamspace)
        studio_cls.assert_called_once_with(
            name="new-studio",
            teamspace="myml",
            user="vaishnavahari",
            create_ok=True,
            cloud_provider="AWS",
        )

        # Verify start was called with machine type
        studio_instance.start.assert_called_once_with(machine="T4")

    @patch("take_me_cloud.base.input")
    @patch("take_me_cloud.base.Studio")
    @patch("take_me_cloud.base.list_existing_studios")
    @patch("take_me_cloud.base.load_config")
    def test_create_or_replace_studio_deletes_existing(
        self,
        load_config_mock: Mock,
        list_existing_studios_mock: Mock,
        studio_cls: Mock,
        input_mock: Mock,
    ) -> None:
        # Setup config mock
        load_config_mock.return_value = {
            "machine_default": "CPU",
            "cloud_provider": "AWS",
            "teamspace": [
                {"name": "vaishnavahari/myml", "owner_type": "user", "machine_default": "T4"},
            ],
        }

        # Mock existing studio
        existing_studio = StudioSummary(
            name="existing-studio",
            teamspace="vaishnavahari/myml",
            owner="vaishnavahari",
            cluster="cluster-1",
            machine_type="CPU",
            state="RUNNING",
            description="existing",
            studio_id="st-existing",
        )
        list_existing_studios_mock.return_value = [existing_studio]

        # Mock the Studio instances (one for deletion, one for creation)
        studio_instance_delete = Mock()
        studio_instance_create = Mock()
        studio_cls.side_effect = [studio_instance_delete, studio_instance_create]
        input_mock.return_value = "1"

        # Mock existing studio with machine_type
        existing_studio_updated = StudioSummary(
            name="existing-studio",
            teamspace="vaishnavahari/myml",
            owner="vaishnavahari",
            cluster="cluster-1",
            machine_type="CPU",
            state="RUNNING",
            description="existing",
            studio_id="st-existing",
        )
        list_existing_studios_mock.return_value = [existing_studio_updated]

        # Call the function
        create_or_replace_studio("existing-studio")

        # Verify Studio was called twice: once for delete, once for create
        self.assertEqual(studio_cls.call_count, 2)

        # Verify delete was called with user parameter
        delete_call = studio_cls.call_args_list[0]
        self.assertEqual(
            delete_call,
            ((),
             {
                 "name": "existing-studio",
                 "teamspace": "myml",
                 "user": "vaishnavahari",
             }),
        )

        # Verify delete was called on the delete instance
        studio_instance_delete.delete.assert_called_once()

        # Verify create was called with correct params
        create_call = studio_cls.call_args_list[1]
        self.assertEqual(
            create_call,
            ((),
             {
                 "name": "existing-studio",
                 "teamspace": "myml",
                 "user": "vaishnavahari",
                 "create_ok": True,
                 "cloud_provider": "AWS",
             }),
        )

        # Verify start was called on the create instance
        studio_instance_create.start.assert_called_once_with(machine="T4")

    @patch("take_me_cloud.base.input")
    @patch("take_me_cloud.base.Studio")
    @patch("take_me_cloud.base.list_existing_studios")
    @patch("take_me_cloud.base.load_config")
    def test_create_or_replace_studio_deletes_from_different_teamspace(
        self,
        load_config_mock: Mock,
        list_existing_studios_mock: Mock,
        studio_cls: Mock,
        input_mock: Mock,
    ) -> None:
        """Test that existing studio is deleted from its original teamspace, not the newly selected one.
        
        Bug scenario: User has a studio 'skillcomp' in 'rwth-gut/skillcomp-ws' (org-owned).
        User runs: take-me-cloud --create-replace skillcomp
        User selects: vaishnavahari/dev (user-owned) as the new location.
        
        Expected: Delete should use org='rwth-gut' and teamspace='skillcomp-ws' (from existing studio),
                  not user='vaishnavahari' and teamspace='dev' (from selected teamspace).
        """
        # Setup config with two teamspaces
        load_config_mock.return_value = {
            "machine_default": "CPU",
            "cloud_provider": "AWS",
            "teamspace": [
                {"name": "vaishnavahari/dev", "owner_type": "user", "machine_default": "CPU"},
                {"name": "rwth-gut/skillcomp-ws", "owner_type": "org", "machine_default": "T4"},
            ],
        }

        # Mock existing studio in rwth-gut/skillcomp-ws
        existing_studio = StudioSummary(
            name="skillcomp",
            teamspace="rwth-gut/skillcomp-ws",
            owner="rwth-gut",
            cluster="cluster-1",
            machine_type="T4",
            state="RUNNING",
            description="existing org-owned studio",
            studio_id="st-existing",
        )
        list_existing_studios_mock.return_value = [existing_studio]

        # Mock the Studio instances (one for deletion, one for creation)
        studio_instance_delete = Mock()
        studio_instance_create = Mock()
        studio_cls.side_effect = [studio_instance_delete, studio_instance_create]
        
        # User selects vaishnavahari/dev (index 1, but will be 0-indexed so input is "1")
        input_mock.return_value = "1"

        # Call the function
        create_or_replace_studio("skillcomp")

        # Verify Studio was called twice: once for delete, once for create
        self.assertEqual(studio_cls.call_count, 2)

        # Verify delete was called with org parameter and correct teamspace from existing studio
        delete_call = studio_cls.call_args_list[0]
        self.assertEqual(
            delete_call,
            ((),
             {
                 "name": "skillcomp",
                 "teamspace": "skillcomp-ws",  # From existing studio's teamspace
                 "org": "rwth-gut",  # From existing studio's owner (org-owned)
             }),
        )

        # Verify delete was called on the delete instance
        studio_instance_delete.delete.assert_called_once()

        # Verify create was called with user parameter and new teamspace (vaishnavahari/dev)
        create_call = studio_cls.call_args_list[1]
        self.assertEqual(
            create_call,
            ((),
             {
                 "name": "skillcomp",
                 "teamspace": "dev",  # From newly selected teamspace
                 "user": "vaishnavahari",  # From newly selected teamspace (user-owned)
                 "create_ok": True,
                 "cloud_provider": "AWS",
             }),
        )

        # Verify start was called on the create instance
        studio_instance_create.start.assert_called_once_with(machine="CPU")
