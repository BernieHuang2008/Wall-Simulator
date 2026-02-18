from flask import Flask, render_template, request, jsonify
from manager import TestManager
import os

app = Flask(__name__)

# Assuming launcher is running in the 'launcher' directory, so parent is project root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
manager = TestManager(BASE_DIR)

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
