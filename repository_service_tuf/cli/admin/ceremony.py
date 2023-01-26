# SPDX-FileCopyrightText: 2022-2023 VMware Inc
#
# SPDX-License-Identifier: MIT

#
# Ceremony
#
import json
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Optional

from rich import box, markdown, prompt, table  # type: ignore
from rich.console import Console  # type: ignore
from securesystemslib.exceptions import (  # type: ignore
    CryptoError,
    Error,
    FormatError,
    StorageError,
)
from securesystemslib.interface import (  # type: ignore
    import_ed25519_privatekey_from_file,
)

from repository_service_tuf.cli import click
from repository_service_tuf.cli.admin import admin
from repository_service_tuf.helpers.api_client import (
    URL,
    Methods,
    is_logged,
    request_server,
)
from repository_service_tuf.helpers.tuf import (
    RolesKeysInput,
    initialize_metadata,
)

CEREMONY_INTRO = """
# Repository Metadata and Settings for the Repository Service for TUF

Create new Repository Metadata and Settings

Repository Service for TUF is an implementation for The Update Framework (TUF)
as a Service to be deployed in Cloud or on-premises, protecting your target
files repository.

TUF helps developers maintain the security of software update systems,
providing protection even against attackers that compromise the repository or
signing keys. TUF provides a flexible framework and specification that
developers can adopt to any software update system.

More about TUF access https://theupdateframework.io
"""

CEREMONY_INTRO_ROLES_RESPONSIBILITIES = """

## Roles and Responsibilities
Repository Service for TUF implements Roles and Responsibilities based on TUF
top roles (root, targets, timestamp, and snapshot) and the delegated roles hash
bins.

The inspiration for Repository Service for TUF is the
[Python Enhancement Proposal 458](https://peps.python.org/pep-0458/).



                       .-------------,
            .--------- |   root *    |-----------.
            |          `-------------'           |
            |                 |                  |
            V                 V                  V
    .-------------,    .-------------,    .-------------,
    |  timestamp  |    |  snapshot   |    |   targets * |
    `-------------'    `-------------'    `-------------'
                                                 .
                                                 .
                                                 .
                             .........................................
                             .                   .                   .
                             .                   .                   .
                             .                   .                   .
                             V                   V                   V
                      .-------------,     .-------------,     .-------------,
                      |  bins 0-X   | ... |  bin A-FF   | ... |  bin X-FF   |
                      `-------------'     `-------------'     `-------------'
    * offline keys

The explanation will follow an example of the Organization Example Inc.

**root**

The root role is the locus of trust for the entire repository. The root role
signs the `root.json` metadata file. This file indicates the authorized keys
for each top-level role, including the root role itself.

Minimum recommended: 2 Keys and a Threshold equal to 1.

Example:
Corp Example Inc will use two keys and a threshold of one. Key Owners:
- CTO (Jimi Hendrix)
- VP of Security (Janis Joplin).

**targets**

The targets role is responsible for indicating which target files are available
from the repository. More precisely, it shares the responsibility of providing
information about the content of updates. The targets role signs `targets.json`
metadata and delegates to the hash bins roles (called bins).

Recommended: 2 Keys and a Threshold equal to 2. Destroy after the ceremony.

Example:
Corp Example Inc will use two Keys and a Threshold of two keys.
The Keys will be generated by the Security Team and discarded after the
Ceremony.
- Head of Development (Kurt Cobain)
- Release Manager (Chris Cornell).

**bins**

The bins role is a target delegated role and is responsible for signing the
target files in the file repositories. This key is an online key.

Recommended: 1 Key and a Threshold equal to 1.

Example:
Corp Example Inc will use one Key and a Threshold of 1 Key.
- DevOpsSec Team

**snapshot**

The snapshot role ensures that clients see a consistent repository state.
It provides repository state information by indicating the latest versions
of the top-level targets (the targets role) and delegated targets
(hash bins roles) metadata files on the repository in `snapshot.json`.

Recommended: 1 Key and a Threshold equal to 1.

Example:
Corp Example Inc will use one Key and a Threshold of one Key.
- DevOps Team

**timestamp**

The timestamp role is responsible for providing information about the
timelines of available updates. Timelines information is made available by
frequently signing a new timestamp.json file with a short expiration time.
This file indicates the latest version of `snapshot.json`.

Recommended: 1 Key and a Threshold equal to 1

Example:
Corp Example Inc will use one Key and a Threshold of one Key.
- DevOps Team
"""

STEP_1 = """
# STEP 1: Configure the Roles

The TUF roles supports multiple keys and the threshold (quorum trust)
defines the minimal number of keys required to take actions using
a specific Role.

Reference: [TUF](https://theupdateframework.github.io/specification/latest/#goals-for-pki)

"""  # noqa

STEP_2 = """
# STEP 2: Load roles keys

The keys must have a password, and the file must be accessible.

Depending on the Organization, each key has an owner, and each owner should
insert the password personally.

The Ceremony process doesn't show the password or key content.
"""

STEP_3 = """
# STEP 3: Validate configuration

The information below is the configuration done in the preview steps.
Check the number of keys, the threshold/quorum, and the key details.

"""

BINS_DELEGATION_MESSAGE = """
The role *targets* delegates to the hash bin roles.
See:
[TUF Specification about succinct hash bin delegation](
    https://github.com/theupdateframework/taps/blob/master/tap15.md
)
"""

HASH_BINS_EXAMPLE = """

Example:
--------

The Organization Example (https://example.com) has all files downloaded
`/downloads` path, meaning https://example.com/downloads/.

Additionally, it has two sub-folders, productA and productB where the clients
can find all files (i.e.: productA-v1.0.tar, productB-v1.0.tar), for productB
it even has a sub-folder, updates where clients can find update files
(i.e.: servicepack-1.tar, servicepack-2.tar).
The organization has decided to use 8 hash bins. Target files will be
uniformly distributed over 8 bins whose names will be "1.bins-0.json",
"1.bins-1.json", ... , "1.bins-7.json".

Now imagine that the organization stores the following files:
- https://example.com/downloads/productA/productA-v1.0.tar
- https://example.com/downloads/productB/productB-v1.0.tar
- https://example.com/downloads/productB/updates/servicepack-1.tar

As we said the targets will be uniformly distributed over the 8 bins no matter
if they are located in the same folder.
In this example here is how they will be distributed:
- "1.bins-0.json" will be responsible for file:
 https://example.com/downloads/productA/productA-v1.0.tar
- "1.bins-1.json" will be responsible for file:
 https://example.com/downloads/productB/productB-v1.0.tar
- "1.bins-5.json" will be responsible for file:
 https://example.com/downloads/productB/updates/servicepack-1.tar
"""

console = Console()


class Roles(Enum):
    ROOT = "root"
    TARGETS = "targets"
    SNAPSHOT = "snapshot"
    TIMESTAMP = "timestamp"
    BINS = "bins"


@dataclass
class RoleSettings:
    expiration: int
    threshold: int
    keys: int
    offline_keys: bool


default_settings = {
    Roles.ROOT.value: RoleSettings(365, 1, 2, True),
    Roles.TARGETS.value: RoleSettings(365, 1, 2, True),
    Roles.SNAPSHOT.value: RoleSettings(1, 1, 1, False),
    Roles.TIMESTAMP.value: RoleSettings(1, 1, 1, False),
    Roles.BINS.value: RoleSettings(1, 1, 1, False),
}


@dataclass
class Key:
    key: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class ServiceSettings:
    targets_base_url: str

    def to_dict(self):
        return asdict(self)


@dataclass
class PayloadSettings:
    roles: Dict[str, RolesKeysInput]
    service: ServiceSettings


OFFLINE_KEYS = {Roles.ROOT.value, Roles.TARGETS.value}

# generate the basic data structure
SETTINGS = PayloadSettings(
    roles={role.value: RolesKeysInput() for role in Roles},
    service=ServiceSettings(targets_base_url=""),
)


def _key_is_duplicated(key: Dict[str, Any]) -> bool:
    for role in SETTINGS.roles.values():
        if any(k for k in role.keys.values() if key == k.get("key")):
            return True
        if any(k for k in role.keys.values() if key == k.get("path")):
            return False

    return False


def _load_key(filepath: str, password: str) -> Key:
    try:
        key = import_ed25519_privatekey_from_file(filepath, password)
        return Key(key=key)
    except CryptoError as err:
        return Key(
            error=(
                f":cross_mark: [red]Failed[/]: {str(err)} Check the"
                " password."
            )
        )

    except (StorageError, FormatError, Error) as err:
        return Key(error=f":cross_mark: [red]Failed[/]: {str(err)}")


def _configure_role(rolename: str, role: RolesKeysInput) -> None:
    # default reset when start configuration
    role.keys.clear()

    role.threshold = default_settings[rolename].threshold
    role.offline_keys = default_settings[rolename].offline_keys

    role.expiration = prompt.IntPrompt.ask(
        (
            f"\nWhat [green]Metadata expiration[/] for [cyan]{rolename}[/]"
            " role?(Days)"
        ),
        default=default_settings[rolename].expiration,
        show_default=True,
    )

    role.num_of_keys = prompt.IntPrompt.ask(
        (
            f"What is the [green]number of keys[/] for "
            f"[cyan]{rolename}[/] role?"
        ),
        default=default_settings[rolename].keys,
        show_default=True,
    )
    if role.num_of_keys > 1:
        role.threshold = prompt.IntPrompt.ask(
            (
                f"What is the key [green]threshold[/] for "
                f"[cyan]{rolename}[/] role signing?"
            ),
            default=default_settings[rolename].threshold,
            show_default=True,
        )
    else:
        role.threshold = 1
        console.print(
            f"The [green]threshold[/] for [cyan]{rolename}[/] is "
            "[cyan]1[/] (one) based on the number of keys "
            "([cyan]1[/])."
        )

    if rolename == Roles.TARGETS.value:
        console.print(markdown.Markdown(BINS_DELEGATION_MESSAGE), width=100)
        show_example = prompt.Confirm.ask("Show example", default="y")
        if show_example:
            console.print(markdown.Markdown(HASH_BINS_EXAMPLE), width=100)

        role.number_hash_prefixes = prompt.IntPrompt.ask(
            f"[green]How many hash bins[/] do you want for [cyan]{rolename}[/]?",  # noqa
            default=8,
            show_default=True,
        )

        targets_base_url = click.prompt(
            "\nWhat is the Base URL (i.e.: https://www.example.com/downloads/)"
        )
        if targets_base_url.endswith("/") is False:
            targets_base_url = targets_base_url + "/"

        SETTINGS.service.targets_base_url = targets_base_url


def _configure_keys(rolename: str, role: RolesKeysInput) -> None:
    key_count = 1
    while len(role.keys) < role.num_of_keys:
        filepath = prompt.Prompt.ask(
            f"\nEnter {key_count}/{role.num_of_keys} the "
            f"[cyan]{rolename}[/]`s Key [green]path[/]"
        )

        password = click.prompt(
            f"Enter {key_count}/{role.num_of_keys} the "
            f"{rolename}`s Key password",
            hide_input=True,
        )
        key: Key = _load_key(filepath, password)

        if key.error:
            console.print(key.error)
            try_again = prompt.Confirm.ask("Try again?", default="y")
            if try_again:
                continue
            else:
                raise click.ClickException("Required key not validated.")

        if key.key is not None and _key_is_duplicated(key.key) is True:
            console.print(":cross_mark: [red]Failed[/]: Key is duplicated.")
            continue

        role.keys[f"{rolename}_{key_count}"] = {
            "filename": filepath.split("/")[-1],
            "password": password,
            "key": key.key,
        }
        console.print(
            ":white_check_mark: Key "
            f"{key_count}/{role.num_of_keys} [green]Verified[/]"
        )
        key_count += 1


def _check_server(settings) -> dict[str, str]:
    server = settings.get("SERVER")
    token = settings.get("TOKEN")
    if server and token:
        token_access_check = is_logged(server, token)
        if token_access_check.state is False:
            raise click.ClickException(
                f"{str(token_access_check.data)}"
                "\n\nTry re-login: 'Repository Service for TUF admin login'"
            )

        expired_admin = token_access_check.data.get("expired")
        if expired_admin is True:
            raise click.ClickException(
                "Token expired. Run 'Repository Service for TUF admin login'"
            )
        else:
            headers = {"Authorization": f"Bearer {token}"}
            response = request_server(
                server, URL.bootstrap.value, Methods.get, headers=headers
            )
            if response.status_code != 200 and (
                response.json().get("bootstrap") is True or None
            ):
                raise click.ClickException(f"{response.json().get('detail')}")
    else:
        raise click.ClickException("Login first. Run 'rstuf-cli admin login'")

    return headers


def _bootstrap(server, headers, json_payload) -> Optional[str]:
    task_id = None
    response = request_server(
        server,
        URL.bootstrap.value,
        Methods.post,
        json_payload,
        headers=headers,
    )
    response_json = response.json()
    if response.status_code != 202:
        raise click.ClickException(
            f"Error {response.status_code} {response_json.get('detail')}"
        )

    elif (
        response_json.get("message") is None
        or response_json.get("message") != "Bootstrap accepted."
    ):
        raise click.ClickException(response.text)

    else:
        if data := response_json.get("data"):
            task_id = data.get("task_id")
            console.print(f"Bootstrap status: ACCEPTED ({task_id})")

    return task_id


def _bootstrap_state(task_id, server, headers) -> None:
    received_state = []
    while True:
        state_response = request_server(
            server, f"{URL.task.value}{task_id}", Methods.get, headers=headers
        )

        if state_response.status_code != 200:
            raise click.ClickException(
                f"Unexpected response {state_response.text}"
            )

        data = state_response.json().get("data")

        if data:
            if state := data.get("state"):
                if state not in received_state:
                    console.print(f"Bootstrap status: {state}")
                    received_state.append(state)

                if state == "SUCCESS":
                    try:
                        result = data.get("result")
                        bootstrap_result = result.get("details").get(
                            "bootstrap"
                        )
                    except AttributeError:
                        bootstrap_result = False

                    if bootstrap_result is not True:
                        raise click.ClickException(
                            f"Something went wrong, result: {result}"
                        )

                    console.print("[green]Bootstrap finished.[/]")
                    break

                elif state == "FAILURE":
                    raise click.ClickException(
                        f"Failed: {state_response.text}"
                    )
            else:
                raise click.ClickException(
                    f"No state in data received {state_response.text}"
                )
        else:
            raise click.ClickException(
                f"No data received {state_response.text}"
            )
        time.sleep(2)


@admin.command()
@click.option(
    "-b",
    "--bootstrap",
    "bootstrap",
    help=(
        "Bootstrap a Repository Service for TUF using the Repository Metadata "
        "after Ceremony"
    ),
    required=False,
    is_flag=True,
)
@click.option(
    "-f",
    "--file",
    "file",
    default="payload.json",
    help=(
        "Generate specific JSON Payload compatible with TUF Repository "
        "Service bootstrap after Ceremony"
    ),
    show_default=True,
    required=False,
)
@click.option(
    "-u",
    "--upload",
    help=(
        "Upload existent payload 'file'. Requires '-b/--bootstrap'. "
        "Optional '-f/--file' to use non default file."
    ),
    required=False,
    is_flag=True,
)
@click.option(
    "-s",
    "--save",
    help=(
        "Save a copy of the metadata locally. This option saves the metadata "
        "files (json) in the 'metadata' folder in the current directory."
    ),
    show_default=True,
    is_flag=True,
)
@click.pass_context
def ceremony(context, bootstrap, file, upload, save) -> None:
    """
    Start a new Metadata Ceremony.
    """

    if save:
        try:
            os.makedirs("metadata", exist_ok=True)
        except OSError as err:
            raise click.ClickException(str(err))

    if upload is True and bootstrap is False:
        raise click.ClickException("Requires '-b/--bootstrap' option.")

    settings = context.obj["settings"]
    if bootstrap:
        headers = _check_server(settings)
        bs_response = request_server(
            settings.SERVER, URL.bootstrap.value, Methods.get, headers=headers
        )
        bs_data = bs_response.json()
        if bs_response.status_code == 404:
            raise click.ClickException(
                f"Server {settings.SERVER} doesn't allow bootstrap"
            )
        if bs_response.status_code != 200:
            raise click.ClickException(
                f"Error {bs_response.status_code} {bs_data.get('detail')}"
            )

        if bs_data.get("bootstrap") is True or None:
            raise click.ClickException(f"{bs_data.get('message')}")

    if upload is False:
        console.print(markdown.Markdown(CEREMONY_INTRO), width=100)

        ceramony_detailed = prompt.Confirm.ask(
            "\nDo you want more information about roles and responsibilities?"
        )
        if ceramony_detailed is True:
            with console.pager():
                console.print(
                    markdown.Markdown(CEREMONY_INTRO_ROLES_RESPONSIBILITIES),
                    width=100,
                )

        start_ceremony = prompt.Confirm.ask(
            "\nDo you want start the ceremony?"
        )

        if start_ceremony is False:
            raise click.ClickException("Ceremony aborted.")

        console.print(markdown.Markdown(STEP_1), width=80)
        for rolename, role in SETTINGS.roles.items():
            _configure_role(rolename, role)

        console.print(markdown.Markdown(STEP_2), width=100)
        start_ceremony = prompt.Confirm.ask(
            "\nReady to start loading the keys? Passwords will be "
            "required for keys"
        )
        if start_ceremony is False:
            raise click.ClickException("Ceremony aborted.")

        for rolename, role in SETTINGS.roles.items():
            _configure_keys(rolename, role)

        console.print(markdown.Markdown(STEP_3), width=100)

        for rolename, role in SETTINGS.roles.items():
            while True:
                role_table = table.Table()
                role_table.add_column(
                    "ROLE SUMMARY",
                    style="yellow",
                    justify="center",
                    vertical="middle",
                )
                role_table.add_column(
                    "KEYS", justify="center", vertical="middle"
                )
                keys_table = table.Table(box=box.MINIMAL)
                keys_table.add_column(
                    "path", justify="right", style="cyan", no_wrap=True
                )
                keys_table.add_column("id", justify="center")
                keys_table.add_column("verified", justify="center")
                for key in role.keys.values():
                    keys_table.add_row(
                        key.get("filename"),
                        key.get("key").get("keyid"),
                        ":white_heavy_check_mark:",
                    )

                if role.offline_keys is True:
                    key_type = "[red]offline[/red]"
                else:
                    key_type = "[green]online[/]"

                role_table.add_row(
                    (
                        f"Role: [cyan]{rolename}[/]"
                        f"\nNumber of Keys: {len(role.keys)}"
                        f"\nThreshold: {role.threshold}"
                        f"\nKeys Type: {key_type}"
                        f"\nRole Expiration: {role.expiration} days"
                    ),
                    keys_table,
                )

                if rolename == Roles.TARGETS.value:
                    role_table.add_row(
                        (
                            "\n"
                            "\n[orange1]DELEGATIONS[/]"
                            f"\n[aquamarine3]{rolename} -> bins[/]"
                            f"\nNumber bins: {role.number_hash_prefixes}"
                        ),
                        "",
                    )

                console.print(role_table)
                confirm_config = prompt.Confirm.ask(
                    f"Configuration correct for {rolename}?"
                )
                if not confirm_config:
                    # reconfigure role and keys
                    _configure_role(rolename, role)
                    _configure_keys(rolename, role)
                else:
                    break

        metadata = initialize_metadata(SETTINGS.roles, save=save)

        json_payload: Dict[str, Any] = dict()

        json_payload["settings"] = {"service": SETTINGS.service.to_dict()}
        for settings_role, data in SETTINGS.roles.items():
            if data.offline_keys is True:
                data.keys.clear()

            if "roles" not in json_payload["settings"]:
                json_payload["settings"]["roles"] = {
                    settings_role: data.to_dict()
                }
            else:
                json_payload["settings"]["roles"][
                    settings_role
                ] = data.to_dict()

        json_payload["metadata"] = {
            key: data.to_dict() for key, data in metadata.items()
        }

        if file:
            with open(file, "w") as f:
                f.write(json.dumps(json_payload, indent=2))

        if bootstrap is True:
            _bootstrap(settings.SERVER, headers, json_payload)

    elif bootstrap is True and upload is True:
        try:
            with open(file) as payload_file:
                json_payload = json.load(payload_file)
        except OSError:
            raise click.ClickException(f"Invalid file {file}")

        console.print("Starting online bootstrap")
        task_id = _bootstrap(settings.SERVER, headers, json_payload)

        if task_id is None:
            raise click.ClickException("task id wasn't received")

        _bootstrap_state(task_id, settings.SERVER, headers)

    console.print("\nCeremony done. 🔐 🎉")
