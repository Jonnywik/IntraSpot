"""Malformed version preconditions must not become server errors."""
import pytest

from app.core.errors import DomainError
from app.domains.announcements.report_routes import _parse_if_match


@pytest.mark.parametrize('value', ['"' + '9' * 4500 + '"', '"2147483648"', '"9999999999"', 'W/"1"'])
def test_invalid_report_version_is_a_controlled_conflict(value):
    with pytest.raises(DomainError) as caught:
        _parse_if_match(value, required=True)
    assert caught.value.status == 409
    assert caught.value.code == 'announcement_version_invalid'
    assert value not in caught.value.message


@pytest.mark.parametrize('version', [1, 2147483647])
def test_current_integer_range_version_header_is_accepted(version):
    assert _parse_if_match(f'"{version}"', required=True) == version
