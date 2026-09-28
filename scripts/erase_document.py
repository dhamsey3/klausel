"""Right to erasure (GDPR Art. 17): delete a document from MinIO and Qdrant.

    python scripts/erase_document.py samples/dienstleistungsvertrag.txt

Bucket versioning is enabled, so all object versions are removed as well.
ZenML artifacts from past runs contain the (redacted) text too; prune them with
`zenml artifact prune` if the document must disappear everywhere.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from klausel.config import get_settings  # noqa: E402
from klausel.storage import make_s3_client  # noqa: E402
from klausel.vectorstore import erase_source, make_client  # noqa: E402


def main() -> None:
    s = get_settings()
    ap = argparse.ArgumentParser()
    ap.add_argument("key", help="S3 key of the document, as stored in the 'source' payload")
    ap.add_argument("--keep-object", action="store_true", help="only remove vectors")
    a = ap.parse_args()

    erase_source(make_client(s), s.qdrant_collection, a.key)
    print(f"Removed vectors for {a.key} from '{s.qdrant_collection}'")

    if not a.keep_object:
        s3 = make_s3_client(s)
        versions = s3.list_object_versions(Bucket=s.s3_bucket, Prefix=a.key)
        for v in versions.get("Versions", []) + versions.get("DeleteMarkers", []):
            if v["Key"] == a.key:
                s3.delete_object(Bucket=s.s3_bucket, Key=a.key, VersionId=v["VersionId"])
        print(f"Removed all versions of s3://{s.s3_bucket}/{a.key}")


if __name__ == "__main__":
    main()
