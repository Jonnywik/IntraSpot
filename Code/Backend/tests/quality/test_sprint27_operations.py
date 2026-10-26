from datetime import timedelta
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
import pytest

from app.db.models import now
from app.hosted_entrypoint import prepare_ca
from app.operations_models import MaintenanceState
from tests.shared.test_sprint25_configuration import hosted_settings


def test_public_health_private_operations(client, make_user, token_for, db):
    db.add(MaintenanceState(name='events', last_error_code='database_unavailable'))
    db.commit()
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/ready').json() == {'status': 'ready'}
    assert client.get('/api/v1/platform/operations').status_code == 401
    member = make_user()
    assert client.get('/api/v1/platform/operations', headers={'Authorization': f'Bearer {token_for(member)}'}).status_code == 403
    admin = make_user(platform_admin=True)
    result = client.get('/api/v1/platform/operations', headers={'Authorization': f'Bearer {token_for(admin)}'})
    assert result.status_code == 200
    assert result.json()['maintenance'][0]['last_error_code'] == 'database_unavailable'
    assert result.json()['pending_receipts'] == 0


@pytest.mark.parametrize('changes', [
    {'rate_limit_enabled': False}, {'maintenance_enabled': False},
    {'rate_limit_secret': None}, {'rate_limit_secret': 'short'}, {'trusted_proxy': 'none'},
])
def test_hosted_guards_are_required(tmp_path, changes):
    with pytest.raises(ValueError):
        hosted_settings(tmp_path, **changes)


def test_public_ca_materialized_without_secret(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Fictional database CA')])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now()-timedelta(days=1))
            .not_valid_after(now()+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256()))
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    environ = {'SUPABASE_DATABASE_CA_PEM': pem}
    path = tmp_path / 'ca.pem'
    prepare_ca(environ, path)
    assert path.read_text() == pem and 'SUPABASE_DATABASE_CA_PEM' not in environ
    with pytest.raises(ValueError):
        prepare_ca({'SUPABASE_DATABASE_CA_PEM': 'PRIVATE KEY'}, path)
