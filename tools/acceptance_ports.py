"""Host ports of the disposable proxy acceptance fixtures.

The defaults are the documented ports. Each can be moved with an environment
variable, because Windows (Hyper-V/WinNAT) may reserve dynamic port ranges that
include them; `run_integration_tests.ps1` sets the same variables for Docker
Compose and these tools.
"""

import os

PROXY_HTTP = ("ATEP_ACCEPTANCE_PROXY_PORT", 18800)
PROXY_REPLICA_A = ("ATEP_ACCEPTANCE_REPLICA_A_PORT", 18801)
PROXY_REPLICA_B = ("ATEP_ACCEPTANCE_REPLICA_B_PORT", 18802)
PROXY_TLS = ("ATEP_ACCEPTANCE_TLS_PORT", 18443)


def port(setting: tuple[str, int]) -> int:
    """The configured host port, or the default when the variable is unset."""
    variable, default = setting
    raw = os.environ.get(variable, "").strip()
    if not raw:
        return default
    if not raw.isdigit() or not 1024 <= int(raw) <= 65535:
        raise ValueError(f"{variable} must be a port between 1024 and 65535, got {raw!r}")
    return int(raw)
