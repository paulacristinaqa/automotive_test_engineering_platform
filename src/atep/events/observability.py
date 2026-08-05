from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    start_http_server,
)


class OutboxObservability:
    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        PlatformCollector(registry=self.registry)
        ProcessCollector(registry=self.registry)
        self.publication_attempts = Counter(
            "atep_outbox_publication_attempts_total",
            "RabbitMQ outbox publication attempts by bounded outcome.",
            ("outcome",),
            registry=self.registry,
        )
        self.batch_duration = Histogram(
            "atep_outbox_batch_duration_seconds",
            "Duration of one transactional outbox publication batch.",
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
            registry=self.registry,
        )
        self.unpublished_events = Gauge(
            "atep_outbox_unpublished_events",
            "Current number of unpublished transactional outbox events.",
            registry=self.registry,
        )
        self.oldest_unpublished_age = Gauge(
            "atep_outbox_oldest_unpublished_age_seconds",
            "Age in seconds of the oldest unpublished outbox event.",
            registry=self.registry,
        )
        self.worker_up = Gauge(
            "atep_outbox_worker_up",
            "Whether the outbox worker loop has initialized.",
            registry=self.registry,
        )
        self.worker_up.set(0)

    def start_server(self, port: int) -> None:
        start_http_server(port, addr="0.0.0.0", registry=self.registry)

    def update_backlog(self, *, count: int, oldest_age_seconds: float) -> None:
        self.unpublished_events.set(count)
        self.oldest_unpublished_age.set(oldest_age_seconds)
