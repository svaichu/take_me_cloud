from unittest import TestCase
from unittest.mock import Mock, patch

from take_me_cloud.base import StudioSummary
from take_me_cloud.cli import main


class TestCLI(TestCase):
    @patch("take_me_cloud.cli.format_studios")
    @patch("take_me_cloud.cli.list_existing_studios")
    def test_list_flag_success(self, list_existing_studios, format_studios) -> None:
        list_existing_studios.return_value = [
            StudioSummary(
                name="studio-a",
                teamspace="ts",
                owner="owner",
                cluster="cluster",
                machine_type="T4",
                state="RUNNING",
                description="desc",
                studio_id="id-1",
            )
        ]
        format_studios.return_value = "ok"

        exit_code = main(["--list"])

        self.assertEqual(exit_code, 0)
        list_existing_studios.assert_called_once_with()
        format_studios.assert_called_once()

    @patch("take_me_cloud.cli.lock_lightning_ssh_config")
    @patch("take_me_cloud.cli.list_existing_studios")
    def test_lock_ssh_flag_success(self, list_existing_studios, lock_lightning_ssh_config) -> None:
        list_existing_studios.return_value = [
            StudioSummary(
                name="studio-a",
                teamspace="ts",
                owner="owner",
                cluster="cluster",
                machine_type="T4",
                state="RUNNING",
                description="desc",
                studio_id="id-1",
            )
        ]
        lock_lightning_ssh_config.return_value = (1, 1)

        exit_code = main(["--lock-ssh"])

        self.assertEqual(exit_code, 0)
        list_existing_studios.assert_called_once_with()
        lock_lightning_ssh_config.assert_called_once_with(list_existing_studios.return_value)

    @patch("take_me_cloud.cli.create_or_replace_studio")
    def test_create_replace_flag_success(self, create_or_replace_studio: Mock) -> None:
        exit_code = main(["--create-replace", "test-studio"])

        self.assertEqual(exit_code, 0)
        create_or_replace_studio.assert_called_once_with("test-studio")

    @patch("take_me_cloud.cli.get_version")
    def test_version_flag_success(self, get_version_mock: Mock) -> None:
        get_version_mock.return_value = "0.1.2"

        exit_code = main(["--version"])

        self.assertEqual(exit_code, 0)
        get_version_mock.assert_called_once()
