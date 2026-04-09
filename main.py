# app.py - Ultimate Bot Hosting Platform (Render?friendly)
import os
import sys
import time
import json
import threading
import subprocess
import shlex
import shutil
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, abort
)
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import logging

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)

app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production'),
    UPLOAD_FOLDER='uploads',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    ALLOWED_EXTENSIONS={'py', 'txt', 'json', 'env', 'yaml', 'yml', 'cfg', 'ini'},
    BOTS_FOLDER='bots',
    LOGS_FOLDER='logs'
)

# Create necessary directories
for folder in [app.config['UPLOAD_FOLDER'], app.config['BOTS_FOLDER'], app.config['LOGS_FOLDER']]:
    Path(folder).mkdir(exist_ok=True)

# Store running bot processes
running_bots = {}

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_python_executable():
    """Get the correct Python executable path (fix for Windows pythonw)."""
    if sys.platform == 'win32':
        pythonw_path = sys.executable
        if pythonw_path.endswith('pythonw.exe'):
            python_path = pythonw_path.replace('pythonw.exe', 'python.exe')
            if os.path.exists(python_path):
                return python_path
    return sys.executable

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_absolute_path(relative_path):
    return Path(__file__).parent.absolute() / relative_path

def run_bot_with_encoding_fix(bot_id, bot_path):
    """Run a bot and capture its output (existing function, unchanged)."""
    log_path = get_absolute_path(app.config['LOGS_FOLDER']) / f"{bot_id}.log"
    python_executable = get_python_executable()

    log_path.parent.mkdir(exist_ok=True)

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUTF8'] = '1'

    with open(log_path, 'w', encoding='utf-8', errors='ignore') as log_file:
        log_file.write(f"[{datetime.now()}] Starting bot: {bot_id}\n")
        log_file.write(f"[{datetime.now()}] Python: {python_executable}\n")
        log_file.write(f"[{datetime.now()}] CWD: {bot_path}\n")
        log_file.flush()

        # Find main Python file
        python_files = [f for f in bot_path.iterdir() if f.is_file() and f.suffix == '.py']
        if not python_files:
            log_file.write(f"[{datetime.now()}] Error: No Python files found\n")
            return

        common_names = ['main.py', 'bot.py', 'app.py', 'run.py', 'start.py']
        main_script = None
        for name in common_names:
            match = next((f for f in python_files if f.name.lower() == name), None)
            if match:
                main_script = match
                break
        if not main_script:
            main_script = python_files[0]

        log_file.write(f"[{datetime.now()}] Using script: {main_script.name}\n")

        # Install dependencies if requirements.txt exists
        requirements_file = bot_path / 'requirements.txt'
        if requirements_file.exists():
            try:
                log_file.write(f"[{datetime.now()}] Installing dependencies...\n")
                result = subprocess.run(
                    [python_executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='ignore',
                    cwd=str(bot_path),
                    env=env,
                    timeout=60
                )
                if result.returncode == 0:
                    log_file.write(f"[{datetime.now()}] Dependencies installed\n")
                else:
                    log_file.write(f"[{datetime.now()}] Failed to install deps\n{result.stderr}\n")
                log_file.flush()
            except subprocess.TimeoutExpired:
                log_file.write(f"[{datetime.now()}] Dependency installation timed out\n")
            except Exception as e:
                log_file.write(f"[{datetime.now()}] Error installing deps: {str(e)}\n")

        # Run the bot
        try:
            log_file.write(f"[{datetime.now()}] Running: {python_executable} {main_script.name}\n")
            log_file.flush()

            process = subprocess.Popen(
                [python_executable, str(main_script.name)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore',
                cwd=str(bot_path),
                env=env,
                bufsize=1
            )

            running_bots[bot_id] = {
                'process': process,
                'start_time': datetime.now(),
                'log_path': str(log_path)
            }

            # Read output in real?time
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_file.write(f"[{timestamp}] {output}")
                    log_file.flush()

            return_code = process.poll()
            log_file.write(f"[{datetime.now()}] Bot ended with code: {return_code}\n")

        except Exception as e:
            log_file.write(f"[{datetime.now()}] Error running bot: {str(e)}\n")
        finally:
            running_bots.pop(bot_id, None)

# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route('/')
def index():
    """Dashboard (unchanged)."""
    bots = []
    bots_folder = get_absolute_path(app.config['BOTS_FOLDER'])
    if bots_folder.exists():
        for bot_dir in bots_folder.iterdir():
            if bot_dir.is_dir():
                bot_info = {
                    'id': bot_dir.name,
                    'name': bot_dir.name,
                    'status': 'running' if bot_dir.name in running_bots else 'stopped',
                    'created_at': datetime.fromtimestamp(bot_dir.stat().st_ctime).strftime('%Y-%m-%d %H:%M'),
                    'files': [f.name for f in bot_dir.iterdir() if f.is_file()],
                    'has_py': any(f.suffix == '.py' for f in bot_dir.iterdir() if f.is_file())
                }
                bots.append(bot_info)
    return render_template('index.html', bots=bots, python_executable=get_python_executable())

@app.route('/upload', methods=['GET', 'POST'])
def upload_bot():
    """Upload bot files (unchanged)."""
    if request.method == 'POST':
        if 'files[]' not in request.files:
            return jsonify({'error': 'No files uploaded'}), 400
        files = request.files.getlist('files[]')
        bot_name = request.form.get('bot_name', '').strip()
        if not bot_name:
            bot_name = f"bot_{int(time.time())}"
        bot_id = secure_filename(bot_name.replace(' ', '_'))
        bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
        bot_path.mkdir(exist_ok=True)
        uploaded_files = []
        for file in files:
            if file and (allowed_file(file.filename) or file.filename == 'requirements.txt'):
                filename = secure_filename(file.filename)
                file_path = bot_path / filename
                file.save(file_path)
                uploaded_files.append(filename)
        return jsonify({'success': True, 'bot_id': bot_id,
                        'message': f'Uploaded {len(uploaded_files)} files', 'files': uploaded_files})
    return render_template('upload.html')

@app.route('/bot/<bot_id>/start', methods=['POST'])
def start_bot(bot_id):
    """Start a bot (unchanged)."""
    if bot_id in running_bots:
        return jsonify({'error': 'Bot is already running'}), 400
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404
    if not any(f.suffix == '.py' for f in bot_path.iterdir() if f.is_file()):
        return jsonify({'error': 'No Python files found'}), 400
    threading.Thread(target=run_bot_with_encoding_fix, args=(bot_id, bot_path), daemon=True).start()
    time.sleep(0.5)
    return jsonify({'success': True, 'message': f'Bot {bot_id} started'})

@app.route('/bot/<bot_id>/stop', methods=['POST'])
def stop_bot(bot_id):
    """Stop a running bot (unchanged)."""
    if bot_id not in running_bots:
        return jsonify({'error': 'Bot is not running'}), 400
    process = running_bots[bot_id]['process']
    try:
        process.terminate()
        process.wait(timeout=5)
    except:
        try:
            process.kill()
            process.wait()
        except:
            pass
    running_bots.pop(bot_id, None)
    return jsonify({'success': True, 'message': f'Bot {bot_id} stopped'})

@app.route('/bot/<bot_id>/logs')
def get_logs(bot_id):
    """Get bot logs (unchanged)."""
    log_path = get_absolute_path(app.config['LOGS_FOLDER']) / f"{bot_id}.log"
    if not log_path.exists():
        return jsonify({'logs': [], 'status': 'no_logs'})
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            logs = f.read().split('\n')[-100:]
    except:
        logs = []
    status = 'running' if bot_id in running_bots else 'stopped'
    return jsonify({'logs': logs, 'status': status, 'bot_id': bot_id})

@app.route('/bot/<bot_id>/files')
def list_bot_files(bot_id):
    """List bot files (unchanged)."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404
    files = []
    for file in bot_path.iterdir():
        if file.is_file():
            files.append({'name': file.name, 'size': file.stat().st_size, 'is_python': file.suffix == '.py'})
    return jsonify({'files': files})

@app.route('/bot/<bot_id>/view/<filename>')
def view_bot_file(bot_id, filename):
    """View file content (unchanged)."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    file_path = bot_path / secure_filename(filename)
    if not file_path.exists() or not file_path.is_file():
        return jsonify({'error': 'File not found'}), 404
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return jsonify({'filename': filename, 'content': content, 'size': file_path.stat().st_size})
    except Exception as e:
        return jsonify({'error': f'Cannot read file: {str(e)}'}), 500

@app.route('/bot/<bot_id>/delete', methods=['POST'])
def delete_bot(bot_id):
    """Delete a bot (unchanged)."""
    if bot_id in running_bots:
        return jsonify({'error': 'Stop bot before deleting'}), 400
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    log_path = get_absolute_path(app.config['LOGS_FOLDER']) / f"{bot_id}.log"
    if bot_path.exists():
        shutil.rmtree(bot_path)
    if log_path.exists():
        try:
            log_path.unlink()
        except:
            pass
    return jsonify({'success': True, 'message': f'Bot {bot_id} deleted'})

@app.route('/bot/<bot_id>/status')
def bot_status(bot_id):
    """Get current status and basic info."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404
    files = [f.name for f in bot_path.iterdir() if f.is_file()]
    return jsonify({
        'status': 'running' if bot_id in running_bots else 'stopped',
        'files': files,
        'bot_id': bot_id
    })

# ----------------------------------------------------------------------
# NEW FEATURES
# ----------------------------------------------------------------------

@app.route('/bot/<bot_id>/file/<filename>', methods=['PUT'])
def update_bot_file(bot_id, filename):
    """Update file content (edit/save)."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    file_path = bot_path / secure_filename(filename)
    if not file_path.exists() or not file_path.is_file():
        return jsonify({'error': 'File not found'}), 404

    data = request.get_json()
    if not data or 'content' not in data:
        return jsonify({'error': 'No content provided'}), 400

    try:
        # Write with UTF-8, preserve original line endings? We'll just write.
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data['content'])
        return jsonify({'success': True, 'message': 'File saved'})
    except Exception as e:
        return jsonify({'error': f'Failed to save: {str(e)}'}), 500

@app.route('/bot/<bot_id>/execute', methods=['POST'])
def execute_code(bot_id):
    """Run arbitrary Python code inside the bot's directory."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404

    data = request.get_json()
    if not data or 'code' not in data:
        return jsonify({'error': 'No code provided'}), 400

    code = data['code']
    # Use the bot's Python (same interpreter) to run the snippet
    python_exec = get_python_executable()

    # We'll feed the code via stdin to avoid writing temporary files
    try:
        process = subprocess.run(
            [python_exec, '-c', code],
            cwd=str(bot_path),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=30  # prevent runaway code
        )
        return jsonify({
            'stdout': process.stdout,
            'stderr': process.stderr,
            'returncode': process.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Execution timed out (30s limit)'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bot/<bot_id>/terminal', methods=['POST'])
def run_command(bot_id):
    """Run a shell command inside the bot's directory."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404

    data = request.get_json()
    if not data or 'command' not in data:
        return jsonify({'error': 'No command provided'}), 400

    command = data['command'].strip()
    if not command:
        return jsonify({'error': 'Empty command'}), 400

    # Security: prevent dangerous commands (optional)
    # You could whitelist basic commands, but for a personal tool it's okay.
    # We'll run without shell=True to avoid injection, but user can still do harmful things.
    # Consider adding a warning.

    try:
        # Use shlex.split to safely split the command into args
        args = shlex.split(command)
        process = subprocess.run(
            args,
            cwd=str(bot_path),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=30
        )
        return jsonify({
            'stdout': process.stdout,
            'stderr': process.stderr,
            'returncode': process.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Command timed out (30s limit)'}), 408
    except FileNotFoundError:
        return jsonify({'error': 'Command not found'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/bot/<bot_id>/install', methods=['POST'])
def install_package(bot_id):
    """Install a Python package via pip."""
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return jsonify({'error': 'Bot not found'}), 404

    data = request.get_json()
    if not data or 'package' not in data:
        return jsonify({'error': 'No package specified'}), 400

    package = data['package'].strip()
    if not package:
        return jsonify({'error': 'Empty package name'}), 400

    python_exec = get_python_executable()
    try:
        process = subprocess.run(
            [python_exec, '-m', 'pip', 'install', package],
            cwd=str(bot_path),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=60
        )
        return jsonify({
            'stdout': process.stdout,
            'stderr': process.stderr,
            'returncode': process.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Installation timed out'}), 408
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'running_bots': len(running_bots),
        'python': sys.version,
        'platform': sys.platform
    })

@app.route('/bot/<bot_id>/manage')
def manage_bot(bot_id):
    bot_path = get_absolute_path(app.config['BOTS_FOLDER']) / bot_id
    if not bot_path.exists():
        return "Bot not found", 404
    python_files = [f.name for f in bot_path.iterdir() if f.is_file() and f.suffix == '.py']
    return render_template('manage_bot.html',
                          bot_id=bot_id,
                          has_python_files=len(python_files) > 0,
                          python_files=python_files)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    print("?? Ultimate Bot Hosting Platform")
    print(f"?? Bots folder: {get_absolute_path(app.config['BOTS_FOLDER'])}")
    print(f"?? Python: {get_python_executable()}")
    app.run(host=host, port=port, debug=debug)