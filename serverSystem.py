from gevent import monkey
monkey.patch_all()
from gevent.pywsgi import WSGIServer

import datetime
import sqlite3
import logging
import threading
import time
import ctypes
import os
import sys
import queue
import json
from typing import Final
from enum import Enum
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, Response
from dotenv import load_dotenv

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

app = Flask(__name__)

load_dotenv()

flasking = False
DB_FILE: Final = "trackingFile.db"
PORT: Final = 5000

sseSubs = []
sseLock = threading.Lock()

API_KEY: Final = os.environ.get('NFC_API_KEY')

if not API_KEY:
    print("ERROR: NFC_API_KEY not set. Please check .env file.")
    sys.exit(1)


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
        if provided != API_KEY:
            print(f"  [AUTH] Rejected request from {request.remote_addr} - bad API key")
            return jsonify({
                'status': 'error',
                'message': 'Invalid API key'
            }), 401
        return f(*args, **kwargs)
    return decorated

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
            (0, None, 'Condor', 'Alpha', datetime.date(2026, 6, 5).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (1, None, 'Albatross', 'Beta', datetime.date(2026, 6, 6).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (2, None, 'Eagle', 'Gamma', datetime.date(2026, 6, 7).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (3, None, 'Raven', 'Delta', datetime.date(2026, 6, 8).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (4, None, 'Pelican', 'Epsilon', datetime.date(2026, 6, 9).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (5, None, 'Falcon', 'Zeta', datetime.date(2026, 6, 10).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (6, None, 'Sparrow', 'Eta', datetime.date(2026, 6, 11).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (7, None, 'Hummingbird', 'Theta', datetime.date(2026, 6, 12).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (8, None, 'Owl', 'Iota', datetime.date(2026, 6, 13).strftime("%m-%d-%Y"), Locale.InTransit.toString())
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

@app.route('/scan', methods = ['POST'])
@require_api_key
def processScan():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON body'}), 400
    
    nfcUid = data.get('uid')
    clientLocation = data.get('location') # In String form

    if nfcUid is None or clientLocation is None:
        return jsonify({'status': 'error', 'message': 'Missing UID or location'}), 400

    validLocations = [loc.toString() for loc in Locale]
    if clientLocation not in validLocations:
        return jsonify({'status': 'error', 'message': f'Invalid location. Must be on of: {validLocations}'}), 400
    
    nfcUid = nfcUid.upper()

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, current_location FROM carts WHERE nfc_uid = ?', (nfcUid,))
    cartData = cursor.fetchone()
    if not cartData:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unknown Tag UID', 'uid': nfcUid}), 400
    
    cartId, name, lastLocation = cartData # lastLocation in String form
    timeNow = datetime.datetime.now().strftime('%m-%d-%Y %H:%M:%S')

    locationChanged = lastLocation != clientLocation
    if locationChanged:
        cursor.execute('UPDATE carts SET current_location = ? WHERE id = ?', (clientLocation, cartId))
        cursor.execute('INSERT INTO history (cart_id, old_location, new_location, timestamp) VALUES (?, ?, ?, ?)', (cartId, lastLocation, clientLocation, timeNow))
        conn.commit()
        
        print(f"[UPDATE] {name} moved from {lastLocation} to {clientLocation} ({timeNow})")

    conn.close()
    if locationChanged:
        broadcastUpdate()

    return jsonify({'status': 'success', 'cartId': cartId, 'cartName': name, 'location': clientLocation})

@app.after_request
def log_request(response):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
          f"{request.remote_addr} "
          f"{request.method} {request.path} "
          f"-> {response.status_code}")
    return response


@app.route('/enroll', methods=['POST'])
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


@app.route('/api/carts', methods=['GET'])
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


@app.route('/api/history', methods=['GET'])
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


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'time': datetime.datetime.now().isoformat()
    })


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

@app.route('/')
def dashboard():
    return send_from_directory('static', 'dashboard.html')

@app.route('/api/stream')
def event_stream():
    def gen():
        q = queue.Queue(maxsize=10)
        with sseLock:
            sseSubs.append(q)

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

if __name__ == '__main__':
    init_database()

    if not testing:
        threading.Thread(target=prevent_sleep, daemon=True).start()
        threading.Thread(target=backup_loop, daemon=True).start()

    print("=" * 60)
    print("  Starting Server...")
    print("  Cart Tracker Server (HTTPS)")
    print(f"  Listening on: https://0.0.0.0:{PORT}")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    try:
        http_server = WSGIServer(
            ('0.0.0.0', PORT),
            app,
            certfile='cert.pem',
            keyfile='key.pem'
        )
        http_server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    
    print("Server Terminated.")