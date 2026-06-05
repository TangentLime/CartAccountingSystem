import cv2
import datetime
import sqlite3
import numpy as np
from pupil_apriltags import Detector
from typing import Final
from enum import Enum

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


CURRENT_LOCATION: Final = Locale.JurassicPark

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
            location TEXT,
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

# How we see
def processCartDetection(cartId):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute('SELECT name, contents, date_usage, current_location FROM carts WHERE id = ?', (cartId,))
    cartData = cursor.fetchone()

    if cartData is None:
        conn.close()
        return f"Could not find cart with ID: {cartId}", (0, 0, 255)
    
    name, contents, dateUsage, lastLocation = cartData
    timeNow = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")

    # Check for location change
    if lastLocation != CURRENT_LOCATION.toString(): # This might cause problems
        cursor.execute("UPDATE carts SET current_location = ? WHERE id = ?", (CURRENT_LOCATION.toString(), cartId))
        cursor.execute("INSERT INTO history (cart_id, location, timestamp) VALUES (?, ?, ?)", (cartId, CURRENT_LOCATION.toString(), timeNow))

        conn.commit()
        print(f"\n Database Update: {name} moved from {lastLocation} to {CURRENT_LOCATION.toString()} at {timeNow}")
    conn.close()

    return f"{name} | Usage Date: {dateUsage} | Location: {CURRENT_LOCATION.toString()}", (0, 255, 0)

def transitBuffer(cartId):
    pass


# Main Execution
init_database()
tagDetector = Detector(families='tag36h11', nthreads=4)
vidCap = cv2.VideoCapture(0)

print(f"\nTracking system live at {CURRENT_LOCATION.toString()}. Recognizes tags 0 through 8.")

while True:
    success, frame = vidCap.read()
    if not success:
        print('Error: Failed to capture video')
        break
    #print('reached')
    grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections = tagDetector.detect(grayFrame)

    for tag in detections:
        cartId = tag.tag_id

        uiText, color = processCartDetection(cartId)

        corners = tag.corners.astype(int).reshape((-1, 1, 2))
        cv2.polylines(frame, [corners], isClosed=True, color=color, thickness=2)
        topLeft = tuple(corners[0][0])
        cv2.putText(frame, uiText, (topLeft[0], topLeft[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    cv2.imshow(f"Tracking Terminal - {CURRENT_LOCATION.toString()}", frame)


    if cv2.waitKey(1) & 0xFF == ord(' '):
        break

print('Exiting process...')
vidCap.release()
cv2.destroyAllWindows()
print("Process Terminated.")