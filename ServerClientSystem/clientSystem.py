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

CURRENT_LOCATION : Final = Locale.JIT
SERVER_IP : Final = '10.35.174.27'
SERVER_URL : Final = f'http://{SERVER_IP}:5000/scan'

lastKnownState = {}

arucoDict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(arucoDict, parameters)

videoCapture = cv2.VideoCapture(0)

print(f'Scanner Client active at [{CURRENT_LOCATION}]. Point Camera at some AprilTags...')

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
                    
                except requests.exceptions.RequestException:
                    print('Connection Error: Server unreachable over network.')
    
    cv2.imshow(f'Scanner Terminal - {CURRENT_LOCATION.toString()}', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

videoCapture.release()
cv2.destroyAllWindows()