"""MinIO access through the standard boto3 S3 client.

Credentials and the endpoint come from the usual AWS_* variables (see
`.env.example`), so the same code works against MinIO on localhost or on a VM.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import boto3
from botocore.client import BaseClient
from botocore.config import Config

from klausel.config import Settings, get_settings


@dataclass(frozen=True)
class S3Object:
    key: str
    etag: str
    size: int


def make_s3_client(settings: Settings | None = None) -> BaseClient:
    s = settings or get_settings()
    return boto3.client(
        "s3",
        endpoint_url=s.aws_endpoint_url,
        aws_access_key_id=s.aws_access_key_id,
        aws_secret_access_key=s.aws_secret_access_key,
        region_name=s.aws_default_region,
        # MinIO needs path-style addressing; SigV4 is required for auth.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def list_objects(
    client: BaseClient, bucket: str, prefix: str = "", suffixes: tuple[str, ...] = ()
) -> Iterator[S3Object]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith("/"):
                continue
            if suffixes and not key.lower().endswith(suffixes):
                continue
            yield S3Object(key=key, etag=obj["ETag"].strip('"'), size=obj["Size"])


def get_object_bytes(client: BaseClient, bucket: str, key: str) -> bytes:
    return client.get_object(Bucket=bucket, Key=key)["Body"].read()


def upload_file(client: BaseClient, bucket: str, key: str, path: str) -> None:
    client.upload_file(path, bucket, key)
