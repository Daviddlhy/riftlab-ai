"""Construit un ZIP par liste explicite, sans secrets ni données locales."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]


def package(destination):
    paths = [ROOT / name for name in ("function_app.py", "host.json", "requirements.txt")]
    paths.extend(sorted((ROOT / "ingestion").glob("*.py")))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT))
    print(f"Package : {destination} ({len(paths)} fichiers)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/riftlab-function.zip"))
    package(parser.parse_args().output)
