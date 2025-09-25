#!/usr/bin/env python3
"""
Test script to generate sample job logs for testing the logs viewer
"""

import os
import sys
import time
from datetime import datetime

# Add Django project to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'clarity_dx_portal'))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
import django
django.setup()

from jobs.utils.job_logger import create_scan_processor_logger, create_upload_logger, create_mapping_logger


def test_scan_processing():
    """Test scan processing with enhanced logging"""
    print("🧪 Testing scan processing logging...")
    
    logger = create_scan_processor_logger()
    
    with logger.job_context(total_items=10, metadata={'test': True}):
        logger.log_info("Starting test scan processing")
        
        for i in range(10):
            bill_id = f"test_bill_{i+1}"
            logger.log_item_start(bill_id, f"Processing test bill {i+1}/10")
            
            # Simulate processing time
            time.sleep(0.5)
            
            if i < 8:  # 8 successful, 2 failed
                logger.log_item_success(bill_id, "Successfully processed test bill")
            else:
                logger.log_item_error(bill_id, "Test error", "Simulated processing failure")
        
        logger.log_info("Test scan processing completed")


def test_upload_processing():
    """Test upload processing with enhanced logging"""
    print("🧪 Testing upload processing logging...")
    
    logger = create_upload_logger()
    
    with logger.job_context(total_items=5, metadata={'test': True, 'filename': 'test_batch.pdf'}):
        logger.log_info("Starting test upload processing")
        
        for i in range(5):
            page_id = f"test_page_{i+1}"
            logger.log_item_start(page_id, f"Processing page {i+1}/5")
            
            # Simulate processing time
            time.sleep(0.3)
            
            if i < 4:  # 4 successful, 1 failed
                logger.log_item_success(page_id, "Successfully uploaded page")
            else:
                logger.log_item_error(page_id, "Upload failed", "Simulated upload error")
        
        logger.log_info("Test upload processing completed")


def test_mapping_processing():
    """Test mapping processing with enhanced logging"""
    print("🧪 Testing mapping processing logging...")
    
    logger = create_mapping_logger()
    
    with logger.job_context(total_items=7, metadata={'test': True}):
        logger.log_info("Starting test mapping processing")
        
        for i in range(7):
            bill_id = f"test_mapping_{i+1}"
            logger.log_item_start(bill_id, f"Mapping bill {i+1}/7")
            
            # Simulate processing time
            time.sleep(0.4)
            
            if i < 5:  # 5 successful, 2 failed
                logger.log_item_success(bill_id, "Successfully mapped bill")
            else:
                logger.log_item_error(bill_id, "Mapping failed", "Simulated mapping error")
        
        logger.log_info("Test mapping processing completed")


def main():
    """Run all test scenarios"""
    print("🚀 Starting enhanced logging tests...")
    print("=" * 50)
    
    try:
        # Test different job types
        test_scan_processing()
        time.sleep(1)
        
        test_upload_processing()
        time.sleep(1)
        
        test_mapping_processing()
        
        print("\n✅ All tests completed successfully!")
        print("📁 Check the logs/ directory for generated log files")
        print("🌐 Visit /billing/logs/ in your web browser to view the logs viewer")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
