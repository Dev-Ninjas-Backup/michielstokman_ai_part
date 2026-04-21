import boto3
from botocore.exceptions import ClientError
import uuid
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

def get_s3_client():
    if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY or not settings.AWS_BUCKET_NAME:
        logger.warning("AWS S3 credentials are not fully set in the environment variables.")
        return None
    
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION_NAME
    )


def upload_audio_bytes_to_s3(audio_bytes: bytes, file_extension: str = "mp3") -> str | None:
    """
    Uploads audio bytes to AWS S3 and returns the public URL.
    Returns None if S3 is not configured or an error occurs.
    """
    client = get_s3_client()
    if not client:
        return None

    file_name = f"audio/{uuid.uuid4().hex}.{file_extension}"
    bucket_name = settings.AWS_BUCKET_NAME

    try:
        # Uploading to S3
        client.put_object(
            Bucket=bucket_name,
            Key=file_name,
            Body=audio_bytes,
            ContentType="audio/mpeg",  # Change depending on extension if needed
            # ACL='public-read' # Optional: if your bucket allows public ACLs
        )
        
        # Construct the URL
        url = f"https://{bucket_name}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{file_name}"
        return url
        
    except ClientError as e:
        logger.error(f"Failed to upload audio to S3: {e}")
        return None


def upload_image_to_s3(image_bytes: bytes, file_extension: str = "jpg") -> tuple[str, str] | tuple[None, None]:
    """
    Uploads image bytes to AWS S3 under the images/ prefix.
    Returns (public_url, s3_key) on success, or (None, None) on failure.
    S3 is required for images — there is no local fallback.
    """
    client = get_s3_client()
    if not client:
        logger.error("S3 is not configured. Cannot upload image — no local fallback for images.")
        return None, None

    ext = file_extension.lower().lstrip(".")
    content_type_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
    }
    content_type = content_type_map.get(ext, "application/octet-stream")

    s3_key = f"images/{uuid.uuid4().hex}.{ext}"
    bucket_name = settings.AWS_BUCKET_NAME

    try:
        client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=image_bytes,
            ContentType=content_type,
        )
        url = f"https://{bucket_name}.s3.{settings.AWS_REGION_NAME}.amazonaws.com/{s3_key}"
        logger.info(f"Image uploaded to S3: {s3_key}")
        return url, s3_key

    except ClientError as e:
        logger.error(f"Failed to upload image to S3: {e}")
        return None, None


def delete_s3_object(s3_key: str) -> bool:
    """
    Deletes an object from S3 by its key (e.g. 'images/abc123.jpg').
    Returns True on success, False on failure.
    """
    client = get_s3_client()
    if not client:
        logger.error("S3 is not configured. Cannot delete object.")
        return False

    try:
        client.delete_object(Bucket=settings.AWS_BUCKET_NAME, Key=s3_key)
        logger.info(f"S3 object deleted: {s3_key}")
        return True
    except ClientError as e:
        logger.error(f"Failed to delete S3 object '{s3_key}': {e}")
        return False
