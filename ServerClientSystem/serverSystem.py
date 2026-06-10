import datetime
import sqlite3
import numpy as np
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

DB_FILE: Final = "trackingFile.db"



def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

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
    cartId = data.get('cartId')
    clientLocation = data.get('location') # In String form

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

if __name__ == '__main__':
    init_database()
    # Maybe change host variable for better security: 0.0.0.0 listens to whole network
    app.run(host='0.0.0.0', port=5000)
