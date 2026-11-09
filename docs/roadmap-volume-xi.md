# Volume XI Virtual Test Bench Roadmap

Volume XI brings ATEP closer to an automotive system-test bench. Each increment keeps the
deterministic ATEP evidence model and adds the artifacts and workflows used with Vector CANoe,
vTESTstudio and HiL benches.

- [x] **XI-1 Real CAN stack and Vector artifacts** - DBC export, ASC and BLF trace export,
  python-can bench bus with allowlisted interfaces, deterministic and real-time replay, and a
  virtual bench demo cross-checked with an independent DBC implementation.
- [ ] **XI-2 ECU communication** - ISO-TP (ISO 15765-2), UDS over CAN frames with P2/P2* timing,
  cyclic messages with timeout supervision, and E2E protection with alive counter and CRC.
- [ ] **XI-3 Virtual airbag control unit** - device under test with squib loop resistance
  monitoring, crash sensors, warning lamp, start-up self-test, DTCs and crash output message.
- [ ] **XI-4 Bench instruments** - programmable power supply (KL30/KL15, undervoltage, cranking,
  overvoltage profiles), fault-injection box, multimeter and climate chamber with SCPI-style
  commands.
- [ ] **XI-5 Transients and EMC concepts** - voltage transient pulses and bus disturbances judged
  by functional status class. Conceptual only; no real EMC measurement.
- [ ] **XI-6 vTESTstudio-style authoring** - event-driven test units (`on_message`, `on_timer`,
  `wait_for_signal`), test tables, verdicts, HTML/XML reports and ALM traceability export.
- [ ] **XI-7 System test campaign** - test specification, plan, execution on the virtual bench,
  report and traceability matrix for the virtual airbag control unit.

## Next recommended increment

XI-2 ECU communication. It reuses the XI-1 bench bus and makes diagnostic tests run over real
CAN frames instead of direct API calls.
