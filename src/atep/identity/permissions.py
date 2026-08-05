from enum import StrEnum


class PermissionName(StrEnum):
    USERS_READ = "users:read"
    USERS_WRITE = "users:write"
    ROLES_MANAGE = "roles:manage"
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"
    MODULES_READ = "modules:read"
    MODULES_MANAGE = "modules:manage"
    VEHICLES_READ = "vehicles:read"
    VEHICLES_MANAGE = "vehicles:manage"
    TELEMETRY_READ = "telemetry:read"
    VEHICLE_COMMANDS_READ = "vehicle_commands:read"
    VEHICLE_COMMANDS_WRITE = "vehicle_commands:write"
    PLATFORM_ADMIN = "platform:admin"


ADMIN_PERMISSIONS = frozenset(PermissionName)
