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
                # Check status directly to avoid lock recursion
                is_running = False
                if project_id in self.processes:
                    process = self.processes[project_id]
                    if process.poll() is None:
                        is_running = True
                elif 'pid' in self.projects[project_id]:
                    pid = self.projects[project_id]['pid']
                    if psutil.pid_exists(pid):
                        is_running = True

                # Stop if running
                if is_running:
                    self.stop_project(project_id)
                
                # Remove the project
                del self.projects[project_id]
                if project_id in self.logs:
                    del self.logs[project_id]
                if project_id in self.processes:
                    del self.processes[project_id]
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
                    if process and process.stdout:
                        while process and process.poll() is None:
                            try:
                                line = process.stdout.readline()
                                if line:
                                    with self.lock:
                                        self.logs[project_id].append(line.strip())
                                        # Keep only the last 100 lines
                                        if len(self.logs[project_id]) > 100:
                                            self.logs[project_id] = self.logs[project_id][-100:]
                            except Exception as e:
                                logger.error(f"Error reading output: {e}")
                                break
                    
                    # Process has terminated or there was an error
                    with self.lock:
                        if project_id in self.projects:
                            self.projects[project_id]['status'] = 'stopped'
                        if project_id in self.processes:
                            del self.processes[project_id]
                
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
            
            # Check if the project is running - direct check to avoid deadlock
            is_running = False
            if project_id in self.processes:
                process = self.processes[project_id]
                if process.poll() is None:
                    is_running = True
            elif 'pid' in self.projects[project_id]:
                pid = self.projects[project_id]['pid']
                if psutil.pid_exists(pid):
                    is_running = True
                    
            if not is_running:
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
                # Create a copy to avoid modifying the original while it's being read
                project = self.projects[project_id].copy()
                
                # Directly update status to avoid deadlock
                if project_id in self.processes:
                    process = self.processes[project_id]
                    if process.poll() is None:
                        project['status'] = 'running'
                    else:
                        project['status'] = 'stopped'
                elif 'pid' in project:
                    pid = project['pid']
                    if psutil.pid_exists(pid):
                        project['status'] = 'running'
                    else:
                        project['status'] = 'stopped'
                else:
                    project['status'] = 'stopped'
                
                return project
            return None
    
    def get_all_projects(self):
        """Get all projects."""
        with self.lock:
            # Create a copy of projects to avoid modification issues
            projects = []
            for project_id, project in self.projects.items():
                # Create a copy of the project
                project_copy = project.copy()
                
                # Directly update status to avoid calling update_status which could cause deadlocks
                if project_id in self.processes:
                    process = self.processes[project_id]
                    if process.poll() is None:
                        project_copy['status'] = 'running'
                    else:
                        project_copy['status'] = 'stopped'
                elif 'pid' in project:
                    pid = project['pid']
                    if psutil.pid_exists(pid):
                        project_copy['status'] = 'running'
                    else:
                        project_copy['status'] = 'stopped'
                else:
                    project_copy['status'] = 'stopped'
                
                projects.append(project_copy)
                
            return projects
    
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
                # Check status directly without calling update_status
                if project_id in self.processes:
                    process = self.processes[project_id]
                    if process and process.poll() is None:
                        return 'running'
                    else:
                        return 'stopped'
                elif 'pid' in self.projects[project_id]:
                    pid = self.projects[project_id]['pid']
                    if psutil.pid_exists(pid):
                        try:
                            process = psutil.Process(pid)
                            if 'python' in process.name().lower():
                                return 'running'
                        except:
                            pass
                return 'stopped'
            return 'unknown'
    
    def get_project_files(self, project_id):
        """Get important files for a project."""
        if project_id not in self.projects:
            return {'success': False, 'message': 'Project not found'}
        
        project = self.projects[project_id]
        path = project['path']
        
        # File categories to search for
        file_categories = {
            'documentation': ['README.md', 'README.txt', 'CHANGELOG.md', 'CONTRIBUTING.md', 'docs/index.md'],
            'configuration': ['config.yaml', 'config.yml', 'settings.ini', '.env.example', 'pyproject.toml', 'setup.py'],
            'dependencies': ['requirements.txt', 'Pipfile', 'poetry.lock', 'package.json']
        }
        
        result = {
            'success': True,
            'files': {}
        }
        
        # Check for files in each category
        for category, file_list in file_categories.items():
            result['files'][category] = []
            
            for file_name in file_list:
                file_path = os.path.join(path, file_name)
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    # Get file stats
                    stats = os.stat(file_path)
                    
                    file_info = {
                        'name': file_name,
                        'path': file_path,
                        'size': stats.st_size,
                        'modified': time.ctime(stats.st_mtime)
                    }
                    
                    # Try to determine if it's a text file that can be displayed
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            preview = f.read(1000)  # Read first 1000 chars as preview
                            file_info['preview'] = preview
                            file_info['is_text'] = True
                    except UnicodeDecodeError:
                        # Not a text file or not UTF-8 encoded
                        file_info['is_text'] = False
                    except Exception as e:
                        logger.error(f"Error reading file {file_path}: {e}")
                        file_info['is_text'] = False
                    
                    result['files'][category].append(file_info)
        
        return result
    
    def get_file_content(self, project_id, file_path):
        """Get the content of a specific file."""
        if project_id not in self.projects:
            return {'success': False, 'message': 'Project not found'}
        
        project = self.projects[project_id]
        project_path = project['path']
        
        # Ensure the file is within the project directory (security check)
        if not os.path.abspath(file_path).startswith(os.path.abspath(project_path)):
            return {'success': False, 'message': 'File path is outside project directory'}
        
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            return {'success': False, 'message': 'File not found'}
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return {'success': True, 'content': content}
        except UnicodeDecodeError:
            return {'success': False, 'message': 'File is not a text file or not UTF-8 encoded'}
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return {'success': False, 'message': f'Error reading file: {str(e)}'}
    
    def check_dependencies(self, project_id):
        """Check and return the dependencies of a project."""
        if project_id not in self.projects:
            return {'found': False, 'message': 'Project not found'}
        
        project = self.projects[project_id]
        path = project['path']
        
        # Check for requirements.txt
        req_file = os.path.join(path, 'requirements.txt')
        if not os.path.exists(req_file):
            return {'found': False, 'message': 'No requirements.txt found'}
        
        # Read requirements
        with open(req_file, 'r') as f:
            requirements = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        
        return {'found': True, 'requirements': requirements}
    
    def install_dependencies(self, project_id):
        """Install dependencies for a project."""
        if project_id not in self.projects:
            return {'success': False, 'message': 'Project not found'}
        
        deps = self.check_dependencies(project_id)
        if not deps['found']:
            return {'success': False, 'message': deps['message']}
        
        project = self.projects[project_id]
        path = project['path']
        
        # Check for virtual environment
        venv_path = os.path.join(path, 'venv')
        venv_bin = os.path.join(venv_path, 'bin', 'pip')
        
        if os.path.exists(venv_bin):
            # Use venv pip
            pip_path = venv_bin
        else:
            # Use system pip
            pip_path = 'pip'
        
        try:
            # Install requirements
            process = subprocess.Popen(
                [pip_path, 'install', '-r', os.path.join(path, 'requirements.txt')],
                cwd=path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            # Capture output
            output = []
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    output.append(line.strip())
                    if process.poll() is not None:
                        break
            
            # Get remaining output
            remaining_output, _ = process.communicate()
            if remaining_output:
                output.extend(remaining_output.splitlines())
            
            if process.returncode == 0:
                return {'success': True, 'message': 'Dependencies installed successfully', 'output': output}
            else:
                return {'success': False, 'message': 'Error installing dependencies', 'output': output}
        
        except Exception as e:
            logger.error(f"Error installing dependencies: {e}")
            return {'success': False, 'message': f'Error: {str(e)}'}
    
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
