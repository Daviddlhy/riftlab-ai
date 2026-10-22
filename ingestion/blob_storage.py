import hashlib
import os
from pathlib import Path

from azure.core.exceptions import ResourceExistsError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv


class BlobStorage:
    """Stockage des fichiers JSON Riot dans Azure Blob Storage."""

    def __init__(self):
        load_dotenv()

        account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "riot-raw")

        if not account_name:
            raise ValueError("AZURE_STORAGE_ACCOUNT_NAME is missing")

        account_url = f"https://{account_name}.blob.core.windows.net"

        credential = AzureCliCredential()

        service_client = BlobServiceClient(
            account_url=account_url,
            credential=credential,
        )

        self.container = service_client.get_container_client(container_name)

    def upload_file(
        self,
        local_path: Path,
        blob_name: str,
    ) -> bool:
        """Envoie un fichier ; ignore un blob existant seulement s'il est identique."""

        local_path = Path(local_path)

        if not local_path.is_file():
            raise FileNotFoundError(local_path)

        with local_path.open("rb") as file:
            try:
                self.container.upload_blob(
                    name=blob_name,
                    data=file,
                    overwrite=False,
                )
            except ResourceExistsError:
                self.verify_file(local_path, blob_name)
                return False

        return True

    def verify_file(self, local_path: Path, blob_name: str) -> str:
        """Compare les octets locaux et distants ; retourne leur SHA-256 commun."""
        local_hash = hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
        remote = self.container.download_blob(blob_name).readall()
        remote_hash = hashlib.sha256(remote).hexdigest()
        if remote_hash != local_hash:
            raise ValueError(f"Contenu Azure différent du fichier local : {blob_name}")
        return local_hash
