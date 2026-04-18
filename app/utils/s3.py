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
