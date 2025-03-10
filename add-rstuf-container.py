#!/usr/bin/env python3

import sys
import hashlib
import json
from oras.client import OrasClient
from oras import defaults

def _to_rstuf(path: str, size: int, digest: str):
    """Placeholder function to  an artifact to RSTUF."""
    # Replace this with your actual RSTUF API call
    print(f"ing to RSTUF: path={path}, size={size}, digest={digest}")

def calculate_size_and_hash(data: bytes) -> tuple[int, str]:
    """Calculate the size and SHA-256 hash of the given data."""
    size = len(data)
    digest = f"sha256:{hashlib.sha256(data).hexdigest()}"
    return size, digest

def process_image(image_ref: str):
    """Process the container image and  artifacts to RSTUF."""
    # Initialize ORAS client (assuming public registry;  auth if needed)
    client = OrasClient()

    # Extract repository and tag from image_ref
    if "@" in image_ref:
        repo, tag_or_digest = image_ref.split("@", 1)
    else:
        repo, tag_or_digest = image_ref.rsplit(":", 1)
    rstuf_path_base = repo.split("/", 1)[1]  # Remove registry prefix (ghcr.io/)

    # Fetch the manifest or index
    try:
        manifest_data, manifest_headers = client.get_manifest(image_ref, raw=True)
        content_type = manifest_headers.get("Content-Type")
        manifest_json = json.loads(manifest_data.decode("utf-8"))
    except Exception as e:
        print(f"Error fetching manifest for {image_ref}: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if it’s an index (manifest list) or a single manifest
    if content_type == defaults.multi_manifest_content_type:  # Index (manifest list)
        # Calculate size and hash of the index
        size, digest = calculate_size_and_hash(manifest_data)
        index_path = f"{rstuf_path_base}:{tag_or_digest}"
        _to_rstuf(index_path, size, digest)

        # Process each manifest in the index
        for manifest in manifest_json.get("manifests", []):
            digest = manifest["digest"]
            manifest_path = f"{rstuf_path_base}@{digest}"
            # Fetch the individual manifest to get its size
            manifest_data, _ = client.get_manifest(f"{repo}@{digest}", raw=True)
            size, _ = calculate_size_and_hash(manifest_data)
            _to_rstuf(manifest_path, size, digest)

    else:  # Single manifest
        # Calculate size and hash of the manifest
        size, digest = calculate_size_and_hash(manifest_data)
        
        #  artifact with tag
        tag_path = f"{rstuf_path_base}:{tag_or_digest}"
        _to_rstuf(tag_path, size, digest)
        
        #  artifact with digest
        digest_path = f"{rstuf_path_base}@{digest}"
        _to_rstuf(digest_path, size, digest)

def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <image-reference>", file=sys.stderr)
        sys.exit(1)

    image_ref = sys.argv[1]
    process_image(image_ref)

if __name__ == "__main__":
    main()