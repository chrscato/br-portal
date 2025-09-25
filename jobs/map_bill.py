#!/usr/bin/env python3
"""
map_bill.py

Maps validated ProviderBill records to claims.
Supports both operational and diagnostic CLI mode.
Integrated with Django project structure.
"""
import os
import sys
import logging
import sqlite3
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import re
from difflib import SequenceMatcher
from typing import Optional

# Get the project root directory (2 levels up from this file) for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Add Django project to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'clarity_dx_portal'))

# Load environment variables from the root .env file
load_dotenv(PROJECT_ROOT / '.env')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Utilities ───────────────────────────────────────────────────

def clean_name(name: str) -> str:
    if not name:
        return ""
    name = name.lower().replace(",", "").strip()
    name = re.sub(r'[^a-z\s-]', '', name)
    suffixes = ['jr', 'sr', 'ii', 'iii', 'iv', 'v', 'phd', 'md', 'do']
    for sfx in suffixes:
        name = re.sub(rf'\b{sfx}\b', '', name)
    name = re.sub(r'\s+', ' ', name)
    return name.strip()

def normalize_date(date_str: str) -> Optional[datetime.date]:
    if not date_str:
        return None
    date_str = str(date_str).strip()
    if ' - ' in date_str:
        date_str = date_str.split(' - ')[0].strip()
    if ' ' in date_str:
        date_str = date_str.split(' ')[0]
    formats = [
        '%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y',
        '%Y/%m/%d', '%m/%d/%y', '%m-%d-%y',
        '%Y%m%d', '%m%d%Y', '%m%d%y'
    ]
    for fmt in formats:
        try:
            d = datetime.strptime(date_str, fmt).date()
            if 2020 <= d.year <= 2035:
                return d
        except ValueError:
            continue
    return None

def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ─── Matching Logic ──────────────────────────────────────────────

def map_provider_bill_django(bill_id: str) -> tuple[str, str, str]:
    """
    Map a ProviderBill record to a claim using Django ORM.
    Returns (status, action, error_message)
    """
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill, BillLineItem, Order, OrderLineItem
    
    try:
        # Get the ProviderBill record
        bill = ProviderBill.objects.get(id=bill_id)
    except ProviderBill.DoesNotExist:
        return 'INVALID', 'to_validate', f"ProviderBill {bill_id} not found"
    
    if bill.status != 'VALID' or bill.action != 'to_map':
        return bill.status, bill.action, "Bill not ready for mapping"

    claim_id = find_matching_claim_django(bill)
    if claim_id:
        try:
            order = Order.objects.get(order_id=claim_id)
            
            if order.fully_paid == 'Y':
                order.bills_rec = (order.bills_rec or 0) + 1
                order.save()
                
                bill.claim_id = claim_id
                bill.status = 'DUPLICATE'
                bill.action = 'to_review'
                bill.last_error = 'Order already fully paid'
                bill.save()
                return 'DUPLICATE', 'to_review', 'Order already fully paid'

            bill.claim_id = claim_id
            bill.status = 'MAPPED'
            bill.action = 'to_review'
            bill.last_error = None
            bill.save()
            return 'MAPPED', 'to_review', None
        except Order.DoesNotExist:
            error = "Matching order not found"
            bill.status = 'UNMAPPED'
            bill.action = 'to_map'
            bill.last_error = error
            bill.save()
            return 'UNMAPPED', 'to_map', error
    else:
        error = "No matching claim found for patient and dates"
        bill.status = 'UNMAPPED'
        bill.action = 'to_map'
        bill.last_error = error
        bill.save()
        return 'UNMAPPED', 'to_map', error

def find_matching_claim_django(bill) -> str | None:
    """
    Find matching claim for a ProviderBill using Django ORM.
    """
    # Import Django models locally to avoid import issues
    from billing.models import BillLineItem, Order, OrderLineItem
    
    bill_patient_name = clean_name(bill.patient_name)
    logger.info(f"📌 Cleaned bill name: {bill_patient_name}")

    # Get bill dates
    bill_line_items = BillLineItem.objects.filter(provider_bill=bill)
    bill_dates = []
    for item in bill_line_items:
        normalized_date = normalize_date(item.date_of_service)
        if normalized_date:
            bill_dates.append(normalized_date)
    
    if not bill_dates:
        logger.warning("❌ No valid DOS found in BillLineItem")
        return None

    # Get orders with line items
    orders = Order.objects.filter(
        orderlineitem__dos__gte='2024-01-01',
        orderlineitem__dos__lte='2025-12-31'
    ).distinct()

    best_match = None
    best_score = 0.0
    top_matches = []

    for order in orders:
        # Try "first last" format first
        order_name = f"{clean_name(order.patient_first_name)} {clean_name(order.patient_last_name)}"
        sim = similar(bill_patient_name, order_name)
        
        # Get order dates
        order_line_items = OrderLineItem.objects.filter(order=order)
        for oli in order_line_items:
            order_date = normalize_date(oli.dos)
            if order_date:
                date_close = any(abs((order_date - bd).days) <= 21 for bd in bill_dates)
                
                # If no match with "first last", try "last first" format
                if sim < 0.80 and date_close:
                    order_name_flipped = f"{clean_name(order.patient_last_name)} {clean_name(order.patient_first_name)}"
                    sim = similar(bill_patient_name, order_name_flipped)

                if sim >= 0.80 and date_close:
                    top_matches.append((order.order_id, sim, order_date))
                    if sim > best_score:
                        best_score = sim
                        best_match = order.order_id

    if not best_match:
        logger.warning("⚠️ No matching claim found")
        return None

    # CPT check
    bill_cpts = set(item.cpt_code.strip() for item in bill_line_items if item.cpt_code)
    order_cpts = set(oli.cpt.strip() for oli in order_line_items if oli.cpt)

    overlap = bill_cpts & order_cpts
    logger.info(f"✅ CPT match overlap: {overlap} (count: {len(overlap)})")

    return best_match

def process_mapping():
    """Process all ProviderBill records that need mapping using Django ORM."""
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill
    from utils.job_logger import create_mapping_logger
    
    # Create job logger
    job_logger = create_mapping_logger()
    
    with job_logger.job_context():
        try:
            # Get all bills that need mapping (status = 'VALID' and action = 'to_map')
            bills = ProviderBill.objects.filter(status='VALID', action='to_map')
            total = len(bills)
            job_logger.log_info(f"Mapping {total} bills...")
            
            # Update total items for progress tracking
            job_logger.progress.total_items = total

            mapped = 0
            duplicate = 0
            unmapped = 0
            failed = 0

            for i, bill in enumerate(bills, 1):
                bill_id = bill.id
                job_logger.log_item_start(bill_id, f"Mapping bill {i}/{total}")
                
                try:
                    # Perform mapping
                    status, action, error = map_provider_bill_django(bill_id)
                    
                    if status == "MAPPED":
                        mapped += 1
                        job_logger.log_item_success(bill_id, f"Mapped successfully")
                    elif status == "DUPLICATE":
                        duplicate += 1
                        job_logger.log_item_success(bill_id, f"Identified as duplicate")
                    elif status == "UNMAPPED":
                        unmapped += 1
                        job_logger.log_item_success(bill_id, f"No matching order found")
                    else:
                        failed += 1
                        job_logger.log_item_error(bill_id, f"Unexpected status: {status}")
                        
                except Exception as e:
                    failed += 1
                    job_logger.log_item_error(bill_id, f"Exception during mapping: {str(e)}")

            job_logger.log_info(f"Mapping complete - MAPPED: {mapped}, DUPLICATE: {duplicate}, UNMAPPED: {unmapped}, FAILED: {failed}")
            job_logger.log_info(f"Total processed: {total}")

        except Exception as e:
            job_logger.log_error(f"Error in mapping process: {str(e)}", e)
            raise


def run_diagnostic(bill_id: str):
    """Run diagnostic mode for a specific bill using Django ORM."""
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill
    
    try:
        bill = ProviderBill.objects.get(id=bill_id)
        
        print(f"\n🩺 Running diagnostic for bill: {bill_id}")
        print(f"Original Name: {bill.patient_name}")
        print(f"Normalized: {clean_name(bill.patient_name)}\n")

        find_matching_claim_django(bill, is_diagnostic=True)
    except ProviderBill.DoesNotExist:
        print(f"❌ Bill {bill_id} not found.")
    except Exception as e:
        print(f"❌ Error running diagnostic: {e}")

def find_matching_claim_django(bill, is_diagnostic=False) -> str | None:
    """
    Find matching claim for a ProviderBill using Django ORM.
    """
    # Import Django models locally to avoid import issues
    from billing.models import BillLineItem, Order, OrderLineItem
    
    bill_patient_name = clean_name(bill.patient_name)
    logger.info(f"📌 Cleaned bill name: {bill_patient_name}")

    # Get bill dates
    bill_line_items = BillLineItem.objects.filter(provider_bill=bill)
    bill_dates = []
    for item in bill_line_items:
        normalized_date = normalize_date(item.date_of_service)
        if normalized_date:
            bill_dates.append(normalized_date)
    
    if not bill_dates:
        logger.warning("❌ No valid DOS found in BillLineItem")
        return None

    # Get orders with line items
    orders = Order.objects.filter(
        orderlineitem__dos__gte='2024-01-01',
        orderlineitem__dos__lte='2025-12-31'
    ).distinct()

    best_match = None
    best_score = 0.0
    top_matches = []

    for order in orders:
        # Try "first last" format first
        order_name = f"{clean_name(order.patient_first_name)} {clean_name(order.patient_last_name)}"
        sim = similar(bill_patient_name, order_name)
        
        # Get order dates
        order_line_items = OrderLineItem.objects.filter(order=order)
        for oli in order_line_items:
            order_date = normalize_date(oli.dos)
            if order_date:
                date_close = any(abs((order_date - bd).days) <= 21 for bd in bill_dates)
                
                # If no match with "first last", try "last first" format
                if sim < 0.80 and date_close:
                    order_name_flipped = f"{clean_name(order.patient_last_name)} {clean_name(order.patient_first_name)}"
                    sim = similar(bill_patient_name, order_name_flipped)

                if sim >= 0.80 and date_close:
                    top_matches.append((order.order_id, sim, order_date))
                    if sim > best_score:
                        best_score = sim
                        best_match = order.order_id

    if is_diagnostic:
        print(f"\n🔍 Top Matching Orders:")
        for match in sorted(top_matches, key=lambda x: x[1], reverse=True)[:10]:
            print(f"  → Order: {match[0]} | Similarity: {match[1]:.2f} | DOS: {match[2]}")
        print(f"\n🎯 Best Match: {best_match} (Score: {best_score:.2f})")
        if not best_match:
            print("⚠️ No claim found.\n")
        return None  # Don't map in diagnostic mode

    if not best_match:
        logger.warning("⚠️ No matching claim found")
        return None

    # CPT check
    bill_cpts = set(item.cpt_code.strip() for item in bill_line_items if item.cpt_code)
    order_cpts = set(oli.cpt.strip() for oli in order_line_items if oli.cpt)

    overlap = bill_cpts & order_cpts
    logger.info(f"✅ CPT match overlap: {overlap} (count: {len(overlap)})")

    return best_match

# ─── Entry Point ─────────────────────────────────────────────────

if __name__ == '__main__':
    import django
    
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
    django.setup()
    
    if len(sys.argv) == 3 and sys.argv[1] == "--diagnostic":
        run_diagnostic(sys.argv[2])
    else:
        process_mapping()
