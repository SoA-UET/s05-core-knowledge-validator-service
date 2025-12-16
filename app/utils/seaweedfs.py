"""
SeaweedFS client utility for file storage operations.
"""

import os
import json
import requests
from typing import Any
from dotenv import load_dotenv

load_dotenv()


class SeaweedFSClient:
    """
    Client for interacting with SeaweedFS file storage.
    """

    def __init__(self):
        self.master_url = os.getenv("SEAWEEDFS_MASTER_URL", "http://localhost:9333")
        self.volume_url = os.getenv("SEAWEEDFS_VOLUME_URL", "http://localhost:8080")

    def upload_file(self, data: bytes, filename: str = "data.json") -> str:
        """
        Upload a file to SeaweedFS and return the file ID.

        Args:
            data: The file content as bytes
            filename: The filename to use

        Returns:
            The SeaweedFS file ID (e.g., "3,01234567")

        Raises:
            Exception: If upload fails
        """
        # First, get an assignment from the master
        assign_response = requests.post(f"{self.master_url}/dir/assign")
        assign_response.raise_for_status()
        assign_data = assign_response.json()

        fid = assign_data["fid"]  # e.g., "3,01234567"
        url = assign_data["url"]  # e.g., "localhost:8080"

        # Upload the file to the volume server
        upload_url = f"http://{url}/{fid}"
        files = {"file": (filename, data)}
        upload_response = requests.post(upload_url, files=files)
        upload_response.raise_for_status()

        return fid

    def upload_json(self, data: dict | list) -> str:
        """
        Upload JSON data to SeaweedFS.

        Args:
            data: The data to serialize to JSON and upload

        Returns:
            The SeaweedFS file ID

        Raises:
            Exception: If upload fails
        """
        json_bytes = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        return self.upload_file(json_bytes, "data.json")

    def download_file(self, file_id: str) -> bytes:
        """
        Download a file from SeaweedFS.

        Args:
            file_id: The SeaweedFS file ID (e.g., "3,01234567")

        Returns:
            The file content as bytes

        Raises:
            Exception: If download fails
        """
        # Lookup the file location from master
        lookup_response = requests.get(
            f"{self.master_url}/dir/lookup", params={"volumeId": file_id.split(",")[0]}
        )
        lookup_response.raise_for_status()
        lookup_data = lookup_response.json()

        if "locations" not in lookup_data or not lookup_data["locations"]:
            raise Exception(f"File not found: {file_id}")

        volume_url = lookup_data["locations"][0]["url"]

        # Download the file
        download_url = f"http://{volume_url}/{file_id}"
        download_response = requests.get(download_url)
        download_response.raise_for_status()

        return download_response.content

    def download_json(self, file_id: str) -> dict | list:
        """
        Download and parse JSON data from SeaweedFS.

        Args:
            file_id: The SeaweedFS file ID

        Returns:
            The parsed JSON data

        Raises:
            Exception: If download or parsing fails
        """
        content = self.download_file(file_id)
        return json.loads(content.decode("utf-8"))

    def delete_file(self, file_id: str) -> bool:
        """
        Delete a file from SeaweedFS.

        Args:
            file_id: The SeaweedFS file ID

        Returns:
            True if deletion was successful

        Raises:
            Exception: If deletion fails
        """
        # Lookup the file location
        lookup_response = requests.get(
            f"{self.master_url}/dir/lookup", params={"volumeId": file_id.split(",")[0]}
        )
        lookup_response.raise_for_status()
        lookup_data = lookup_response.json()

        if "locations" not in lookup_data or not lookup_data["locations"]:
            return True  # File doesn't exist, consider it deleted

        volume_url = lookup_data["locations"][0]["url"]

        # Delete the file
        delete_url = f"http://{volume_url}/{file_id}"
        delete_response = requests.delete(delete_url)
        delete_response.raise_for_status()

        return True


# Singleton instance
seaweedfs_client = SeaweedFSClient()
