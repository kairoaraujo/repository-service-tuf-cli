# SPDX-License-Identifier: MIT

import os
from typing import Optional

from click import Context
from rich import print_json

from repository_service_tuf.cli import (
    HEADERS_EXAMPLE,
    _set_settings,
    click,
    console,
)
from repository_service_tuf.cli.artifact import artifact
from repository_service_tuf.helpers.api_client import URL, send_payload
from repository_service_tuf.helpers.cli import (
    create_artifact_add_payload_from_filepath,
)
from repository_service_tuf.helpers.oras_registry import (
    RSTUFRegistry,
    add_container_oci,
)


@artifact.command()
@click.argument(
    "artifact",
    required=True,
)
@click.option(
    "--oci-image",
    help="Force it as OCI image and not try to check if it is local artifact.",
    is_flag=True,
    required=False,
    default=False,
)
@click.option(
    "-p",
    "--path",
    help="A custom path (`TARGETPATH`) for the file, defined in the metadata.",
    type=str,
    required=False,
    default=None,
)
@click.option(
    "--api-server",
    help="URL to an RSTUF API.",
    required=False,
)
@click.option(
    "--headers",
    "-H",
    help=("Headers to include in the request. " f"Example: {HEADERS_EXAMPLE}"),
    required=False,
)
@click.pass_context
def add(
    context: Context,
    artifact: str,
    oci_image: bool,
    path: Optional[str],
    api_server: Optional[str],
    headers: Optional[str],
) -> None:
    """
    Add artifacts to the TUF metadata.

    A POST /api/v1/artifacts/ request to the RSTUF API service is carried out,
    where:
    - file info is discovered and added to the request payload. The blake2b-256
    cryptographic hash function is used to hash the file.
    - `custom` key of the payload is an empty object
    - `path` key of the payload is defined by the user
    """

    settings = _set_settings(context, api_server, headers)

    if api_server:
        settings.SERVER = api_server

    if settings.get("SERVER") is None:
        raise click.ClickException(
            "Requires '--api-server' "
            "Example: --api-server https://api.rstuf.example.com"
        )

    if not oci_image and os.path.isfile(artifact):
        payload = create_artifact_add_payload_from_filepath(
            filepath=artifact, path=path
        )
    else:
        context.oci_cli = RSTUFRegistry()
        payload = add_container_oci(context, artifact)

    task_id = send_payload(
        settings=settings,
        url=URL.ARTIFACTS.value,
        payload=payload,
        expected_msg="New Artifact(s) successfully submitted.",
        command_name="Artifact Addition",
    )

    console.print("Successfully submitted task with a payload of:")
    print_json(data=payload)
    console.print(f"\nRSTUF task ID (use to check its status) is: {task_id}")
