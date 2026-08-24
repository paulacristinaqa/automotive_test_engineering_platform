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
    DIGITAL_VEHICLE_READ = "digital_vehicle:read"
    DIGITAL_VEHICLE_WRITE = "digital_vehicle:write"
    ECUS_READ = "ecus:read"
    ECUS_MANAGE = "ecus:manage"
    TEST_RUNS_READ = "test_runs:read"
    TEST_RUNS_WRITE = "test_runs:write"
    ENVIRONMENT_PROFILES_READ = "environment_profiles:read"
    ENVIRONMENT_PROFILES_MANAGE = "environment_profiles:manage"
    TEST_JOBS_READ = "test_jobs:read"
    TEST_JOBS_MANAGE = "test_jobs:manage"
    TEST_ARTIFACTS_READ = "test_artifacts:read"
    TEST_ARTIFACTS_WRITE = "test_artifacts:write"
    PLATFORM_ADMIN = "platform:admin"


ADMIN_PERMISSIONS = frozenset(PermissionName)
