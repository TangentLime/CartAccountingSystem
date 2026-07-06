import requests
import os
from typing import Final
from dotenv import load_dotenv

load_dotenv()

# Enrollment is a write -> HTTPS write port (5000). Use the hostname the cert
# was issued for (not an IP), since the self-signed cert covers hostnames only.
SERVER  = "https://GNELTS00014685:5000"
API_KEY: Final = os.environ.get('NFC_API_KEY')

# Verify TLS against the server's own cert (run this from the repo root, where
# cert.pem lives). This pins the connection the same way the ESP32 does, so the
# API key isn't exposed to a man-in-the-middle. Swap to verify=False only if you
# knowingly accept an unverified (but still encrypted) connection.
CERT: Final = "cert.pem"

ENROLLMENTS = [
    # Examples
    (0, "04A1B2C3D4E5F6"),  # Condor
    (1, "04D5E6F708090A"),  # Albatross
    (2, "0411223344556B"),  # Eagle
    # ... etc for all 9
]

for cart_id, uid in ENROLLMENTS:
    r = requests.post(
        f"{SERVER}/enroll",
        headers={"X-API-Key": API_KEY},
        json={"cartId": cart_id, "uid": uid},
        verify=CERT
    )
    print(f"Cart {cart_id} <- {uid}: {r.status_code} {r.text}")