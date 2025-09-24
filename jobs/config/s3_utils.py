"""
S3 utility functions for interacting with AWS S3.
"""
import os
import logging
import boto3
from botocore.exceptions import ClientError
from pathlib import Path

logger = logging.getLogger(__name__)

def get_s3_client():
    """Get an S3 client with credentials from environment variables."""
    return boto3.client(
        's3',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-2')
    )

def upload(file_path: str, s3_key: str, bucket: str = None) -> bool:
    """
    Upload a file to S3.
    
    Args:
        file_path: Local path to the file
        s3_key: S3 key (path) where the file will be stored
        bucket: S3 bucket name (defaults to S3_BUCKET env var)
    
    Returns:
        bool: True if upload was successful, False otherwise
    """
    if bucket is None:
        bucket = os.getenv('S3_BUCKET') or os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        s3_client = get_s3_client()
        s3_client.upload_file(file_path, bucket, s3_key)
        logger.info(f"Successfully uploaded {file_path} to s3://{bucket}/{s3_key}")
        return True
    except ClientError as e:
        logger.error(f"Error uploading {file_path} to s3://{bucket}/{s3_key}: {str(e)}")
        return False

def download(s3_key: str, local_path: str, bucket: str = None) -> bool:
    """
    Download a file from S3.
    
    Args:
        s3_key: S3 key (path) of the file to download
        local_path: Local path where the file will be saved
        bucket: S3 bucket name (defaults to S3_BUCKET env var)
    
    Returns:
        bool: True if download was successful, False otherwise
    """
    if bucket is None:
        bucket = os.getenv('S3_BUCKET') or os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    logger.debug(f"Downloading from bucket: {bucket}, key: {s3_key}")
    
    try:
        s3_client = get_s3_client()
        s3_client.download_file(bucket, s3_key, local_path)
        logger.info(f"Successfully downloaded s3://{bucket}/{s3_key} to {local_path}")
        return True
    except ClientError as e:
        logger.error(f"Error downloading s3://{bucket}/{s3_key} to {local_path}: {str(e)}")
        return False

def list_objects(prefix: str, bucket: str = None) -> list:
    """
    List objects in an S3 bucket with the given prefix.
    
    Args:
        prefix: S3 key prefix to filter objects
        bucket: S3 bucket name (defaults to S3_BUCKET env var)
    
    Returns:
        list: List of object keys
    """
    if bucket is None:
        bucket = os.getenv('S3_BUCKET') or os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        s3_client = get_s3_client()
        response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [obj['Key'] for obj in response.get('Contents', [])]
    except ClientError as e:
        logger.error(f"Error listing objects in s3://{bucket}/{prefix}: {str(e)}")
        return []

def move(source_key: str, dest_key: str, bucket: str = None) -> bool:
    if bucket is None:
        bucket = os.getenv('S3_BUCKET') or os.getenv('AWS_STORAGE_BUCKET_NAME')
    
    try:
        s3_client = get_s3_client()
        
        # First, verify source exists
        try:
            s3_client.head_object(Bucket=bucket, Key=source_key)
        except ClientError:
            logger.error(f"Source object does not exist: s3://{bucket}/{source_key}")
            return False
        
        # Copy to new location
        s3_client.copy_object(
            Bucket=bucket,
            CopySource={'Bucket': bucket, 'Key': source_key},
            Key=dest_key
        )
        
        # Verify the copy was successful before deleting
        try:
            s3_client.head_object(Bucket=bucket, Key=dest_key)
        except ClientError:
            logger.error(f"Copy verification failed for: s3://{bucket}/{dest_key}")
            return False
        
        # Only delete after successful copy verification
        s3_client.delete_object(Bucket=bucket, Key=source_key)
        logger.info(f"Successfully moved s3://{bucket}/{source_key} to s3://{bucket}/{dest_key}")
        return True
        
    except ClientError as e:
        logger.error(f"Error moving s3://{bucket}/{source_key} to s3://{bucket}/{dest_key}: {str(e)}")
        return False