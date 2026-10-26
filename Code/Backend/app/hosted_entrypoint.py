"""Materialize only the public CA on ephemeral disk; never migrate at startup."""
import os
from pathlib import Path
import re
from uuid import UUID

from cryptography import x509

CA_PATH = Path('/tmp/intraspot-supabase-ca.pem')


def prepare_ca(environ=os.environ, path=CA_PATH):
    pem = environ.get('SUPABASE_DATABASE_CA_PEM')
    if pem is None:
        return  # An explicitly configured existing certificate file also works.
    if len(pem) > 65536 or 'PRIVATE KEY' in pem:
        raise ValueError('Invalid public database CA')
    certificates = x509.load_pem_x509_certificates(pem.encode('ascii'))
    if not certificates or any(not cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca for cert in certificates):
        raise ValueError('A public CA certificate is required')
    path.write_bytes(pem.encode('ascii'))
    path.chmod(0o600)
    # Remove the redundant process environment copy before spawning the server.
    environ.pop('SUPABASE_DATABASE_CA_PEM', None)


def main():
    try:
        # This image's forwarded-address policy is valid only behind Koyeb's edge.
        UUID(os.environ['KOYEB_SERVICE_ID'])
        UUID(os.environ['KOYEB_INSTANCE_ID'])
        prepare_ca()
        port = os.environ.get('PORT', '8000')
        if not re.fullmatch(r'[0-9]{1,5}', port) or not 1 <= int(port) <= 65535:
            raise ValueError('Invalid listening port')
    except Exception:
        raise SystemExit('Hosted startup configuration is invalid') from None
    os.execvp('uvicorn', ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', port,
                         '--workers', '1', '--no-access-log', '--no-proxy-headers'])


if __name__ == '__main__':
    main()
