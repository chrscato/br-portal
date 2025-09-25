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
        # Import enhanced logging
        from utils.job_logger import create_upload_logger
        
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        # Create job logger
        job_logger = create_upload_logger()
        
        with job_logger.job_context(metadata={
            'source_filename': source_filename,
            'uploaded_by': uploaded_by,
            'pdf_path': pdf_path
        }):
            try:
                # Read PDF
                reader = PdfReader(pdf_path)
                num_pages = len(reader.pages)
                job_logger.log_info(f"Processing PDF with {num_pages} pages: {source_filename}")
                
                # Update total items for progress tracking
                job_logger.progress.total_items = num_pages
                
                created_bill_ids = []
                successful = 0
                failed = 0
                
                # Create temporary directory for split pages
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    
                    # Process each page
                    for page_num in range(num_pages):
                        unique_id = uuid4().hex
                        job_logger.log_item_start(unique_id, f"Processing page {page_num + 1}/{num_pages}")
                        
                        try:
                            # Create single-page PDF
                            writer = PdfWriter()
                            writer.add_page(reader.pages[page_num])
                            
                            # Generate unique ID for this page
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
                                successful += 1
                                job_logger.log_item_success(unique_id, f"Created ProviderBill record for page {page_num + 1}")
                            
                        except Exception as e:
                            failed += 1
                            job_logger.log_item_error(unique_id, f"Error processing page {page_num + 1}: {str(e)}")
                            continue
                    
                    job_logger.log_info(f"Successfully processed {successful} pages from {source_filename}")
                    if failed > 0:
                        job_logger.log_warning(f"{failed} pages failed to process")
                    
                    return created_bill_ids
                    
            except Exception as e:
                job_logger.log_error(f"Error processing PDF {source_filename}: {e}", e)
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
    
    def process_multiple_uploaded_pdfs(self, uploaded_files, uploaded_by):
        """
        Process multiple uploaded PDF files from Django
        
        Args:
            uploaded_files: List of Django UploadedFile objects
            uploaded_by (str): Username of the user who uploaded the files
            
        Returns:
            dict: Dictionary with 'success' and 'failed' lists containing results
        """
        from utils.job_logger import create_upload_logger
        
        # Create job logger for batch processing
        job_logger = create_upload_logger()
        
        results = {
            'success': [],
            'failed': [],
            'total_files': len(uploaded_files),
            'total_bills_created': 0
        }
        
        with job_logger.job_context(metadata={
            'batch_upload': True,
            'uploaded_by': uploaded_by,
            'file_count': len(uploaded_files)
        }):
            job_logger.log_info(f"Starting batch processing of {len(uploaded_files)} PDF files")
            
            for i, uploaded_file in enumerate(uploaded_files, 1):
                file_id = f"file_{i}_{uploaded_file.name}"
                job_logger.log_item_start(file_id, f"Processing file {i}/{len(uploaded_files)}: {uploaded_file.name}")
                
                try:
                    # Validate file type
                    if not uploaded_file.name.lower().endswith('.pdf'):
                        raise ValueError(f"File {uploaded_file.name} is not a PDF file")
                    
                    # Process the individual PDF
                    bill_ids = self.process_uploaded_pdf(uploaded_file, uploaded_by)
                    
                    results['success'].append({
                        'filename': uploaded_file.name,
                        'bill_ids': bill_ids,
                        'pages_created': len(bill_ids)
                    })
                    results['total_bills_created'] += len(bill_ids)
                    
                    job_logger.log_item_success(file_id, f"Successfully processed {uploaded_file.name}, created {len(bill_ids)} bill records")
                    
                except Exception as e:
                    results['failed'].append({
                        'filename': uploaded_file.name,
                        'error': str(e)
                    })
                    job_logger.log_item_error(file_id, f"Failed to process {uploaded_file.name}: {str(e)}")
            
            job_logger.log_info(f"Batch processing complete. {len(results['success'])} files succeeded, {len(results['failed'])} failed. Total bills created: {results['total_bills_created']}")
            
            return results


def main():
    """Main function for command-line usage"""
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Single file: python pdf_intake_split.py <pdf_path> <uploaded_by>")
        print("  Multiple files: python pdf_intake_split.py --batch <pdf_path1> <pdf_path2> ... <uploaded_by>")
        sys.exit(1)
    
    processor = PDFIntakeProcessor()
    
    # Check if this is a batch operation
    if sys.argv[1] == '--batch':
        if len(sys.argv) < 4:
            print("Batch mode requires at least 2 PDF files and uploaded_by")
            print("Usage: python pdf_intake_split.py --batch <pdf_path1> <pdf_path2> ... <uploaded_by>")
            sys.exit(1)
        
        # Extract uploaded_by (last argument) and PDF paths (all but first and last)
        uploaded_by = sys.argv[-1]
        pdf_paths = sys.argv[2:-1]
        
        print(f"Processing {len(pdf_paths)} PDF files for user: {uploaded_by}")
        
        results = {
            'success': [],
            'failed': [],
            'total_bills_created': 0
        }
        
        for i, pdf_path in enumerate(pdf_paths, 1):
            print(f"\n[{i}/{len(pdf_paths)}] Processing: {os.path.basename(pdf_path)}")
            
            try:
                if not os.path.exists(pdf_path):
                    raise FileNotFoundError(f"PDF file not found: {pdf_path}")
                
                bill_ids = processor.split_pdf_and_upload(pdf_path, uploaded_by, os.path.basename(pdf_path))
                
                results['success'].append({
                    'filename': os.path.basename(pdf_path),
                    'bill_ids': bill_ids,
                    'pages_created': len(bill_ids)
                })
                results['total_bills_created'] += len(bill_ids)
                
                print(f"  ✓ Successfully processed {len(bill_ids)} pages")
                
            except Exception as e:
                results['failed'].append({
                    'filename': os.path.basename(pdf_path),
                    'error': str(e)
                })
                print(f"  ✗ Error: {e}")
        
        # Print summary
        print(f"\n=== BATCH PROCESSING SUMMARY ===")
        print(f"Total files processed: {len(pdf_paths)}")
        print(f"Successful: {len(results['success'])}")
        print(f"Failed: {len(results['failed'])}")
        print(f"Total ProviderBill records created: {results['total_bills_created']}")
        
        if results['failed']:
            print(f"\nFailed files:")
            for failed in results['failed']:
                print(f"  - {failed['filename']}: {failed['error']}")
        
        if results['success']:
            print(f"\nSuccessful files:")
            for success in results['success']:
                print(f"  - {success['filename']}: {success['pages_created']} pages")
    
    else:
        # Single file mode (original behavior)
        pdf_path = sys.argv[1]
        uploaded_by = sys.argv[2]
        
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
