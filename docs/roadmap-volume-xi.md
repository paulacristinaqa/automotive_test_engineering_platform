# Volume XI Virtual Test Bench Roadmap

Volume XI brings ATEP closer to an automotive system-test bench. Each increment keeps the
deterministic ATEP evidence model and adds the artifacts and workflows used with Vector CANoe,
vTESTstudio and HiL benches.

- [x] **XI-1 Real CAN stack and Vector artifacts** - DBC export, ASC and BLF trace export,
  python-can bench bus with allowlisted interfaces, deterministic and real-time replay, and a
  virtual bench demo cross-checked with an independent DBC implementation.
- [x] **XI-2 ECU communication** - ISO-TP (ISO 15765-2) with flow control, a UDS tester with
  P2/P2* timing, a virtual ECU diagnostic server, cyclic message timeout supervision, E2E
  protection with alive counter and CRC-8, fault injection, and a deterministic simulated link.
- [x] **XI-3 Virtual airbag control unit** - device under test with squib loop resistance
  monitoring, a two-sensor deployment decision, warning lamp and self-test, energy reserve,
  debounced DTCs, E2E-protected status and crash messages, UDS diagnostics, and a 15-case
  system-test campaign.
- [x] **XI-4 Bench instruments** - SCPI layer with error queue; programmable supply with
  ISO 16750-2-style profiles (momentary drop, dropout, starting profile, slow decrease and
  increase, overvoltage); relay card for KL15; fault-injection box (open, shorts, substitute
  resistance); multimeter; climate chamber; ACU current model; 15-case HiL campaign.
- [x] **XI-5 Transients and EMC concepts** - SCPI transient generator (ISO 7637-2-style pulses
  1, 2a, 3a, 3b and load dump 5b), ACU input protection with a latched firing inhibit, CAN error
  frames with retransmission and bus-off, functional status classification A-E, and a 7-case EMC
  campaign with a test plan. Conceptual only; no real EMC measurement.
- [x] **XI-6 vTESTstudio-style authoring** - event-driven test units (`on_message`, `on_timer`,
  `wait_for_signal`, `expect_diag`), JSON test tables with parameters, worst-wins verdicts,
  CANoe-style XML, JUnit, HTML and traceability CSV reports, and a requirement coverage matrix.
- [x] **XI-7 System test campaign** - test plan and specification mapped to Automotive SPICE
  SYS.5, test object and environment identification, six exit criteria, release recommendation,
  defect drafts, an evidence manifest, and seeded-defect variants that block the release.

## Status

Volume XI is complete. The next planned volume is Volume XII DevOps.

Candidate follow-ups for the bench, not yet planned: export arbitration batches and multi-bus
campaigns as traces; store campaign evidence through the ATEP artifact API; ReqIF export of
the traceability matrix.
