/**
 * Job Progress Monitor
 * 
 * Provides real-time monitoring of job progress with automatic updates
 * and visual progress indicators.
 */

class JobMonitor {
    constructor(options = {}) {
        this.jobId = options.jobId;
        this.updateInterval = options.updateInterval || 2000; // 2 seconds
        this.maxRetries = options.maxRetries || 3;
        this.retryDelay = options.retryDelay || 5000; // 5 seconds
        this.onComplete = options.onComplete || (() => {});
        this.onError = options.onError || (() => {});
        this.onProgress = options.onProgress || (() => {});
        
        this.isMonitoring = false;
        this.retryCount = 0;
        this.intervalId = null;
        
        // Create progress display elements
        this.createProgressDisplay();
    }
    
    createProgressDisplay() {
        // Create progress modal if it doesn't exist
        if (!document.getElementById('job-progress-modal')) {
            const modalHtml = `
                <div class="modal fade" id="job-progress-modal" tabindex="-1" aria-hidden="true">
                    <div class="modal-dialog modal-lg">
                        <div class="modal-content">
                            <div class="modal-header">
                                <h5 class="modal-title" id="job-progress-title">Job Progress</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                            </div>
                            <div class="modal-body">
                                <div class="row">
                                    <div class="col-md-6">
                                        <div class="card">
                                            <div class="card-body">
                                                <h6 class="card-title">Progress</h6>
                                                <div class="progress mb-2">
                                                    <div class="progress-bar" id="job-progress-bar" role="progressbar" style="width: 0%"></div>
                                                </div>
                                                <small class="text-muted" id="job-progress-text">0% complete</small>
                                            </div>
                                        </div>
                                    </div>
                                    <div class="col-md-6">
                                        <div class="card">
                                            <div class="card-body">
                                                <h6 class="card-title">Statistics</h6>
                                                <div class="row text-center">
                                                    <div class="col-4">
                                                        <div class="text-success">
                                                            <strong id="job-successful">0</strong>
                                                            <br><small>Successful</small>
                                                        </div>
                                                    </div>
                                                    <div class="col-4">
                                                        <div class="text-danger">
                                                            <strong id="job-failed">0</strong>
                                                            <br><small>Failed</small>
                                                        </div>
                                                    </div>
                                                    <div class="col-4">
                                                        <div class="text-info">
                                                            <strong id="job-total">0</strong>
                                                            <br><small>Total</small>
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row mt-3">
                                    <div class="col-12">
                                        <div class="card">
                                            <div class="card-body">
                                                <h6 class="card-title">Current Status</h6>
                                                <div id="job-current-item" class="text-muted">Initializing...</div>
                                                <div id="job-elapsed-time" class="text-muted mt-1"></div>
                                                <div id="job-remaining-time" class="text-muted"></div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="row mt-3">
                                    <div class="col-12">
                                        <div class="card">
                                            <div class="card-body">
                                                <h6 class="card-title">Recent Activity</h6>
                                                <div id="job-activity-log" class="small" style="max-height: 200px; overflow-y: auto;">
                                                    <div class="text-muted">Starting job...</div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div class="modal-footer">
                                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                                <button type="button" class="btn btn-danger" id="cancel-job-btn" style="display: none;">Cancel Job</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHtml);
        }
        
        // Show the modal
        const modal = new bootstrap.Modal(document.getElementById('job-progress-modal'));
        modal.show();
    }
    
    startMonitoring() {
        if (this.isMonitoring) {
            return;
        }
        
        this.isMonitoring = true;
        this.retryCount = 0;
        
        // Start polling for updates
        this.intervalId = setInterval(() => {
            this.updateProgress();
        }, this.updateInterval);
        
        // Initial update
        this.updateProgress();
    }
    
    stopMonitoring() {
        this.isMonitoring = false;
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
    
    async updateProgress() {
        try {
            const response = await fetch(`/billing/api/jobs/progress/${this.jobId}/`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.updateDisplay(data.progress);
                this.retryCount = 0; // Reset retry count on success
                
                // Check if job is complete
                if (data.progress.status === 'completed' || data.progress.status === 'failed') {
                    this.stopMonitoring();
                    this.onComplete(data.progress);
                    
                    // Auto-close modal after 5 seconds if completed successfully
                    if (data.progress.status === 'completed') {
                        setTimeout(() => {
                            const modal = bootstrap.Modal.getInstance(document.getElementById('job-progress-modal'));
                            if (modal) {
                                modal.hide();
                            }
                        }, 5000);
                    }
                } else {
                    this.onProgress(data.progress);
                }
            } else {
                throw new Error(data.error || 'Unknown error');
            }
            
        } catch (error) {
            console.error('Error updating job progress:', error);
            this.retryCount++;
            
            if (this.retryCount >= this.maxRetries) {
                this.stopMonitoring();
                this.onError(error);
                this.addActivityLog(`❌ Failed to get job updates after ${this.maxRetries} retries: ${error.message}`, 'error');
            } else {
                this.addActivityLog(`⚠️ Error getting job updates (retry ${this.retryCount}/${this.maxRetries}): ${error.message}`, 'warning');
                
                // Wait before retrying
                setTimeout(() => {
                    if (this.isMonitoring) {
                        this.updateProgress();
                    }
                }, this.retryDelay);
            }
        }
    }
    
    updateDisplay(progress) {
        // Update progress bar
        const progressBar = document.getElementById('job-progress-bar');
        const progressText = document.getElementById('job-progress-text');
        const percentage = Math.round(progress.progress_percentage || 0);
        
        if (progressBar) {
            progressBar.style.width = `${percentage}%`;
            progressBar.setAttribute('aria-valuenow', percentage);
        }
        
        if (progressText) {
            progressText.textContent = `${percentage}% complete (${progress.processed_items || 0}/${progress.total_items || 0})`;
        }
        
        // Update statistics
        const successfulEl = document.getElementById('job-successful');
        const failedEl = document.getElementById('job-failed');
        const totalEl = document.getElementById('job-total');
        
        if (successfulEl) successfulEl.textContent = progress.successful_items || 0;
        if (failedEl) failedEl.textContent = progress.failed_items || 0;
        if (totalEl) totalEl.textContent = progress.total_items || 0;
        
        // Update current status
        const currentItemEl = document.getElementById('job-current-item');
        const elapsedTimeEl = document.getElementById('job-elapsed-time');
        const remainingTimeEl = document.getElementById('job-remaining-time');
        
        if (currentItemEl) {
            currentItemEl.textContent = progress.current_item || 'Processing...';
        }
        
        if (elapsedTimeEl) {
            elapsedTimeEl.textContent = progress.elapsed_time ? `Elapsed: ${progress.elapsed_time}` : '';
        }
        
        if (remainingTimeEl) {
            remainingTimeEl.textContent = progress.estimated_remaining_time ? `Remaining: ${progress.estimated_remaining_time}` : '';
        }
        
        // Update title with job type
        const titleEl = document.getElementById('job-progress-title');
        if (titleEl) {
            const jobType = progress.job_type || 'Job';
            const status = progress.status || 'running';
            titleEl.textContent = `${jobType} - ${status.charAt(0).toUpperCase() + status.slice(1)}`;
        }
        
        // Add activity log entry
        if (progress.current_item) {
            this.addActivityLog(`🔄 Processing: ${progress.current_item}`, 'info');
        }
    }
    
    addActivityLog(message, type = 'info') {
        const logEl = document.getElementById('job-activity-log');
        if (!logEl) return;
        
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `mb-1 text-${type === 'error' ? 'danger' : type === 'warning' ? 'warning' : 'muted'}`;
        logEntry.textContent = `[${timestamp}] ${message}`;
        
        logEl.insertBefore(logEntry, logEl.firstChild);
        
        // Keep only last 20 entries
        while (logEl.children.length > 20) {
            logEl.removeChild(logEl.lastChild);
        }
    }
}

// Global function to start job monitoring (called from templates)
function startJobMonitoring(jobId, options = {}) {
    const monitor = new JobMonitor({
        jobId: jobId,
        ...options
    });
    
    monitor.startMonitoring();
    
    return monitor;
}

// Utility function to show loading with job monitoring
function showLoadingWithJobMonitoring(title, message, jobId) {
    // Show the loading message first
    showLoading(title, message);
    
    // Start job monitoring after a short delay
    setTimeout(() => {
        startJobMonitoring(jobId, {
            onComplete: (progress) => {
                console.log('Job completed:', progress);
                // You can add custom completion handling here
            },
            onError: (error) => {
                console.error('Job monitoring error:', error);
                // You can add custom error handling here
            }
        });
    }, 1000);
}

