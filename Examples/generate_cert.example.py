"""
Generate a self-signed certificate for HTTPS on a server with a dynamic IP.
The cert is valid for hostnames only - clients connect via hostname, not IP.
"""
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta, timezone
import socket

# ============================================================
# CONFIGURE THESE
# ============================================================
# Hostnames clients will use to reach this server.
# Add all the ways your ESP32s / browsers might address the machine.
HOSTNAMES = [
    "[SERVER NAME]",          # short name (works via NetBIOS/mDNS)
    "[SERVER NAME].local",    # mDNS-style name
    "localhost",
]

# Auto-detect this machine's hostname and add it too
try:
    detected = socket.gethostname()
    if detected and detected not in HOSTNAMES:
        HOSTNAMES.append(detected)
        HOSTNAMES.append(f"{detected}.local")
except Exception:
    pass

VALID_DAYS = 3650
PRIMARY_NAME = HOSTNAMES[0]  # used as the cert's Common Name
# ============================================================


def main():
    print("Generating private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, PRIMARY_NAME),
    ])

    # Build SAN list - DNS names only, no IPs (since IP is dynamic)
    san_list = [x509.DNSName(name) for name in HOSTNAMES]

    print("Building certificate...")
    print(f"  Valid for hostnames: {', '.join(HOSTNAMES)}")
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(private_key, hashes.SHA256())
    )

    with open("key.pem", "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    print("  Wrote key.pem")

    with open("cert.pem", "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("  Wrote cert.pem")

    fp = cert.fingerprint(hashes.SHA256())
    fp_hex = ":".join(f"{b:02X}" for b in fp)
    print()
    print("=" * 60)
    print(" Certificate generated successfully!")
    print("=" * 60)
    print(f" Primary name: {PRIMARY_NAME}")
    print(f" Valid for:    {', '.join(HOSTNAMES)}")
    print(f" Expires:      {(now + timedelta(days=VALID_DAYS)).strftime('%Y-%m-%d')}")
    print(f" Fingerprint:  {fp_hex}")
    print("=" * 60)
    print()
    print(" >> Clients MUST connect using one of the hostnames above,")
    print("    not the server's IP address.")
    print()
    print(" ⚠ Add key.pem and cert.pem to .gitignore!")


if __name__ == "__main__":
    main()