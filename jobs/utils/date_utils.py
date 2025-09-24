# billing/logic/preprocess/utils/date_utils.py
"""
Date utilities for standardizing and validating date formats in medical billing.

All dates are standardized to YYYY-MM-DD format for consistency across the system.
"""

import re
import logging
from datetime import datetime, date
from typing import Optional, Tuple, Union

logger = logging.getLogger(__name__)

class DateStandardizer:
    """
    Standardizes various date formats to YYYY-MM-DD format.
    Handles both single dates and date ranges commonly found in medical billing.
    """
    
    def __init__(self):
        # Define supported input formats in order of preference
        self.input_formats = [
            # ISO and year-first formats
            '%Y-%m-%d',      # 2024-01-17 (already standardized)
            '%Y/%m/%d',      # 2024/01/17
            '%Y%m%d',        # 20240117
            
            # US formats (most common in medical billing)
            '%m/%d/%Y',      # 01/17/2024
            '%m-%d-%Y',      # 01-17-2024
            '%m/%d/%y',      # 01/17/24
            '%m-%d-%y',      # 01-17-24
            '%m.%d.%Y',      # 01.17.2024
            '%m.%d.%y',      # 01.17.24
            
            # International formats
            '%d/%m/%Y',      # 17/01/2024
            '%d-%m-%Y',      # 17-01-2024
            '%d/%m/%y',      # 17/01/24
            '%d-%m-%y',      # 17-01-24
            '%d.%m.%Y',      # 17.01.2024
            '%d.%m.%y',      # 17.01.24
            
            # Month name formats
            '%B %d, %Y',     # January 17, 2024
            '%b %d, %Y',     # Jan 17, 2024
            '%d %B %Y',      # 17 January 2024
            '%d %b %Y',      # 17 Jan 2024
        ]
        
        # Range separators in order of specificity
        self.range_separators = [
            ' - ',    # "01/17/2024 - 01/18/2024"
            ' – ',    # En dash with spaces
            ' — ',    # Em dash with spaces
            ' to ',   # "01/17/2024 to 01/18/2024"
            ' TO ',
            ' thru ',
            ' THRU ',
            '–',      # En dash without spaces
            '—',      # Em dash without spaces
        ]
    
    def is_iso_date(self, date_str: str) -> bool:
        """Check if string is already in YYYY-MM-DD format."""
        return bool(re.match(r'^\d{4}-\d{1,2}-\d{1,2}$', date_str.strip()))
    
    def extract_date_range(self, date_str: str) -> Optional[Tuple[str, str]]:
        """
        Extract start and end dates from a date range string.
        
        Returns:
            Tuple of (start_date_str, end_date_str) or None if not a range
        """
        date_str = str(date_str).strip()
        
        # Try explicit range separators first
        for separator in self.range_separators:
            if separator in date_str:
                parts = date_str.split(separator)
                if len(parts) >= 2:
                    return parts[0].strip(), parts[-1].strip()
        
        # Handle single hyphen carefully (avoid ISO date conflicts)
        if '-' in date_str and not self.is_iso_date(date_str):
            parts = date_str.split('-')
            if len(parts) == 2:
                left, right = parts[0].strip(), parts[1].strip()
                # Both parts should look like dates
                if (re.search(r'\d', left) and re.search(r'\d', right) and
                    (any(char in left for char in ['/', '.']) or 
                     any(char in right for char in ['/', '.']))):
                    return left, right
        
        return None
    
    def parse_single_date(self, date_str: str) -> Optional[date]:
        """
        Parse a single date string into a date object.
        
        Args:
            date_str: Date string to parse
            
        Returns:
            date object or None if parsing fails
        """
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # Remove any non-date prefixes (like "MX" or other text)
        date_str = re.sub(r'^[^0-9]+', '', date_str)
        
        # Try each format
        for fmt in self.input_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                
                # Handle 2-digit years
                if parsed_date.year < 100:
                    if parsed_date.year <= 30:
                        parsed_date = parsed_date.replace(year=parsed_date.year + 2000)
                    else:
                        parsed_date = parsed_date.replace(year=parsed_date.year + 1900)
                
                # Validate reasonable year range for medical billing
                if 1900 <= parsed_date.year <= 2030:
                    return parsed_date
                    
            except ValueError:
                continue
        
        # Try regex patterns for edge cases
        return self._parse_with_regex(date_str)
    
    def _parse_with_regex(self, date_str: str) -> Optional[date]:
        """Parse using regex patterns for edge cases."""
        patterns = [
            (r'(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})', 'mdy'),  # MM/DD/YY
            (r'(\d{4})[\/\-\.](\d{1,2})[\/\-\.](\d{1,2})', 'ymd'),     # YYYY/MM/DD
            (r'(\d{1,2})\s+(\d{1,2})\s+(\d{2,4})', 'mdy'),            # MM DD YY
        ]
        
        for pattern, order in patterns:
            match = re.match(pattern, date_str)
            if match:
                part1, part2, part3 = match.groups()
                
                try:
                    if order == 'mdy':
                        month, day, year = int(part1), int(part2), int(part3)
                    elif order == 'ymd':
                        year, month, day = int(part1), int(part2), int(part3)
                    
                    # Handle 2-digit years
                    if year < 100:
                        year = year + 2000 if year <= 30 else year + 1900
                    
                    # Validate ranges
                    if 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2030:
                        try:
                            return date(year, month, day)
                        except ValueError:
                            pass  # Invalid date (like Feb 30)
                            
                except ValueError:
                    continue
        
        return None
    
    def standardize_date(self, date_str: str) -> Optional[str]:
        """
        Standardize any date format to YYYY-MM-DD.
        For date ranges, returns the start date.
        
        Args:
            date_str: Input date string (any supported format)
            
        Returns:
            Standardized date string (YYYY-MM-DD) or None if invalid
        """
        if not date_str:
            return None
        
        date_str = str(date_str).strip()
        
        # If already in standard format, validate and return
        if self.is_iso_date(date_str):
            try:
                # Validate it's a real date
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError:
                return None
        
        # Handle date ranges - take the first date
        range_result = self.extract_date_range(date_str)
        if range_result:
            start_date_str, _ = range_result
            parsed_date = self.parse_single_date(start_date_str)
        else:
            # Handle single date
            parsed_date = self.parse_single_date(date_str)
        
        if parsed_date:
            return parsed_date.strftime('%Y-%m-%d')
        
        return None


# Global standardizer instance
_date_standardizer = DateStandardizer()


def standardize_date_of_service(date_str: str) -> Optional[str]:
    """
    Main function to standardize date of service to YYYY-MM-DD format.
    
    Args:
        date_str: Input date string (any supported format)
        
    Returns:
        Standardized date string (YYYY-MM-DD) or None if invalid
    """
    try:
        result = _date_standardizer.standardize_date(date_str)
        if result:
            logger.debug(f"Standardized date: '{date_str}' -> '{result}'")
        else:
            logger.warning(f"Could not standardize date: '{date_str}'")
        return result
    except Exception as e:
        logger.error(f"Error standardizing date '{date_str}': {str(e)}")
        return None


def validate_standardized_date(date_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a standardized date string.
    
    Args:
        date_str: Date string in YYYY-MM-DD format
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not date_str:
        return False, "Missing date"
    
    try:
        # Parse the standardized date
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Check if date is in the future
        if parsed_date > datetime.now().date():
            return False, f"Future date not allowed: {date_str}"
        
        # Check reasonable range for medical billing
        if parsed_date.year < 1900 or parsed_date.year > 2030:
            return False, f"Date out of reasonable range: {date_str}"
        
        return True, None
        
    except ValueError:
        return False, f"Invalid date format (expected YYYY-MM-DD): {date_str}"
    except Exception as e:
        return False, f"Error validating date: {str(e)}"


def standardize_and_validate_date_of_service(date_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Combined function to standardize and validate date of service.
    
    Args:
        date_str: Input date string (any supported format)
        
    Returns:
        Tuple of (is_valid, standardized_date, error_message)
    """
    # Step 1: Standardize
    standardized = standardize_date_of_service(date_str)
    if not standardized:
        return False, None, f"Could not parse date format: {date_str}"
    
    # Step 2: Validate
    is_valid, error_msg = validate_standardized_date(standardized)
    
    return is_valid, standardized if is_valid else None, error_msg


# Convenience functions for common operations
def is_future_date(date_str: str) -> bool:
    """Check if a YYYY-MM-DD date is in the future."""
    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        return parsed_date > datetime.now().date()
    except ValueError:
        return False


def format_date_for_display(date_str: str, format_str: str = '%m/%d/%Y') -> str:
    """Convert YYYY-MM-DD to display format (default: MM/DD/YYYY)."""
    try:
        parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        return parsed_date.strftime(format_str)
    except ValueError:
        return date_str  # Return original if parsing fails


# Testing function
def test_date_standardizer():
    """Test the date standardizer with common formats."""
    test_cases = [
        "2024-01-17",                    # ISO format
        "01/17/2024",                    # US format
        "01/17/24",                      # US 2-digit year
        "12/26/24 - 12/26/24",          # Date range
        "01/17/2025 - 01/17/2025",      # Date range with 4-digit year
        "January 17, 2024",              # Month name format
        "MX01/17/2024",                  # With prefix
        "invalid-date",                  # Invalid case
        "",                              # Empty case
        None,                            # None case
    ]
    
    print("Testing Date Standardizer:")
    print("=" * 50)
    
    for test_date in test_cases:
        is_valid, standardized, error = standardize_and_validate_date_of_service(test_date)
        status = "✓ VALID" if is_valid else "✗ INVALID"
        
        print(f"Input: {str(test_date):25} -> {status}")
        if standardized:
            print(f"  Standardized: {standardized}")
        if error:
            print(f"  Error: {error}")
        print()


if __name__ == "__main__":
    test_date_standardizer()