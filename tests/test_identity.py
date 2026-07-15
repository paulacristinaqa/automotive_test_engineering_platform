from atep.identity.permissions import ADMIN_PERMISSIONS, PermissionName
from atep.identity.service import normalize_email


def test_email_is_normalized_for_identity_lookup() -> None:
    assert normalize_email("  Engineer@Example.COM ") == "engineer@example.com"


def test_administrator_permission_set_is_explicit() -> None:
    assert ADMIN_PERMISSIONS == frozenset(PermissionName)
    assert PermissionName.PLATFORM_ADMIN in ADMIN_PERMISSIONS
