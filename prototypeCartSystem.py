import cv2
import datetime
import sqlite3
import numpy as np
from pupil_apriltags import Detector
from typing import Final
from enum import Enum
import threading

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

TRANSIT_DELAY: Final = 10 # seconds



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
    #print(cartData)
    name, contents, dateUsage, lastLocation = cartData
    timeNow = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")

    # Check for location change
    if lastLocation != CURRENT_LOCATION.toString(): # This might cause problems
        cursor.execute("UPDATE carts SET current_location = ? WHERE id = ?", (CURRENT_LOCATION.toString(), cartId))
        cursor.execute("INSERT INTO history (cart_id, location, timestamp) VALUES (?, ?, ?)", (cartId, CURRENT_LOCATION.toString(), timeNow))

        conn.commit()
        print(f"\n [LOCATION UPDATE]: {name} moved from {lastLocation} to {CURRENT_LOCATION.toString()} at {timeNow}")
    conn.close()

    return f"{name} | Usage Date: {dateUsage} | Location: {CURRENT_LOCATION.toString()}", (0, 255, 0)

def cartsInLocation(location):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM carts WHERE current_location = ?", (location.toString(),))
    expectedIds = cursor.fetchall()
    expectedIds = [item[0] for item in expectedIds]
    #print(expectedIds)
    return expectedIds

def triggerInTransit(cartId):
    timeNow = datetime.datetime.now().strftime("%m-%d-%Y %H:%M:%S")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("UPDATE carts SET current_location = ? WHERE id = ?", (Locale.InTransit.toString(), cartId))
    cursor.execute("INSERT INTO history (cart_id, location, timestamp) VALUES (?, ?, ?)", (cartId, Locale.InTransit.toString(), timeNow))

    cursor.execute("SELECT name FROM carts WHERE id = ?", (cartId,))
    name = cursor.fetchone()
    print(f"\n [NOTICE] {name} has left {CURRENT_LOCATION.toString()}.")

    conn.commit()
    conn.close()
    with timerLock:
        if cartId in activeTimers:
            activeTimers[cartId].cancel()
            if not activeTimers[cartId].is_alive():
                del activeTimers[cartId]



# Main Execution
init_database()
tagDetector = Detector(families='tag36h11', nthreads=2)
vidCap = cv2.VideoCapture(0)

print(f"\nTracking system live at {CURRENT_LOCATION.toString()}. Recognizes tags 0 through 8.")

activeTimers = {}
timerLock = threading.Lock()

while True:
    expectedCarts = cartsInLocation(CURRENT_LOCATION)
    #DEBUGGING: expectedCarts = [0,1,2,3,4,5,6,7,8]
    success, frame = vidCap.read()
    if not success:
        print('Error: Failed to capture video')
        break
    #print('reached')
    grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detections = tagDetector.detect(grayFrame)

    visibleIds = []

    for tag in detections:
        cartId = tag.tag_id
        visibleIds.append(cartId)
        uiText, color = processCartDetection(cartId)

        corners = tag.corners.astype(int).reshape((-1, 1, 2))
        cv2.polylines(frame, [corners], isClosed=True, color=color, thickness=2)
        topLeft = tuple(corners[0][0])
        cv2.putText(frame, uiText, (topLeft[0], topLeft[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    
    with timerLock:
        for cartId in expectedCarts:
            if cartId in visibleIds:
                # Cart is visible: cancel any timers for it
                if cartId in activeTimers:
                    activeTimers[cartId].cancel()
                    del activeTimers[cartId]
            else:
                # Cart is missing: start a timer if its not already started
                if cartId not in activeTimers:
                    t = threading.Timer(TRANSIT_DELAY, triggerInTransit, args=[cartId])
                    activeTimers[cartId] = t
                    t.start()


    cv2.imshow(f"Tracking Terminal - {CURRENT_LOCATION.toString()}", frame)

    if cv2.waitKey(1) & 0xFF == ord(' '):
        break

with timerLock:
    for cartId, timer in activeTimers.items():
        timer.cancel()
        timer.join()

print('Exiting process...')
vidCap.release()
cv2.destroyAllWindows()
print("Process Terminated.")