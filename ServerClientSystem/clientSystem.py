import cv2
import requests
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



localTesting = True



CURRENT_LOCATION : Final = Locale.JIT
CAMERA_TIMEOUT : Final = 5
SERVER_IP : Final = 'GNELTS00014685.local'
LOCAL_IP : Final = '127.0.0.1'
if localTesting:
    SERVER_URL : Final = f'http://{LOCAL_IP}:5000/scan'
else:
    SERVER_URL : Final = f'http://{SERVER_IP}:5000/scan'

lastKnownState = {}

arucoDict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(arucoDict, parameters)

videoCapture = cv2.VideoCapture(0)

print(f'Scanner Client active at [{CURRENT_LOCATION.toString()}]. Point Camera at some AprilTags...')

def removeDebounce(cartId):
    with timerLock:
        if cartId in activeTimers:
            activeTimers[cartId].cancel()
            del activeTimers[cartId]
            lastKnownState[cartId] = None

activeTimers = {}
timerLock =  threading.Lock()

# Main loop 
while True:
    success, frame = videoCapture.read()
    if not success:
        break

    grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(grayFrame)

    if ids is not None: 
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        for markerId in ids:
            cartId = int(markerId[0])

            # Debouncing:
            if lastKnownState.get(cartId) != CURRENT_LOCATION:
                try:
                    payload = {'cartId': cartId, 'location': CURRENT_LOCATION.toString()}
                    response = requests.post(SERVER_URL, json=payload, timeout=1.5)

                    if response.status_code == 200:
                        lastKnownState[cartId] = CURRENT_LOCATION

                        print(f'Dispatched: Cart {cartId} is at {CURRENT_LOCATION.toString()}.')
                    else:
                        lastKnownState[cartId] = CURRENT_LOCATION
                        print(f'Rejected: Could not find cart {cartId}.')
                    with timerLock:
                        if cartId not in activeTimers:
                            t = threading.Timer(CAMERA_TIMEOUT, removeDebounce, args=[cartId])
                            activeTimers[cartId] = t
                            t.start()

                except requests.exceptions.RequestException:
                    print('Connection Error: Server unreachable over network.')
    
    cv2.imshow(f'Scanner Terminal - {CURRENT_LOCATION.toString()}', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

with timerLock:
    for cartId, timer in activeTimers.items():
        timer.cancel()
        timer.join()

videoCapture.release()
cv2.destroyAllWindows()