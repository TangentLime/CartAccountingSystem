from pynput import keyboard
import requests
from dotenv import load_dotenv
import os
import sys

load_dotenv()
API_KEY = os.environ.get('NFC_API_KEY')
if not API_KEY:
    print("ERROR: NFC_API_KEY not set. Please check .env file.")
    sys.exit(1)

# A scan is a write -> HTTPS write port (5000). The cert covers "localhost"
# (see generate_cert.py HOSTNAMES), so verify against cert.pem from the repo root.
SERVER_URL = f'https://localhost:5000/scan'
CERT = "cert.pem"


targetLocation = "Jurassic Park"

locKeys = {'m': 'MAL', 't': 'JIT', 'p': 'Jurassic Park'}

cartKeys = {str(i) for i in range(0,10)}

print('Starting Testing Client...')
print('Press m, p, or t to change the target location.')
print('Press the number of the cart you want to move to move it to the target location.')
print('Press c to exit')

def onPress(key):
    global targetLocation
    try:
        if key.char in locKeys:
            targetLocation = locKeys[key.char]
            print(targetLocation)
        elif key.char in cartKeys:
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": API_KEY
            }
            body = {
                "uid": key.char,
                "location": targetLocation
            }
            response = requests.post(SERVER_URL, json=body, headers=headers, verify=CERT)
            print(f'Moved Cart {key.char} to {targetLocation}')
        elif key.char == 'c':
            sys.exit(1)

    except AttributeError:
        pass

with keyboard.Listener(on_press=onPress) as listener:
    listener.join()

print('Testing Client Terminated.')

