"""
S3 utilities for PDF retrieval
"""
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class S3PDFService:
    def __init__(self):
        self.s3_client = None
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize S3 client with credentials"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            self.s3_client = None
    
    def find_pdf(self, bill_id):
        """
        Find PDF file for a given bill ID in multiple S3 locations
        
        Args:
            bill_id (str): The provider bill ID
            
        Returns:
            tuple: (found, s3_key, pre_signed_url) or (False, None, None)
        """
        if not self.s3_client or not self.bucket_name:
            logger.error("S3 client not initialized or bucket name not set")
            return False, None, None
        
        # Define possible file extensions
        extensions = ['.pdf', '.PDF']
        
        # Search in each location
        for location in settings.PDF_SEARCH_LOCATIONS:
            for ext in extensions:
                # Try different naming patterns
                possible_keys = [
                    f"{location}{bill_id}{ext}",
                    f"{location}{bill_id}_{ext}",
                    f"{location}{bill_id}-{ext}",
                    f"{location}{bill_id}.{ext}",
                ]
                
                for key in possible_keys:
                    if self._object_exists(key):
                        try:
                            # Generate pre-signed URL (valid for 1 hour) with inline display
                            pre_signed_url = self.s3_client.generate_presigned_url(
                                'get_object',
                                Params={
                                    'Bucket': self.bucket_name, 
                                    'Key': key,
                                    'ResponseContentType': 'application/pdf',
                                    'ResponseContentDisposition': 'inline; filename="' + key.split('/')[-1] + '"'
                                },
                                ExpiresIn=3600  # 1 hour
                            )
                            logger.info(f"Found PDF for bill {bill_id} at {key}")
                            return True, key, pre_signed_url
                        except ClientError as e:
                            logger.error(f"Error generating pre-signed URL for {key}: {e}")
                            continue
        
        logger.warning(f"PDF not found for bill {bill_id} in any location")
        return False, None, None
    
    def _object_exists(self, key):
        """Check if an object exists in S3"""
        try:
            self.s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"Error checking object {key}: {e}")
                return False
    
    def get_pdf_content(self, bill_id):
        """
        Get PDF content directly from S3 for streaming
        
        Args:
            bill_id (str): The provider bill ID
            
        Returns:
            tuple: (found, s3_key, content_stream, content_type) or (False, None, None, None)
        """
        if not self.s3_client or not self.bucket_name:
            logger.error("S3 client not initialized or bucket name not set")
            return False, None, None, None
        
        # Define possible file extensions
        extensions = ['.pdf', '.PDF']
        
        # Search in each location
        for location in settings.PDF_SEARCH_LOCATIONS:
            for ext in extensions:
                # Try different naming patterns
                possible_keys = [
                    f"{location}{bill_id}{ext}",
                    f"{location}{bill_id}_{ext}",
                    f"{location}{bill_id}-{ext}",
                    f"{location}{bill_id}.{ext}",
                ]
                
                for key in possible_keys:
                    if self._object_exists(key):
                        try:
                            # Get the object from S3
                            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                            content_stream = response['Body']
                            content_type = response.get('ContentType', 'application/pdf')
                            
                            logger.info(f"Found PDF for bill {bill_id} at {key}")
                            return True, key, content_stream, content_type
                        except ClientError as e:
                            logger.error(f"Error getting PDF content for {key}: {e}")
                            continue
        
        logger.warning(f"PDF not found for bill {bill_id} in any location")
        return False, None, None, None

    def get_pdf_info(self, bill_id):
        """
        Get PDF information including file size and last modified
        
        Args:
            bill_id (str): The provider bill ID
            
        Returns:
            dict: PDF information or None if not found
        """
        found, s3_key, pre_signed_url = self.find_pdf(bill_id)
        
        if not found:
            return None
        
        try:
            response = self.s3_client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return {
                's3_key': s3_key,
                'pre_signed_url': pre_signed_url,
                'file_size': response.get('ContentLength', 0),
                'last_modified': response.get('LastModified'),
                'content_type': response.get('ContentType', 'application/pdf')
            }
        except ClientError as e:
            logger.error(f"Error getting PDF info for {s3_key}: {e}")
            return None

# Global instance
s3_pdf_service = S3PDFService()
