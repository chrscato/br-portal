#!/usr/bin/env python3
"""
validate_intake.py

Validates ProviderBill records that have been processed by LLM.
Performs various checks and updates status and action fields accordingly.
"""
import os
import sys
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from .date_utils import standardize_and_validate_date_of_service

# Get the project root directory (2 levels up from this file) for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Load environment variables from the root .env file
load_dotenv(PROJECT_ROOT / '.env')

# Get the absolute path to the monolith root directory
DB_ROOT = Path(r"C:\Users\ChristopherCato\OneDrive - clarity-dx.com\code\br-portal")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def validate_provider_bill(bill_id: str, cursor: sqlite3.Cursor) -> tuple[str, str, str]:
    """
    Validate a ProviderBill record and its line items.
    Returns (status, action, error_message)
    """
    # Get the connection from the cursor
    conn = cursor.connection
    if not hasattr(conn, 'row_factory') or conn.row_factory != sqlite3.Row:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
    
    # Get the ProviderBill record
    cursor.execute("""
        SELECT * FROM ProviderBill WHERE id = ?
    """, (bill_id,))
    bill = cursor.fetchone()
    
    if not bill:
        return 'INVALID', 'to_validate', f"ProviderBill {bill_id} not found"
    
    # Get all line items for this bill
    cursor.execute("""
        SELECT * FROM BillLineItem WHERE provider_bill_id = ?
    """, (bill_id,))
    line_items = cursor.fetchall()
    
    if not line_items:
        return 'INVALID', 'add_line_items', f"No line items found for ProviderBill {bill_id}"
    
    # Validation checks
    errors = []
    
    # 1. Check required fields (only patient_name and total_charge are required)
    if not bill['patient_name']:
        errors.append("Missing Patient name")
    if not bill['total_charge']:
        errors.append("Missing Total charge")
    
    # 2. Validate line items
    for item in line_items:
        # Check CPT code format
        if not item['cpt_code'] or len(item['cpt_code']) != 5:
            errors.append(f"Invalid CPT code format: {item['cpt_code']}")
        
        # Check charge amount
        if not item['charge_amount'] or item['charge_amount'] <= 0:
            errors.append(f"Invalid charge amount: {item['charge_amount']}")
        
        # Check date of service - UPDATED with date utils
        try:
            date_str = item['date_of_service']
            
            # Date of service is required - null/empty dates are invalid
            if not date_str:
                errors.append(f"Missing date of service")
            else:
                is_valid, standardized_date, error_msg = standardize_and_validate_date_of_service(date_str)
                
                if not is_valid:
                    errors.append(f"Date of service error: {error_msg}")
                else:
                    # Log if we standardized the format
                    if date_str != standardized_date:
                        logger.info(f"Standardized date for line item {item['id']}: '{date_str}' -> '{standardized_date}'")
                    
        except Exception as e:
            errors.append(f"Error processing date: {date_str} - {str(e)}")
    
    # 3. Check total charge matches sum of line items
    total_line_charges = sum(item['charge_amount'] for item in line_items)
    if abs(total_line_charges - bill['total_charge']) > 10.00:  # Allow for small rounding differences
        errors.append(f"Total charge mismatch: {bill['total_charge']} vs {total_line_charges}")
    
    # Determine status and action based on validation results
    if errors:
        error_message = "; ".join(errors)
        return 'INVALID', 'to_validate', error_message
    
    # If all validations pass
    return 'VALID', 'to_map', None

def process_validation():
    """Process all ProviderBill records that need validation."""
    db_path = DB_ROOT / 'monolith.db'
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Set row factory to return rows as dictionaries
    cursor = conn.cursor()
    
    try:
        # Get all bills that need validation (status = 'SCRAPED')
        cursor.execute("""
            SELECT id FROM ProviderBill 
            WHERE status = 'SCRAPED'
        """)
        bills = cursor.fetchall()
        
        logger.info(f"Found {len(bills)} bills with status 'SCRAPED' to validate")
        
        for bill in bills:  # Changed from (bill_id,) to bill since we're using Row factory
            bill_id = bill['id']  # Access the id field using dictionary syntax
            logger.info(f"Validating bill {bill_id}")
            
            # Perform validation
            status, action, error = validate_provider_bill(bill_id, cursor)
            
            # Update the record
            cursor.execute("""
                UPDATE ProviderBill 
                SET status = ?,
                    action = ?,
                    last_error = ?
                WHERE id = ?
            """, (status, action, error, bill_id))
            
            logger.info(f"Updated bill {bill_id}: status={status}, action={action}")
            if error:
                logger.warning(f"Validation errors: {error}")
        
        conn.commit()
        logger.info("Validation complete")
        
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Database error: {str(e)}")
    finally:
        conn.close()

if __name__ == '__main__':
    process_validation()
