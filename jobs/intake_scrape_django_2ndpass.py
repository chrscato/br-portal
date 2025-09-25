#!/usr/bin/env python3
"""
Django-compatible second pass HCFA-1500 extractor for INVALID bills

This script handles bills that failed initial processing (status = 'INVALID').
It reads the last_error message, analyzes the failure reason, and gives
the bill a second attempt with enhanced processing strategies.

Enhanced features for second pass:
• Error analysis and adaptive retry strategies
• Enhanced image processing for failed extractions
• Multiple extraction strategies based on error type
• Comprehensive logging of retry attempts
• Smart fallback mechanisms
• Django ORM integration for database operations

Required:
    pip install pymupdf pillow openai python-dotenv pytesseract numpy opencv-python
"""

import os, json, base64, tempfile, sys, time, logging, io
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import traceback
import warnings

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError

# OCR fallback disabled - using LLM vision directly
TESSERACT_AVAILABLE = False

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    warnings.warn("OpenCV not available. Advanced image processing disabled.")

# Django imports will be done after Django setup

# Setup Django if not already configured (for when imported from web interface)
def _ensure_django_setup():
    """Ensure Django is set up when imported from web interface."""
    try:
        from django.conf import settings
        if not settings.configured:
            raise Exception("Django not configured")
    except Exception:
        # Django not set up, configure it
        import django
        from django.conf import settings
        
        # Add the project root and Django project to Python path
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        django_project_path = os.path.join(project_root, 'clarity_dx_portal')
        
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        if django_project_path not in sys.path:
            sys.path.insert(0, django_project_path)
        
        # Setup Django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
        django.setup()

# Ensure Django is set up when this module is imported
_ensure_django_setup()

# Import S3 utilities (will be imported dynamically)
# from jobs.config.s3_utils import list_objects, download, upload, move

# Import validation utilities (will be imported dynamically)
# from jobs.utils.validate_intake import validate_provider_bill
# from jobs.utils.date_utils import standardize_and_validate_date_of_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load prompt configuration
PROMPT_FN = Path(__file__).parent / "utils" / "gpt4o_prompt_ultimate.json"

try:
    with open(PROMPT_FN, "r", encoding="utf-8") as f:
        _PROMPT_JSON = json.load(f)
    SYSTEM_PROMPT = _PROMPT_JSON["system"]
    USER_HINT = _PROMPT_JSON["user_hint"]
    FUNCTIONS = _PROMPT_JSON["functions"]
    EXTRACTION_STRATEGY = _PROMPT_JSON["extraction_strategy"]
    OCR_CORRECTIONS = _PROMPT_JSON["ocr_correction_rules"]
except Exception as e:
    logger.error(f"Failed to load prompt configuration: {e}")
    SYSTEM_PROMPT = "You are an expert medical billing AI specializing in extracting structured data from CMS-1500 (HCFA-1500) medical claim forms."
    USER_HINT = "Extract structured data from this medical claim form."
    FUNCTIONS = []
    EXTRACTION_STRATEGY = {}
    OCR_CORRECTIONS = {}

# S3 Configuration
S3_BUCKET = os.getenv("S3_BUCKET") or os.getenv("AWS_STORAGE_BUCKET_NAME", "bill-review-prod")
INPUT_PREFIX = "data/ProviderBills/pdf/"
OUTPUT_PREFIX = "data/ProviderBills/json/"
ARCHIVE_PREFIX = "data/ProviderBills/pdf/archive/"

# Model clients - will be initialized after Django setup
openai_client = None
OPENAI_MODEL = "gpt-4o"

def initialize_openai_client():
    """Initialize OpenAI client after Django setup and environment loading."""
    global openai_client
    try:
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info("OpenAI client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize OpenAI client: {e}")
        logger.info("Please check your OPENAI_API_KEY environment variable")
        openai_client = None


class FormQuality(Enum):
    """Form quality assessment levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"

class ExtractionStrategy(Enum):
    """Different extraction strategies."""
    STANDARD = "standard"
    HIGH_QUALITY = "high_quality"
    ENHANCED_CONTRAST = "enhanced_contrast"
    OCR_FALLBACK = "ocr_fallback"
    ZONE_BASED = "zone_based"
    ULTRA_ENHANCED = "ultra_enhanced"  # New strategy for second pass

class ErrorType(Enum):
    """Types of errors that can occur during extraction."""
    NO_SERVICE_LINES = "no_service_lines"
    INVALID_CPT = "invalid_cpt"
    MISSING_PATIENT_INFO = "missing_patient_info"
    MISSING_BILLING_INFO = "missing_billing_info"
    TOTAL_CHARGE_MISMATCH = "total_charge_mismatch"
    DATE_FORMAT_ERROR = "date_format_error"
    IMAGE_QUALITY = "image_quality"
    API_ERROR = "api_error"
    UNKNOWN = "unknown"

@dataclass
class ExtractionResult:
    """Enhanced extraction result with detailed metadata."""
    success: bool
    data: Optional[Dict] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    processing_time: float = 0.0
    validation_errors: List[str] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    strategy_used: Optional[ExtractionStrategy] = None
    form_quality: Optional[FormQuality] = None
    warnings: List[str] = field(default_factory=list)
    error_type: Optional[ErrorType] = None
    
    @property
    def overall_confidence(self) -> float:
        """Calculate overall confidence score."""
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores.values()) / len(self.confidence_scores)

@dataclass
class ProcessingStats:
    """Enhanced statistics tracking for second pass."""
    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    retried: int = 0
    validation_failures: int = 0
    ocr_fallbacks: int = 0
    high_confidence: int = 0
    low_confidence: int = 0
    start_time: Optional[datetime] = None
    strategy_usage: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_type_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    def __post_init__(self):
        self.start_time = datetime.now()
    
    def get_summary(self) -> str:
        duration = datetime.now() - self.start_time
        success_rate = (self.successful / self.total_processed * 100) if self.total_processed > 0 else 0
        
        return (f"Processed: {self.total_processed}, "
                f"Success: {self.successful} ({success_rate:.1f}%), "
                f"Failed: {self.failed}, "
                f"Retried: {self.retried}, "
                f"Validation Failures: {self.validation_failures}, "
                f"OCR Fallbacks: {self.ocr_fallbacks}, "
                f"High Confidence: {self.high_confidence}, "
                f"Low Confidence: {self.low_confidence}, "
                f"Duration: {duration}")

# HCFA-1500 Box Zones (relative coordinates)
HCFA_ZONES = {
    "patient_insurance": {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.25},  # Boxes 1-13
    "patient_condition": {"x": 0.0, "y": 0.25, "w": 0.5, "h": 0.15},  # Boxes 14-20
    "diagnosis": {"x": 0.0, "y": 0.35, "w": 0.5, "h": 0.1},  # Box 21
    "service_lines": {"x": 0.0, "y": 0.45, "w": 1.0, "h": 0.25},  # Box 24
    "billing_totals": {"x": 0.0, "y": 0.70, "w": 1.0, "h": 0.15},  # Boxes 25-30 (bottom section)
    "provider_info": {"x": 0.0, "y": 0.85, "w": 1.0, "h": 0.15}  # Boxes 31-33 (bottom section)
}

# Common CPT codes for validation
COMMON_CPT_CODES = {
    "73221", "73721", "72148", "72141", "73218", "73718", "72146", "70551", "95886", "70450",
    "95910", "72110", "73700", "72195", "72100", "A9576", "73222", "73130", "74176", "73564",
    "73200", "73030", "72131", "72125", "72070", "71250", "G9500", "93971", "73562", "73040",
    "72050", "23350", "95911", "95887", "77080", "76882", "76870", "76376", "73590", "73580",
    "73223", "73080", "72197", "72158", "72072", "72040", "70544", "27369", "Q9967", "E1399",
    "E0731", "A9901", "A9573", "A4595", "99215", "99213", "95912", "93880", "77003", "76856",
    "75561", "73723", "73722", "73610", "73600", "73560", "73552", "73521", "73502", "73202",
    "73110", "72192", "72156", "72052", "71552", "71550", "70150"
}

class ErrorAnalyzer:
    """Analyzes error messages to determine the best retry strategy."""
    
    @staticmethod
    def analyze_error(error_message: str) -> Tuple[ErrorType, ExtractionStrategy]:
        """Analyze error message and return error type and recommended strategy."""
        if not error_message:
            return ErrorType.UNKNOWN, ExtractionStrategy.ULTRA_ENHANCED
        
        error_lower = error_message.lower()
        
        # Check for specific error patterns
        if "no service lines" in error_lower or "service lines" in error_lower:
            return ErrorType.NO_SERVICE_LINES, ExtractionStrategy.ZONE_BASED
        elif "cpt" in error_lower or "invalid" in error_lower:
            return ErrorType.INVALID_CPT, ExtractionStrategy.ENHANCED_CONTRAST
        elif "patient" in error_lower and ("missing" in error_lower or "name" in error_lower):
            return ErrorType.MISSING_PATIENT_INFO, ExtractionStrategy.ZONE_BASED
        elif "billing" in error_lower and "missing" in error_lower:
            return ErrorType.MISSING_BILLING_INFO, ExtractionStrategy.ZONE_BASED
        elif "total charge" in error_lower or "mismatch" in error_lower:
            return ErrorType.TOTAL_CHARGE_MISMATCH, ExtractionStrategy.ULTRA_ENHANCED
        elif "date" in error_lower:
            return ErrorType.DATE_FORMAT_ERROR, ExtractionStrategy.ENHANCED_CONTRAST
        elif "image" in error_lower or "quality" in error_lower:
            return ErrorType.IMAGE_QUALITY, ExtractionStrategy.ULTRA_ENHANCED
        elif "api" in error_lower or "rate limit" in error_lower:
            return ErrorType.API_ERROR, ExtractionStrategy.STANDARD
        else:
            return ErrorType.UNKNOWN, ExtractionStrategy.ULTRA_ENHANCED

class ImageProcessor:
    """Advanced image processing for HCFA forms with enhanced second-pass capabilities."""
    
    @staticmethod
    def assess_quality(image: Image.Image) -> FormQuality:
        """Assess the quality of the form image."""
        # Convert to grayscale for analysis
        gray = image.convert('L')
        pixels = np.array(gray)
        
        # Calculate metrics
        contrast = pixels.std()
        brightness = pixels.mean()
        
        # Check for skew (requires OpenCV)
        if OPENCV_AVAILABLE:
            skew = ImageProcessor._detect_skew(pixels)
        else:
            skew = 0
        
        # Assess quality based on metrics
        if contrast > 50 and 100 < brightness < 200 and abs(skew) < 2:
            return FormQuality.EXCELLENT
        elif contrast > 30 and 80 < brightness < 220 and abs(skew) < 5:
            return FormQuality.GOOD
        elif contrast > 20 and 60 < brightness < 240 and abs(skew) < 10:
            return FormQuality.FAIR
        else:
            return FormQuality.POOR
    
    @staticmethod
    def _detect_skew(image_array: np.ndarray) -> float:
        """Detect skew angle in degrees."""
        if not OPENCV_AVAILABLE:
            return 0.0
        
        try:
            # Edge detection
            edges = cv2.Canny(image_array, 50, 150, apertureSize=3)
            
            # Hough transform to find lines
            lines = cv2.HoughLines(edges, 1, np.pi/180, 200)
            
            if lines is not None:
                angles = []
                for rho, theta in lines[:, 0]:
                    angle = np.degrees(theta) - 90
                    if -45 < angle < 45:
                        angles.append(angle)
                
                if angles:
                    return np.median(angles)
        except:
            pass
        
        return 0.0
    
    @staticmethod
    def enhance_image(image: Image.Image, strategy: ExtractionStrategy) -> Image.Image:
        """Enhance image based on extraction strategy."""
        if strategy == ExtractionStrategy.ENHANCED_CONTRAST:
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(1.5)
            
            # Sharpen
            image = image.filter(ImageFilter.SHARPEN)
            
        elif strategy == ExtractionStrategy.HIGH_QUALITY:
            # Minimal processing for good quality images
            pass
            
        elif strategy == ExtractionStrategy.ZONE_BASED:
            # Enhance for zone extraction
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.1)
        
        elif strategy == ExtractionStrategy.ULTRA_ENHANCED:
            # Maximum enhancement for difficult cases
            # Enhance contrast
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)
            
            # Enhance brightness
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.2)
            
            # Sharpen
            image = image.filter(ImageFilter.SHARPEN)
            
            # Additional sharpening
            image = image.filter(ImageFilter.EDGE_ENHANCE)
        
        return image
    
    @staticmethod
    def deskew_image(image: Image.Image) -> Image.Image:
        """Deskew the image if needed."""
        if not OPENCV_AVAILABLE:
            return image
        
        try:
            # Convert to numpy array
            img_array = np.array(image.convert('L'))
            
            # Detect skew
            skew = ImageProcessor._detect_skew(img_array)
            
            if abs(skew) > 2:
                # Rotate to correct skew
                (h, w) = img_array.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, skew, 1.0)
                rotated = cv2.warpAffine(img_array, M, (w, h), 
                                        flags=cv2.INTER_CUBIC,
                                        borderMode=cv2.BORDER_REPLICATE)
                
                # Convert back to PIL Image
                return Image.fromarray(rotated)
        except Exception as e:
            logger.warning(f"Deskew failed: {e}")
        
        return image
    
    @staticmethod
    def extract_zone(image: Image.Image, zone: Dict[str, float]) -> Image.Image:
        """Extract a specific zone from the image."""
        width, height = image.size
        
        # Calculate actual coordinates
        x = int(zone["x"] * width)
        y = int(zone["y"] * height)
        w = int(zone["w"] * width)
        h = int(zone["h"] * height)
        
        # Crop the zone
        return image.crop((x, y, x + w, y + h))

def get_invalid_bills_from_db(limit: int = None) -> List[Dict[str, Any]]:
    """Query database for bills with status 'INVALID'."""
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill
    
    logger.info(f"Querying database for INVALID bills")
    
    try:
        bills = ProviderBill.objects.filter(status='INVALID')  # Only process INVALID, not INVALID_2
        if limit:
            bills = bills[:limit]
        
        bill_list = []
        for bill in bills:
            bill_list.append({
                'id': bill.id,
                'source_file': bill.source_file,
                'last_error': bill.last_error
            })
        
        logger.info(f"Found {len(bill_list)} bills with status 'INVALID'")
        return bill_list
        
    except Exception as e:
        logger.error(f"Database error querying INVALID bills: {e}")
        return []

def get_existing_bill_data(bill_id: str) -> Dict[str, Any]:
    """Get existing data for a bill to avoid duplicates."""
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill, BillLineItem
    
    try:
        # Get existing ProviderBill data
        try:
            bill = ProviderBill.objects.get(id=bill_id)
            bill_data = {
                'id': bill.id,
                'patient_name': bill.patient_name,
                'total_charge': bill.total_charge,
                'billing_provider_name': bill.billing_provider_name,
                'billing_provider_npi': bill.billing_provider_npi,
                'source_file': bill.source_file,
                'last_error': bill.last_error,
                'status': bill.status
            }
        except ProviderBill.DoesNotExist:
            bill_data = None
        
        # Get existing BillLineItem data
        line_items = BillLineItem.objects.filter(provider_bill_id=bill_id)
        line_items_data = []
        for item in line_items:
            line_items_data.append({
                'id': item.id,
                'cpt_code': item.cpt_code,
                'modifier': item.modifier,
                'units': item.units,
                'charge_amount': item.charge_amount,
                'date_of_service': item.date_of_service,
                'place_of_service': item.place_of_service,
                'diagnosis_pointer': item.diagnosis_pointer
            })
        
        existing_data = {
            'bill': bill_data,
            'line_items': line_items_data
        }
        
        logger.info(f"Retrieved existing data for bill {bill_id}: {len(existing_data['line_items'])} line items")
        return existing_data
        
    except Exception as e:
        logger.error(f"Database error retrieving existing data for bill {bill_id}: {e}")
        return {'bill': None, 'line_items': []}

def compare_bill_data(existing_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    """Compare existing and new data to determine what needs updating."""
    comparison = {
        'bill_needs_update': False,
        'line_items_to_add': [],
        'line_items_to_update': [],
        'line_items_to_remove': [],
        'changes': []
    }
    
    # Compare bill-level data
    if existing_data['bill']:
        existing_bill = existing_data['bill']
        patient_info = new_data.get('patient_info', {})
        billing_info = new_data.get('billing_info', {})
        
        # Check if key fields have changed
        key_fields = [
            ('patient_name', patient_info.get('patient_name')),
            ('total_charge', billing_info.get('total_charge')),
            ('billing_provider_name', billing_info.get('billing_provider_name')),
            ('billing_provider_npi', billing_info.get('billing_provider_npi'))
        ]
        
        for field, new_value in key_fields:
            existing_value = existing_bill.get(field)
            if existing_value != new_value:
                comparison['bill_needs_update'] = True
                comparison['changes'].append(f"{field}: '{existing_value}' -> '{new_value}'")
    
    # Compare line items
    existing_items = existing_data['line_items']
    new_items = new_data.get('service_lines', [])
    
    # Create lookup for existing items by CPT code and date
    existing_lookup = {}
    for item in existing_items:
        key = f"{item.get('cpt_code', '')}_{item.get('date_of_service', '')}_{item.get('charge_amount', '')}"
        existing_lookup[key] = item
    
    # Check new items against existing
    for new_item in new_items:
        key = f"{new_item.get('cpt_code', '')}_{new_item.get('date_of_service', '')}_{new_item.get('charge_amount', '')}"
        
        if key in existing_lookup:
            # Item exists, check if it needs updating
            existing_item = existing_lookup[key]
            if (existing_item.get('modifier', '') != ','.join(new_item.get('modifiers', [])) or
                existing_item.get('units', 1) != new_item.get('units', 1)):
                comparison['line_items_to_update'].append({
                    'existing': existing_item,
                    'new': new_item
                })
        else:
            # New item to add
            comparison['line_items_to_add'].append(new_item)
    
    # Find items to remove (existing items not in new data)
    new_keys = set()
    for new_item in new_items:
        key = f"{new_item.get('cpt_code', '')}_{new_item.get('date_of_service', '')}_{new_item.get('charge_amount', '')}"
        new_keys.add(key)
    
    for existing_item in existing_items:
        key = f"{existing_item.get('cpt_code', '')}_{existing_item.get('date_of_service', '')}_{existing_item.get('charge_amount', '')}"
        if key not in new_keys:
            comparison['line_items_to_remove'].append(existing_item)
    
    logger.info(f"Data comparison: {len(comparison['line_items_to_add'])} to add, "
                f"{len(comparison['line_items_to_update'])} to update, "
                f"{len(comparison['line_items_to_remove'])} to remove")
    
    return comparison

def validate_provider_bill_django(bill_id: str) -> tuple[str, str, str]:
    """
    Validate a ProviderBill record and its line items using Django ORM.
    Returns (status, action, error_message)
    """
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill, BillLineItem
    
    try:
        # Get the ProviderBill record
        bill = ProviderBill.objects.get(id=bill_id)
    except ProviderBill.DoesNotExist:
        return 'INVALID', 'to_validate', f"ProviderBill {bill_id} not found"
    
    # Get all line items for this bill
    line_items = BillLineItem.objects.filter(provider_bill=bill)
    
    if not line_items.exists():
        return 'INVALID', 'add_line_items', f"No line items found for ProviderBill {bill_id}"
    
    # Validation checks
    errors = []
    
    # 1. Check required fields (only patient_name and total_charge are required)
    if not bill.patient_name:
        errors.append("Missing Patient name")
    if not bill.total_charge:
        errors.append("Missing Total charge")
    
    # 2. Validate line items
    for item in line_items:
        # Check CPT code format
        if not item.cpt_code or len(item.cpt_code) != 5:
            errors.append(f"Invalid CPT code format: {item.cpt_code}")
        
        # Check charge amount
        if not item.charge_amount or item.charge_amount <= 0:
            errors.append(f"Invalid charge amount: {item.charge_amount}")
        
            # Check date of service
            try:
                date_str = item.date_of_service
                if date_str:
                    try:
                        from jobs.utils.date_utils import standardize_and_validate_date_of_service
                    except ImportError:
                        from utils.date_utils import standardize_and_validate_date_of_service
                    is_valid, standardized_date, error_msg = standardize_and_validate_date_of_service(date_str)
                    
                    if not is_valid:
                        errors.append(f"Date of service error: {error_msg}")
                    else:
                        # Log if we standardized the format
                        if date_str != standardized_date:
                            logger.info(f"Standardized date for line item {item.id}: '{date_str}' -> '{standardized_date}'")
                        
            except Exception as e:
                errors.append(f"Error processing date: {date_str} - {str(e)}")
    
    # 3. Check total charge matches sum of line items
    total_line_charges = sum(item.charge_amount for item in line_items if item.charge_amount)
    if bill.total_charge and total_line_charges:
        if abs(total_line_charges - bill.total_charge) > 10.00:  # Allow for small rounding differences
            errors.append(f"Total charge mismatch: {bill.total_charge} vs {total_line_charges}")
    elif bill.total_charge and not total_line_charges:
        errors.append(f"Total charge exists but no line item charges found")
    elif not bill.total_charge and total_line_charges:
        errors.append(f"Line item charges exist but no total charge found")
    
    # Determine status and action based on validation results
    if errors:
        error_message = "; ".join(errors)
        # For second pass, use INVALID_2 to distinguish from initial processing failures
        return 'INVALID_2', 'to_validate', error_message
    
    # If all validations pass
    return 'VALID', 'to_map', None

def update_provider_bill_record_2nd_pass(provider_bill_id: str, extracted_data: dict, success: bool = True) -> bool:
    """Update ProviderBill record after second pass processing with duplicate prevention."""
    # Import Django models locally to avoid import issues
    from django.utils import timezone
    from django.db import transaction
    from billing.models import ProviderBill, BillLineItem
    
    logger.info(f"Updating database for second pass bill: {provider_bill_id}")
    
    try:
        with transaction.atomic():
            # Get the ProviderBill record
            try:
                bill = ProviderBill.objects.get(id=provider_bill_id)
            except ProviderBill.DoesNotExist:
                logger.error(f"Record {provider_bill_id} not found in ProviderBill table")
                return False
            
            if success:
                # Get existing data to compare
                existing_data = get_existing_bill_data(provider_bill_id)
                comparison = compare_bill_data(existing_data, extracted_data)
                
                # Only update if there are actual changes
                if not comparison['bill_needs_update'] and not comparison['line_items_to_add'] and not comparison['line_items_to_update'] and not comparison['line_items_to_remove']:
                    logger.info(f"No changes detected for bill {provider_bill_id}, skipping update")
                    # Still update status to SCRAPED if it's currently INVALID
                    if bill.status == 'INVALID':
                        bill.status = 'SCRAPED'
                        bill.save()
                    return True
                
                # Log changes
                if comparison['changes']:
                    logger.info(f"Changes detected for bill {provider_bill_id}: {', '.join(comparison['changes'])}")
                
                # Extract patient and billing info
                patient_info = extracted_data.get('patient_info', {})
                billing_info = extracted_data.get('billing_info', {})
                
                # Convert total charge from string to float if present
                total_charge = None
                if 'total_charge' in billing_info and billing_info['total_charge']:
                    try:
                        total_charge = float(billing_info['total_charge'].replace('$', '').replace(',', ''))
                    except (ValueError, AttributeError):
                        logger.warning(f"Could not convert total_charge: {billing_info.get('total_charge')}")
                
                # Update ProviderBill record
                bill.status = 'SCRAPED'
                bill.last_error = None
                bill.patient_name = patient_info.get('patient_name')
                bill.patient_dob = patient_info.get('patient_dob')
                bill.patient_zip = patient_info.get('patient_zip')
                bill.billing_provider_name = billing_info.get('billing_provider_name')
                bill.billing_provider_address = billing_info.get('billing_provider_address')
                bill.billing_provider_tin = billing_info.get('billing_provider_tin')
                bill.billing_provider_npi = billing_info.get('billing_provider_npi')
                bill.total_charge = total_charge
                bill.patient_account_no = billing_info.get('patient_account_no')
                bill.action = None
                bill.bill_paid = 'N'
                bill.updated_at = timezone.now()
                bill.save()
                
                # Handle line items based on comparison
                # Remove items that are no longer in the new data
                for item_to_remove in comparison['line_items_to_remove']:
                    try:
                        BillLineItem.objects.get(id=item_to_remove['id']).delete()
                        logger.info(f"Removed line item {item_to_remove['id']} for bill {provider_bill_id}")
                    except BillLineItem.DoesNotExist:
                        logger.warning(f"Line item {item_to_remove['id']} not found for removal")
                
                # Update existing items that have changed
                for update_item in comparison['line_items_to_update']:
                    existing_item = update_item['existing']
                    new_item = update_item['new']
                    
                    try:
                        line_item = BillLineItem.objects.get(id=existing_item['id'])
                        
                        # Convert charge amount
                        charge_amount = None
                        if new_item.get('charge_amount'):
                            try:
                                charge_amount = float(new_item['charge_amount'].replace('$', '').replace(',', ''))
                            except (ValueError, AttributeError):
                                logger.warning(f"Could not convert charge_amount: {new_item.get('charge_amount')}")
                                continue
                        
                        # Join modifiers
                        modifiers = ','.join(new_item.get('modifiers', [])) if new_item.get('modifiers') else ''
                        
                        # Update line item
                        line_item.cpt_code = new_item.get('cpt_code')
                        line_item.modifier = modifiers
                        line_item.units = new_item.get('units', 1)
                        line_item.charge_amount = charge_amount
                        line_item.date_of_service = new_item.get('date_of_service')
                        line_item.place_of_service = new_item.get('place_of_service')
                        line_item.diagnosis_pointer = new_item.get('diagnosis_pointer')
                        line_item.save()
                        
                        logger.info(f"Updated line item {existing_item['id']} for bill {provider_bill_id}")
                    except BillLineItem.DoesNotExist:
                        logger.warning(f"Line item {existing_item['id']} not found for update")
                
                # Add new items
                for new_item in comparison['line_items_to_add']:
                    try:
                        # Convert charge amount from string to float
                        charge_amount = None
                        if new_item.get('charge_amount'):
                            try:
                                charge_amount = float(new_item['charge_amount'].replace('$', '').replace(',', ''))
                            except (ValueError, AttributeError):
                                logger.warning(f"Could not convert charge_amount: {new_item.get('charge_amount')}")
                                continue
                        
                        # Join modifiers with comma if multiple
                        modifiers = ','.join(new_item.get('modifiers', [])) if new_item.get('modifiers') else ''
                        
                        # Create new line item
                        BillLineItem.objects.create(
                            provider_bill=bill,
                            cpt_code=new_item.get('cpt_code'),
                            modifier=modifiers,
                            units=new_item.get('units', 1),
                            charge_amount=charge_amount,
                            allowed_amount=None,
                            decision='pending',
                            reason_code='',
                            date_of_service=new_item.get('date_of_service'),
                            place_of_service=new_item.get('place_of_service'),
                            diagnosis_pointer=new_item.get('diagnosis_pointer')
                        )
                        logger.info(f"Added new line item for bill {provider_bill_id}")
                    except Exception as e:
                        logger.error(f"Error inserting new service line for bill {provider_bill_id}: {e}")
                        continue
            else:
                # Update with failure status
                bill.status = 'INVALID_2'
                bill.last_error = 'Second pass processing failed'
                bill.save()
            
            logger.info(f"Successfully updated database for second pass bill {provider_bill_id}")
            
            # Validate the bill after updating
            logger.info(f"Validating bill {provider_bill_id} after second pass extraction")
            status, action, error_message = validate_provider_bill_django(provider_bill_id)
            
            # Update the bill with validation results
            bill.status = status
            bill.action = action
            bill.last_error = error_message
            bill.updated_at = timezone.now()
            bill.save()
            
            logger.info(f"Validation complete for bill {provider_bill_id}: status={status}, action={action}")
            if error_message:
                logger.warning(f"Validation errors: {error_message}")
            
            return True
            
    except Exception as e:
        logger.error(f"Error updating ProviderBill {provider_bill_id}: {str(e)}")
        return False

def extract_with_llm_2nd_pass(image: Image.Image, strategy: ExtractionStrategy = ExtractionStrategy.STANDARD, 
                             error_context: str = None) -> ExtractionResult:
    """Extract data from HCFA form using LLM vision with second pass enhancements."""
    if not openai_client:
        return ExtractionResult(
            success=False,
            error_message="OpenAI client not initialized. Check OPENAI_API_KEY.",
            error_type=ErrorType.API_ERROR
        )
    
    start_time = time.time()
    temp_file = None
    
    try:
        # Convert image to base64
        buffer = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp_file = buffer.name
        image.save(temp_file, 'PNG')
        buffer.close()
        
        with open(temp_file, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')
        
        os.unlink(temp_file)
        temp_file = None  # Mark as cleaned up
        
        # Prepare enhanced user hint for second pass
        enhanced_hint = USER_HINT
        if error_context:
            enhanced_hint += f"\n\nPrevious extraction failed with: {error_context}. Please pay extra attention to these areas and ensure all required fields are extracted accurately."
        
        # Prepare messages
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user", 
                "content": [
                    {
                        "type": "text",
                        "text": enhanced_hint
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}"
                        }
                    }
                ]
            }
        ]
        
        # Make API call with enhanced parameters for second pass
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            functions=FUNCTIONS,
            function_call={"name": "extract_hcfa1500"},
            temperature=0.1,  # Slightly higher temperature for second pass
            max_tokens=4000
        )
        
        # Parse response
        function_call = response.choices[0].message.function_call
        if function_call and function_call.name == "extract_hcfa1500":
            extracted_data = json.loads(function_call.arguments)
            
            # Enhanced validation for second pass
            validation_errors = []
            if not extracted_data.get('service_lines'):
                validation_errors.append("No service lines found")
                error_type = ErrorType.NO_SERVICE_LINES
            else:
                error_type = None
            
            # Check for common CPT codes
            confidence_scores = {}
            for line in extracted_data.get('service_lines', []):
                cpt_code = line.get('cpt_code')
                if cpt_code and cpt_code in COMMON_CPT_CODES:
                    confidence_scores[cpt_code] = 0.9
                elif cpt_code:
                    confidence_scores[cpt_code] = 0.6
            
            processing_time = time.time() - start_time
            
            return ExtractionResult(
                success=True,
                data=extracted_data,
                processing_time=processing_time,
                validation_errors=validation_errors,
                confidence_scores=confidence_scores,
                strategy_used=strategy,
                form_quality=ImageProcessor.assess_quality(image),
                error_type=error_type
            )
        else:
            return ExtractionResult(
                success=False,
                error_message="No function call in response",
                processing_time=time.time() - start_time,
                error_type=ErrorType.API_ERROR
            )
            
    except RateLimitError as e:
        return ExtractionResult(
            success=False,
            error_message=f"Rate limit exceeded: {e}",
            processing_time=time.time() - start_time,
            error_type=ErrorType.API_ERROR
        )
    except APIError as e:
        return ExtractionResult(
            success=False,
            error_message=f"API error: {e}",
            processing_time=time.time() - start_time,
            error_type=ErrorType.API_ERROR
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error_message=f"Unexpected error: {e}",
            processing_time=time.time() - start_time,
            error_type=ErrorType.UNKNOWN
        )
    finally:
        # Clean up temporary file if it still exists
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"Error deleting temporary file {temp_file}: {e}")

def process_single_bill_2nd_pass(bill_id: str, pdf_key: str, error_message: str) -> bool:
    """Process a single bill from S3 with second pass enhancements."""
    logger.info(f"Processing second pass for bill {bill_id}")
    logger.info(f"Previous error: {error_message}")
    
    try:
        # Analyze the error to determine strategy
        error_type, recommended_strategy = ErrorAnalyzer.analyze_error(error_message)
        logger.info(f"Error type: {error_type}, Recommended strategy: {recommended_strategy}")
        
        # Import S3 utilities dynamically
        try:
            from jobs.config.s3_utils import download
        except ImportError:
            from config.s3_utils import download
        
        # Download PDF
        tmp_pdf = tempfile.mktemp(suffix='.pdf')
        try:
            download(pdf_key, tmp_pdf)
        except Exception as e:
            logger.error(f"Failed to download PDF from S3: {pdf_key} - {e}")
            # Update database with failure
            update_provider_bill_record_2nd_pass(bill_id, {}, success=False)
            return False
        
        # Convert PDF to image
        doc = fitz.open(tmp_pdf)
        page = doc[0]  # First page
        mat = fitz.Matrix(2.5, 2.5)  # Higher zoom for second pass
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        # Create PIL Image
        image = Image.open(io.BytesIO(img_data))
        
        # Assess quality and choose strategy
        quality = ImageProcessor.assess_quality(image)
        logger.info(f"Image quality: {quality}")
        
        # Use recommended strategy or fallback based on quality
        if recommended_strategy == ExtractionStrategy.ULTRA_ENHANCED or quality == FormQuality.POOR:
            strategy = ExtractionStrategy.ULTRA_ENHANCED
        elif recommended_strategy == ExtractionStrategy.ZONE_BASED:
            strategy = ExtractionStrategy.ZONE_BASED
        else:
            strategy = recommended_strategy
        
        # Enhance image based on strategy
        image = ImageProcessor.enhance_image(image, strategy)
        
        # Deskew if needed
        image = ImageProcessor.deskew_image(image)
        
        # Extract data with error context
        result = extract_with_llm_2nd_pass(image, strategy, error_message)
        
        if result.success and result.data:
            # Update database
            if update_provider_bill_record_2nd_pass(bill_id, result.data, success=True):
                # Save JSON to S3
                try:
                    from jobs.config.s3_utils import upload
                except ImportError:
                    from config.s3_utils import upload
                tmp_json = tempfile.mktemp(suffix='.json')
                with open(tmp_json, 'w', encoding='utf-8') as f:
                    json.dump(result.data, f, indent=2)
                upload(tmp_json, f"{OUTPUT_PREFIX}{bill_id}_2nd_pass.json")
                os.unlink(tmp_json)
                
                logger.info(f"Successfully processed second pass for {bill_id}")
                return True
            else:
                logger.error(f"Database update failed for second pass {bill_id}")
                return False
        else:
            logger.error(f"Second pass extraction failed for {bill_id}: {result.error_message}")
            # Update database with failure
            update_provider_bill_record_2nd_pass(bill_id, {}, success=False)
            return False
            
    except Exception as e:
        logger.error(f"Error in second pass processing {bill_id}: {e}")
        # Update database with failure
        update_provider_bill_record_2nd_pass(bill_id, {}, success=False)
        return False
    finally:
        if 'tmp_pdf' in locals() and os.path.exists(tmp_pdf):
            try:
                os.unlink(tmp_pdf)
            except OSError:
                # File might be locked, ignore cleanup error
                pass

def process_invalid_bills(limit: int = None):
    """Process bills from database with status 'INVALID' for second pass."""
    # Import enhanced logging
    try:
        from utils.job_logger import create_second_pass_logger
    except ImportError:
        from jobs.utils.job_logger import create_second_pass_logger
    
    # Create job logger
    job_logger = create_second_pass_logger()
    
    with job_logger.job_context(metadata={'limit': limit}):
        try:
            # Get bills from database
            bills = get_invalid_bills_from_db(limit)
            
            if not bills:
                job_logger.log_info("No bills with status 'INVALID' found")
                return
            
            job_logger.log_info(f"Found {len(bills)} bills for second pass processing")
            
            # Update total items for progress tracking
            job_logger.progress.total_items = len(bills)
            
            successful = 0
            failed = 0
            
            for i, bill in enumerate(bills, 1):
                bill_id = bill['id']
                source_file = bill['source_file']
                last_error = bill['last_error']
                
                job_logger.log_item_start(bill_id, f"Second pass processing {i}/{len(bills)}")
                job_logger.log_info(f"Previous error: {last_error}")
                
                # Construct the S3 key using bill_id in the archive folder
                # PDFs are stored as: data/ProviderBills/pdf/archive/{bill_id}.pdf
                pdf_key = f"{ARCHIVE_PREFIX}{bill_id}.pdf"
                
                try:
                    if process_single_bill_2nd_pass(bill_id, pdf_key, last_error):
                        successful += 1
                        job_logger.log_item_success(bill_id, "Second pass processing successful")
                    else:
                        failed += 1
                        job_logger.log_item_error(bill_id, "Second pass processing failed", "process_single_bill_2nd_pass returned False")
                except Exception as e:
                    failed += 1
                    job_logger.log_item_error(bill_id, f"Exception during second pass: {str(e)}")
            
            job_logger.log_info(f"Second pass processing complete: {successful} successful, {failed} failed")
            
        except Exception as e:
            job_logger.log_error(f"Error in second pass processing: {e}", e)
            raise

if __name__ == "__main__":
    import sys
    import django
    
    # Add the project root and Django project to Python path
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    django_project_path = os.path.join(project_root, 'clarity_dx_portal')
    
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    if django_project_path not in sys.path:
        sys.path.insert(0, django_project_path)
    
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
    django.setup()
    
    # Initialize OpenAI client after Django setup
    initialize_openai_client()
    
    # Check for limit argument
    limit = None
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
            logger.info(f"Processing with limit: {limit}")
        except ValueError:
            logger.warning(f"Invalid limit argument: {sys.argv[1]}. Processing all bills.")
    
    process_invalid_bills(limit)
