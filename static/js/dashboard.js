document.addEventListener('DOMContentLoaded', function() {
    // Show the dashboard after DOM is loaded
    document.getElementById('main-content').style.display = 'block';
    
    // Start the auto-refresh for project status
    refreshProjectStatuses();
    setInterval(refreshProjectStatuses, 5000);
    
    // Setup log polling for the project details page
    const projectDetailsElement = document.getElementById('project-details');
    if (projectDetailsElement) {
        const projectId = projectDetailsElement.dataset.projectId;
        if (projectId) {
            refreshProjectLogs(projectId);
            setInterval(() => refreshProjectLogs(projectId), 3000);
        }
    }
    
    // Setup event listeners for start/stop buttons
    document.addEventListener('click', function(event) {
        if (event.target.classList.contains('btn-start-project')) {
            startProject(event.target.dataset.projectId);
        } else if (event.target.classList.contains('btn-stop-project')) {
            stopProject(event.target.dataset.projectId);
        } else if (event.target.classList.contains('btn-remove-project')) {
            removeProject(event.target.dataset.projectId);
        }
    });
});

function refreshProjectStatuses() {
    fetch('/api/projects')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success === false) {
                throw new Error(data.message || 'Unknown error');
            }
            
            // If it's an array, process it as before
            if (Array.isArray(data)) {
                data.forEach(project => {
                    updateProjectStatus(project);
                });
            } else {
                console.error('Unexpected data format from API:', data);
            }
        })
        .catch(error => {
            console.error('Error fetching project statuses:', error);
            // Only show toast for serious errors, not for regular polling
            if (error.message !== 'Failed to fetch') {
                showToast('Error', 'Failed to fetch project statuses. Check server logs.', 'danger');
            }
        });
}

function updateProjectStatus(project) {
    const statusElement = document.getElementById(`project-status-${project.id}`);
    if (statusElement) {
        let statusClass = '';
        let statusText = '';
        
        switch (project.status) {
            case 'running':
                statusClass = 'bg-success';
                statusText = 'Running';
                break;
            case 'stopped':
                statusClass = 'bg-secondary';
                statusText = 'Stopped';
                break;
            case 'error':
                statusClass = 'bg-danger';
                statusText = 'Error';
                break;
            default:
                statusClass = 'bg-warning';
                statusText = 'Unknown';
        }
        
        statusElement.className = `badge ${statusClass}`;
        statusElement.textContent = statusText;
        
        // Update action buttons based on status
        const startBtn = document.getElementById(`start-btn-${project.id}`);
        const stopBtn = document.getElementById(`stop-btn-${project.id}`);
        
        if (startBtn && stopBtn) {
            if (project.status === 'running') {
                startBtn.disabled = true;
                stopBtn.disabled = false;
            } else {
                startBtn.disabled = false;
                stopBtn.disabled = true;
            }
        }
    }
}

function startProject(projectId) {
    fetch(`/api/project/${projectId}/start`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', data.message, 'success');
            // Force a refresh of statuses
            refreshProjectStatuses();
        } else {
            showToast('Error', data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error starting project:', error);
        showToast('Error', 'Failed to start project', 'danger');
    });
}

function stopProject(projectId) {
    fetch(`/api/project/${projectId}/stop`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', data.message, 'success');
            // Force a refresh of statuses
            refreshProjectStatuses();
        } else {
            showToast('Error', data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error stopping project:', error);
        showToast('Error', 'Failed to stop project', 'danger');
    });
}

function removeProject(projectId) {
    if (!confirm('Are you sure you want to remove this project?')) {
        return;
    }
    
    fetch(`/api/project/${projectId}/remove`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showToast('Success', data.message, 'success');
            // Redirect to dashboard after removal
            window.location.href = '/dashboard';
        } else {
            showToast('Error', data.message, 'danger');
        }
    })
    .catch(error => {
        console.error('Error removing project:', error);
        showToast('Error', 'Failed to remove project', 'danger');
    });
}

function refreshProjectLogs(projectId) {
    const logsElement = document.getElementById('project-logs');
    if (!logsElement) return;
    
    fetch(`/api/project/${projectId}/logs`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success === false) {
                throw new Error(data.message || 'Unknown error');
            }
            
            if (data.success && data.logs && data.logs.length > 0) {
                logsElement.innerHTML = '';
                data.logs.forEach(log => {
                    const logLine = document.createElement('div');
                    logLine.className = 'log-line';
                    logLine.textContent = log;
                    logsElement.appendChild(logLine);
                });
                // Auto-scroll to bottom
                logsElement.scrollTop = logsElement.scrollHeight;
            }
        })
        .catch(error => {
            console.error('Error fetching project logs:', error);
            // Don't show a toast for log errors, as they happen too frequently
        });
}

function showToast(title, message, type = 'info') {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) return;
    
    const toastId = `toast-${Date.now()}`;
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-bg-${type} border-0`;
    toast.setAttribute('id', toastId);
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <strong>${title}</strong>: ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const toastInstance = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 5000
    });
    
    toastInstance.show();
    
    // Remove toast from DOM after it's hidden
    toast.addEventListener('hidden.bs.toast', function() {
        toast.remove();
    });
}
