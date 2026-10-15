"""Generate ignored credentials for fictional loopback-only development."""
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

ROOT = Path(__file__).resolve().parents[1]


def main():
    local = ROOT / '.local'
    local.mkdir(exist_ok=True)
    key_file = local / 'private.pem'
    if not key_file.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        (local / 'public.pem').write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    if not (ROOT / '.env.local').exists():
        password = secrets.token_urlsafe(32)
        (ROOT / '.env.local').write_text(
            f'ENVIRONMENT=local\nFIXTURE_AUTH=true\nDATABASE_URL=postgresql+psycopg://intraspot:{password}@127.0.0.1:5433/intraspot_mvp\nMVP_DB_PASSWORD={password}\n', encoding='utf-8')
    print('Ignored local signing keys and database configuration ready; no credentials printed.')


if __name__ == '__main__':
    main()
