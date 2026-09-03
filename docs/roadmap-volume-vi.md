# ATEP Volume VI - Electric Vehicle Roadmap

| Increment | Outcome | Status |
|---|---|---|
| VI-1 | Persistent battery pack, bounded cell model, SOC/SOH, deterministic thermal behavior, BMS protection, RBAC, audit, and outbox | Implemented |
| VI-2 | Motor torque, inverter efficiency, electrical power, and drive-mode limits | Planned |
| VI-3 | Regenerative-braking strategy and blended friction braking | Planned |
| VI-4 | AC/DC charging sessions, charge curves, limits, and fault handling | Planned |
| VI-5 | Active thermal-management loops for battery, motor, and cabin | Planned |
| VI-6 | Range and energy-consumption estimation across reproducible drive cycles | Planned |
| VI-7 | Cross-domain EV scenarios integrating BMS ECU, CAN, UDS, tests, and evidence | Planned |

VI-1 creates a vehicle-scoped battery aggregate without replacing the lighter battery projection
owned by Volume II. A pack contains 4 to 192 deterministic cell states, LFP or NMC chemistry,
nominal capacity and voltage, internal resistance, SOC, SOH, pack voltage/current/temperature,
logical simulation time, contactor state, and BMS operating state.

Battery steps use commanded current where positive current means discharge and negative current
means charge. Coulomb counting updates SOC, an explicit lumped thermal model updates temperature,
and BMS thresholds select normal, warning, or protection behavior. Protection opens the contactors
and makes delivered current zero. Commands use optimistic versioning, exact replay, stable changed-
reuse conflicts, bounded inputs, minimized audit/outbox evidence, and no wall-clock simulation loop.

The recommended next increment is VI-2: motor, inverter, torque delivery, efficiency maps, and
power limits derived from the battery's available electrical state.
