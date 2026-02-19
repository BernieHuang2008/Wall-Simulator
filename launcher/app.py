from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from manager import TestManager
import os
import threading
import select
import time

app = Flask(__name__)
socketio = SocketIO(app, async_mode='eventlet') # Use eventlet for async support

# Assuming launcher is running in the 'launcher' directory, so parent is project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
manager = TestManager(BASE_DIR)

# Store terminal threads to manage them
terminal_sessions = {}

@app.route('/')
def index():
    # List available tests
    testee_dir = os.path.join(BASE_DIR, 'testee')
    tests = [d for d in os.listdir(testee_dir) if os.path.isdir(os.path.join(testee_dir, d))]
    return render_template('index.html', tests=tests)

@app.route('/start', methods=['POST'])
def start_test():
    test_name = request.form.get('test_name')
    if not test_name:
        return jsonify({'error': 'No test name provided'}), 400
    try:
        result = manager.start_test(test_name)
        return jsonify({'status': 'started', 'details': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stop', methods=['POST'])
def stop_test():
    manager.stop_test()
    return jsonify({'status': 'stopped'})

@app.route('/status')
def status():
    return jsonify(manager.get_status())

@app.route('/exec', methods=['POST'])
def execute_cmd():
    role = request.json.get('role')
    cmd = request.json.get('cmd')
    exit_code, output = manager.execute_command(role, cmd)
    return jsonify({'exit_code': exit_code, 'output': output.decode('utf-8')})

# --- Terminal Handling ---

def read_from_socket(socket_obj, role, sid):
    """Read output from container socket and emit to client."""
    try:
        while True:
            # Check if socket_obj is a true socket or file-like
            if hasattr(socket_obj, 'recv'):
                # Use select for true sockets
                ready = select.select([socket_obj], [], [], 0.1)
                if ready[0]:
                    data = socket_obj.recv(4096)
                    if not data:
                        break
                    socketio.emit('terminal_output', {'role': role, 'data': data.decode('utf-8', errors='replace')}, room=sid)
                else:
                    socketio.sleep(0.01)
            else:
                # Assume file-like (read method)
                # Note: read() might block if not careful, but eventlet monkey-patching helps
                # Or use a smaller read size
                # Some file-like objects (SocketIO) from docker are tricky with read() blocking
                # We can try reading small chunks or use _sock if available for select
                if hasattr(socket_obj, '_sock'):
                     ready = select.select([socket_obj._sock], [], [], 0.1)
                     if not ready[0]:
                         socketio.sleep(0.01)
                         continue
                
                data = socket_obj.read(4096)
                if not data:
                    break
                socketio.emit('terminal_output', {'role': role, 'data': data.decode('utf-8', errors='replace')}, room=sid)
                socketio.sleep(0.01)
            
    except Exception as e:
        print(f"[{role}] Socket read error: {e}")
    finally:
        try:
            socket_obj.close()
        except:
            pass
        print(f"[{role}] Terminal session closed for {sid}.")

@socketio.on('connect_terminal')
def handle_connect_terminal(data):
    role = data.get('role')
    rows = data.get('rows', 24)
    cols = data.get('cols', 80)
    sid = request.sid
    
    if role not in manager.containers:
        emit('terminal_error', {'role': role, 'message': 'Container not running'})
        return

    container = manager.containers[role]
    try:
        # Create exec instance with TTY
        exec_id = container.client.api.exec_create(
            container.id, 
            "/bin/bash", 
            stdin=True, 
            tty=True
        )['Id']
        
        # Start exec instance and get socket
        # Note: socket=True returns the raw socket object
        sock = container.client.api.exec_start(exec_id, socket=True, tty=True)
        # print(f"DEBUG: sock type: {type(sock)}, dir: {dir(sock)}")

        # Configure socket to be non-blocking if it's a real socket
        if hasattr(sock, 'setblocking'):
            sock.setblocking(0)
        
        # Resize right away
        container.client.api.exec_resize(exec_id, height=rows, width=cols)
        
        # Store session
        if sid not in terminal_sessions:
            terminal_sessions[sid] = {}
        
        terminal_sessions[sid][role] = {'socket': sock, 'exec_id': exec_id}

        # Start background thread to read output
        socketio.start_background_task(read_from_socket, sock, role, sid)
        
        emit('terminal_connected', {'role': role})
        
    except Exception as e:
        emit('terminal_error', {'role': role, 'message': str(e)})

@socketio.on('terminal_input')
def handle_terminal_input(data):
    role = data.get('role')
    input_data = data.get('data')
    sid = request.sid
    
    if sid in terminal_sessions and role in terminal_sessions[sid]:
        sock = terminal_sessions[sid][role]['socket']
        try:
            # Check if it has a raw socket attribute (common in some wrappers)
            if hasattr(sock, '_sock'):
                sock._sock.send(input_data.encode('utf-8'))
            elif hasattr(sock, 'send'):
                sock.send(input_data.encode('utf-8'))
            else:
                # If it's a file-like object
                sock.write(input_data.encode('utf-8'))
                sock.flush()
        except Exception as e:
            # print(f"Input error: {e}, type: {type(sock)}")
            socketio.emit('terminal_error', {'role': role, 'message': str(e)}, room=sid)

@socketio.on('terminal_resize')
def handle_terminal_resize(data):
    role = data.get('role')
    rows = data.get('rows')
    cols = data.get('cols')
    sid = request.sid
    
    if sid in terminal_sessions and role in terminal_sessions[sid]:
        exec_id = terminal_sessions[sid][role]['exec_id']
        container = manager.containers[role]
        try:
            container.client.api.exec_resize(exec_id, height=rows, width=cols)
        except Exception as e:
            print(f"Resize error: {e}")

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in terminal_sessions:
        for role, session in terminal_sessions[sid].items():
            try:
                session['socket'].close()
            except:
                pass
        del terminal_sessions[sid]

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
