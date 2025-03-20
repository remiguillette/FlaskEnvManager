import os
import json
import uuid
import subprocess
import signal
import logging
import time
import yaml
from threading import Lock
import psutil

logger = logging.getLogger(__name__)

class ProjectManager:
    """Manages Flask projects for the dashboard."""
    
    CONFIG_FILE = 'flask_dashboard_config.yaml'
    
    def __init__(self):
        """Initialize the project manager."""
        self.projects = {}
        self.processes = {}
        self.logs = {}
        self.lock = Lock()
        self.load_config()
    
    def load_config(self):
        """Load project configuration from YAML file."""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, 'r') as f:
                    data = yaml.safe_load(f)
                    if data and 'projects' in data:
                        self.projects = data['projects']
                        
                # Check for any processes that might still be running from a previous session
                for project_id, project in self.projects.items():
                    self.update_status(project_id)
            else:
                # Create empty config if it doesn't exist
                self.save_config()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            # Create empty config if there was an error
            self.projects = {}
            self.save_config()
    
    def save_config(self):
        """Save project configuration to YAML file."""
        try:
            with open(self.CONFIG_FILE, 'w') as f:
                yaml.dump({'projects': self.projects}, f)
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def add_project(self, name, path, entry_file='main.py', port=5000):
        """Add a new project to the manager."""
        with self.lock:
            try:
                project_id = str(uuid.uuid4())
                self.projects[project_id] = {
                    'id': project_id,
                    'name': name,
                    'path': path,
                    'entry_file': entry_file,
                    'port': port,
                    'status': 'stopped',
                    'added_date': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                return self.save_config()
            except Exception as e:
                logger.error(f"Error adding project: {e}")
                return False
    
    def remove_project(self, project_id):
        """Remove a project from the manager."""
        with self.lock:
            if project_id in self.projects:
                # Stop the project if it's running
                if self.get_project_status(project_id) == 'running':
                    self.stop_project(project_id)
                
                # Remove the project
                del self.projects[project_id]
                if project_id in self.logs:
                    del self.logs[project_id]
                return self.save_config()
            return False
    
    def start_project(self, project_id):
        """Start a Flask project."""
        with self.lock:
            if project_id not in self.projects:
                logger.error(f"Project {project_id} not found")
                return False
            
            project = self.projects[project_id]
            
            # Check if already running - directly check process status to avoid deadlock
            if project_id in self.processes:
                process = self.processes[project_id]
                if process.poll() is None:
                    logger.info(f"Project {project_id} is already running")
                    return True
            
            try:
                # Prepare the command
                python_path = os.path.join(project['path'], 'venv', 'bin', 'python')
                if not os.path.exists(python_path):
                    python_path = 'python'  # Fallback to system python
                
                entry_file_path = os.path.join(project['path'], project['entry_file'])
                
                # Start the process
                process = subprocess.Popen(
                    [python_path, entry_file_path],
                    cwd=project['path'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                self.processes[project_id] = process
                self.logs[project_id] = []
                
                # Update project status
                self.projects[project_id]['status'] = 'running'
                self.projects[project_id]['pid'] = process.pid
                self.save_config()
                
                # Start a thread to read process output
                def read_output():
                    while process.poll() is None:
                        line = process.stdout.readline()
                        if line:
                            with self.lock:
                                self.logs[project_id].append(line.strip())
                                # Keep only the last 100 lines
                                if len(self.logs[project_id]) > 100:
                                    self.logs[project_id] = self.logs[project_id][-100:]
                    
                    # Process has terminated
                    with self.lock:
                        self.update_status(project_id)
                
                import threading
                output_thread = threading.Thread(target=read_output)
                output_thread.daemon = True
                output_thread.start()
                
                return True
            
            except Exception as e:
                logger.error(f"Error starting project {project_id}: {e}")
                self.projects[project_id]['status'] = 'error'
                self.save_config()
                return False
    
    def stop_project(self, project_id):
        """Stop a running Flask project."""
        with self.lock:
            if project_id not in self.projects:
                logger.error(f"Project {project_id} not found")
                return False
            
            # Check if the project is running
            if self.get_project_status(project_id) != 'running':
                logger.info(f"Project {project_id} is not running")
                return True
            
            try:
                # Get the process
                if project_id in self.processes:
                    process = self.processes[project_id]
                    pid = process.pid
                    
                    # Try to terminate process gracefully first
                    process.terminate()
                    
                    # Wait for a bit to see if it terminates
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        # Force kill if it doesn't terminate
                        process.kill()
                    
                    # Remove from processes dict
                    del self.processes[project_id]
                
                # Also try to kill the process by PID in case the subprocess reference is stale
                elif 'pid' in self.projects[project_id]:
                    pid = self.projects[project_id]['pid']
                    try:
                        os.kill(pid, signal.SIGTERM)
                        time.sleep(1)  # Give it a second to terminate
                        # Check if still running
                        if psutil.pid_exists(pid):
                            os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        # Process already gone
                        pass
                
                # Update project status
                self.projects[project_id]['status'] = 'stopped'
                if 'pid' in self.projects[project_id]:
                    del self.projects[project_id]['pid']
                self.save_config()
                
                return True
            
            except Exception as e:
                logger.error(f"Error stopping project {project_id}: {e}")
                return False
    
    def get_project(self, project_id):
        """Get a project by ID."""
        with self.lock:
            if project_id in self.projects:
                project = self.projects[project_id].copy()
                self.update_status(project_id)
                return project
            return None
    
    def get_all_projects(self):
        """Get all projects."""
        with self.lock:
            # Update status for all projects
            for project_id in self.projects:
                self.update_status(project_id)
            return list(self.projects.values())
    
    def get_project_logs(self, project_id):
        """Get the logs for a project."""
        with self.lock:
            if project_id in self.logs:
                return self.logs[project_id]
            return []
    
    def get_project_status(self, project_id):
        """Get the status of a project."""
        with self.lock:
            if project_id in self.projects:
                self.update_status(project_id)
                return self.projects[project_id]['status']
            return 'unknown'
    
    def update_status(self, project_id):
        """Update the status of a project based on its process."""
        if project_id not in self.projects:
            return
        
        # Check if we have a process object
        if project_id in self.processes:
            process = self.processes[project_id]
            if process.poll() is None:
                self.projects[project_id]['status'] = 'running'
            else:
                self.projects[project_id]['status'] = 'stopped'
                del self.processes[project_id]
                if 'pid' in self.projects[project_id]:
                    del self.projects[project_id]['pid']
        
        # Check by PID if we don't have a process object
        elif 'pid' in self.projects[project_id]:
            pid = self.projects[project_id]['pid']
            if psutil.pid_exists(pid):
                try:
                    process = psutil.Process(pid)
                    # Check if it's a python process
                    if 'python' in process.name().lower():
                        self.projects[project_id]['status'] = 'running'
                    else:
                        self.projects[project_id]['status'] = 'stopped'
                        del self.projects[project_id]['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.projects[project_id]['status'] = 'stopped'
                    del self.projects[project_id]['pid']
            else:
                self.projects[project_id]['status'] = 'stopped'
                del self.projects[project_id]['pid']
        else:
            self.projects[project_id]['status'] = 'stopped'
