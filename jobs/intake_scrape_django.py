#!/usr/bin/env python3
"""
Django-compatible intake scrape processor for HCFA-1500 forms
Processes bills with 'SCANNED' status and outputs 'SCRAPED' status
"""

import os
import sys
import json
import base64
import tempfile
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import warnings

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError

# Django imports will be done after Django setup

# Import S3 utilities
from config.s3_utils import list_objects, download, upload, move

# Import validation utilities
from utils.validate_intake import validate_provider_bill
from utils.date_utils import standardize_and_validate_date_of_service

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

# Initialize OpenAI client
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    openai_client = None
    OPENAI_MODEL = "gpt-4o"

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
    
    @property
    def overall_confidence(self) -> float:
        """Calculate overall confidence score."""
        if not self.confidence_scores:
            return 0.0
        return sum(self.confidence_scores.values()) / len(self.confidence_scores)

class ImageProcessor:
    """Advanced image processing for HCFA forms."""
    
    @staticmethod
    def assess_quality(image: Image.Image) -> FormQuality:
        """Assess the quality of the form image."""
        # Convert to grayscale for analysis
        gray = image.convert('L')
        pixels = np.array(gray)
        
        # Calculate metrics
        contrast = pixels.std()
        brightness = pixels.mean()
        
        # Assess quality based on metrics
        if contrast > 50 and 100 < brightness < 200:
            return FormQuality.EXCELLENT
        elif contrast > 30 and 80 < brightness < 220:
            return FormQuality.GOOD
        elif contrast > 20 and 60 < brightness < 240:
            return FormQuality.FAIR
        else:
            return FormQuality.POOR
    
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
        
        return image

def extract_with_llm(image: Image.Image, strategy: ExtractionStrategy = ExtractionStrategy.STANDARD) -> ExtractionResult:
    """Extract data from HCFA form using LLM vision."""
    if not openai_client:
        return ExtractionResult(
            success=False,
            error_message="OpenAI client not initialized. Check OPENAI_API_KEY."
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
                        "text": USER_HINT
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
        
        # Make API call
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            functions=FUNCTIONS,
            function_call={"name": "extract_hcfa1500"},
            temperature=0.0,
            max_tokens=4000
        )
        
        # Parse response
        function_call = response.choices[0].message.function_call
        if function_call and function_call.name == "extract_hcfa1500":
            extracted_data = json.loads(function_call.arguments)
            
            # Validate extracted data
            validation_errors = []
            if not extracted_data.get('service_lines'):
                validation_errors.append("No service lines found")
            
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
                form_quality=ImageProcessor.assess_quality(image)
            )
        else:
            return ExtractionResult(
                success=False,
                error_message="No function call in response",
                processing_time=time.time() - start_time
            )
            
    except RateLimitError as e:
        return ExtractionResult(
            success=False,
            error_message=f"Rate limit exceeded: {e}",
            processing_time=time.time() - start_time
        )
    except APIError as e:
        return ExtractionResult(
            success=False,
            error_message=f"API error: {e}",
            processing_time=time.time() - start_time
        )
    except Exception as e:
        return ExtractionResult(
            success=False,
            error_message=f"Unexpected error: {e}",
            processing_time=time.time() - start_time
        )
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception as e:
                logger.warning(f"Error deleting temporary file {temp_file}: {e}")

def update_provider_bill_record(provider_bill_id: str, extracted_data: dict) -> bool:
    """Update ProviderBill record and create BillLineItem entries using Django ORM."""
    # Import Django models locally to avoid import issues
    from django.utils import timezone
    from django.db import transaction
    from billing.models import ProviderBill, BillLineItem
    
    logger.info(f"Updating database for bill {provider_bill_id}")
    
    try:
        with transaction.atomic():
            # Get the ProviderBill record
            try:
                bill = ProviderBill.objects.get(id=provider_bill_id)
            except ProviderBill.DoesNotExist:
                logger.error(f"Record {provider_bill_id} not found in ProviderBill table")
                return False
            
            # Extract patient and billing info
            patient_info = extracted_data.get('patient_info', {})
            billing_info = extracted_data.get('billing_info', {})
            
            # Convert total charge from string to float if present
            total_charge = None
            if 'total_charge' in billing_info and billing_info['total_charge']:
                try:
                    charge_str = str(billing_info['total_charge'])
                    total_charge = float(charge_str.replace('$', '').replace(',', ''))
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
            
            # Clear existing line items
            BillLineItem.objects.filter(provider_bill=bill).delete()
            
            # Create BillLineItem entries for each service line
            for line in extracted_data.get('service_lines', []):
                try:
                    # Convert charge amount from string to float
                    charge_amount = None
                    if line.get('charge_amount'):
                        try:
                            charge_str = str(line['charge_amount'])
                            charge_amount = float(charge_str.replace('$', '').replace(',', ''))
                        except (ValueError, AttributeError):
                            logger.warning(f"Could not convert charge_amount: {line.get('charge_amount')}")
                            continue
                    
                    # Join modifiers with comma if multiple
                    modifiers_list = line.get('modifiers', [])
                    modifiers = ','.join(modifiers_list) if modifiers_list else ''
                    
                    # Create line item
                    BillLineItem.objects.create(
                        provider_bill=bill,
                        cpt_code=line.get('cpt_code'),
                        modifier=modifiers,
                        units=line.get('units', 1),
                        charge_amount=charge_amount,
                        allowed_amount=None,
                        decision='pending',
                        reason_code='',
                        date_of_service=line.get('date_of_service'),
                        place_of_service=line.get('place_of_service'),
                        diagnosis_pointer=line.get('diagnosis_pointer')
                    )
                except Exception as e:
                    logger.error(f"Error creating service line for bill {provider_bill_id}: {e}")
                    continue
            
            logger.info(f"Successfully updated database for bill {provider_bill_id}")
            return True
            
    except Exception as e:
        logger.error(f"Error updating ProviderBill {provider_bill_id}: {str(e)}")
        return False

def process_single_bill(bill_id: str, pdf_key: str) -> bool:
    """Process a single bill from S3."""
    logger.info(f"Processing bill {bill_id}")
    
    tmp_pdf = None
    doc = None
    
    try:
        # Download PDF
        tmp_pdf = tempfile.mktemp(suffix='.pdf')
        logger.info(f"Attempting to download PDF from S3: {pdf_key}")
        if not download(pdf_key, tmp_pdf):
            logger.error(f"Failed to download PDF for bill {bill_id} from key: {pdf_key}")
            return False
        logger.info(f"Successfully downloaded PDF to: {tmp_pdf}")
        
        # Convert PDF to image
        doc = fitz.open(tmp_pdf)
        try:
            page = doc[0]  # First page
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
        finally:
            # Close the document immediately after extracting image data
            doc.close()
            doc = None
        
        # Create PIL Image
        image = Image.open(io.BytesIO(img_data))
        
        # Assess quality and choose strategy
        quality = ImageProcessor.assess_quality(image)
        if quality == FormQuality.POOR:
            strategy = ExtractionStrategy.ENHANCED_CONTRAST
        elif quality == FormQuality.EXCELLENT:
            strategy = ExtractionStrategy.HIGH_QUALITY
        else:
            strategy = ExtractionStrategy.STANDARD
        
        # Enhance image if needed
        image = ImageProcessor.enhance_image(image, strategy)
        
        # Extract data
        result = extract_with_llm(image, strategy)
        
        if result.success and result.data:
            # Update database
            if update_provider_bill_record(bill_id, result.data):
                # Save JSON to S3
                tmp_json = tempfile.mktemp(suffix='.json')
                with open(tmp_json, 'w', encoding='utf-8') as f:
                    json.dump(result.data, f, indent=2)
                upload(tmp_json, f"{OUTPUT_PREFIX}{bill_id}.json")
                os.unlink(tmp_json)
                
                # Archive PDF
                archive_key = f"{ARCHIVE_PREFIX}{Path(pdf_key).name}"
                move(pdf_key, archive_key)
                
                logger.info(f"Successfully processed {bill_id}")
                return True
            else:
                logger.error(f"Database update failed for {bill_id}")
                return False
        else:
            logger.error(f"Extraction failed for {bill_id}: {result.error_message}")
            return False
            
    except Exception as e:
        logger.error(f"Error processing {bill_id}: {e}")
        return False
    finally:
        # Close the document if it's still open (fallback safety)
        if doc is not None:
            try:
                doc.close()
            except Exception as e:
                logger.warning(f"Error closing PDF document: {e}")
        
        # Delete the temporary file
        if tmp_pdf and os.path.exists(tmp_pdf):
            try:
                os.unlink(tmp_pdf)
            except Exception as e:
                logger.warning(f"Error deleting temporary file {tmp_pdf}: {e}")

def get_scanned_bills_from_db(limit: int = None) -> List[Dict[str, Any]]:
    """Query database for bills with status 'SCANNED'."""
    # Import Django models locally to avoid import issues
    from billing.models import ProviderBill
    
    logger.info(f"Querying database for SCANNED bills")
    
    try:
        bills = ProviderBill.objects.filter(status='SCANNED')
        if limit:
            bills = bills[:limit]
        
        bill_list = []
        for bill in bills:
            bill_list.append({
                'id': bill.id,
                'source_file': bill.source_file
            })
        
        logger.info(f"Found {len(bill_list)} bills with status 'SCANNED'")
        return bill_list
        
    except Exception as e:
        logger.error(f"Database error querying SCANNED bills: {e}")
        return []

def process_scanned_bills(limit: int = None):
    """Process bills from database with status 'SCANNED'."""
    logger.info("Starting database bill processing for SCANNED status")
    
    try:
        # Get bills from database
        bills = get_scanned_bills_from_db(limit)
        
        if not bills:
            logger.info("No bills with status 'SCANNED' found")
            return
        
        logger.info(f"Found {len(bills)} bills to process")
        
        successful = 0
        failed = 0
        
        for i, bill in enumerate(bills, 1):
            bill_id = bill['id']
            source_file = bill['source_file']
            
            logger.info(f"[{i}/{len(bills)}] Processing {bill_id}")
            
            # Construct the S3 key from source_file
            if source_file and source_file.startswith('data/ProviderBills/pdf/'):
                pdf_key = source_file
            else:
                # Fallback: construct key from bill_id
                pdf_key = f"{INPUT_PREFIX}{bill_id}.pdf"
            
            if process_single_bill(bill_id, pdf_key):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"Processing complete: {successful} successful, {failed} failed")
        
    except Exception as e:
        logger.error(f"Error in database processing: {e}")

# Import io for BytesIO
import io

if __name__ == "__main__":
    # Setup Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clarity_dx_portal.settings')
    django.setup()
    
    process_scanned_bills()
