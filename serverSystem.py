from gevent import monkey
monkey.patch_all()
from gevent import spawn
from gevent.pywsgi import WSGIServer

import datetime
import sqlite3
import threading
import time
import ctypes
import os
import sys
import queue
import json
import hmac
from typing import Final
from enum import Enum
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv


# ============================================================
#  Configuration & globals
# ============================================================

class Locale(Enum):
    InTransit = 0
    JurassicPark = 1
    JIT = 2
    MAL = 3

    def toString(self):
        if self.value == 0:
            return "In Transit"
        elif self.value == 1:
            return "Jurassic Park"
        elif self.value == 2:
            return "JIT"
        elif self.value == 3:
            return "MAL"


testing = True

# Two separate apps so each listener exposes ONLY its own routes:
#   scanner_app   -> HTTP  (plaintext) for the NFC scanners
#   dashboard_app -> HTTPS (TLS)       for the browser dashboard + static files
# A scanner route therefore 404s on the HTTPS port and vice versa.
scanner_app = Flask(__name__)
dashboard_app = Flask(__name__)

load_dotenv()

DB_FILE: Final = "trackingFile.db"
PORT: Final = 5000        # HTTPS - dashboard
HTTP_PORT: Final = 5001   # HTTP  - scanners

MAX_SSE_SUBS: Final = 50  # cap concurrent dashboard SSE connections (anti-DoS)

# Cap request body size on both listeners so a huge POST can't exhaust memory.
scanner_app.config['MAX_CONTENT_LENGTH']   = 64 * 1024   # 64 KB
dashboard_app.config['MAX_CONTENT_LENGTH'] = 64 * 1024

# Per-IP rate limiting. In-memory storage is fine for this single gevent process;
# limits are checked in a before_request, so floods are throttled before auth runs.
scanner_limiter = Limiter(get_remote_address, app=scanner_app,
                          default_limits=["120 per minute"], storage_uri="memory://")
dashboard_limiter = Limiter(get_remote_address, app=dashboard_app,
                            default_limits=["300 per minute"], storage_uri="memory://")

sseSubs = []
sseLock = threading.Lock()

API_KEY: Final = os.environ.get('NFC_API_KEY')

if not API_KEY:
    print("ERROR: NFC_API_KEY not set. Please check .env file.")
    sys.exit(1)


# ============================================================
#  Decorators & middleware
# ============================================================

def require_api_key(f):
    """Decorator that rejects any request without a valid X-API-Key header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        provided = request.headers.get('X-API-Key')
        if not provided:
            return jsonify({
                'status': 'error',
                'message': 'Missing X-API-Key header'
            }), 401
        if not hmac.compare_digest(provided, API_KEY):
            print(f"  [AUTH] Rejected request from {request.remote_addr} - bad API key")
            return jsonify({
                'status': 'error',
                'message': 'Invalid API key'
            }), 401
        return f(*args, **kwargs)
    return decorated


def log_request(response):
    # Skip the SSE stream (it's long-lived and has no normal body)
    if request.path == '/api/stream':
        return response

    ts = datetime.datetime.now().strftime('%H:%M:%S')

    # Try to extract the response body as text
    body_text = ""
    try:
        # Only log JSON responses (skip HTML pages, static files, etc.)
        if response.content_type and 'application/json' in response.content_type:
            raw = response.get_data(as_text=True)
            body_text = f"  {raw}"
    except Exception:
        body_text = ""

    print(f"[{ts}] {request.remote_addr:15s} "
          f"{request.method:4s} {request.path:25s} -> {response.status_code}{body_text}")

    return response

# Same logger runs on both listeners
scanner_app.after_request(log_request)
dashboard_app.after_request(log_request)


# ============================================================
#  Database
# ============================================================

def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')

    # State Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY,
            nfc_uid TEXT UNIQUE,
            name TEXT,
            contents TEXT,
            date_usage TEXT,
            current_location TEXT
        )
    ''')

    # Log Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            cart_id INTEGER,
            old_location TEXT,
            new_location TEXT,
            timestamp TEXT
        )
    ''')

    # Initialize the 9 carts
    cursor.execute("SELECT COUNT(*) FROM carts")
    if cursor.fetchone()[0] == 0:
        print("Initializing the 9 carts...")
        imagCarts = [
            (0, '0', 'Condor', 'Alpha', datetime.date(2026, 6, 5).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (1, '1', 'Albatross', 'Beta', datetime.date(2026, 6, 6).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (2, '2', 'Eagle', 'Gamma', datetime.date(2026, 6, 7).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (3, '3', 'Raven', 'Delta', datetime.date(2026, 6, 8).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (4, '4', 'Pelican', 'Epsilon', datetime.date(2026, 6, 9).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (5, '5', 'Falcon', 'Zeta', datetime.date(2026, 6, 10).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (6, '6', 'Sparrow', 'Eta', datetime.date(2026, 6, 11).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (7, '7', 'Hummingbird', 'Theta', datetime.date(2026, 6, 12).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (8, '8', 'Owl', 'Iota', datetime.date(2026, 6, 13).strftime("%m-%d-%Y"), Locale.InTransit.toString())
        ]
        cursor.executemany('INSERT INTO carts VALUES (?, ?, ?, ?, ?, ?)', imagCarts)
        conn.commit()

    # One-time migration: convert old "In Transit" entries to "MAL"
    cursor.execute("UPDATE carts   SET current_location = 'MAL' WHERE current_location = 'In Transit'")
    cursor.execute("UPDATE history SET old_location     = 'MAL' WHERE old_location     = 'In Transit'")
    cursor.execute("UPDATE history SET new_location     = 'MAL' WHERE new_location     = 'In Transit'")
    if cursor.rowcount > 0:
        print(f"Migrated old 'In Transit' entries to 'MAL'.")
    conn.commit()
    conn.close()


# ============================================================
#  Shared state / SSE helpers
# ============================================================

def getFullState():
    # Build JSON for dashboards on connect and each change
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, contents, date_usage, current_location FROM carts ORDER BY id
    ''')
    carts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return {
        'carts': carts,
        'server_time': datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
    }

def broadcastUpdate():
    # Broadcast current state to each dashboard
    payload = getFullState()
    with sseLock:
        dead = []
        for dash in sseSubs:
            try:
                dash.put_nowait(payload)
            except queue.Full:
                dead.append(dash)
        for dash in dead:
            sseSubs.remove(dash)


# ============================================================
#  Scanner routes (HTTP)
# ============================================================

@scanner_app.route('/scan', methods = ['POST'])
@scanner_limiter.limit("60 per minute")
@require_api_key
def processScan():
    data = request.json
    if not data:
        print('no body')
        return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

    nfcUid = data.get('uid')
    clientLocation = data.get('location') # In String form

    if nfcUid is None or clientLocation is None:
        print('missing uid or location')
        return jsonify({'status': 'error', 'message': 'Missing UID or location'}), 400

    validLocations = [loc.toString() for loc in Locale]
    if clientLocation not in validLocations:
        print('Invalid location')
        return jsonify({'status': 'error', 'message': f'Invalid location. Must be on of: {validLocations}'}), 400

    nfcUid = nfcUid.upper()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, current_location FROM carts WHERE nfc_uid = ?', (nfcUid,))
    cartData = cursor.fetchone()
    if not cartData:
        conn.close()
        print('unknown uid')
        return jsonify({'status': 'error', 'message': 'Unknown Tag UID', 'uid': nfcUid}), 400

    cartId, name, lastLocation = cartData # lastLocation in String form
    timeNow = datetime.datetime.now().strftime('%m-%d-%Y %H:%M:%S')

    locationChanged = lastLocation != clientLocation
    if locationChanged:
        # Check for move out of MAL to clear
        if lastLocation == Locale.MAL.toString():
            cursor.execute('UPDATE carts SET current_location = ?, contents = ?, date_usage = ? WHERE id = ?', (clientLocation, 'Empty', 'Return', cartId))
        else:
            cursor.execute('UPDATE carts SET current_location = ? WHERE id = ?', (clientLocation, cartId))
        cursor.execute('INSERT INTO history (cart_id, old_location, new_location, timestamp) VALUES (?, ?, ?, ?)', (cartId, lastLocation, clientLocation, timeNow))
        conn.commit()

        print(f"[UPDATE] ID {cartId} moved from {lastLocation} to {clientLocation} ({timeNow})")

    conn.close()
    if locationChanged:
        broadcastUpdate()

    return jsonify({'status': 'success', 'cartId': cartId, 'cartName': name, 'location': clientLocation})


@scanner_app.route('/enroll', methods=['POST'])
@scanner_limiter.limit("20 per minute")
@require_api_key
def enrollTag():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

    cartId = data.get('cartId')
    nfcUid = data.get('uid')

    if cartId is None or not nfcUid:
        return jsonify({'status': 'error',
                        'message': 'Missing cartId or uid'}), 400

    nfcUid = nfcUid.upper()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Make sure cart exists
    cursor.execute('SELECT name FROM carts WHERE id = ?', (cartId,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'status': 'error',
                        'message': f'No cart with id {cartId}'}), 404

    try:
        cursor.execute('UPDATE carts SET nfc_uid = ? WHERE id = ?',
                       (nfcUid, cartId))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'status': 'error',
                        'message': 'That UID is already assigned to another cart'}), 409

    conn.close()
    print(f"  [ENROLL] Cart #{cartId} ({row[0]}) -> UID {nfcUid}")
    broadcastUpdate()
    return jsonify({'status': 'success', 'cartId': cartId, 'uid': nfcUid})


# ============================================================
#  Dashboard routes (HTTPS)
# ============================================================

@dashboard_app.route('/')
def dashboard():
    return send_from_directory('static', 'dashboard.html')

@dashboard_app.route('/edit')
def edit_page():
    return send_from_directory('static', 'edit.html')

@dashboard_app.route('/api/carts', methods=['GET'])
@require_api_key
def apiCarts():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, nfc_uid, name, contents, date_usage, current_location
        FROM carts ORDER BY id
    ''')
    carts = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(carts)


@dashboard_app.route('/api/carts/<int:cart_id>', methods=['PATCH'])
@dashboard_limiter.limit("30 per minute")
@require_api_key
def updateCart(cart_id):
    """Edit a JP cart's contents and use-by date from the /edit page."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON body'}), 400

    contents = data.get('contents')
    dateUsage = data.get('date_usage')

    # Validate contents: must be a non-empty string
    if not isinstance(contents, str) or not contents.strip():
        return jsonify({'status': 'error', 'message': 'contents must be a non-empty string'}), 400
    contents = contents.strip()

    # Validate date: must match the MM-DD-YYYY format the dashboard parser expects
    if not isinstance(dateUsage, str):
        return jsonify({'status': 'error', 'message': 'date_usage is required'}), 400
    dateUsage = dateUsage.strip()
    try:
        datetime.datetime.strptime(dateUsage, '%m-%d-%Y')
    except ValueError:
        return jsonify({'status': 'error', 'message': 'date_usage must be MM-DD-YYYY'}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Confirm the cart exists and is currently in Jurassic Park (edit scope)
    cursor.execute('SELECT current_location FROM carts WHERE id = ?', (cart_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'status': 'error', 'message': f'No cart with id {cart_id}'}), 404
    if row[0] != Locale.JurassicPark.toString():
        conn.close()
        return jsonify({'status': 'error',
                        'message': 'Only carts in Jurassic Park can be edited here'}), 403

    cursor.execute('UPDATE carts SET contents = ?, date_usage = ? WHERE id = ?',
                   (contents, dateUsage, cart_id))
    conn.commit()
    conn.close()

    print(f"  [EDIT] Cart #{cart_id} -> contents={contents!r}, date_usage={dateUsage}")
    broadcastUpdate()
    return jsonify({'status': 'success', 'cartId': cart_id,
                    'contents': contents, 'date_usage': dateUsage})


@dashboard_app.route('/api/history', methods=['GET'])
@require_api_key
def apiHistory():
    limit = request.args.get('limit', default=50, type=int)
    limit = max(1, min(limit, 500))  # clamp

    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.log_id, h.cart_id, c.name AS cart_name,
               h.old_location, h.new_location, h.timestamp
        FROM history h
        LEFT JOIN carts c ON h.cart_id = c.id
        ORDER BY h.log_id DESC
        LIMIT ?
    ''', (limit,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)


@dashboard_app.route('/api/stream')
def event_stream():
    # Register this subscriber up front (in the route body, not inside gen()) so the
    # capacity check and the append happen atomically under the lock. Doing it in gen()
    # would defer registration until the response starts streaming, making the cap racy.
    q = queue.Queue(maxsize=10)
    with sseLock:
        if len(sseSubs) >= MAX_SSE_SUBS:
            return jsonify({'status': 'error',
                            'message': 'Too many dashboard connections'}), 503
        sseSubs.append(q)

    def gen():
        try:
            # Send initial state immediately on connect
            initial = getFullState()
            yield f"event: snapshot\ndata: {json.dumps(initial)}\n\n"

            while True:
                try:
                    data = q.get(timeout=30)
                except queue.Empty:
                    # Timed out waiting - send a heartbeat and loop again
                    yield ": heartbeat\n\n"
                    continue

                # We only reach here if q.get() actually returned data
                yield f"event: snapshot\ndata: {json.dumps(data)}\n\n"

        except GeneratorExit:
            # Client disconnected - clean exit
            pass
        finally:
            with sseLock:
                if q in sseSubs:
                    sseSubs.remove(q)

    return Response(
        gen(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )


# ============================================================
#  Health (both listeners)
# ============================================================

def health():
    return jsonify({
        'status': 'ok',
        'time': datetime.datetime.now().isoformat()
    })

# Health check available on both listeners
scanner_app.route('/health', methods=['GET'])(health)
dashboard_app.route('/health', methods=['GET'])(health)


# ============================================================
#  Background workers
# ============================================================

def prevent_sleep():
    """Tell Windows to stay awake while server is running. No admin needed."""
    if sys.platform != 'win32':
        return
    ES_CONTINUOUS       = 0x80000000
    ES_SYSTEM_REQUIRED  = 0x00000001
    ES_AWAYMODE_REQUIRED = 0x00000040
    while True:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED
        )
        time.sleep(30)


def backup_loop():
    """Daily SQLite backup using the safe .backup() API. No admin needed."""
    backup_dir = "backups"
    os.makedirs(backup_dir, exist_ok=True)
    INTERVAL_SECONDS = 24 * 60 * 60  # once per day
    KEEP_DAYS = 30

    while True:
        time.sleep(INTERVAL_SECONDS)
        try:
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
            dest_path = os.path.join(backup_dir, f"trackingFile-{ts}.db")
            src = sqlite3.connect(DB_FILE)
            dst = sqlite3.connect(dest_path)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
            print(f"  [BACKUP] Saved {dest_path}")

            # Prune old backups
            backups = sorted([
                f for f in os.listdir(backup_dir)
                if f.startswith("trackingFile-") and f.endswith(".db")
            ])
            while len(backups) > KEEP_DAYS:
                old = backups.pop(0)
                os.remove(os.path.join(backup_dir, old))
                print(f"  [BACKUP] Pruned {old}")
        except Exception as e:
            print(f"  [BACKUP ERROR] {e}")


# ============================================================
#  Entrypoint
# ============================================================

if __name__ == '__main__':
    init_database()

    if not testing:
        threading.Thread(target=prevent_sleep, daemon=True).start()
        threading.Thread(target=backup_loop, daemon=True).start()

    print("=" * 60)
    print("  Starting Server...")
    print("  Cart Tracker Server")
    print(f"  Scanners  (HTTP) : http://0.0.0.0:{HTTP_PORT}")
    print(f"  Dashboard (HTTPS): https://0.0.0.0:{PORT}")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    # Plaintext listener for the scanners (no cert)
    http_server = WSGIServer(
        ('0.0.0.0', HTTP_PORT),
        scanner_app
    )
    # TLS listener for the dashboard
    https_server = WSGIServer(
        ('0.0.0.0', PORT),
        dashboard_app,
        certfile='cert.pem',
        keyfile='key.pem'
    )

    try:
        # Run the HTTP server in the background, block on the HTTPS one
        spawn(http_server.serve_forever)
        https_server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")

    print("Server Terminated.")
