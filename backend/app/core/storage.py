"""S3-compatible storage wrapper. Targets MinIO in dev and R2 in prod.

`S3_ENDPOINT` is the URL the api/worker use to read/write objects (over the
internal compose network). `S3_PUBLIC_ENDPOINT` is the URL we embed into
pre-signed download links — this needs to be reachable from the user's
browser, which usually means a different hostname than the internal one.
"""

from functools import lru_cache
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import get_settings


@lru_cache
def _client(endpoint_url: str | None = None):
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url or s.s3_endpoint,
        aws_access_key_id=s.s3_access_key,
        aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region,
        config=Config(signature_version="s3v4"),
    )


def put_object(key: str, body: bytes | BinaryIO, content_type: str) -> None:
    s = get_settings()
    _client().put_object(
        Bucket=s.s3_bucket, Key=key, Body=body, ContentType=content_type
    )


def get_object(key: str) -> bytes:
    s = get_settings()
    obj = _client().get_object(Bucket=s.s3_bucket, Key=key)
    return obj["Body"].read()


def delete_object(key: str) -> None:
    s = get_settings()
    _client().delete_object(Bucket=s.s3_bucket, Key=key)


def presigned_get_url(key: str, expires_in: int = 300) -> str:
    """Return a pre-signed URL the browser can use to download the object.

    Built against `S3_PUBLIC_ENDPOINT` so it's reachable from the host, not
    just inside the compose network.
    """
    s = get_settings()
    public = _client(s.s3_public_endpoint or s.s3_endpoint)
    return public.generate_presigned_url(
        "get_object",
        Params={"Bucket": s.s3_bucket, "Key": key},
        ExpiresIn=expires_in,
    )
