"""Upload local files (default: data/samples/) into the MinIO bucket.

python scripts/seed_minio.py                     # samples -> s3://$S3_BUCKET/samples/
python scripts/seed_minio.py ~/Verträge --prefix contracts/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from klausel.config import get_settings  # noqa: E402
from klausel.ingest.extract import SUPPORTED_SUFFIXES  # noqa: E402
from klausel.storage import make_s3_client, upload_file  # noqa: E402


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", default=str(ROOT / "data" / "samples"))
    ap.add_argument("--prefix", default="samples/")
    ap.add_argument("--bucket", default=s.s3_bucket)
    a = ap.parse_args()

    client = make_s3_client(s)
    client.head_bucket(Bucket=a.bucket)  # fails clearly if MinIO/bucket isn't up

    folder = Path(a.folder).expanduser()
    files = [
        p
        for p in sorted(folder.rglob("*"))
        if p.suffix.lower() in SUPPORTED_SUFFIXES and p.name.lower() != "readme.md"
    ]
    for p in files:
        key = f"{a.prefix}{p.relative_to(folder).as_posix()}"
        upload_file(client, a.bucket, key, str(p))
        print(f"uploaded s3://{a.bucket}/{key}")
    print(f"{len(files)} file(s) uploaded to {s.aws_endpoint_url}")


if __name__ == "__main__":
    main()
