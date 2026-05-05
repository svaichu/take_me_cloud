from unittest import TestCase
from unittest.mock import patch

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
