#!/usr/bin/env python3
"""
Test script for the PDF intake system
"""

import os
import sys
import tempfile
from pathlib import Path

# Add Django project to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'clarity_dx_portal'))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
import django
django.setup()

from jobs.pdf_intake_split import PDFIntakeProcessor
from billing.models import ProviderBill

def test_pdf_processor():
    """Test the PDF processor with a sample PDF"""
    print("Testing PDF Intake Processor...")
    
    # Check if we have any test PDFs in the project
    test_pdf_paths = [
        "test_sample.pdf",
        "sample.pdf", 
        "test.pdf"
    ]
    
    test_pdf = None
    for pdf_path in test_pdf_paths:
        if os.path.exists(pdf_path):
            test_pdf = pdf_path
            break
    
    if not test_pdf:
        print("No test PDF found. Please place a test PDF file in the project root.")
        print("Expected filenames: test_sample.pdf, sample.pdf, or test.pdf")
        return False
    
    try:
        processor = PDFIntakeProcessor()
        print(f"Processing test PDF: {test_pdf}")
        
        # Process the PDF
        bill_ids = processor.split_pdf_and_upload(test_pdf, "test_user", os.path.basename(test_pdf))
        
        print(f"Successfully created {len(bill_ids)} ProviderBill records:")
        for bill_id in bill_ids:
            print(f"  - {bill_id}")
        
        # Verify records were created
        for bill_id in bill_ids:
            try:
                bill = ProviderBill.objects.get(id=bill_id)
                print(f"✓ Verified bill {bill_id}: status={bill.status}, source_file={bill.source_file}")
            except ProviderBill.DoesNotExist:
                print(f"✗ Bill {bill_id} not found in database")
                return False
        
        return True
        
    except Exception as e:
        print(f"Error testing PDF processor: {e}")
        return False

def test_database_connection():
    """Test database connection and ProviderBill model"""
    print("Testing database connection...")
    
    try:
        # Test basic database operations
        total_bills = ProviderBill.objects.count()
        scanned_bills = ProviderBill.objects.filter(status='SCANNED').count()
        
        print(f"✓ Database connection successful")
        print(f"  Total bills: {total_bills}")
        print(f"  Scanned bills: {scanned_bills}")
        
        return True
        
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False

def test_s3_connection():
    """Test S3 connection"""
    print("Testing S3 connection...")
    
    try:
        processor = PDFIntakeProcessor()
        if processor.s3_client:
            print("✓ S3 client initialized successfully")
            return True
        else:
            print("✗ S3 client not initialized - check AWS credentials")
            return False
            
    except Exception as e:
        print(f"✗ S3 connection test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 50)
    print("PDF Intake System Test")
    print("=" * 50)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("S3 Connection", test_s3_connection),
        ("PDF Processor", test_pdf_processor),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 30)
        result = test_func()
        results.append((test_name, result))
    
    print("\n" + "=" * 50)
    print("Test Results:")
    print("=" * 50)
    
    all_passed = True
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n✓ All tests passed! The intake system is ready to use.")
    else:
        print("\n✗ Some tests failed. Please check the configuration.")
    
    return all_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
