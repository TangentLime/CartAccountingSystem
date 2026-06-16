import requests

SERVER  = "http://http://GNELTS00014685:5000/scan:5000"
API_KEY = "lVj7QgyoL06lqOFDCCKZfXwRle9WVLP0ST4R74-0gT4"

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