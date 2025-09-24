#!/usr/bin/env python3
"""
PDF Intake Split Job
Splits large PDF batches into individual pages and uploads to S3
Creates ProviderBill records for each page with SCANNED status
"""

import os
import sys
import tempfile
import shutil
import logging
from datetime import datetime
from uuid import uuid4
from pathlib import Path

# Add Django project to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'clarity_dx_portal'))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
import django
django.setup()

from PyPDF2 import PdfReader, PdfWriter
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from django.conf import settings
from django.utils import timezone
from django.db import transaction

# Import models
from billing.models import ProviderBill

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PDFIntakeProcessor:
    """Process PDF intake by splitting into individual pages and uploading to S3"""
    
    def __init__(self):
        self.s3_client = None
        self.bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        self._initialize_s3_client()
    
    def _initialize_s3_client(self):
        """Initialize S3 client with credentials"""
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=settings.AWS_S3_REGION_NAME
            )
            logger.info("S3 client initialized successfully")
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            self.s3_client = None
        except Exception as e:
            logger.error(f"Error initializing S3 client: {e}")
            self.s3_client = None
    
    def upload_to_s3(self, file_path, s3_key):
        """Upload file to S3"""
        if not self.s3_client:
            raise Exception("S3 client not initialized")
        
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, s3_key)
            logger.info(f"Successfully uploaded {s3_key} to S3")
            return True
        except ClientError as e:
            logger.error(f"Error uploading {s3_key} to S3: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading {s3_key}: {e}")
            raise
    
    def split_pdf_and_upload(self, pdf_path, uploaded_by, source_filename):
        """
        Split PDF into individual pages and upload each to S3
        Create ProviderBill records for each page
        
        Args:
            pdf_path (str): Path to the PDF file
            uploaded_by (str): Username of the user who uploaded the file
            source_filename (str): Original filename of the uploaded PDF
            
        Returns:
            list: List of created ProviderBill IDs
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        created_bill_ids = []
        
        try:
            # Read PDF
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            logger.info(f"Processing PDF with {num_pages} pages: {source_filename}")
            
            # Create temporary directory for split pages
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Process each page
                for page_num in range(num_pages):
                    try:
                        # Create single-page PDF
                        writer = PdfWriter()
                        writer.add_page(reader.pages[page_num])
                        
                        # Generate unique ID for this page
                        unique_id = uuid4().hex
                        page_filename = f"{unique_id}.pdf"
                        page_path = temp_path / page_filename
                        
                        # Write single-page PDF
                        with open(page_path, "wb") as f_out:
                            writer.write(f_out)
                        
                        # Upload to S3
                        s3_key = f"data/ProviderBills/pdf/{page_filename}"
                        self.upload_to_s3(str(page_path), s3_key)
                        
                        # Create ProviderBill record
                        with transaction.atomic():
                            bill = ProviderBill.objects.create(
                                id=unique_id,
                                uploaded_by=uploaded_by,
                                source_file=f"{source_filename} (Page {page_num + 1})",
                                status='SCANNED',
                                created_at=timezone.now(),
                                updated_at=timezone.now()
                            )
                            created_bill_ids.append(unique_id)
                            logger.info(f"Created ProviderBill record: {unique_id}")
                        
                    except Exception as e:
                        logger.error(f"Error processing page {page_num + 1}: {e}")
                        continue
                
                logger.info(f"Successfully processed {len(created_bill_ids)} pages from {source_filename}")
                return created_bill_ids
                
        except Exception as e:
            logger.error(f"Error processing PDF {source_filename}: {e}")
            raise
    
    def process_uploaded_pdf(self, uploaded_file, uploaded_by):
        """
        Process an uploaded PDF file from Django
        
        Args:
            uploaded_file: Django UploadedFile object
            uploaded_by (str): Username of the user who uploaded the file
            
        Returns:
            list: List of created ProviderBill IDs
        """
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            # Write uploaded file to temporary location
            for chunk in uploaded_file.chunks():
                temp_file.write(chunk)
            temp_file_path = temp_file.name
        
        try:
            # Process the PDF
            return self.split_pdf_and_upload(
                temp_file_path, 
                uploaded_by, 
                uploaded_file.name
            )
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)


def main():
    """Main function for command-line usage"""
    if len(sys.argv) != 3:
        print("Usage: python pdf_intake_split.py <pdf_path> <uploaded_by>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    uploaded_by = sys.argv[2]
    
    processor = PDFIntakeProcessor()
    
    try:
        bill_ids = processor.split_pdf_and_upload(pdf_path, uploaded_by, os.path.basename(pdf_path))
        print(f"Successfully processed PDF. Created {len(bill_ids)} ProviderBill records:")
        for bill_id in bill_ids:
            print(f"  - {bill_id}")
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
