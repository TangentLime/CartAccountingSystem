# CartAccountingSystem

A minimal NFC-based cart tracking system. ESP32 scanner stations read NFC tags attached to carts and report their locations to a Flask server, which logs movements to a SQLite database.

```
┌─────────────────┐     HTTPS      ┌──────────────────────┐
│  ESP32 Scanner  │ ─────────────> │  Flask Server (Win)  │
│  + PN532 NFC    │   POST /scan   │  + SQLite DB         │
│  + KY-006 Buzzer│                │  + Auto backups      │
└─────────────────┘                └──────────────────────┘
       (one per location)              (one server)
```

## Table of Contents

- [Hardware](#hardware)
- [Software Architecture](#software-architecture)
- [Repository Layout](#repository-layout)
- [Server Setup](#server-setup)
- [Client (ESP32) Setup](#client-esp32-setup)
- [Tag Enrollment](#tag-enrollment)
- [API Reference](#api-reference)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)
- [Project Decisions](#project-decisions)

## Hardware

### Per scanner station (3 Stations)

| Part | Notes |
|---|---|
| ESP32-WROOM-32 (30-pin Type-C DevKit) | Any 30-pin variant with USB-C |
| PN532 NFC module (V3, red board) | I²C mode (DIP switches: 1=OFF, 2=ON) |
| KY-006 passive buzzer module | 3-pin breakout |
| 7× female-to-female Dupont jumpers | ESP32-Module connections |
| USB-C cable + 5V wall charger | For power |

### Per cart

| Part | Notes |
|---|---|
| NFC tag/card included with PN532 kit | Or any NTAG213/215 13.56MHz ISO14443A tag |
| Retractable badge reel | Clip + split ring |

### Wiring

```
PN532 VCC -> ESP32 3V3
PN532 GND -> ESP32 GND
PN532 SDA -> ESP32 GPIO 21
PN532 SCL -> ESP32 GPIO 22
KY-006 S  -> ESP32 GPIO 25
KY-006 -  -> ESP32 GND
KY-006 middle pin -> 3V3 (if labeled VCC) or leave NC
```

> **PN532 DIP switches must be set to I²C mode**: switch 1 OFF, switch 2 ON. Otherwise, the firmware can't communicate with the chip.

### Server

Any always-on x86 machine running Windows or Linux. Tested on Windows 10/11. Recommended specs: anything from the last decade with 4GB+ RAM and an SSD. A retired office PC works perfectly.

## Software Architecture

### Server side
- **Framework:** Flask 3.x
- **WSGI/ASGI server:** Hypercorn (HTTPS-capable)
- **Database:** SQLite with WAL mode
- **Auth:** Shared API key in `X-API-Key` header
- **Encryption:** Self-signed TLS certificate (locally generated)

### Client side
- **MCU:** ESP32-WROOM-32
- **Build system:** PlatformIO + Arduino framework
- **NFC:** Adafruit PN532 library, I²C mode
- **Networking:** WiFi station + HTTPS via WiFiClientSecure
- **Audio feedback:** PWM tones via KY-006 passive buzzer

### Communication flow

1. User taps an NFC tag attached to a cart against a scanner
2. ESP32 reads the tag's UID via the PN532
3. ESP32 sends `POST /scan` with `{uid, location}` over HTTPS
4. Server looks up the cart by UID, updates `current_location`, appends to `history` table
5. Server responds with the cart name and outcome
6. ESP32 plays a tone pattern (success / unknown / error) via the buzzer

## Repository Layout
## Tag Enrollment

Before scans work, each NFC tag's UID must be associated with a cart in the database. The 9 carts are created on first server run with `nfc_uid = NULL`.

### Step 1: Capture each tag's UID

With a scanner already running, tap each cart's tag once. Read the UID from the serial monitor:

```
Tag detected: UID=04A1B2C3D4E5F6
```

Write down which UID belongs to which cart number.

### Step 2: Enroll

Edit `server/enroll.py`:

```python
ENROLLMENTS = [
    (0, "04A1B2C3D4E5F6"),  # Condor
    (1, "04D5E6F708090A"),  # Albatross
    # ... etc for all 9 carts
]
```

Then run:

```cmd
cd server
python enroll.py
```

Each successful enrollment prints:

```
Cart 0 <- 04A1B2C3D4E5F6: 200 OK
```

After enrollment, the same tag tapped on a scanner produces a successful scan + database update.

## API Reference

All endpoints except `/health` require the `X-API-Key` header.

### `POST /scan`
Records a scan from a scanner station.

**Request body:**
```json
{"uid": "04A1B2C3D4E5F6", "location": "JIT"}
```

**Responses:**
- `200` — scan recorded: `{"status":"success","cartId":0,"cartName":"Condor","location":"JIT"}`
- `400` — bad input or unknown UID
- `401` — missing/invalid API key

### `POST /enroll`
Associates an NFC UID with a cart record.

**Request body:**
```json
{"cartId": 0, "uid": "04A1B2C3D4E5F6"}
```

**Responses:**
- `200` — enrollment successful
- `400` — missing fields
- `404` — no cart with that ID
- `409` — UID already assigned to another cart

### `GET /api/carts`
Returns all carts and their current state.

**Response (200):**
```json
[
  {
    "id": 0,
    "nfc_uid": "04A1B2C3D4E5F6",
    "name": "Condor",
    "contents": "Alpha",
    "date_usage": "06-05-2026",
    "current_location": "JIT"
  },
  ...
]
```

### `GET /api/history?limit=N`
Returns the most recent N history entries (default 50, max 500). Each entry includes the cart name via a SQL join.

**Response (200):**
```json
[
  {
    "log_id": 142,
    "cart_id": 0,
    "cart_name": "Condor",
    "old_location": "In Transit",
    "new_location": "JIT",
    "timestamp": "11-12-2024 14:23:01"
  },
  ...
]
```

### `GET /health`
Unauthenticated heartbeat. Useful for testing reachability.

**Response (200):**
```json
{"status": "ok", "time": "2024-11-12T14:23:01.234567"}
```

## Configuration Reference

### Server (`.env`)

| Variable | Description | Required |
|---|---|---|
| `NFC_API_KEY` | Shared secret for the `X-API-Key` header. Must match clients. | ✅ |

### Server (top of `serverSystem.py`)

| Constant | Default | Description |
|---|---|---|
| `DB_FILE` | `"trackingFile.db"` | SQLite filename |
| `PORT` | `5000` | TCP port to listen on |
| `Locale` enum | `InTransit`, `JurassicPark`, `JIT` | Valid location values |

### Client (`include/config.h`)

| Constant | Description |
|---|---|
| `SCANNER_LOCATION` | This scanner's location string. Must be one of the `Locale` values. |
| `WIFI_SSID`, `WIFI_PASS` | WiFi credentials |
| `SERVER_URL` | Full HTTPS URL to `/scan` endpoint |
| `API_KEY` | Must match server's `NFC_API_KEY` |
| `SDA_PIN`, `SCL_PIN` | I²C pins for PN532 (default 21, 22) |
| `BUZZER_PIN` | GPIO for KY-006 signal pin (default 25) |
| `SCAN_INTERVAL_MS` | Delay between PN532 polls (default 200ms) |
| `DEBOUNCE_SAME_TAG_MS` | Same UID re-scans ignored within this window (default 3000ms) |
| `HTTP_TIMEOUT_MS` | HTTP request timeout (default 4000ms) |
| `WIFI_RETRY_INTERVAL_S` | Seconds between WiFi reconnect attempts (default 30) |

## Troubleshooting

### Scanner serial output

| Symptom | Likely cause | Fix |
|---|---|---|
| Boot-fail siren forever | PN532 not responding | Check wiring (SDA→21, SCL→22, VCC→3V3, GND→GND); confirm DIP switches set to I²C (1=OFF, 2=ON) |
| `WiFi Failed` repeatedly | Bad SSID/password | Edit `config.h`, rebuild, reflash |
| `Server: -1` | Couldn't reach server | See "Network issues" below |
| `Server: 401` | Auth rejected | API key in `config.h` doesn't match `.env` |
| `Server: 400 Unknown tag UID` | Tag not enrolled yet | Run `enroll.py` for that UID |
| ESP32 reboots when WiFi connects | Power supply too weak | Use a real wall charger, not a PC USB port |
| Buzzer silent | Wiring wrong | Try connecting the middle pin to 3V3, swap S/− if reversed |

### Server console

| Symptom | Likely cause | Fix |
|---|---|---|
| `[AUTH] Rejected request from <ip>` | Client API key mismatch | Match the keys exactly |
| `Address already in use` on startup | Previous server instance still running | Find and kill: `netstat -ano \| findstr :5000` then `taskkill /F /PID <pid>` |
| `[BACKUP ERROR]` | Disk full or permission denied | Check `backups/` folder writability |
| Server starts but `/health` 404s | URL wrong (`/Health` vs `/health`) | Paths are case-sensitive |

### Network issues

If the ESP32 can't reach the server (`Server: -1` repeatedly), test reachability layer by layer:

1. **Server running?** Check the server console — does it print "Listening on https://..."?
2. **Server reachable from server machine?** Open browser on the server PC: `https://localhost:5000/health` should work.
3. **Server reachable from another device?** From your phone on the same WiFi: `https://<server-hostname>:5000/health`. If this fails, the firewall is blocking inbound connections.
4. **DNS working?** From your phone, `ping <server-hostname>` should resolve. If not, you need mDNS or a DHCP reservation (see [Server Setup](#server-setup)).

If reachability from a phone works but the ESP32 still fails, double-check the URL in `config.h` — it must use `https://` and the hostname (not IP, since the cert isn't valid for IPs).

### Common dev mistakes

- Editing `config.h` but forgetting to reflash the ESP32 — `pio run -t upload` again
- Editing `.env` but forgetting to restart the server
- Updating the API key on one side but not the other
- Server's hostname changed (Windows machine renamed) — regenerate the cert
- Self-signed cert expired (10 years from generation) — run `generate_cert.py` again, redistribute the new fingerprint if pinning is used

## Project Decisions

Quick notes on why certain choices were made, in case you want to revisit them later:

### Why SQLite instead of Postgres?
For a few scanners and tens of scans per day, SQLite is simpler, faster to set up, and has zero administrative overhead. WAL mode handles concurrent reads/writes well. If the project grows past ~10 scanners or needs multi-process access, migrate to Postgres — but don't preemptively.

### Why Hypercorn instead of Waitress?
Waitress doesn't support HTTPS natively. Hypercorn handles TLS in-process, runs fine on Windows, and works with Flask via the WSGI compatibility layer. If you don't need HTTPS, Waitress is also a fine choice.

### Why ESP32 + PN532 instead of an all-in-one NFC reader?
The ESP32 is dirt cheap (~$10), has WiFi built in, and is well-supported. The PN532 reads ISO14443A tags reliably. Dedicated all-in-one NFC readers exist but cost 5–10× more.

### Why API key + HTTPS instead of mTLS or OAuth?
For an internal cart-tracking system on a trusted network, a shared secret over HTTPS is sufficient. mTLS is more secure but adds significant complexity (cert generation per client, rotation, revocation). OAuth is overkill — there are no user accounts, just trusted devices.

### Why self-signed cert with `setInsecure()` on the ESP32?
The data being protected (cart locations) isn't catastrophic if seen, but the network is open WiFi so plaintext is unacceptable. `setInsecure()` provides encryption without identity verification, which is the right tradeoff for a closed system. Pinning the cert fingerprint is a future improvement.

### Why I²C for PN532 instead of SPI?
Fewer wires (4 vs 7), same throughput at this scale, simpler library setup. SPI is faster but unnecessary for one tag-read every few seconds.

### Why store NFC UIDs server-side instead of writing cart IDs to tags?
Easier to swap a damaged tag (just re-enroll the new UID) and tags don't need to be programmed before deployment. The PN532 *can* write to tags if you want to migrate later.

## License

Internal Use Only

## Authors & Contributors

### Author: Brian Cook
Email: briancoeng@gmail.com