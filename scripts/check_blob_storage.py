from pathlib import Path

from dotenv import load_dotenv

from ingestion.blob_storage import BlobStorage


def main():
    load_dotenv()

    match_id = "EUW1_8019593098"

    local_path = Path("data/matches") / f"{match_id}.json"
    blob_name = f"matches/{match_id}.json"

    storage = BlobStorage()

    uploaded = storage.upload_file(
        local_path=local_path,
        blob_name=blob_name,
    )

    if uploaded:
        print("Premier upload réussi !")
    else:
        print("Le blob existe déjà !")


if __name__ == "__main__":
    main()
