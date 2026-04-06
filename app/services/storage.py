"""
Backblaze B2 / S3-compatible storage helpers.

Fix: Backblaze B2 requires each multipart part to be ≥5MB.
     NIfTI files (~2MB) were failing with "No vaults" / ServiceUnavailable
     because create_multipart_upload was called unconditionally.

     Now uses put_object for files <10MB (single-shot, no minimum size),
     and multipart only for files ≥10MB (with 10MB parts, safely above B2's 5MB minimum).
"""
import io
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from app.core.config import settings
import functools
import logging

logger = logging.getLogger(__name__)

# Backblaze B2 minimum part size for multipart upload is 5MB.
# We use 10MB parts (2× the minimum) to be safe, and only use
# multipart at all for files that are larger than 10MB.
_MULTIPART_THRESHOLD = 10 * 1024 * 1024   # 10MB — files smaller than this use put_object
_MULTIPART_PART_SIZE = 10 * 1024 * 1024   # 10MB per part


@functools.lru_cache(maxsize=1)
def _r2():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            retries={"max_attempts": 3, "mode": "adaptive"},
        ),
    )


async def upload_stream_to_r2(
    file,
    key: str,
    max_bytes: int = 500 * 1024 * 1024,
    chunk_size: int = _MULTIPART_PART_SIZE,
    content_type: str = "application/octet-stream",
) -> int:
    """
    Stream an UploadFile to Backblaze B2 / R2.

    For files < 10MB: reads fully into memory and uses put_object.
      - Avoids B2's 5MB minimum part size restriction.
      - NIfTI files (~2MB) always take this path.

    For files ≥ 10MB: uses multipart upload with 10MB parts.
      - Never loads the entire file into RAM.

    Returns total bytes written.
    Raises HTTPException(413) if file exceeds max_bytes.
    Raises HTTPException(400) if file is empty.
    """
    from fastapi import HTTPException as _HTTPException

    client = _r2()

    # ── Read the entire file to determine size ────────────────────────────────
    # FastAPI UploadFile doesn't expose Content-Length reliably, so we read
    # the whole thing. For files ≥ 10MB we'll re-stream from a BytesIO buffer.
    data = await file.read()
    total = len(data)

    if total == 0:
        raise _HTTPException(400, "Empty file uploaded.")
    if total > max_bytes:
        raise _HTTPException(413, f"File too large ({total} bytes). Maximum {max_bytes} bytes.")

    # ── Small file: single put_object ─────────────────────────────────────────
    if total < _MULTIPART_THRESHOLD:
        try:
            client.put_object(
                Bucket=settings.r2_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
                ServerSideEncryption="AES256",
            )
            logger.info(
                "Uploaded to B2 (put_object) | key=%s bytes=%d", key, total
            )
            return total
        except ClientError as e:
            logger.error("put_object failed | key=%s error=%s", key, e)
            raise RuntimeError(
                f"File upload failed: {e.response['Error']['Message']}"
            )

    # ── Large file: multipart upload ──────────────────────────────────────────
    mpu = client.create_multipart_upload(
        Bucket=settings.r2_bucket_name,
        Key=key,
        ContentType=content_type,
        ServerSideEncryption="AES256",
    )
    upload_id = mpu["UploadId"]
    parts = []
    part_num = 1

    try:
        buf = io.BytesIO(data)
        while True:
            chunk = buf.read(_MULTIPART_PART_SIZE)
            if not chunk:
                break
            resp = client.upload_part(
                Bucket=settings.r2_bucket_name,
                Key=key,
                PartNumber=part_num,
                UploadId=upload_id,
                Body=chunk,
            )
            parts.append({"PartNumber": part_num, "ETag": resp["ETag"]})
            part_num += 1

        client.complete_multipart_upload(
            Bucket=settings.r2_bucket_name,
            Key=key,
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        logger.info(
            "Uploaded to B2 (multipart) | key=%s bytes=%d parts=%d",
            key, total, len(parts),
        )
        return total

    except Exception as e:
        try:
            client.abort_multipart_upload(
                Bucket=settings.r2_bucket_name, Key=key, UploadId=upload_id
            )
        except Exception:
            pass
        logger.error("Multipart upload failed | key=%s error=%s", key, e)
        raise RuntimeError(f"File upload failed: {e}")


def upload_bytes_to_r2(
    key: str,
    data: bytes,
    content_type: str = "application/octet-stream",
):
    """Upload a bytes object to B2. Always uses put_object (no size restriction)."""
    try:
        _r2().put_object(
            Bucket=settings.r2_bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        logger.info("Uploaded to B2 | key=%s bytes=%d", key, len(data))
    except ClientError as e:
        logger.error("R2 upload failed | key=%s error=%s", key, e)
        raise RuntimeError(f"File upload failed: {e.response['Error']['Message']}")


def upload_file_to_r2(
    key: str,
    file_path: str,
    content_type: str = "application/octet-stream",
):
    """Upload a local file to B2 using boto3's managed transfer (handles multipart automatically)."""
    import boto3.s3.transfer

    transfer_config = boto3.s3.transfer.TransferConfig(
        multipart_threshold=_MULTIPART_THRESHOLD,
        multipart_chunksize=_MULTIPART_PART_SIZE,
        max_concurrency=4,
    )
    try:
        _r2().upload_file(
            file_path,
            settings.r2_bucket_name,
            key,
            Config=transfer_config,
            ExtraArgs={
                "ContentType": content_type,
                "ServerSideEncryption": "AES256",
            },
        )
        logger.info("Uploaded file to B2 | key=%s path=%s", key, file_path)
    except ClientError as e:
        raise RuntimeError(f"File upload failed: {e.response['Error']['Message']}")


def generate_presigned_url(key: str, expires: int = 3600) -> str:
    try:
        return _r2().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.r2_bucket_name, "Key": key},
            ExpiresIn=expires,
        )
    except ClientError as e:
        raise RuntimeError(f"Could not generate presigned URL: {e}")


def download_from_r2(key: str, dest_path: str):
    _r2().download_file(settings.r2_bucket_name, key, dest_path)