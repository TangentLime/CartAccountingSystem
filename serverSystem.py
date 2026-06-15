import datetime
import sqlite3
import logging
from typing import Final
from enum import Enum
from flask import Flask, request, jsonify

class Locale(Enum):
    InTransit = 0
    JurassicPark = 1
    JIT = 2

    def toString(self):
        if self.value == 0:
            return "In Transit"
        elif self.value == 1:
            return "Jurassic Park"
        elif self.value == 2:
            return "JIT"
        

app = Flask(__name__)

flasking = False
DB_FILE: Final = "trackingFile.db"
PORT_NAME: Final = 3000



def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')

    # State Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS carts (
            id INTEGER PRIMARY KEY,
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
            (0, 'Condor', 'Alpha', datetime.date(2026, 6, 5).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (1, 'Albatross', 'Beta', datetime.date(2026, 6, 6).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (2, 'Eagle', 'Gamma', datetime.date(2026, 6, 7).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (3, 'Raven', 'Delta', datetime.date(2026, 6, 8).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (4, 'Pelican', 'Epsilon', datetime.date(2026, 6, 9).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (5, 'Falcon', 'Zeta', datetime.date(2026, 6, 10).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (6, 'Sparrow', 'Eta', datetime.date(2026, 6, 11).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (7, 'Hummingbird', 'Theta', datetime.date(2026, 6, 12).strftime("%m-%d-%Y"), Locale.InTransit.toString()),
            (8, 'Owl', 'Iota', datetime.date(2026, 6, 13).strftime("%m-%d-%Y"), Locale.InTransit.toString())
        ]
        cursor.executemany('INSERT INTO carts VALUES (?, ?, ?, ?, ?)', imagCarts)
        conn.commit()
    conn.close()

@app.route('/scan', methods = ['POST'])
def processScan():
    data = request.json
    if not data:
        return jsonify({'status': 'error', 'message': 'No JSON body'}), 400
    
    cartId = data.get('cartId')
    clientLocation = data.get('location') # In String form

    if cartId is None or clientLocation is None:
        return jsonify({'status': 'error', 'message': 'Missing cartId or location'}), 400

    validLocations = [loc.toString() for loc in Locale]
    if clientLocation not in validLocations:
        return jsonify({'status': 'error', 'message': f'Invalid location. Must be on of: {validLocations}'}), 400

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT name, current_location FROM carts WHERE id = ?', (cartId,))
    cartData = cursor.fetchone()
    if not cartData:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Unknown Cart ID'}), 400
    
    name, lastLocation = cartData # lastLocation in String form
    timeNow = datetime.datetime.now().strftime('%m-%d-%Y %H:%M:%S')

    if lastLocation != clientLocation:
        cursor.execute('UPDATE carts SET current_location = ? WHERE id = ?', (clientLocation, cartId))
        cursor.execute('INSERT INTO history (cart_id, old_location, new_location, timestamp) VALUES (?, ?, ?, ?)', (cartId, lastLocation, clientLocation, timeNow))
        conn.commit()
        
        print(f"[UPDATE] {name} moved from {lastLocation} to {clientLocation} ({timeNow})")

    conn.close()
    return jsonify({'status': 'success', 'cartName': name, 'location': clientLocation})

@app.after_request
def log_request(response):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
          f"{request.remote_addr} "
          f"{request.method} {request.path} "
          f"-> {response.status_code}")
    return response

if __name__ == '__main__':
    init_database()

    logging.basicConfig(
        level = logging.INFO,
        format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt = '%H:%M:%S'
    )

    if not flasking:
        from waitress import serve
        # Maybe change host variable for better security: 0.0.0.0 listens to whole network
        print('='*60)
        print(f'Starting Server on http://GNELTS00014685/{PORT_NAME}')
        print('Press Ctrl+C to terminate')
        print('='*60)
        try:
            serve(app, host='0.0.0.0', port=PORT_NAME, threads=8)
        except KeyboardInterrupt:
            print('\nServer Terminated by user.')
    else:
        app.run(host='0.0.0.0', port=PORT_NAME)
