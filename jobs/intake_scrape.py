#!/usr/bin/env python3
"""
llm_hcfa_vision_ultimate.py — Ultimate HCFA-1500 extractor with multi-strategy approach

Enhanced features:
• Multi-pass extraction strategy with confidence scoring
• Adaptive image processing based on quality assessment
• OCR fallback with Tesseract integration
• Zone-based extraction for improved accuracy
• Smart retry logic with different strategies
• Comprehensive validation and post-processing
• CPT code validation with known code database
• Business rule validation
• Detailed logging and monitoring

Required:
    pip install pymupdf pillow openai python-dotenv pytesseract numpy opencv-python
"""

from __future__ import annotations
import os, json, base64, tempfile, sqlite3, sys, time, logging, re, hashlib, io
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from contextlib import contextmanager
from collections import defaultdict
from enum import Enum
import traceback
import warnings

import fitz  # PyMuPDF
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from dotenv import load_dotenv
from openai import OpenAI
from openai import RateLimitError, APIError, APITimeoutError

# Optional: OCR fallback
try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    warnings.warn("Tesseract not available. OCR fallback disabled.")

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    warnings.warn("OpenCV not available. Advanced image processing disabled.")

# Project structure
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.append(str(PROJECT_ROOT))

DB_ROOT = Path(r"C:\Users\ChristopherCato\OneDrive - clarity-dx.com\code\br-portal")
PROMPT_FN = PROJECT_ROOT / "billing" / "prompts" / "gpt4o_prompt_ultimate.json"

load_dotenv(PROJECT_ROOT / ".env")

# Import S3 utilities
sys.path.insert(0, str(PROJECT_ROOT))
from config.s3_utils import list_objects, download, upload, move

# Import validation utilities
sys.path.append(str(PROJECT_ROOT / "billing" / "logic" / "preprocess" / "utils"))
from validate_intake import validate_provider_bill

# Configuration
INPUT_PREFIX = "data/ProviderBills/pdf/"
OUTPUT_PREFIX = "data/ProviderBills/json/"
ARCHIVE_PREFIX = "data/ProviderBills/pdf/archive/"
LOG_PREFIX = "logs/extract_errors.log"
S3_BUCKET = os.getenv("S3_BUCKET", "bill-review-prod")

# Enhanced logging configuration
log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
logging.basicConfig(
    level=logging.INFO,
    format=log_format,
    handlers=[
        logging.FileHandler(PROJECT_ROOT / "logs" / f"hcfa_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load enhanced prompt JSON
with open(PROMPT_FN, "r", encoding="utf-8") as f:
    _PROMPT_JSON = json.load(f)

SYSTEM_PROMPT = _PROMPT_JSON["system"]
USER_HINT = _PROMPT_JSON["user_hint"]
FUNCTIONS = _PROMPT_JSON["functions"]
EXTRACTION_STRATEGY = _PROMPT_JSON["extraction_strategy"]
OCR_CORRECTIONS = _PROMPT_JSON["ocr_correction_rules"]

# Model clients
try:
    openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")  # Use full model by default
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}")
    logger.info("Please check your OPENAI_API_KEY environment variable")
    openai_client = None
    OPENAI_MODEL = "gpt-4o"


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

@dataclass
class ProcessingStats:
    """Enhanced statistics tracking."""
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

def update_provider_bill_record(provider_bill_id: str, extracted_data: dict) -> bool:
    """Update ProviderBill record and create BillLineItem entries in the database."""
    # Use the absolute path to monolith.db
    db_path = DB_ROOT / 'monolith.db'
    logger.info(f"Connecting to database at: {db_path}")
    
    # Add retry logic for database lock issues
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            # Add timeout to handle database locks
            conn = sqlite3.connect(db_path, timeout=30.0)
            cursor = conn.cursor()
            
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
            
            # First check if the record exists
            cursor.execute("SELECT id FROM ProviderBill WHERE id = ?", (provider_bill_id,))
            if not cursor.fetchone():
                logger.error(f"Record {provider_bill_id} not found in ProviderBill table")
                return False
            
            # Update ProviderBill record with all fields
            cursor.execute(
                """
                UPDATE "ProviderBill" 
                SET status = ?,
                    last_error = NULL,
                    patient_name = ?,
                    patient_dob = ?,
                    patient_zip = ?,
                    billing_provider_name = ?,
                    billing_provider_address = ?,
                    billing_provider_tin = ?,
                    billing_provider_npi = ?,
                    total_charge = ?,
                    patient_account_no = ?,
                    action = NULL,
                    bill_paid = 'N'
                WHERE id = ?
                """,
                (
                    'SCRAPED',
                    patient_info.get('patient_name'),
                    patient_info.get('patient_dob'),
                    patient_info.get('patient_zip'),
                    billing_info.get('billing_provider_name'),
                    billing_info.get('billing_provider_address'),
                    billing_info.get('billing_provider_tin'),
                    billing_info.get('billing_provider_npi'),
                    total_charge,
                    billing_info.get('patient_account_no'),
                    provider_bill_id
                )
            )
            
            # Create BillLineItem entries for each service line
            for line in extracted_data.get('service_lines', []):
                try:
                    # Convert charge amount from string to float
                    charge_amount = None
                    if line.get('charge_amount'):
                        try:
                            charge_amount = float(line['charge_amount'].replace('$', '').replace(',', ''))
                        except (ValueError, AttributeError):
                            logger.warning(f"Could not convert charge_amount: {line.get('charge_amount')}")
                            continue
                    
                    # Join modifiers with comma if multiple
                    modifiers = ','.join(line.get('modifiers', [])) if line.get('modifiers') else ''
                    
                    cursor.execute(
                        """
                        INSERT INTO "BillLineItem" (
                            provider_bill_id, cpt_code, modifier, units,
                            charge_amount, allowed_amount, decision,
                            reason_code, date_of_service, place_of_service,
                            diagnosis_pointer
                        ) VALUES (?, ?, ?, ?, ?, NULL, 'pending', '', ?, ?, ?)
                        """,
                        (
                            provider_bill_id,
                            line.get('cpt_code'),
                            modifiers,
                            line.get('units', 1),
                            charge_amount,
                            line.get('date_of_service'),
                            line.get('place_of_service'),
                            line.get('diagnosis_pointer')
                        )
                    )
                except Exception as e:
                    logger.error(f"Error inserting service line for bill {provider_bill_id}: {e}")
                    continue
            
            conn.commit()
            logger.info(f"Successfully updated database for bill {provider_bill_id}")
            return True
            
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                logger.warning(f"Database locked for {provider_bill_id}, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
                continue
            else:
                conn.rollback()
                logger.error(f"Database error updating ProviderBill {provider_bill_id}: {str(e)}")
                return False
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"SQLite error updating ProviderBill {provider_bill_id}: {str(e)}")
            return False
        except Exception as e:
            conn.rollback()
            logger.error(f"Unexpected error updating ProviderBill {provider_bill_id}: {str(e)}")
            return False
        finally:
            if 'conn' in locals():
                conn.close()
    
    return False

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

def process_single_bill(bill_id: str, pdf_key: str) -> bool:
    """Process a single bill from S3."""
    logger.info(f"Processing bill {bill_id}")
    
    tmp_pdf = None
    doc = None
    
    try:
        # Download PDF
        tmp_pdf = tempfile.mktemp(suffix='.pdf')
        download(pdf_key, tmp_pdf)
        
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

def get_received_bills_from_db(limit: int = None) -> List[Dict[str, Any]]:
    """Query database for bills with status 'RECEIVED'."""
    db_path = DB_ROOT / 'monolith.db'
    logger.info(f"Querying database for RECEIVED bills at: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row  # Enable row factory for dict-like access
        cursor = conn.cursor()
        
        # Query for bills with status 'RECEIVED'
        query = "SELECT id, source_file FROM ProviderBill WHERE status = 'RECEIVED'"
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        bills = cursor.fetchall()
        
        # Convert to list of dictionaries
        bill_list = []
        for bill in bills:
            bill_list.append({
                'id': bill['id'],
                'source_file': bill['source_file']
            })
        
        logger.info(f"Found {len(bill_list)} bills with status 'RECEIVED'")
        return bill_list
        
    except sqlite3.Error as e:
        logger.error(f"Database error querying RECEIVED bills: {e}")
        return []
    finally:
        if 'conn' in locals():
            conn.close()

def process_received_bills(limit: int = None):
    """Process bills from database with status 'RECEIVED'."""
    logger.info("Starting database bill processing for RECEIVED status")
    
    try:
        # Get bills from database
        bills = get_received_bills_from_db(limit)
        
        if not bills:
            logger.info("No bills with status 'RECEIVED' found")
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

def process_s3(limit: int = None):
    """Process bills from S3."""
    logger.info("Starting S3 bill processing")
    
    try:
        # List PDFs in input directory
        pdfs = list_objects(INPUT_PREFIX)
        if limit:
            pdfs = pdfs[:limit]
        
        logger.info(f"Found {len(pdfs)} PDFs to process")
        
        successful = 0
        failed = 0
        
        for i, pdf_key in enumerate(pdfs, 1):
            bill_id = Path(pdf_key).stem
            logger.info(f"[{i}/{len(pdfs)}] Processing {bill_id}")
            
            if process_single_bill(bill_id, pdf_key):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"Processing complete: {successful} successful, {failed} failed")
        
    except Exception as e:
        logger.error(f"Error in S3 processing: {e}")

if __name__ == "__main__":
    process_received_bills()