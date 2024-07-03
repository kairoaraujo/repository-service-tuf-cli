# SPDX-FileCopyrightText: 2023-2024 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

import click
from rich.markdown import Markdown
from tuf.api.metadata import DelegatedRole, Delegations, Metadata, Targets

# TODO: Should we use the global rstuf console exclusively? We do use it for
# `console.print`, but not with `Confirm/Prompt.ask`. The latter uses a default
# console from `rich`. Using a single console everywhere would makes custom
# configuration or, more importantly, patching in tests easier:
# https://rich.readthedocs.io/en/stable/console.html#console-api
# https://rich.readthedocs.io/en/stable/console.html#capturing-output
from repository_service_tuf.cli import console
from repository_service_tuf.cli.admin import metadata
from repository_service_tuf.cli.admin.helpers import (
    SignPayload,
    _add_signature_prompt,
    _configure_targets_delegations,
    _configure_targets_paths,
    _delegated_target_role_name_prompt,
    _expiry_prompt,
    _filter_root_verification_results,
    _print_delegation,
    _print_keys_for_signing,
    _print_root,
    _select_key,
    _threshold_prompt,
)
from repository_service_tuf.helpers.api_client import (
    URL,
    Methods,
    request_server,
    send_payload,
    task_status,
)


def _parse_pending_data(pending_roles_resp: Dict[str, Any]) -> Dict[str, Any]:
    data = pending_roles_resp.get("data")
    if data is None:
        error = "'data' field missing from api server response/file input"
        raise click.ClickException(error)

    pending_roles: Dict[str, Dict[str, Any]] = data.get("metadata", {})
    if len(pending_roles) == 0:
        raise click.ClickException("No metadata available for signing")

    return pending_roles


def _get_pending_roles(settings: Any) -> Dict[str, Dict[str, Any]]:
    """Get dictionary of pending roles for signing."""
    response = request_server(
        settings.SERVER, URL.METADATA_SIGN.value, Methods.GET
    )
    if response.status_code != 200:
        raise click.ClickException(
            f"Failed to fetch metadata for signing. Error: {response.text}"
        )

    return _parse_pending_data(response.json())


DEFAULT_PATH = "new-targets.json"


@metadata.command()  # type: ignore
@click.option(
    "--out",
    is_flag=False,
    flag_value=DEFAULT_PATH,
    help=f"Write output JSON result to FILENAME (default: '{DEFAULT_PATH}')",
    type=click.File("w"),
    required=False,
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help=(
        "Run sign in dry-run mode without sending result to API. "
        "Ignores options and configurations related to API."
    ),
)
@click.pass_context
def new(
    context: click.Context,
    out: Optional[click.File],
    dry_run: bool,
) -> None:
    """
    Perform new Targets metadata.

    * If `--out [FILENAME]` is passed, result is written to local FILENAME
    (in addition to being sent to API).

    * If `--dry-run` is passed, result is not sent to API.
    You can still pass `--out [FILENAME]` to store the result locally.
    """
    console.print("\n", Markdown("# New Targets Metadata Tool"))
    settings = context.obj["settings"]

    # Make sure user understands that result will be send to the API and if the
    # the user wants something else should use '--dry-run'.
    if settings.get("SERVER") is None and not dry_run:
        raise click.ClickException(
            "Either '--api-sever' admin option/'SERVER' in RSTUF config or "
            "'--dry-run' needed"
        )
    ###########################################################################
    # Create new Targets metadata empty object
    new_targets = Metadata(Targets())
    expire_days, expire_date = _expiry_prompt("targets")
    new_targets.signed.expires = expire_date
    name = _delegated_target_role_name_prompt()
    threshold = _threshold_prompt("targets")

    # ###########################################################################
    # Load the Public Keys used to sign the metadata
    delegated_role = DelegatedRole(
        name=name,
        threshold=threshold,
        keyids=[],
        terminating=True,
        paths=[],
        unrecognized_fields={"x-rstuf-expire-policy": expire_days},
    )
    paths = _configure_targets_paths(delegated_role)
    delegations = Delegations(keys={}, roles={})
    _configure_targets_delegations(delegated_role, delegations)
    ###########################################################################
    # Review metadata
    _print_delegation(delegations)

    # ###########################################################################
    # # Sign metadata
    # console.print(Markdown("## Sign"))
    # results = _filter_root_verification_results(root_result)
    # keys = _print_keys_for_signing(results)
    # key = _select_key(keys)
    # signature = _add_signature_prompt(root_md, key)

    # ###########################################################################
    # # Send payload to the API and/or save it locally

    # payload = SignPayload(signature=signature.to_dict())
    if out:
        json.dump({"delegations": delegations.to_dict()}, out, indent=2)  # type: ignore
        console.print(f"Saved result to '{out.name}'")

    # if settings.get("SERVER") and not dry_run:
    #     console.print(f"\nSending signature to {settings.SERVER}")
    #     task_id = send_payload(
    #         settings,
    #         URL.DELEGATION.value,
    #         asdict(payload),
    #         "Metadata sign accepted.",
    #         "Metadata sign",
    #     )
    #     task_status(task_id, settings, "Metadata sign status:")
    #     console.print("\nMetadata Signed and sent to the API! 🔑\n")
