# X-7.10 — Engineering panel and session ownership

The companion showcase now renders a Compose dashboard panel wired to the native
transport. It accepts a temporary operator token and its actual remaining lifetime,
offers three views and explicit connect/disconnect. This is not a new login API or
end-user login flow. Tokens remain memory-only and are cleared from the form on
submission; local disconnection does not revoke the server token.

An owner-thread session coordinator invalidates queued old callbacks and closes
replaced transports. Activity onStop clears drafts, evidence and the connection;
return/rotation requires an explicit new connection. A bounded 12,000-character
preview exposes query-time metadata and explicitly marks truncated output.

Four companion tests cover ownership/cleanup races. Compilation and unit evidence
do not establish device lifecycle, visual accessibility or AAOS acceptance.
Next is real backend/AAOS acceptance: form interaction, background/return, permission
loss, expiry, stale data and normal session completion. Use parked/test environments;
the engineering panel is not a distraction-optimized or road-approved UI.

No backend runtime change, production dependency or paid service. DOCX unchanged.

Companion evidence: 57 JVM tests passed (four new), lint zero errors/15 warnings,
debug APK successful in 1m 2s with one worker. Visual/device acceptance not run.
