import os
from flask import Flask, abort, render_template, render_template_string, send_file, request, jsonify
from threading import Lock, local
from concurrent.futures import ThreadPoolExecutor
import re
import queue
from getOrdContent import process_tx
from bitcoinrpc.authproxy import JSONRPCException

app = Flask(__name__)

# Ensure content directory exists
content_dir = './content'
if not os.path.exists(content_dir):
    os.makedirs(content_dir)

# Queue to manage tasks
task_queue = queue.Queue()
# Thread pool to handle concurrent processing
thread_pool = ThreadPoolExecutor(max_workers=4)
# Thread-local storage for RPC connections
thread_local = local()

# Shared flag and lock to indicate processing state
processing_flag = False
processing_lock = Lock()

def get_rpc_connection():
    if not hasattr(thread_local, "rpc_connection"):
        from getOrdContent import rpc_connection
        thread_local.rpc_connection = rpc_connection
    return thread_local.rpc_connection

def is_hexadecimal(s):
    """Check if the string s is a valid hexadecimal string."""
    return re.fullmatch(r'^[0-9a-fA-F]+$', s) is not None

def process_task(genesis_txid, depth=1000):
    global processing_flag
    with processing_lock:
        processing_flag = True
    try:
        print(f"Starting processing for {genesis_txid}")
        process_tx(genesis_txid, depth)
    except JSONRPCException as e:
        print(f"JSONRPCException: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        with processing_lock:
            processing_flag = False
        print(f"Finished processing for {genesis_txid}")
        task_queue.task_done()

@app.route('/')
def landing_page():
    return render_template('landing_page.html')

@app.route('/content/<file_id>i0')
def serve_content(file_id):
    global processing_flag
    with processing_lock:
        if processing_flag:
            return jsonify({"message": "Server is busy processing ordinal. Please try again later."}), 503

    filename = f"{file_id}"
    file_path = next((os.path.join(content_dir, file) for file in os.listdir(content_dir) if file.startswith(filename)), None)
    
    if file_path and os.path.isfile(file_path):
        print(f"File found: {file_path}")

        if file_path.endswith('.html'):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                return render_template_string(html_content)
            except Exception as e:
                print(f"Error reading HTML file: {e}")
                abort(500)
        elif file_path.endswith('.webp'):
            return send_file(file_path, mimetype='image/webp')
        else:
            return send_file(file_path)
    else:
        print(f"File not found: {filename} in {content_dir}")
        abort(404)

@app.errorhandler(404)
def not_found_error(error):
    global processing_flag
    request_path = request.path.split('/')[-1]
    genesis_txid = request_path[:-2] if request_path.endswith('i0') else None

    if not genesis_txid or not is_hexadecimal(genesis_txid):
        print(f"Invalid genesis_txid: {request_path}")
        return "Invalid transaction ID", 400

    with processing_lock:
        if not processing_flag:
            thread_pool.submit(process_task, genesis_txid, 1000)

    return "Processing ordinal, click refresh when complete", 404

@app.route('/favicon.ico')
def favicon():
    return send_file('favicon.ico', mimetype='image/x-icon')

if __name__ == '__main__':
    app.run(debug=True)
