import requests
import os
from typing import Final

SERVER  = "http://GNELTS00014685:5001"
API_KEY: Final = os.environ.get('NFC_API_KEY')

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
        json={"cartId": cart_id, "uid": uid}
    )
    print(f"Cart {cart_id} <- {uid}: {r.status_code} {r.text}")