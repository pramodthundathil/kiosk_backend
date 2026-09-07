import os
import logging
import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger(__name__)

# TransferConfig for Large File Uploads (Multipart Uploads)
# Configured for efficient multi-threaded transfer of large files (videos, zip archives, high-res assets)
LARGE_FILE_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=8 * 1024 * 1024,   # 8 MB threshold to trigger multipart upload
    max_concurrency=10,                     # 10 concurrent threads for parallel upload
    multipart_chunksize=8 * 1024 * 1024,   # 8 MB chunk size
    use_threads=True
)

def get_boto3_session():
    """Returns a boto3 session initialized with credentials from settings/environment."""
    aws_access_key_id = getattr(settings, "AWS_ACCESS_KEY_ID", os.getenv("AWS_ACCESS_KEY_ID"))
    aws_secret_access_key = getattr(settings, "AWS_SECRET_ACCESS_KEY", os.getenv("AWS_SECRET_ACCESS_KEY"))
    region_name = getattr(settings, "AWS_S3_REGION_NAME", os.getenv("AWS_S3_REGION_NAME", "ap-south-1"))

    return boto3.Session(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name
    )

def get_s3_client():
    """Returns an S3 boto3 client."""
    session = get_boto3_session()
    return session.client("s3")

def test_aws_credentials():
    """
    Tests AWS credentials by calling STS get_caller_identity.
    Returns dict with status, user arn, account id, or error details.
    """
    try:
        session = get_boto3_session()
        sts_client = session.client("sts")
        identity = sts_client.get_caller_identity()
        return {
            "success": True,
            "account": identity.get("Account"),
            "arn": identity.get("Arn"),
            "user_id": identity.get("UserId"),
        }
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"AWS Credential Test Failed: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

def test_s3_bucket_access(bucket_name=None):
    """
    Tests access to the specified (or default configured) S3 bucket by uploading, reading, and deleting a test file.
    """
    if not bucket_name:
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", os.getenv("AWS_STORAGE_BUCKET_NAME"))

    if not bucket_name:
        return {"success": False, "error": "AWS_STORAGE_BUCKET_NAME is not configured."}

    s3_client = get_s3_client()
    test_key = "health_checks/aws_test_file.txt"
    test_content = b"Kiosk Application AWS S3 Health Check"

    try:
        # Upload test object
        s3_client.put_object(Bucket=bucket_name, Key=test_key, Body=test_content, ContentType="text/plain")
        
        # Read back test object
        response = s3_client.get_object(Bucket=bucket_name, Key=test_key)
        content = response["Body"].read()

        # Clean up test object
        s3_client.delete_object(Bucket=bucket_name, Key=test_key)

        is_valid = (content == test_content)
        return {
            "success": is_valid,
            "bucket": bucket_name,
            "message": "S3 read/write test passed successfully." if is_valid else "Content mismatch during S3 read check."
        }
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"S3 Bucket Access Test Failed for {bucket_name}: {str(e)}")
        return {
            "success": False,
            "bucket": bucket_name,
            "error": str(e)
        }

def upload_file_to_s3(file_obj, object_name, bucket_name=None, content_type=None):
    """
    Uploads a file object or bytes to AWS S3 bucket.
    Returns the public/S3 URL of the uploaded file or None on error.
    """
    if not bucket_name:
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", os.getenv("AWS_STORAGE_BUCKET_NAME"))

    s3_client = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        if isinstance(file_obj, (bytes, bytearray)):
            s3_client.put_object(Bucket=bucket_name, Key=object_name, Body=file_obj, **extra_args)
        else:
            s3_client.upload_fileobj(
                file_obj,
                bucket_name,
                object_name,
                ExtraArgs=extra_args if extra_args else None,
                Config=LARGE_FILE_TRANSFER_CONFIG
            )

        region = getattr(settings, "AWS_S3_REGION_NAME", "ap-south-1")
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{object_name}"
        return url
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"Failed to upload file to S3 ({object_name}): {str(e)}")
        raise e

def upload_large_file_to_s3(file_path_or_obj, object_name, bucket_name=None, content_type=None):
    """
    Uploads large files (e.g. >100MB videos/assets) to AWS S3 using multipart transfer config.
    Supports file path string or file-like object.
    """
    if not bucket_name:
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", os.getenv("AWS_STORAGE_BUCKET_NAME"))

    s3_client = get_s3_client()
    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    try:
        if isinstance(file_path_or_obj, str) and os.path.isfile(file_path_or_obj):
            s3_client.upload_file(
                file_path_or_obj,
                bucket_name,
                object_name,
                ExtraArgs=extra_args if extra_args else None,
                Config=LARGE_FILE_TRANSFER_CONFIG
            )
        else:
            s3_client.upload_fileobj(
                file_path_or_obj,
                bucket_name,
                object_name,
                ExtraArgs=extra_args if extra_args else None,
                Config=LARGE_FILE_TRANSFER_CONFIG
            )

        region = getattr(settings, "AWS_S3_REGION_NAME", "ap-south-1")
        url = f"https://{bucket_name}.s3.{region}.amazonaws.com/{object_name}"
        return url
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"Failed large file upload to S3 ({object_name}): {str(e)}")
        raise e

def generate_presigned_upload_url(object_name, bucket_name=None, expiration=3600, content_type=None):
    """
    Generates a pre-signed S3 URL for uploading large files directly from client/browser to S3.
    This bypasses Django server memory & request payload limits completely.
    """
    if not bucket_name:
        bucket_name = getattr(settings, "AWS_STORAGE_BUCKET_NAME", os.getenv("AWS_STORAGE_BUCKET_NAME"))

    s3_client = get_s3_client()
    params = {'Bucket': bucket_name, 'Key': object_name}
    if content_type:
        params['ContentType'] = content_type

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod='put_object',
            Params=params,
            ExpiresIn=expiration
        )
        return url
    except (BotoCoreError, ClientError, Exception) as e:
        logger.error(f"Failed to generate presigned upload URL for {object_name}: {str(e)}")
        raise e
