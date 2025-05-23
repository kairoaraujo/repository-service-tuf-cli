# SPDX-License-Identifier: MIT

import os
from hashlib import sha256
from unittest.mock import mock_open, patch

import pretend
import pytest
from tuf.ngclient import UpdaterConfig

from repository_service_tuf.cli.artifact import download

METADATA_URL = "http://localhost:8080"
ARTIFACT_URL = "http://localhost:8081"
ARTIFACT_NAME = "file.txt"
SRC_PATH = "repository_service_tuf.cli.artifact.download"


@pytest.fixture()
def mocked_os_makedirs(monkeypatch):
    fake_makedirs = pretend.call_recorder(lambda *a, **kw: None)
    path = "repository_service_tuf.cli.artifact.download.os.makedirs"
    monkeypatch.setattr(path, fake_makedirs)

    return fake_makedirs


class TestDownloadArtifacInteractionWithoutConfig:
    """
    Test the artifact download command interaction
    without using a config file
    """

    # mocked_os_makedirs not used directly, but mocks os.makedirs
    def test_download_command_missing_metadata_url(
        self,
        client,
        test_context,
    ):
        test_result = client.invoke(
            download.download,
            ARTIFACT_NAME,
            obj=test_context,
        )

        assert "Please specify metadata url" in test_result.stderr
        assert test_result.exit_code == 1

    def test_download_command_missing_artifacts_url(
        self,
        client,
        test_context,
    ):

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME, "-m", METADATA_URL],
            obj=test_context,
        )

        assert "Please specify artifacts url" in test_result.stderr
        assert test_result.exit_code == 1

    def test_download_command_using_tofu(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):
        metadata_dir = "foo_dir"
        fake_build_metadata_dir = pretend.call_recorder(lambda a: metadata_dir)
        monkeypatch.setattr(
            f"{SRC_PATH}._build_metadata_dir", fake_build_metadata_dir
        )

        fake_is_file = pretend.call_recorder(lambda a: False)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)
        fake_urlretrieve = pretend.call_recorder(lambda *a: "foo/root.json")
        monkeypatch.setattr(
            f"{SRC_PATH}.request.urlretrieve",
            fake_urlretrieve,
        )
        fake__perform_tuf_ngclient_download_artifact = pretend.call_recorder(
            lambda *a: None
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._perform_tuf_ngclient_download_artifact",
            fake__perform_tuf_ngclient_download_artifact,
        )
        updater_conf = UpdaterConfig()
        fake_init_updater_config = pretend.call_recorder(lambda: updater_conf)
        monkeypatch.setattr(
            f"{SRC_PATH}.UpdaterConfig",
            fake_init_updater_config,
        )

        test_result = client.invoke(
            download.download,
            [
                ARTIFACT_NAME,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
            ],
            obj=test_context,
            catch_exceptions=False,
        )

        assert "Trust-on-First-Use: Initialized new root" in test_result.output
        assert fake_urlretrieve.calls == [
            pretend.call(
                f"{METADATA_URL}/1.root.json", f"{metadata_dir}/root.json"
            )
        ]
        assert fake_build_metadata_dir.calls == [
            pretend.call(METADATA_URL),
            pretend.call(METADATA_URL),
        ]
        assert fake_init_updater_config.calls == [pretend.call()]
        assert fake__perform_tuf_ngclient_download_artifact.calls == [
            pretend.call(
                METADATA_URL,
                metadata_dir,
                ARTIFACT_URL,
                ARTIFACT_NAME,
                os.getcwd() + "/downloads",
                updater_conf,
            )
        ]
        assert test_result.exit_code == 0

    def test_download_command_with_trusted_root(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):

        trusted_root_path = "tests/files/"
        fake_build_metadata_dir = pretend.call_recorder(
            lambda a: trusted_root_path
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._build_metadata_dir", fake_build_metadata_dir
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._init_trusted_root",
            pretend.call_recorder(lambda *a: None),
        )
        fake__perform_tuf_ngclient_download_artifact = pretend.call_recorder(
            lambda *a: None
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._perform_tuf_ngclient_download_artifact",
            fake__perform_tuf_ngclient_download_artifact,
        )
        updater_conf = UpdaterConfig()
        fake_init_updater_config = pretend.call_recorder(lambda: updater_conf)
        monkeypatch.setattr(
            f"{SRC_PATH}.UpdaterConfig",
            fake_init_updater_config,
        )

        test_result = client.invoke(
            download.download,
            [
                ARTIFACT_NAME,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
                "-r",
                "root.json",
            ],
            obj=test_context,
            catch_exceptions=False,
        )
        assert fake_build_metadata_dir.calls == [pretend.call(METADATA_URL)]
        assert fake__perform_tuf_ngclient_download_artifact.calls == [
            pretend.call(
                METADATA_URL,
                trusted_root_path,
                ARTIFACT_URL,
                ARTIFACT_NAME,
                os.getcwd() + "/downloads",
                updater_conf,
            )
        ]
        assert test_result.exit_code == 0

    def test_download_command_with_artifact_url(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):
        fake_download_artifact = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(
            f"{SRC_PATH}._download_artifact", fake_download_artifact
        )
        test_result = client.invoke(
            download.download,
            [
                ARTIFACT_NAME,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
            ],
            obj=test_context,
        )
        msg = f"Successfully completed artifact download: {ARTIFACT_NAME}"
        assert msg in test_result.output
        assert test_result.exit_code == 0
        assert fake_download_artifact.calls == [
            pretend.call(
                METADATA_URL, ARTIFACT_URL, False, None, ARTIFACT_NAME, None
            )
        ]

    def test_download_command_with_hash_prefix(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):
        artifact_path = f"example_path/{ARTIFACT_NAME}"
        metadata_dir = "foo_dir"

        fake_build_metadata_dir = pretend.call_recorder(lambda a: metadata_dir)
        monkeypatch.setattr(
            f"{SRC_PATH}._build_metadata_dir", fake_build_metadata_dir
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._init_tofu", pretend.call_recorder(lambda *a: None)
        )
        fake__perform_tuf_ngclient_download_artifact = pretend.call_recorder(
            lambda *a: None
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._perform_tuf_ngclient_download_artifact",
            fake__perform_tuf_ngclient_download_artifact,
        )
        updater_conf = UpdaterConfig(prefix_targets_with_hash=True)
        fake_init_updater_config = pretend.call_recorder(lambda: updater_conf)
        monkeypatch.setattr(
            f"{SRC_PATH}.UpdaterConfig",
            fake_init_updater_config,
        )

        test_result = client.invoke(
            download.download,
            [
                artifact_path,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
                "-p",
            ],
            obj=test_context,
        )
        assert "Successfully completed artifact download" in test_result.output
        assert test_result.exit_code == 0
        assert fake_build_metadata_dir.calls == [pretend.call(METADATA_URL)]
        assert "Using trusted root in " in test_result.output
        assert updater_conf.prefix_targets_with_hash is True
        assert fake__perform_tuf_ngclient_download_artifact.calls == [
            pretend.call(
                METADATA_URL,
                metadata_dir,
                ARTIFACT_URL,
                artifact_path,
                os.getcwd() + "/downloads",
                updater_conf,
            )
        ]

    def test_download_command_with_directory_prefix(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):
        artifact_path = f"example_path/{ARTIFACT_NAME}"
        directory_prefix = os.getcwd() + "/downloads"

        fake_download_artifact = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(
            f"{SRC_PATH}._download_artifact", fake_download_artifact
        )

        test_result = client.invoke(
            download.download,
            [
                artifact_path,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
                "-P",
                directory_prefix,
            ],
            obj=test_context,
        )
        assert "Successfully completed artifact download" in test_result.output
        assert test_result.exit_code == 0
        assert fake_download_artifact.calls == [
            pretend.call(
                METADATA_URL,
                ARTIFACT_URL,
                False,
                directory_prefix,
                artifact_path,
                None,
            )
        ]

    def test_download_command_failed_to_download_artifact(
        self, client, test_context, monkeypatch, mocked_os_makedirs
    ):
        ARTIFACT_NAME = "non-existing"

        metadata_dir = "foo_dir"
        fake_build_metadata_dir = pretend.call_recorder(lambda a: metadata_dir)
        monkeypatch.setattr(
            f"{SRC_PATH}._build_metadata_dir", fake_build_metadata_dir
        )
        monkeypatch.setattr(
            f"{SRC_PATH}._init_tofu", pretend.call_recorder(lambda *a: None)
        )

        class FakeUpdater:
            def __init__(self, **kw):
                pass

            def refresh(self):
                raise OSError("bad")

        monkeypatch.setattr(f"{SRC_PATH}.Updater", FakeUpdater)

        test_result = client.invoke(
            download.download,
            [
                ARTIFACT_NAME,
                "-m",
                METADATA_URL,
                "-a",
                ARTIFACT_URL,
            ],
            obj=test_context,
        )

        assert f"Using trusted root in {metadata_dir}" in test_result.stdout
        err_msg = f"Failed to download artifact {ARTIFACT_NAME}"
        assert err_msg in test_result.stderr
        assert fake_build_metadata_dir.calls == [
            pretend.call(METADATA_URL),
        ]
        assert test_result.exit_code == 1


class TestDownloadArtifacInteractionWithConfig:
    """
    Test the artifact download command interaction
    with using a config
    """

    def test_download_command_no_current_repo(
        self, client, test_context, monkeypatch
    ):
        config = {
            "REPOSITORIES": {
                "r1": {
                    "artifact_base_url": "http://localhost:8081",
                    "hash_prefix": "false",
                    "metadata_url": "http://localhost:8080",
                    "trusted_root": "some_root",
                },
            },
            "SERVER": "http://127.0.0.1",
        }

        test_context["settings"] = config
        fake_is_file = pretend.call_recorder(lambda a: True)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME],
            obj=test_context,
        )
        assert test_result.exit_code == 1
        assert "Please specify current repository" in test_result.stderr

    def test_download_command_no_repos_listed(
        self, client, test_context, monkeypatch
    ):
        config = {
            "CURRENT_REPOSITORY": "r1",
            "REPOSITORIES": {},
            "SERVER": "http://127.0.0.1",
        }

        test_context["settings"] = config
        fake_is_file = pretend.call_recorder(lambda a: True)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME],
            obj=test_context,
        )
        assert test_result.exit_code == 1
        assert (
            "No reposotiroes listed in the config file" in test_result.stderr
        )

    def test_download_command_and_no_root_param(
        self, client, test_context, monkeypatch
    ):
        config = {
            "CURRENT_REPOSITORY": "r1",
            "REPOSITORIES": {
                "r1": {
                    "artifact_base_url": "http://localhost:8081",
                    "hash_prefix": "false",
                    "metadata_url": "http://localhost:8080",
                    "trusted_root": "c29tZV9yb290",
                },
            },
            "SERVER": "http://127.0.0.1",
        }

        test_context["settings"] = config
        fake_is_file = pretend.call_recorder(lambda a: True)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)
        fake_download_artifact = pretend.call_recorder(lambda *a: None)
        monkeypatch.setattr(
            f"{SRC_PATH}._download_artifact", fake_download_artifact
        )

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME],
            obj=test_context,
        )
        assert "Successfully completed artifact download" in test_result.output

    def test_download_command_repo_is_missing(
        self, client, test_context, monkeypatch
    ):
        config = {
            "CURRENT_REPOSITORY": "r1_expected",
            "REPOSITORIES": {
                "r2_other": {
                    "artifact_base_url": "http://localhost:8081",
                    "hash_prefix": "false",
                    "metadata_url": "http://localhost:8080",
                    "trusted_root": "some_root",
                },
            },
            "SERVER": "http://127.0.0.1",
        }

        test_context["settings"] = config
        fake_is_file = pretend.call_recorder(lambda a: True)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME],
            obj=test_context,
        )
        assert test_result.exit_code == 1
        err_msg = "Repository r1_expected is missing in the configuration file"
        assert err_msg in test_result.stderr

    def test_download_command_no_trusted_root(
        self, client, test_context, monkeypatch
    ):
        config = {
            "CURRENT_REPOSITORY": "r1",
            "REPOSITORIES": {
                "r1": {
                    "artifact_base_url": "http://localhost:8081",
                    "hash_prefix": "false",
                    "metadata_url": "http://localhost:8080",
                },
            },
            "SERVER": "http://127.0.0.1",
        }

        test_context["settings"] = config
        fake_is_file = pretend.call_recorder(lambda a: True)
        monkeypatch.setattr(f"{SRC_PATH}.os.path.isfile", fake_is_file)

        test_result = client.invoke(
            download.download,
            [ARTIFACT_NAME],
            obj=test_context,
        )
        assert test_result.exit_code == 1
        assert "Trusted root is not cofigured." in test_result.stderr


class TestDownloadArtifactOptions:
    """Test the artifact download command hepler methods"""

    def test_decode_trusted_root(self):
        trusted_root = "ZXhhbXBsZS9ob21lL3BhdGgvLmxvY2FsL3NoYXJlL3JzdHVmL3Jvb3QuanNvbg=="  # noqa
        want = "example/home/path/.local/share/rstuf/root.json"

        actual = download._decode_trusted_root(trusted_root)
        assert want == actual

    def test_build_metadata_dir(self, monkeypatch):
        metadata_url = "http://example.org"
        metadata_url_hash = sha256(metadata_url.encode()).hexdigest()[:8]
        want = "example_home/.local/share/rstuf/" + metadata_url_hash
        fake_path_home = pretend.call_recorder(lambda: "example_home")
        monkeypatch.setattr(f"{SRC_PATH}.Path.home", fake_path_home)

        actual = download._build_metadata_dir(metadata_url)
        assert want == actual

    def test__init_trusted_root(self):

        with (
            patch(
                f"{SRC_PATH}._build_metadata_dir",
                return_value=pretend.call_recorder(lambda a: "foo_dir"),
            ),
            patch(
                f"{SRC_PATH}.os.makedirs",
                return_value=pretend.call_recorder(lambda a: None),
            ),
            patch("builtins.open", new_callable=mock_open, read_data="data"),
        ):
            result = download._init_trusted_root(
                "http://rstuf.local", "tests/files/root.json"
            )

        assert result is None
