"""Materialize only the public CA on ephemeral disk; never migrate at startup."""
import os
from pathlib import Path
import re
from uuid import UUID

from cryptography import x509

CA_PATH = Path('/tmp/intraspot-supabase-ca.pem')
_RENDER_SERVICE_ID = re.compile(r'srv-[a-z0-9]{20,40}')
_RENDER_HOSTNAME = re.compile(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+onrender\.com')
_RENDER_ENV_KEYS = {
    'RENDER', 'RENDER_SERVICE_TYPE', 'RENDER_SERVICE_ID', 'RENDER_INSTANCE_ID',
    'RENDER_EXTERNAL_HOSTNAME', 'RENDER_EXTERNAL_URL',
}


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


def _validate_provider(environ):
    trusted_proxy = environ.get('TRUSTED_PROXY')
    if trusted_proxy == 'render':
        instance_id = environ.get('RENDER_INSTANCE_ID', '')
        hostname = environ.get('RENDER_EXTERNAL_HOSTNAME', '')
        external_url = f'https://{hostname}'
        if (environ.get('RENDER') != 'true'
                or environ.get('RENDER_SERVICE_TYPE') != 'web'
                or not _RENDER_SERVICE_ID.fullmatch(environ.get('RENDER_SERVICE_ID', ''))
                or not instance_id.strip() or len(instance_id) > 128
                or any(ord(char) < 32 or ord(char) == 127 for char in instance_id)
                or not _RENDER_HOSTNAME.fullmatch(hostname)
                or environ.get('RENDER_EXTERNAL_URL') != external_url
                or environ.get('PUBLIC_API_URL') != external_url
                or 'KOYEB_SERVICE_ID' in environ or 'KOYEB_INSTANCE_ID' in environ):
            raise ValueError('Invalid Render service identity')
        return 'render'

    if trusted_proxy == 'koyeb':
        if any(name in environ for name in _RENDER_ENV_KEYS):
            raise ValueError('Koyeb proxy does not match Render service identity')
        # Keep Koyeb's existing UUID-based identity checks.
        UUID(environ['KOYEB_SERVICE_ID'])
        UUID(environ['KOYEB_INSTANCE_ID'])
        return 'koyeb'

    raise ValueError('Unsupported trusted proxy')


def main():
    try:
        _validate_provider(os.environ)
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
