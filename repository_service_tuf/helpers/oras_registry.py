# SPDX-FileCopyrightText: 2025 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT
import hashlib
import json
import re
import sys
from typing import Any, Dict

from click import Context
from oras.provider import Registry


class RSTUFRegistry(Registry):
    """
    Custom ORAS registry with raw manifest and blob fetching.
    """

    from oras import decorator

    @decorator.ensure_container
    def get_raw_data(self, container, allowed_media_type=None):
        """
        Get an image index as a manifest.
        """
        if not allowed_media_type:
            default_image_index_media_type = (
                "application/vnd.oci.image.index.v1+json"
            )
            allowed_media_type = [default_image_index_media_type]

        headers = {"Accept": ";".join(allowed_media_type)}
        manifest_url = f"{self.prefix}://{container.manifest_url()}"
        response = self.do_request(manifest_url, "GET", headers=headers)
        self._check_200_response(response)
        manifest = response.json()
        return manifest


def _parse_container_url(url):
    """
    Parse container reference URLs into their components.

    Args:
        url (str): Container reference URL (e.g., 'postgres:17', 'ngnix:1.27.4',
        'ghcr.io/in-toto/archivista:0.9.0')

    Returns:
        str: normalized URL
    """
    # Default values
    server = "registry-1.docker.io"
    path = ""
    tag = "latest"

    # Handle tag separation first
    if ":" in url:
        image_part, tag = url.rsplit(":", 1)
    else:
        image_part = url

    # Check if there's a server (contains a dot or starts with a known registry)
    parts = image_part.split("/")

    # Determine if first part is a server
    if "." in parts[0] or parts[0].startswith("registry"):
        server = parts[0]
        parts = parts[1:]

    # Handle path and image
    if len(parts) > 1:
        path = "/".join(parts[:-1])
        image = parts[-1]
    else:
        image = parts[0]
        # For Docker Hub, use 'library' if no custom path
        path = "library" if server == "registry-1.docker.io" else ""

    # Build normalized URL
    if path:
        normalized_url = f"{server}/{path}/{image}:{tag}"
    else:
        normalized_url = f"{server}/{image}:{tag}"

    return normalized_url


def _add_to_rstuf(path: str, size: int, digest: str, payload: Dict[str, Any]):
    """Placeholder function to add an artifact to RSTUF."""
    # Replace this with your actual RSTUF API call
    payload["artifacts"].append(
        {
            "info": {
                "length": size,
                "hashes": {digest.split(":")[0]: digest.split(":")[1]},
            },
            "path": path,
        }
    )
    return payload


def _calculate_size_and_hash(data: bytes) -> tuple[int, str]:
    """Calculate the size and SHA-256 hash of the given data."""
    size = len(data)
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    return size, digest


def _get_uri_for_digest(uri: str, digest: str) -> str:
    """Given a URI for an image, return a URI for the related digest."""
    base_uri = re.split(r"[@:]", uri, maxsplit=1)[0]
    return f"{base_uri}@{digest}"


def _sanitize_dockerhub_path(image_ref: str, path: str) -> str:
    """Sanitize the path to remove any leading slashes."""
    # if image_ref.startswith("registry-1.docker.io"):
    #     return path.replace("library/", "")
    return path


def add_container_oci(context: Context, image_ref: str):
    """Process the container image and add artifacts to RSTUF."""
    # Initialize ORAS client with custom registry
    client = context.oci_cli

    # Extract repository and tag from image_ref
    if "@" in image_ref:
        print("It doesn't support hashs, only tags")
        sys.exit(1)

    # Extract repository and tag from image_ref
    image_ref = _parse_container_url(image_ref)
    if "@" in image_ref:
        repo, tag_or_digest = image_ref.split("@", 1)
    else:
        repo, tag_or_digest = image_ref.rsplit(":", 1)

    if len(repo.split("/")) > 1:
        rstuf_path_base = repo.split("/", 1)[1]
    else:
        rstuf_path_base = repo

    # Fetch the raw manifest or index data
    try:
        raw_data = client.get_raw_data(container=image_ref)
        manifest = json.dumps(raw_data)
    except Exception as e:
        print(f"Error fetching manifest for {image_ref}: {e}", file=sys.stderr)
        sys.exit(1)

    # Calculate size and hash of the raw data
    size, digest = _calculate_size_and_hash(manifest.encode("utf-8"))

    payload = {"artifacts": []}
    # Check if it’s an index or a single manifest
    if (
        raw_data["mediaType"] == "application/vnd.oci.image.index.v1+json"
    ):  # Index
        # Add the index artifact
        index_path = _sanitize_dockerhub_path(
            image_ref, f"{rstuf_path_base}:{tag_or_digest}"
        )
        payload = _add_to_rstuf(index_path, size, digest, payload)

        # Process each manifest in the index
        for manifest in raw_data.get("manifests", []):
            digest = manifest["digest"]
            manifest_path = _sanitize_dockerhub_path(
                image_ref, f"{rstuf_path_base}@{digest}"
            )
            # Fetch the individual manifest to get its size and hash
            manifest_data = client.get_manifest(
                container=_get_uri_for_digest(image_ref, digest)
            )
            size, digest = _calculate_size_and_hash(
                json.dumps(manifest_data).encode("utf-8")
            )
            payload = _add_to_rstuf(manifest_path, size, digest, payload)

    else:  # Single manifest
        # Add artifact with tag
        tag_path = _sanitize_dockerhub_path(
            image_ref, f"{rstuf_path_base}:{tag_or_digest}"
        )
        payload = _add_to_rstuf(tag_path, size, digest, payload)

        # Add artifact with digest
        digest_path = f"{rstuf_path_base}@{digest}"
        payload = _add_to_rstuf(digest_path, size, digest, payload)

    return payload
