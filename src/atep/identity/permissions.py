from enum import StrEnum


class PermissionName(StrEnum):
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    ROLES_MANAGE = "roles:manage"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    MODULES_READ = "modules:read"
    MODULES_MANAGE = "modules:manage"
    PLATFORM_ADMIN = "platform:admin"


ADMIN_PERMISSIONS = frozenset(PermissionName)
