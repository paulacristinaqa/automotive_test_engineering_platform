# Performance and Stress Testing

Volume VIII-4 adds bounded, reproducible performance profiles and immutable execution evidence. The
API stores workload intent and externally measured results; it does not run a load generator inside
the web process.

Profiles distinguish performance from stress intent. Up to twelve stages define duration, virtual
users, and request rate. Resource limits cap execution at four CPU cores, 4096 MB, one hour, 500
virtual users, and 1000 requests per second. GPU use is prohibited.

Thresholds use explicit minimum or maximum operators. An execution passes only when every threshold
passes. A prior terminal execution using the same profile may be selected as a baseline; the stored
comparison preserves baseline, current value, and signed delta for every shared metric.

Hosted CI remains the preferred place for meaningful load execution. Local tests validate contracts,
aggregation, persistence, and historical comparison without generating load.
