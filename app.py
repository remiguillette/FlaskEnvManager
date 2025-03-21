import os
import logging
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, g, session
from flask_babel import Babel, gettext as _
from project_manager import ProjectManager

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Create the Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "devkey-replace-in-production")

# Initialize project manager
project_manager = ProjectManager()

# Configure Babel
app.config['BABEL_DEFAULT_LOCALE'] = 'en'
app.config['BABEL_SUPPORTED_LOCALES'] = ['en', 'fr']

# Define locale selector function
def get_locale():
    """
    Select the best language based on user preference and browser settings
    """
    # Check if the user has set a language preference in the session
    if 'lang_code' in session:
        return session['lang_code']
    
    # Otherwise, try to detect from the browser's accept-language header
    return request.accept_languages.best_match(app.config['BABEL_SUPPORTED_LOCALES'])

# Initialize Flask-Babel with the locale selector
babel = Babel(app, locale_selector=get_locale)

@app.before_request
def before_request():
    """
    Set the language for the current request
    """
    g.lang_code = get_locale()

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
        
        # Validate port
        try:
            port = int(port)
            if port < 1024 or port > 65535:
                flash(f'Port must be between 1024 and 65535!', 'danger')
                return redirect(url_for('add_project'))
        except ValueError:
            flash(f'Port must be a valid number!', 'danger')
            return redirect(url_for('add_project'))
        
        # Check for port conflicts with existing projects
        projects = project_manager.get_all_projects()
        for project in projects:
            if int(project['port']) == port:
                flash(f'Port {port} is already in use by project "{project["name"]}"!', 'danger')
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
    try:
        projects = project_manager.get_all_projects()
        return jsonify(projects)
    except Exception as e:
        logger.error(f"Error getting projects: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

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

@app.route('/api/project/<project_id>/files')
def api_project_files(project_id):
    """API endpoint to get important files for a project."""
    try:
        result = project_manager.get_project_files(project_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting files for project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/file')
def api_file_content(project_id):
    """API endpoint to get the content of a specific file."""
    try:
        file_path = request.args.get('path')
        if not file_path:
            return jsonify({"success": False, "message": "No file path provided"}), 400
        
        result = project_manager.get_file_content(project_id, file_path)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting file content for project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/dependencies')
def api_project_dependencies(project_id):
    """API endpoint to get the dependencies of a project."""
    try:
        result = project_manager.check_dependencies(project_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error checking dependencies for project {project_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/project/<project_id>/install-dependencies', methods=['POST'])
def api_install_dependencies(project_id):
    """API endpoint to install dependencies for a project."""
    try:
        result = project_manager.install_dependencies(project_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error installing dependencies for project {project_id}: {str(e)}")
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

@app.route('/set-language/<lang>')
def set_language(lang):
    """Set the language for the user session."""
    # Validate the language
    if lang in app.config['BABEL_SUPPORTED_LOCALES']:
        session['lang_code'] = lang
        flash(_('Language changed successfully!'), 'success')
    else:
        flash(_('Invalid language selection!'), 'danger')
    
    # Redirect to the previous page or dashboard
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/help')
def help_page():
    """Display the help and documentation page."""
    return render_template('help.html')

@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors."""
    return render_template('base.html', error=_("Internal server error")), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
