#!/usr/bin/env python3

import os
import json
import requests
from typing import Iterator
from urllib.parse import urlparse
from oras.client import OrasClient
from oras.provider import Registry
from oras import decorator
from tuf.ngclient.fetcher import FetcherInterface
from tuf.api.exceptions import DownloadError, DownloadHTTPError

class MyRegistry(Registry):
    """
    Custom ORAS registry with raw manifest and blob fetching.
    """
    @decorator.ensure_container
    def get_raw_data(self, container, allowed_media_type=None):
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
    def get_blob(self, container, digest: str) -> bytes:
        """
        Fetch a blob by digest from the registry.
        """
        blob_url = f"{self.prefix}://{container.blobs_url()}/{digest}"
        response = self.do_request(blob_url, "GET")
        if response.status_code != 200:
            raise DownloadHTTPError(f"HTTP {response.status_code} received for {blob_url}", response.status_code)
        return response.content

class RSTUFFetcher(FetcherInterface):
    """
    A python-tuf Fetcher that uses oras-py to retrieve files from a Container Registry.
    """
    def __init__(self):
        """
        Initialize the RSTUFFetcher with registry details.

        Credentials are sourced from environment variables:
            RSTUF_CR_USERNAME: Username for the registry.
            RSTUF_CR_PASSWORD: Password or token for the registry.
        """
        self.client = MyRegistry()
        self.oci_registry = False

        # Check environment variables for credentials
        username = os.getenv("RSTUF_CR_USERNAME")
        password = os.getenv("RSTUF_CR_PASSWORD")
        if username and password:
            self.client.login(username=username, password=password)

    def _fetch(self, url: str) -> Iterator[bytes]:
        """
        Fetch the contents of a URL, using requests for HTTP/HTTPS or oras-py for OCI URIs.

        Args:
            url: A URI, either:
                 - HTTP/HTTPS URL (e.g., 'https://example.com/metadata/1.root.json')
                 - OCI URI (e.g., 'ghcr.io/repository-service-tuf/targets:example.txt')

        Raises:
            DownloadHTTPError: HTTP error code was received (e.g., 404, 403).
            DownloadError: General fetch error occurred.

        Returns:
            Bytes iterator of the requested content.
        """
        parsed_url = urlparse(url)

        if parsed_url.scheme in ["http", "https"]:
            # Use requests for HTTP/HTTPS URLs (e.g., TUF metadata)
            try:
                response = requests.get(url, stream=True)
                if response.status_code != 200:
                    raise DownloadHTTPError(f"HTTP {response.status_code} received for {url}", response.status_code)
                response.raw.decode_content = True  # Handle content-encoding
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:  # Filter out keep-alive chunks
                        yield chunk
            except requests.RequestException as e:
                raise DownloadError(f"Failed to fetch {url}: {str(e)}")

        else:
            self.oci_registry = True
            # Use oras-py for OCI URIs (e.g., container registry targets)
            try:
                # Assume OCI-style URI without protocol (e.g., ghcr.io/repo:tag)
                image_ref = url

                if ":" not in image_ref and "@" not in image_ref:
                    raise DownloadError(f"Invalid OCI URI: {url}. Must include tag or digest.")

                # Fetch the manifest
                raw_data = self.client.get_raw_data(container=image_ref)
                yield json.dumps(raw_data).encode("utf-8")
            except DownloadHTTPError as e:
                raise e
            except Exception as e:
                raise DownloadError(f"Failed to fetch {url}: {str(e)}")

#         target_path = updater.download_target(target_info)
#         print(f"Downloaded target to: {target_path}")