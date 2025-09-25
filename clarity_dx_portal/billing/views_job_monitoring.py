"""
Job Monitoring Views for Enhanced Logging and Progress Tracking

Provides API endpoints to monitor job progress and retrieve job logs.
"""

import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.conf import settings
from pathlib import Path

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def get_job_progress(request, job_id):
    """Get current progress for a specific job"""
    try:
        from jobs.utils.job_logger import get_job_progress
        
        progress = get_job_progress(job_id)
        
        if progress is None:
            return JsonResponse({
                'error': 'Job not found or expired',
                'job_id': job_id
            }, status=404)
        
        return JsonResponse({
            'success': True,
            'job_id': job_id,
            'progress': progress
        })
        
    except Exception as e:
        logger.error(f"Error getting job progress for {job_id}: {e}")
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_job_logs(request, job_id):
    """Get log file for a specific job"""
    try:
        # Construct log file path
        logs_dir = Path("logs")
        log_file = logs_dir / f"*_{job_id}.log"
        
        # Find the actual log file (since we don't know the job type prefix)
        log_files = list(logs_dir.glob(f"*_{job_id}.log"))
        
        if not log_files:
            return JsonResponse({
                'error': 'Log file not found',
                'job_id': job_id
            }, status=404)
        
        log_file = log_files[0]
        
        # Read log file content
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            return JsonResponse({
                'success': True,
                'job_id': job_id,
                'log_file': str(log_file),
                'content': log_content
            })
            
        except Exception as e:
            return JsonResponse({
                'error': 'Error reading log file',
                'message': str(e)
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error getting job logs for {job_id}: {e}")
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def list_active_jobs(request):
    """List all currently active jobs"""
    try:
        from jobs.utils.job_logger import list_active_jobs
        
        active_jobs = list_active_jobs()
        
        return JsonResponse({
            'success': True,
            'active_jobs': active_jobs,
            'count': len(active_jobs)
        })
        
    except Exception as e:
        logger.error(f"Error listing active jobs: {e}")
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_job_status_summary(request):
    """Get a summary of job statuses and recent activity"""
    try:
        # This would typically query a database or cache for job history
        # For now, we'll return a simple summary
        
        summary = {
            'total_jobs_today': 0,  # Would be calculated from logs or DB
            'active_jobs': 0,       # Would be calculated from cache
            'recent_jobs': [],      # Would be recent job history
            'job_types': {
                'process_scans': 0,
                'process_validation': 0,
                'process_second_pass': 0,
                'upload_batch': 0,
                'process_mapping': 0
            }
        }
        
        return JsonResponse({
            'success': True,
            'summary': summary
        })
        
    except Exception as e:
        logger.error(f"Error getting job status summary: {e}")
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
@csrf_exempt
def cancel_job(request, job_id):
    """Cancel a running job (if supported)"""
    try:
        # This would implement job cancellation logic
        # For now, we'll just return a not implemented response
        
        return JsonResponse({
            'error': 'Job cancellation not yet implemented',
            'job_id': job_id
        }, status=501)
        
    except Exception as e:
        logger.error(f"Error canceling job {job_id}: {e}")
        return JsonResponse({
            'error': 'Internal server error',
            'message': str(e)
        }, status=500)

