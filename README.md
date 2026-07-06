# CartAccountingSystem

A minimal NFC-based cart tracking system. ESP32 scanner stations read NFC tags attached to carts and report their locations to a Flask server, which logs movements to a SQLite database and drives a live browser dashboard.

```
┌─────────────────┐   HTTPS :5000   ┌──────────────────────────┐
│  ESP32 Scanner  │ ──────────────> │   Flask Server (Windows) │
│  + PN532 NFC    │   POST /scan    │   gevent, 2 listeners     │
│  + KY-006 Buzzer│   (encrypted)   │   + SQLite (WAL)          │
└─────────────────┘                 │   + daily backups        │
   (one per location)               └──────────────────────────┘
                                          ▲              ▲
┌──────────────────┐  HTTPS :5000 (write) │              │ HTTP :5001 (read)
│  Edit computer   │ ─────────────────────┘              │
│  GET /edit + save│                                     │
└──────────────────┘   ┌─────────────────┐  GET /  ·  /api/stream
                       │ Dashboard display│ ────────────┘
                       │ (any browser/TV) │  (live board, plaintext)
                       └─────────────────┘
```

The server runs **two listeners in one process, split by operation type**: an **HTTPS**
listener on port **5000** for everything that *writes* (scanner scans/enrollments, and the
edit page + its saves), and a plaintext **HTTP** listener on port **5001** for everything
that *reads* (the live dashboard and its SSE stream). **Rationale: all writing is
encrypted, all reading is unencrypted.** Each app exposes only its own routes, so a write
route 404s on the read port and vice-versa. A bonus of the plaintext read side: any
display — including a smart TV that can't install a cert — can show the dashboard.

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

### Per scanner station (3 stations)

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

> **PN532 DIP switches must be set to I²C mode**: switch 1 OFF, switch 2 ON. Otherwise the firmware can't communicate with the chip.

### Server

Any always-on x86 machine running Windows or Linux. Tested on Windows 10/11. Recommended specs: anything from the last decade with 4GB+ RAM and an SSD. A retired office PC works perfectly.

## Software Architecture

### Server side (`serverSystem.py`)
- **Framework:** Flask 3.x — **two** `Flask` apps in one process, split by operation:
  `write_app` and `read_app`
- **WSGI server:** **gevent** (`gevent.pywsgi.WSGIServer`), monkey-patched for cooperative concurrency
  - HTTPS listener on **:5000** → `write_app` (scans, enrollments, the edit page + its saves)
  - HTTP  listener on **:5001** → `read_app` (dashboard, SSE stream, history)
- **Database:** SQLite with WAL mode (`trackingFile.db`)
- **Auth:** Shared API key in the `X-API-Key` header on the write routes (see per-endpoint table below)
- **Encryption:** Self-signed TLS certificate (`cert.pem`/`key.pem`) — the HTTPS *write* listener only
- **Live updates:** Server-Sent Events (`/api/stream`, on the read listener) push full cart state to every dashboard on each change — a write on `:5000` broadcasts to readers on `:5001` (shared in-process state)
- **Resilience:** daily SQLite `.backup()` to `backups/` and a Windows keep-awake thread (both skipped when `testing = True`)

### Dashboard & editing
- **`GET /` (HTTP :5001)** — full-screen live board (`static/dashboard.html` + `app.js` + `styles.css`), grouped by location, with overdue/warning highlighting. Updates in real time over SSE. Plaintext, so any display can load it with no cert.
- **`GET /edit` (HTTPS :5000)** — a page for a computer stationed in Jurassic Park to edit each JP cart's **contents** and **use-by date**. Saves via `PATCH /api/carts/<id>` over HTTPS; edits broadcast instantly to the live board.

### Client side (`NFCSystem/`)
- **MCU:** ESP32-WROOM-32
- **Build system:** PlatformIO + Arduino framework
- **NFC:** Adafruit PN532 library, I²C mode
- **Networking:** WiFi station + **HTTPS** via `WiFiClientSecure`, with the server's self-signed cert **pinned** (`setCACert`). Requires an NTP time sync at boot so cert-date validation passes.
- **Audio feedback:** PWM tones via KY-006 passive buzzer

### Communication flow

1. User taps an NFC tag attached to a cart against a scanner
2. ESP32 reads the tag's UID via the PN532
3. ESP32 sends `POST /scan` with `{uid, location}` over **HTTPS** to `:5000` (cert pinned)
4. Server looks up the cart by UID, updates `current_location`, appends to the `history` table
5. Server responds with the cart name and outcome; the change is broadcast to dashboards (on `:5001`) via SSE
6. ESP32 plays a tone pattern (success / unknown / error) via the buzzer

## Repository Layout

```
serverSystem.py         Flask server: write (HTTPS :5000) + read (HTTP :5001) listeners
static/                 Browser assets (edit page served by write_app, dashboard by read_app)
  dashboard.html          Live board markup
  app.js                  SSE client + rendering for the board
  styles.css              Board styling (kiosk-oriented)
  edit.html               Jurassic Park contents/date editor
  edit.js                 Loads JP carts, saves via PATCH /api/carts/<id>
  edit.css                Editor styling (interactive, not kiosk)
enroll.py               One-off: associate NFC UIDs with cart records
localClientTesting.py   Keyboard-driven fake scanner for local testing
generate_cert.py        Generates self-signed cert.pem/key.pem for the HTTPS write listener (pinned by scanners)
requirements.txt        Python dependencies (grouped by purpose)
start_server.bat        Launch the server (Windows)
start_dashboard.bat     Launch server + testing client + kiosk browser
trackingFile.db         SQLite database (created/updated at runtime)
backups/                Daily database backups
NFCSystem/              ESP32 firmware (PlatformIO)
  platformio.ini          Board + per-location build environments
  src/main.cpp            Scanner firmware
  include/config.h        Device secrets/config (gitignored; see Examples/)
Examples/               Sanitized templates
  .env.example            Server env template (NFC_API_KEY)
  config.example.h        Firmware config template
  generate_cert.example.py  Cert-generation template
```

## Server Setup

The production server lives in `C:\NFC-Tracker` on the Windows host.

1. **Install dependencies** (Python 3.10+ recommended):
   ```cmd
   pip install -r requirements.txt
   ```
2. **Create `.env`** next to `serverSystem.py` (copy from `Examples/.env.example`):
   ```
   NFC_API_KEY=your-shared-secret
   ```
   The server refuses to start if `NFC_API_KEY` is unset.
3. **Generate the TLS certificate** for the HTTPS write listener:
   ```cmd
   python generate_cert.py
   ```
   Edit the `HOSTNAMES` list first so the cert covers how scanners/editors address the
   machine. This writes `cert.pem` and `key.pem`. The scanners **pin** this cert, so paste
   `cert.pem` into each scanner's `config.h` (`SERVER_CERT`) and reflash whenever you
   regenerate it.
4. **Run the server:**
   ```cmd
   python serverSystem.py
   ```
   or double-click `start_server.bat`. On start it prints both listeners:
   ```
   Writes (HTTPS): https://0.0.0.0:5000  (scans, enroll, edit)
   Reads  (HTTP) : http://0.0.0.0:5001  (dashboard, stream, history)
   ```

**Testing toggle:** `testing = True` at the top of `serverSystem.py` disables the
keep-awake and daily-backup background threads. Set it to `False` for real deployment.

**Kiosk launch:** `start_dashboard.bat` starts the server minimized, launches
`localClientTesting.py` (a keyboard-driven fake scanner), then opens Chrome/Edge in kiosk
mode at `http://localhost:5001/` — the read side is plaintext, so no cert flags are needed.

## Client (ESP32) Setup

1. Install [PlatformIO](https://platformio.org/) (VS Code extension or CLI).
2. Copy `Examples/config.example.h` to `NFCSystem/include/config.h` and fill in WiFi
   credentials, `SERVER_URL` (`https://<host>:5000/scan` — use the cert's hostname, not an
   IP), `API_KEY` (must match the server's `NFC_API_KEY`), and `SERVER_CERT` (paste the
   server's `cert.pem` — the firmware pins it).
3. Build and flash the environment for that station's location (`SCANNER_LOCATION` is set
   per-environment via `build_flags` in `platformio.ini`):
   ```cmd
   pio run -e jp  -t upload    :: Jurassic Park
   pio run -e jit -t upload    :: JIT
   pio run -e mal -t upload    :: MAL
   ```
4. Open the serial monitor at 115200 baud to watch scans.

## Tag Enrollment

Before scans work, each NFC tag's UID must be associated with a cart in the database. The 9 carts are created on first server run with `nfc_uid = NULL`.

### Step 1: Capture each tag's UID

With a scanner already running, tap each cart's tag once and read the UID from the serial monitor:

```
Tag detected: UID=04A1B2C3D4E5F6
```

Write down which UID belongs to which cart number.

### Step 2: Enroll

Edit `enroll.py` (repo root) — set `SERVER` to `https://<host>:5000` (enrollment is a
write), ensure `NFC_API_KEY` is in your `.env`, and fill in the `ENROLLMENTS` list. Run it
from the repo root so it can verify TLS against `cert.pem`:

```python
ENROLLMENTS = [
    (0, "04A1B2C3D4E5F6"),  # Condor
    (1, "04D5E6F708090A"),  # Albatross
    # ... etc for all 9 carts
]
```

Then run:

```cmd
python enroll.py
```

Each successful enrollment prints:

```
Cart 0 <- 04A1B2C3D4E5F6: 200 {"status":"success",...}
```

After enrollment, the same tag tapped on a scanner produces a successful scan + database update.

## API Reference

The server exposes two listeners. Routes are **not** shared: a write route 404s on the read
port and a read route 404s on the write port.

### Write listener — HTTPS, port 5000

#### `POST /scan`  *(requires `X-API-Key`)*
Records a scan from a scanner station. On a move out of `MAL`, the cart's `contents` are
reset to `Empty` and `date_usage` to `Return`.

**Request body:**
```json
{"uid": "04A1B2C3D4E5F6", "location": "JIT"}
```
**Responses:** `200` recorded · `400` bad input / unknown UID · `401` bad key · `429` rate-limited

#### `POST /enroll`  *(requires `X-API-Key`)*
Associates an NFC UID with a cart record.

**Request body:**
```json
{"cartId": 0, "uid": "04A1B2C3D4E5F6"}
```
**Responses:** `200` ok · `400` missing fields · `404` no such cart · `409` UID already assigned

#### `GET /edit`  *(open — HTML)*
The Jurassic Park contents/date editor. Served on the write listener (not the read one) so
its same-origin API calls stay on HTTPS. The page sends the API key on the calls below.

#### `GET /api/carts`  *(requires `X-API-Key`)*
Returns all carts and their current state. It's a read, but it lives here because the HTTPS
edit page fetches it same-origin — an HTTP fetch from an HTTPS page is blocked as mixed content.
```json
[
  {"id": 0, "nfc_uid": "04A1B2C3D4E5F6", "name": "Condor",
   "contents": "Alpha", "date_usage": "06-05-2026", "current_location": "JIT"}
]
```

#### `PATCH /api/carts/<id>`  *(requires `X-API-Key`)*
Edits a cart's `contents` and `date_usage`. Only carts currently in **Jurassic Park** may
be edited; `date_usage` must be `MM-DD-YYYY`. Broadcasts the change to dashboards.

**Request body:**
```json
{"contents": "Widgets", "date_usage": "07-15-2026"}
```
**Responses:** `200` saved · `400` bad body/date · `403` cart not in Jurassic Park · `404` no such cart

#### `GET /health`  *(open)*
Unauthenticated heartbeat: `{"status":"ok","time":"..."}`.

### Read listener — HTTP, port 5001

#### `GET /`  *(open)*
The live dashboard HTML.

#### `GET /api/history?limit=N`  *(open)*
Most recent N history entries (default 50, max 500), each joined to its cart name. Open (no
key) — it's a plaintext read exposing the same movement data the dashboard already shows.
```json
[
  {"log_id": 142, "cart_id": 0, "cart_name": "Condor",
   "old_location": "MAL", "new_location": "JIT", "timestamp": "07-06-2026 14:23:01"}
]
```

#### `GET /api/stream`  *(open)*
Server-Sent Events stream. Emits a `snapshot` event with full cart state on connect and on
every change, plus periodic heartbeats.

#### `GET /health`  *(open)*
Same heartbeat as the write listener.

## Configuration Reference

### Server (`.env`)

| Variable | Description | Required |
|---|---|---|
| `NFC_API_KEY` | Shared secret for the `X-API-Key` header. Must match clients. | ✅ |

### Server (top of `serverSystem.py`)

| Constant | Default | Description |
|---|---|---|
| `DB_FILE` | `"trackingFile.db"` | SQLite filename |
| `WRITE_PORT` | `5000` | HTTPS port — write listener (scans, enroll, edit + PATCH) |
| `READ_PORT` | `5001` | HTTP port — read listener (dashboard, SSE, history) |
| `testing` | `True` | When `True`, skip keep-awake + backup threads |
| `MAX_SSE_SUBS` | `50` | Max concurrent dashboard SSE connections; beyond this, `/api/stream` returns `503` (anti-DoS) |
| `MAX_CONTENT_LENGTH` | `64 KB` | Request-body cap on both listeners; larger POSTs get `413` (anti-DoS) |
| `Locale` enum | `InTransit`, `JurassicPark`, `JIT`, `MAL` | Valid location values. On startup any legacy `In Transit` rows are migrated to `MAL`. |

**Rate limiting:** the API is rate-limited per client IP via `flask-limiter` (in-memory).
Defaults: write listener 120/min, read listener 300/min, with tighter caps on
`POST /scan` (60/min), `POST /enroll` (20/min), and `PATCH /api/carts/<id>` (30/min).
Exceeding a limit returns `429`. All values are tunable constants/decorators in
`serverSystem.py`.

### Client (`include/config.h`)

| Constant | Description |
|---|---|
| `WIFI_SSID`, `WIFI_PASS` | WiFi credentials (`""` password for an open network) |
| `SERVER_URL` | Full HTTPS URL to the scan (write) endpoint, e.g. `https://<host>:5000/scan` |
| `SERVER_CERT` | The server's `cert.pem` (PEM), pinned via `setCACert` |
| `API_KEY` | Must match server's `NFC_API_KEY` |
| `SDA_PIN`, `SCL_PIN` | I²C pins for PN532 (default 21, 22) |
| `BUZZER_PIN` | GPIO for KY-006 signal pin (default 25) |
| `SCAN_INTERVAL_MS` | Delay between PN532 polls (default 200ms) |
| `DEBOUNCE_SAME_TAG_MS` | Same UID re-scans ignored within this window (default 3000ms) |
| `HTTP_TIMEOUT_MS` | HTTP request timeout (default 4000ms) |
| `WIFI_RETRY_INTERVAL_S` | Seconds between WiFi reconnect attempts (default 30) |

> `SCANNER_LOCATION` is **not** in `config.h` — it's injected per-station by PlatformIO
> `build_flags` (`platformio.ini` envs `esp32dev`/`jit`/`jp`/`mal`).

## Troubleshooting

### Scanner serial output

| Symptom | Likely cause | Fix |
|---|---|---|
| Boot-fail siren forever | PN532 not responding | Check wiring (SDA→21, SCL→22, VCC→3V3, GND→GND); confirm DIP switches set to I²C (1=OFF, 2=ON) |
| `WiFi Failed` repeatedly | Bad SSID/password | Edit `config.h`, rebuild, reflash |
| `Server: -1` | Couldn't reach server, or TLS handshake failed | See "Network issues" below; if WiFi is up, suspect TLS (see next row) |
| `Server: -1` right after "Syncing time for TLS" fails | Clock never synced → cert-date validation fails | Ensure NTP (UDP 123) egress is allowed; the boot log should show time sync "done" before scans work |
| TLS/cert errors in serial | `SERVER_CERT` doesn't match the server's current `cert.pem` | Re-paste `cert.pem` into `config.h` and reflash (pinning = reflash on cert change) |
| `Server: 401` | Auth rejected | API key in `config.h` doesn't match `.env` |
| `Server: 400 Unknown Tag UID` | Tag not enrolled yet | Run `enroll.py` for that UID |
| ESP32 reboots when WiFi connects | Power supply too weak | Use a real wall charger, not a PC USB port |
| Buzzer silent | Wiring wrong | Try connecting the middle pin to 3V3, swap S/− if reversed |

### Server console

| Symptom | Likely cause | Fix |
|---|---|---|
| `[AUTH] Rejected request from <ip>` | Client API key mismatch | Match the keys exactly |
| `Address already in use` on startup | Previous instance still running | `netstat -ano \| findstr :5000` (or `:5001`) then `taskkill /F /PID <pid>` |
| `[BACKUP ERROR]` | Disk full or permission denied | Check `backups/` folder writability |
| `/health` 404s | Wrong port or case | Write routes are on 5000 (HTTPS), read routes on 5001 (HTTP); paths are case-sensitive |

### Network issues

If the ESP32 can't reach the server (`Server: -1` repeatedly), test reachability layer by layer:

1. **Server running?** The console should print both listeners on startup.
2. **Reachable locally?** On the server PC, `https://localhost:5000/health` (write) and `http://localhost:5001/health` (read) should both respond.
3. **Reachable from another device?** From a phone on the same network: `http://<server-host>:5001/health` (the plaintext read side is easiest to test). If this fails, a firewall is blocking inbound connections.
4. **DNS working?** `ping <server-host>` should resolve. If not, use mDNS or a DHCP reservation. Scanners must reach the server by the **cert's hostname** (not an IP), or pinning fails.

The scanner (write) path is HTTPS with a **pinned** cert — if scans fail while WiFi is up,
suspect the cert or the boot-time clock sync, not just the network. The dashboard (read)
path is plain HTTP on 5001, so no certificate is involved there.

### Common dev mistakes

- Editing `config.h` but forgetting to reflash the ESP32 — `pio run -e <env> -t upload` again
- Editing `.env` but forgetting to restart the server
- Updating the API key on one side but not the other
- Pointing a display at `:5000` (HTTPS write) instead of `:5001` (HTTP read), or a scanner at the read port
- Regenerating `cert.pem` but forgetting to re-paste it into every scanner's `config.h` and reflash (pinning)
- Server's hostname changed (Windows machine renamed) — regenerate the cert *and* reflash scanners

## Project Decisions

Quick notes on why certain choices were made, in case you want to revisit them later:

### Why SQLite instead of Postgres?
For a few scanners and tens of scans per day, SQLite is simpler, faster to set up, and has zero administrative overhead. WAL mode handles concurrent reads/writes well. If the project grows past ~10 scanners or needs multi-process access, migrate to Postgres — but don't preemptively.

### Why gevent instead of Waitress/Hypercorn?
The server needs to run two listeners in one process and hold many long-lived SSE
connections open without a thread per client. gevent's monkey-patched cooperative
concurrency handles both cheaply, serves TLS in-process for the write listener, and runs
fine on Windows. (An earlier design used Hypercorn; gevent replaced it once SSE was added.)

### Why split by write (HTTPS) vs read (HTTP)?
The guiding principle is **all writing is encrypted, all reading is unencrypted.** Anything
that mutates the database — scanner scans, enrollments, JP edits — carries the API key and
changes state, so it goes over TLS. The dashboard is a passive, read-only view of
low-sensitivity data, so it runs plaintext. Two payoffs: the key never crosses the wire in
cleartext, and *any* display (including a smart TV that can't install a cert) can show the
board over plain HTTP. Two Flask apps on two ports means each listener exposes only its own
routes — a write endpoint simply doesn't exist on the read port, and vice-versa. The one
wrinkle: `GET /api/carts` is a read that lives on the HTTPS side, because the HTTPS edit
page must fetch it same-origin (an HTTP fetch from an HTTPS page is blocked as mixed content).

### Why ESP32 + PN532 instead of an all-in-one NFC reader?
The ESP32 is dirt cheap (~$10), has WiFi built in, and is well-supported. The PN532 reads ISO14443A tags reliably. Dedicated all-in-one NFC readers exist but cost 5–10× more.

### Why an API key instead of mTLS or OAuth?
For an internal cart-tracking system on a trusted network, a shared secret is sufficient.
mTLS adds significant complexity (per-client certs, rotation, revocation). OAuth is overkill
— there are no user accounts, just trusted devices.

### Why cert pinning on the scanners (not `setInsecure`)?
Scanners write, so they must use HTTPS — and to make that HTTPS actually mean something, the
firmware **pins** the server's self-signed cert with `setCACert(SERVER_CERT)`, giving real
MITM protection rather than encryption-without-authentication. The cost is operational:
pinning validates the cert's dates, so each ESP32 must NTP-sync its clock at boot, and
regenerating the cert means re-pasting it into every `config.h` and reflashing.
*(History: scanners have been plaintext HTTP, and HTTPS-with-`setInsecure()`, at different
points; pinning is the current choice.)* If reflashing on cert rotation becomes painful,
`setInsecure()` (encrypt-only) is the fallback.

### Why I²C for PN532 instead of SPI?
Fewer wires (4 vs 7), same throughput at this scale, simpler library setup. SPI is faster but unnecessary for one tag-read every few seconds.

### Why store NFC UIDs server-side instead of writing cart IDs to tags?
Easier to swap a damaged tag (just re-enroll the new UID) and tags don't need to be programmed before deployment. The PN532 *can* write to tags if you want to migrate later.

## License

Internal Use Only

## Authors & Contributors

### Author: Brian Cook
Email: briancoeng@gmail.com
