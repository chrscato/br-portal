"""
Job Monitoring Views for Enhanced Logging and Progress Tracking

Provides API endpoints to monitor job progress and retrieve job logs.
"""

import json
import logging
from datetime import datetime
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
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
        # Add the jobs directory to the Python path
        import sys
        import os
        jobs_path = os.path.join(os.path.dirname(__file__), '..', '..', 'jobs')
        jobs_path = os.path.abspath(jobs_path)
        if jobs_path not in sys.path:
            sys.path.insert(0, jobs_path)
        
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
        # Construct log file path (logs are in parent directory)
        logs_dir = Path("../logs")
        log_file = logs_dir / f"*_{job_id}.log"
        
        # Find the actual log file (since we don't know the job type prefix)
        # Try both patterns: *_jobid.log and *_*_jobid.log
        log_files = list(logs_dir.glob(f"*_{job_id}.log"))
        if not log_files:
            log_files = list(logs_dir.glob(f"*_*_{job_id}.log"))
        
        if not log_files:
            return JsonResponse({
                'error': 'Log file not found',
                'job_id': job_id
            }, status=404)
        
        log_file = log_files[0]
        
        # Check if download is requested
        download = request.GET.get('download', False)
        
        # Read log file content
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            if download:
                # Return file for download
                response = HttpResponse(log_content, content_type='text/plain')
                response['Content-Disposition'] = f'attachment; filename="job_{job_id}.log"'
                return response
            
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
        # Get jobs from cache and log files
        jobs = []
        
        # Process log files to get job information
        logs_dir = Path("../logs")
        if logs_dir.exists():
            log_files = list(logs_dir.glob("*.log"))
            
            for log_file in log_files:
                try:
                    # Extract job info from filename
                    # Format: jobtype_jobtype_jobid.log (e.g., process_mapping_process_mapping_1758817106.log)
                    filename_parts = log_file.stem.split('_')
                    if len(filename_parts) >= 3:
                        # For files like process_mapping_process_mapping_1758817106.log
                        # job_type is the first part, job_id is the last part (timestamp)
                        job_type = filename_parts[0]
                        job_id = filename_parts[-1]  # Last part is the timestamp
                    elif len(filename_parts) >= 2:
                        # Fallback for simpler naming
                        job_type = filename_parts[0]
                        job_id = '_'.join(filename_parts[1:])
                    else:
                        continue
                    
                    # Try to get progress from cache (optional)
                    progress = None
                    try:
                        # Add the jobs directory to the Python path
                        import sys
                        import os
                        jobs_path = os.path.join(os.path.dirname(__file__), '..', '..', 'jobs')
                        jobs_path = os.path.abspath(jobs_path)
                        if jobs_path not in sys.path:
                            sys.path.insert(0, jobs_path)
                        
                        from jobs.utils.job_logger import get_job_progress
                        progress = get_job_progress(job_id)
                    except Exception as e:
                        logger.debug(f"Could not get progress from cache for {job_id}: {e}")
                    
                    if progress:
                        jobs.append(progress)
                    else:
                        # Create basic job info from log file
                        stat = log_file.stat()
                        
                        # Try to determine job status from log content
                        job_status = 'completed'  # Default
                        error_message = ''
                        
                        try:
                            with open(log_file, 'r', encoding='utf-8') as f:
                                log_content = f.read()
                            
                            # Check for error indicators in log
                            if 'ERROR' in log_content or '❌' in log_content:
                                job_status = 'failed'
                                # Extract error message from last error line
                                error_lines = [line for line in log_content.split('\n') if 'ERROR' in line or '❌' in line]
                                if error_lines:
                                    error_message = error_lines[-1].strip()
                            
                            # Check for completion indicators
                            elif 'completed successfully' in log_content or '✅' in log_content:
                                job_status = 'completed'
                            
                        except Exception as e:
                            logger.warning(f"Error reading log file {log_file} for status detection: {e}")
                        
                        jobs.append({
                            'job_id': job_id,
                            'job_type': job_type,
                            'status': job_status,
                            'start_time': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                            'total_items': 0,
                            'processed_items': 0,
                            'successful_items': 0,
                            'failed_items': 0,
                            'progress_percentage': 100,
                            'current_item': '',
                            'elapsed_time': 'N/A',
                            'estimated_remaining_time': None,
                            'error_message': error_message,
                            'metadata': {}
                        })
                except Exception as e:
                    logger.warning(f"Error processing log file {log_file}: {e}")
                    continue
        
        # Sort by start time (newest first)
        jobs.sort(key=lambda x: x.get('start_time', ''), reverse=True)
        
        return JsonResponse({
            'success': True,
            'active_jobs': jobs,
            'count': len(jobs)
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
        # Get actual job data from logs directory
        logs_dir = Path("../logs")
        total_jobs = 0
        completed_jobs = 0
        running_jobs = 0
        failed_jobs = 0
        
        job_types = {
            'process_scans': 0,
            'process_validation': 0,
            'process_second_pass': 0,
            'upload_batch': 0,
            'process_mapping': 0
        }
        
        if logs_dir.exists():
            log_files = list(logs_dir.glob("*.log"))
            total_jobs = len(log_files)
            
            # Count by job type
            for log_file in log_files:
                try:
                    filename_parts = log_file.stem.split('_')
                    if len(filename_parts) >= 3:
                        # For files like process_mapping_process_mapping_1758817106.log
                        job_type = filename_parts[0]
                    elif len(filename_parts) >= 2:
                        # Fallback for simpler naming
                        job_type = filename_parts[0]
                    else:
                        continue
                        
                    if job_type in job_types:
                        job_types[job_type] += 1
                except Exception:
                    continue
            
            # Count jobs by status from log content
            completed_jobs = 0
            running_jobs = 0
            failed_jobs = 0
            
            for log_file in log_files:
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    
                    if 'ERROR' in log_content or '❌' in log_content:
                        failed_jobs += 1
                    elif 'completed successfully' in log_content or '✅' in log_content:
                        completed_jobs += 1
                    else:
                        # Default to completed if no clear status
                        completed_jobs += 1
                        
                except Exception:
                    # If we can't read the file, assume completed
                    completed_jobs += 1
        
        summary = {
            'total_jobs_today': total_jobs,
            'active_jobs': running_jobs,
            'completed_jobs': completed_jobs,
            'failed_jobs': failed_jobs,
            'recent_jobs': [],
            'job_types': job_types
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


@login_required
def logs_viewer(request):
    """Main logs viewer page"""
    return render(request, 'billing/logs_viewer.html')

