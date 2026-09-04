# ATEP Volume VI - Electric Vehicle Roadmap

| Increment | Outcome | Status |
|---|---|---|
| VI-1 | Persistent battery pack, bounded cell model, SOC/SOH, deterministic thermal behavior, BMS protection, RBAC, audit, and outbox | Implemented |
| VI-2 | Motor torque, inverter efficiency, electrical power, and drive-mode limits | Implemented |
| VI-3 | Regenerative-braking strategy and blended friction braking | Implemented |
| VI-4 | AC/DC charging sessions, charge curves, limits, and fault handling | Implemented |
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

VI-2 adds one motor/inverter aggregate per vehicle, bounded torque and speed, eco/normal/sport
drive modes, a deterministic efficiency surface, mechanical/electrical power, thermal losses,
motor and inverter temperature, protection, and battery-derived power limits. Negative torque is
deliberately rejected until VI-3 defines regenerative and blended braking semantics.

VI-3 adds one regenerative-braking aggregate per vehicle. It derives recoverable motor torque,
battery charge acceptance, regenerative and friction deceleration, recovered power and energy,
and the resulting battery SOC transition. Low speed, high SOC, unsafe battery temperature,
protection, or open contactors disable regeneration while preserving bounded friction braking.

VI-4 adds one charging-system aggregate per vehicle. Versioned commands control AC Type 2 and DC
CCS session start, deterministic energy-transfer steps, pause, resume, stop, injected faults, and
fault clearing. Charging power is constrained by connector capability, battery voltage/current,
temperature, BMS state, target SOC, remaining energy room, and a taper above 80% SOC.

The recommended next increment is VI-5: active thermal-management loops for the battery, motor,
inverter, and cabin.
