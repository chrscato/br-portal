#!/usr/bin/env python3
"""
Enhanced Job Logging and Progress Tracking Utility

Provides comprehensive logging, progress tracking, and status reporting
for long-running job operations like processing scans, validation, etc.
"""

import os
import sys
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager

# Django imports will be done conditionally to avoid conflicts
# from django.core.cache import cache
# from django.conf import settings


@dataclass
class JobProgress:
    """Tracks progress of a job operation"""
    job_id: str
    job_type: str
    total_items: int = 0
    processed_items: int = 0
    successful_items: int = 0
    failed_items: int = 0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    current_item: str = ""
    status: str = "pending"  # pending, running, completed, failed, cancelled
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100
    
    @property
    def elapsed_time(self) -> Optional[timedelta]:
        """Calculate elapsed time"""
        if not self.start_time:
            return None
        end_time = self.end_time or datetime.now()
        return end_time - self.start_time
    
    @property
    def estimated_remaining_time(self) -> Optional[timedelta]:
        """Estimate remaining time based on current progress"""
        if not self.start_time or self.processed_items == 0:
            return None
        
        elapsed = self.elapsed_time
        if not elapsed:
            return None
            
        rate = self.processed_items / elapsed.total_seconds()
        remaining_items = self.total_items - self.processed_items
        
        if rate > 0:
            remaining_seconds = remaining_items / rate
            return timedelta(seconds=remaining_seconds)
        return None


class JobLogger:
    """Enhanced logger for job operations with progress tracking"""
    
    def __init__(self, job_type: str, job_id: Optional[str] = None):
        self.job_type = job_type
        self.job_id = job_id or f"{job_type}_{int(time.time())}"
        self.logger = logging.getLogger(f"job.{job_type}")
        self.progress = JobProgress(job_id=self.job_id, job_type=job_type)
        self._lock = threading.Lock()
        
        # Set up enhanced logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up enhanced logging configuration"""
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Create file handler for job-specific logs
        log_file = logs_dir / f"{self.job_type}_{self.job_id}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Create console handler for immediate feedback
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.INFO)
        
        # Prevent duplicate logs
        self.logger.propagate = False
    
    def start_job(self, total_items: int = 0, metadata: Optional[Dict[str, Any]] = None):
        """Start a new job operation"""
        with self._lock:
            self.progress.start_time = datetime.now()
            self.progress.total_items = total_items
            self.progress.status = "running"
            if metadata:
                self.progress.metadata.update(metadata)
            
            self.logger.info(f"🚀 Starting {self.job_type} job {self.job_id}")
            self.logger.info(f"📊 Total items to process: {total_items}")
            if metadata:
                self.logger.info(f"📋 Metadata: {json.dumps(metadata, indent=2)}")
            
            self._update_cache()
    
    def update_progress(self, processed: int, successful: int, failed: int, 
                       current_item: str = "", metadata: Optional[Dict[str, Any]] = None):
        """Update job progress"""
        with self._lock:
            self.progress.processed_items = processed
            self.progress.successful_items = successful
            self.progress.failed_items = failed
            self.progress.current_item = current_item
            
            if metadata:
                self.progress.metadata.update(metadata)
            
            # Log progress every 10% or every 10 items
            if (processed % max(1, self.progress.total_items // 10) == 0 or 
                processed % 10 == 0 or processed == self.progress.total_items):
                
                progress_pct = self.progress.progress_percentage
                elapsed = self.progress.elapsed_time
                remaining = self.progress.estimated_remaining_time
                
                self.logger.info(
                    f"📈 Progress: {processed}/{self.progress.total_items} "
                    f"({progress_pct:.1f}%) - ✅ {successful} successful, ❌ {failed} failed"
                )
                
                if current_item:
                    self.logger.info(f"🔄 Currently processing: {current_item}")
                
                if elapsed:
                    self.logger.info(f"⏱️  Elapsed: {elapsed}")
                
                if remaining:
                    self.logger.info(f"⏳ Estimated remaining: {remaining}")
            
            self._update_cache()
    
    def log_item_start(self, item_id: str, item_info: str = ""):
        """Log the start of processing a specific item"""
        self.logger.info(f"🔄 Processing item {item_id}: {item_info}")
        self.update_progress(
            self.progress.processed_items,
            self.progress.successful_items,
            self.progress.failed_items,
            current_item=item_id
        )
    
    def log_item_success(self, item_id: str, result_info: str = ""):
        """Log successful processing of an item"""
        self.logger.info(f"✅ Successfully processed {item_id}: {result_info}")
        self.update_progress(
            self.progress.processed_items + 1,
            self.progress.successful_items + 1,
            self.progress.failed_items
        )
    
    def log_item_error(self, item_id: str, error: str, details: str = ""):
        """Log error processing an item"""
        self.logger.error(f"❌ Failed to process {item_id}: {error}")
        if details:
            self.logger.error(f"   Details: {details}")
        
        self.update_progress(
            self.progress.processed_items + 1,
            self.progress.successful_items,
            self.progress.failed_items + 1
        )
    
    def log_info(self, message: str, metadata: Optional[Dict[str, Any]] = None):
        """Log general information"""
        self.logger.info(f"ℹ️  {message}")
        if metadata:
            self.logger.info(f"   Metadata: {json.dumps(metadata, indent=2)}")
    
    def log_warning(self, message: str, metadata: Optional[Dict[str, Any]] = None):
        """Log warning"""
        self.logger.warning(f"⚠️  {message}")
        if metadata:
            self.logger.warning(f"   Metadata: {json.dumps(metadata, indent=2)}")
    
    def log_error(self, message: str, error: Optional[Exception] = None, 
                  metadata: Optional[Dict[str, Any]] = None):
        """Log error"""
        self.logger.error(f"❌ {message}")
        if error:
            self.logger.error(f"   Error: {str(error)}")
            self.logger.error(f"   Type: {type(error).__name__}")
        if metadata:
            self.logger.error(f"   Metadata: {json.dumps(metadata, indent=2)}")
    
    def complete_job(self, success: bool = True, error_message: str = ""):
        """Complete the job operation"""
        with self._lock:
            self.progress.end_time = datetime.now()
            self.progress.status = "completed" if success else "failed"
            self.progress.error_message = error_message
            
            elapsed = self.progress.elapsed_time
            
            if success:
                self.logger.info(f"🎉 Job {self.job_id} completed successfully!")
                self.logger.info(f"📊 Final stats: {self.progress.successful_items} successful, "
                               f"{self.progress.failed_items} failed")
            else:
                self.logger.error(f"💥 Job {self.job_id} failed: {error_message}")
            
            if elapsed:
                self.logger.info(f"⏱️  Total time: {elapsed}")
            
            self._update_cache()
    
    def _update_cache(self):
        """Update progress in cache for real-time monitoring"""
        try:
            # Import Django cache dynamically to avoid conflicts
            from django.core.cache import cache
            
            cache_key = f"job_progress_{self.job_id}"
            cache.set(cache_key, {
                'job_id': self.progress.job_id,
                'job_type': self.progress.job_type,
                'total_items': self.progress.total_items,
                'processed_items': self.progress.processed_items,
                'successful_items': self.progress.successful_items,
                'failed_items': self.progress.failed_items,
                'progress_percentage': self.progress.progress_percentage,
                'current_item': self.progress.current_item,
                'status': self.progress.status,
                'start_time': self.progress.start_time.isoformat() if self.progress.start_time else None,
                'elapsed_time': str(self.progress.elapsed_time) if self.progress.elapsed_time else None,
                'estimated_remaining_time': str(self.progress.estimated_remaining_time) if self.progress.estimated_remaining_time else None,
                'error_message': self.progress.error_message,
                'metadata': self.progress.metadata
            }, timeout=3600)  # Cache for 1 hour
        except Exception as e:
            self.logger.warning(f"Failed to update cache: {e}")
    
    @contextmanager
    def job_context(self, total_items: int = 0, metadata: Optional[Dict[str, Any]] = None):
        """Context manager for job operations"""
        try:
            self.start_job(total_items, metadata)
            yield self
            self.complete_job(success=True)
        except Exception as e:
            self.complete_job(success=False, error_message=str(e))
            raise


def get_job_progress(job_id: str) -> Optional[Dict[str, Any]]:
    """Get current progress for a job"""
    try:
        # Import Django cache dynamically to avoid conflicts
        from django.core.cache import cache
        
        cache_key = f"job_progress_{job_id}"
        return cache.get(cache_key)
    except Exception:
        return None


def list_active_jobs() -> List[Dict[str, Any]]:
    """List all active jobs"""
    try:
        # This is a simplified implementation
        # In production, you might want to store job IDs in a separate cache key
        active_jobs = []
        # Implementation would depend on how you want to track active jobs
        return active_jobs
    except Exception:
        return []


# Convenience functions for common job types
def create_scan_processor_logger(job_id: Optional[str] = None) -> JobLogger:
    """Create logger for scan processing jobs"""
    return JobLogger("process_scans", job_id)


def create_validation_logger(job_id: Optional[str] = None) -> JobLogger:
    """Create logger for validation jobs"""
    return JobLogger("process_validation", job_id)


def create_second_pass_logger(job_id: Optional[str] = None) -> JobLogger:
    """Create logger for second pass processing jobs"""
    return JobLogger("process_second_pass", job_id)


def create_upload_logger(job_id: Optional[str] = None) -> JobLogger:
    """Create logger for upload batch jobs"""
    return JobLogger("upload_batch", job_id)


def create_mapping_logger(job_id: Optional[str] = None) -> JobLogger:
    """Create logger for mapping jobs"""
    return JobLogger("process_mapping", job_id)

