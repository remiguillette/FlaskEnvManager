import os
import logging
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from project_manager import ProjectManager

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "devkey-replace-in-production")

# Initialize project manager
project_manager = ProjectManager()

@app.route('/')
def index():
    """Redirect to the dashboard page."""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    """Display the main dashboard page."""
    projects = project_manager.get_all_projects()
    return render_template('dashboard.html', projects=projects)

@app.route('/project/add', methods=['GET', 'POST'])
def add_project():
    """Add a new project to the dashboard."""
    if request.method == 'POST':
        name = request.form.get('name')
        path = request.form.get('path')
        entry_file = request.form.get('entry_file', 'main.py')
        port = request.form.get('port', 5000)
        
        # Validate inputs
        if not name or not path:
            flash('Project name and path are required!', 'danger')
            return redirect(url_for('add_project'))
        
        # Check if path exists
        if not os.path.exists(path):
            flash(f'The path {path} does not exist!', 'danger')
            return redirect(url_for('add_project'))
            
        # Add the project
        success = project_manager.add_project(name, path, entry_file, port)
        
        if success:
            flash(f'Project {name} added successfully!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash(f'Failed to add project {name}!', 'danger')
            return redirect(url_for('add_project'))
            
    return render_template('add_project.html')

@app.route('/project/<project_id>')
def project_details(project_id):
    """Display details for a specific project."""
    project = project_manager.get_project(project_id)
    if not project:
        flash('Project not found!', 'danger')
        return redirect(url_for('dashboard'))
        
    return render_template('project_details.html', project=project)

@app.route('/api/projects')
def api_projects():
    """API endpoint to get all projects and their status."""
    projects = project_manager.get_all_projects()
    return jsonify(projects)

@app.route('/api/project/<project_id>/start', methods=['POST'])
def api_start_project(project_id):
    """API endpoint to start a project."""
    try:
        result = project_manager.start_project(project_id)
        return jsonify({"success": result, "message": "Project started successfully" if result else "Failed to start project"})
    except Exception as e:
        logger.error(f"Error starting project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/stop', methods=['POST'])
def api_stop_project(project_id):
    """API endpoint to stop a project."""
    try:
        result = project_manager.stop_project(project_id)
        return jsonify({"success": result, "message": "Project stopped successfully" if result else "Failed to stop project"})
    except Exception as e:
        logger.error(f"Error stopping project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/logs')
def api_project_logs(project_id):
    """API endpoint to get the logs for a project."""
    try:
        logs = project_manager.get_project_logs(project_id)
        return jsonify({"success": True, "logs": logs})
    except Exception as e:
        logger.error(f"Error getting logs for project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/status')
def api_project_status(project_id):
    """API endpoint to get the status of a project."""
    try:
        status = project_manager.get_project_status(project_id)
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error getting status for project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/remove', methods=['POST'])
def api_remove_project(project_id):
    """API endpoint to remove a project."""
    try:
        result = project_manager.remove_project(project_id)
        return jsonify({"success": result, "message": "Project removed successfully" if result else "Failed to remove project"})
    except Exception as e:
        logger.error(f"Error removing project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors."""
    return render_template('base.html', error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('base.html', error="Internal server error"), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
