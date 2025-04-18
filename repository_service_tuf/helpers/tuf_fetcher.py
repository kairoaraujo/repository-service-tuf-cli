# SPDX-FileCopyrightText: 2025 Repository Service for TUF Contributors
#
# SPDX-License-Identifier: MIT
import json
import os
from typing import Iterator
from urllib.parse import urlparse

import requests
from tuf.api.exceptions import DownloadError, DownloadHTTPError
from tuf.ngclient.fetcher import FetcherInterface

from repository_service_tuf.helpers.oras_registry import RSTUFRegistry


class RSTUFFetcher(FetcherInterface):
    """
    A python-tuf Fetcher that uses oras-py to retrieve files from a Container
    Registry.
    """

    def __init__(self, oci_client: RSTUFRegistry):
        """
        Initialize the RSTUFFetcher with registry details.

        Args:
            oci_client: An instance of RSTUFRegistry.

        Credentials are sourced from environment variables:
            RSTUF_CR_USERNAME: Username for the registry.
            RSTUF_CR_PASSWORD: Password or token for the registry.
        """
        self.client = oci_client
        self.oci_registry = False

        # Check environment variables for credentials
        username = os.getenv("RSTUF_CR_USERNAME")
        password = os.getenv("RSTUF_CR_PASSWORD")
        if username and password:
            self.client.login(username=username, password=password)

    def _fetch(self, url: str) -> Iterator[bytes]:
        """
        Fetch the contents of a URL, using requests for HTTP/HTTPS or
        oras-py for OCI URIs.

        Args:
            url: A URI, either:
                 - HTTP/HTTPS URL (e.g., 'https://md.example.com/1.root.json')
                 - OCI URI (e.g., 'ghcr.io/repository-service-tuf/targets:tag')

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
                    raise DownloadHTTPError(
                        f"HTTP {response.status_code} received for {url}",
                        response.status_code,
                    )
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
                # Assume OCI-style URI without protocol
                # (e.g., ghcr.io/project/repo:tag)
                image_ref = url

                if ":" not in image_ref and "@" not in image_ref:
                    raise DownloadError(
                        f"Invalid OCI URI: {url}. Must include tag or digest."
                    )

                # Fetch the manifest
                raw_data = self.client.get_raw_data(container=image_ref)
                yield json.dumps(raw_data).encode("utf-8")
            except DownloadHTTPError as e:
                raise e
            except Exception as e:
                raise DownloadError(f"Failed to fetch {url}: {str(e)}")
