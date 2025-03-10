#!/usr/bin/env python3

import sys
import hashlib
import json
import re
from oras.client import OrasClient
from oras.provider import Registry
from oras import decorator
from typing import Dict, Any
import requests

class MyRegistry(Registry):
    """
    Oras registry with support for image indexes.
    """
    @decorator.ensure_container
    def get_image_index(self, container, allowed_media_type=None):
        """
        Get an image index as a manifest.
        """
        if not allowed_media_type:
            default_image_index_media_type = "application/vnd.oci.image.index.v1+json"
            allowed_media_type = [default_image_index_media_type]

        headers = {"Accept": ";".join(allowed_media_type)}
        manifest_url = f"{self.prefix}://{container.manifest_url()}"
        response = self.do_request(manifest_url, "GET", headers=headers)
        self._check_200_response(response)
        manifest = response.json()
        return manifest

    @decorator.ensure_container
    def get_manifest_raw(self, container, allowed_media_type=None):
        """
        Get the raw manifest or index data (bytes) with headers.
        """
        if not allowed_media_type:
            allowed_media_type = [
                "application/vnd.oci.image.index.v1+json",  # Index
                "application/vnd.oci.image.manifest.v1+json"  # Manifest
            ]

        headers = {"Accept": ";".join(allowed_media_type)}
        manifest_url = f"{self.prefix}://{container.manifest_url()}"
        response = self.do_request(manifest_url, "GET", headers=headers)
        self._check_200_response(response)
        return response.content, response.headers

def add_to_rstuf(path: str, size: int, digest: str, payload: Dict[str, Any]):
    """Placeholder function to add an artifact to RSTUF."""
    # Replace this with your actual RSTUF API call
    payload["artifacts"].append(
         {
             "info": {
                 "length": size,
                 "hashes": {
                     digest.split(":")[0]: digest.split(":")[1]
                 },
            },
            "path": path
        }
    )
    print(f"Adding to RSTUF: path={path}, size={size}, digest={digest}")
    return payload

def send_payload_to_rstuf(rstuf_url, payload: Dict[str, Any]):
    print(json.dumps(payload, indent=4))
    resp = requests.post(f"{rstuf_url}/api/v1/artifacts/", json=payload, headers={"apikey": "Yuc1gkhWcM3xXLAcob0_xvsNO5-iCyL4XPuLZl0WsoI"})
    print(resp.text)

def calculate_size_and_hash(data: bytes) -> tuple[int, str]:
    """Calculate the size and SHA-256 hash of the given data."""
    size = len(data)
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    return size, digest

def get_uri_for_digest(uri: str, digest: str) -> str:
    """Given a URI for an image, return a URI for the related digest."""
    base_uri = re.split(r"[@:]", uri, maxsplit=1)[0]
    return f"{base_uri}@{digest}"

def process_image(image_ref: str, rstuf_api: str):
    """Process the container image and add artifacts to RSTUF."""
    # Initialize ORAS client with custom registry
    client = MyRegistry()

    # Extract repository and tag from image_ref
    if "@" in image_ref:
        print("It doesn't support hashs, only tags")
        sys.exit(1)

    # Extract repository and tag from image_ref
    if "@" in image_ref:
        repo, tag_or_digest = image_ref.split("@", 1)
    else:
        repo, tag_or_digest = image_ref.rsplit(":", 1)
    rstuf_path_base = repo.split("/", 1)[1]

    # Fetch the raw manifest or index data
    try:
        raw_data = client.get_image_index(container=image_ref)
        manifest = json.dumps(raw_data)
    except Exception as e:
        print(f"Error fetching manifest for {image_ref}: {e}", file=sys.stderr)
        sys.exit(1)

    # Calculate size and hash of the raw data
    size, digest = calculate_size_and_hash(manifest.encode("utf-8"))

    payload = {"artifacts": []}
    # Check if it’s an index or a single manifest
    if raw_data["mediaType"] == "application/vnd.oci.image.index.v1+json":  # Index
        # Add the index artifact
        index_path = f"{rstuf_path_base}:{tag_or_digest}"
        payload = add_to_rstuf(index_path, size, digest, payload)

        # Process each manifest in the index
        for manifest in raw_data.get("manifests", []):
            digest = manifest["digest"]
            manifest_path = f"{rstuf_path_base}@{digest}"
            # Fetch the individual manifest to get its size and hash
            manifest_data = client.get_manifest(container=get_uri_for_digest(image_ref, digest))
            size, digest = calculate_size_and_hash(json.dumps(manifest_data).encode("utf-8"))
            payload = add_to_rstuf(manifest_path, size, digest, payload)

    else:  # Single manifest
        # Add artifact with tag
        tag_path = f"{rstuf_path_base}:{tag_or_digest}"
        payload = add_to_rstuf(tag_path, size, digest, payload)

        # Add artifact with digest
        digest_path = f"{rstuf_path_base}@{digest}"
        payload = add_to_rstuf(digest_path, size, digest, payload)

    send_payload_to_rstuf(rstuf_api, payload)

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <image-reference> <rstuf-api>", file=sys.stderr)
        sys.exit(1)

    image_ref = sys.argv[1]
    rstuf_api = sys.argv[2]
    process_image(image_ref, rstuf_api)

if __name__ == "__main__":
    main()