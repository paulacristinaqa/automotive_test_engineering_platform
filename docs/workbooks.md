# ATEP Engineering Workbook Index

ATEP maintains one engineering workbook per project volume. This prevents platform-infrastructure
decisions from becoming mixed with vehicle, protocol, diagnostics, test-framework, or AI domain
decisions while preserving cross-volume traceability.

| Volume | Domain | Status | Editable source | Formatted workbook |
|---|---|---|---|---|
| I | Core Platform | Active baseline | `docs/workbook-volume-i.md` | `docs/ATEP_Volume_I_Core_Platform_Engineering_Workbook.docx` |
| II | Digital Vehicle | II-1 through II-6 implemented | `docs/workbook-volume-ii.md` | `docs/ATEP_Volume_II_Digital_Vehicle_Engineering_Workbook.docx` |
| III | ECU Simulator | III-1 through III-7 implemented | `docs/workbook-volume-iii.md` | `docs/ATEP_Volume_III_ECU_Simulator_Engineering_Workbook.docx` |
| IV | CAN Network | IV-1 through IV-7 implemented | `docs/workbook-volume-iv.md` | `docs/ATEP_Volume_IV_CAN_Network_Engineering_Workbook.docx` |
| V | Diagnostics | V-1 through V-5 implemented | `docs/workbook-volume-v.md` | `docs/ATEP_Volume_V_Diagnostics_Engineering_Workbook.docx` |
| VI | Electric Vehicle | Planned | To be created when development begins | To be created |
| VII | ADAS | Planned | To be created when development begins | To be created |
| VIII | Test Framework | Planned | To be created when development begins | To be created |
| IX | AI Test Engineer | Planned | To be created when development begins | To be created |
| X | Dashboard | Planned | To be created when development begins | To be created |
| XI | DevOps | Planned | To be created when development begins | To be created |
| XII | Enterprise Features | Planned | To be created when development begins | To be created |

## Ownership Rules

- Volume I owns shared platform infrastructure: identity, RBAC, persistence, messaging, audit,
  observability, delivery, security, and operational controls.
- Volume II owns the Digital Vehicle domain: aggregate state, simulation time, components, sensors,
  actuators, deterministic dynamics, and multi-vehicle sessions.
- Volume III owns ECU identity, lifecycle, memory, faults, deterministic execution, and future
  controller behavior profiles.
- Volume IV owns CAN topology, frame identifiers, payload contracts, logical bus time, and future
  arbitration, DBC, CAN FD, and network-fault behavior.
- Cross-volume integrations are referenced from both relevant workbooks, but the detailed design
  belongs to the workbook that owns the behavior.
- Historical revision entries remain in the workbook where they were originally recorded; new
  domain detail is maintained only in its owning workbook.
