"""Bounded loopback-only TCP fault fixture. Never logs or persists wire data."""

import select
import socket
import threading
import time
from types import TracebackType


class LoopbackFaultProxy:
    def __init__(self, port: int = 18001, upstream_port: int = 18000) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._mode = "normal"
        self._peers: dict[socket.socket, socket.socket] = {}
        self._accepted = 0
        self._accepted_at: list[float] = []
        self._upstream_port = upstream_port
        self._listener = socket.socket()
        try:
            self._listener.bind(("127.0.0.1", port))
            self._listener.listen(4)
            self._listener.settimeout(0.5)
        except BaseException:
            self._listener.close()
            raise
        self.port = int(self._listener.getsockname()[1])
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    @property
    def accepted(self) -> int:
        with self._lock:
            return self._accepted

    def pause(self) -> None:
        with self._lock:
            self._mode = "paused"

    @property
    def accepted_at(self) -> tuple[float, ...]:
        with self._lock:
            return tuple(self._accepted_at)

    def restore(self) -> None:
        with self._lock:
            self._mode = "normal"

    def cut(self) -> None:
        with self._lock:
            self._mode = "broken"
            peers = list(self._peers)
        for peer in peers:
            self._drop(peer)

    def _drop(self, connection: socket.socket) -> None:
        with self._lock:
            peer = self._peers.pop(connection, None)
            if peer is not None:
                self._peers.pop(peer, None)
        for item in (connection, peer):
            if item is not None:
                try:
                    item.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                item.close()

    def _serve(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                reads = [self._listener]
                if self._mode == "normal":
                    reads += list(self._peers)
            try:
                ready, _, _ = select.select(reads, [], [], 0.1)
            except (OSError, ValueError):
                continue
            for source in ready:
                if source is self._listener:
                    try:
                        client, _ = self._listener.accept()
                        with self._lock:
                            self._accepted += 1
                            if len(self._accepted_at) < 16:
                                self._accepted_at.append(time.monotonic())
                            allowed = self._mode == "normal" and self._accepted <= 4
                        if not allowed:
                            client.close()
                            continue
                        try:
                            upstream = socket.create_connection(
                                ("127.0.0.1", self._upstream_port), timeout=0.5
                            )
                        except OSError:
                            client.close()
                            continue
                        client.settimeout(0.5)
                        upstream.settimeout(0.5)
                        with self._lock:
                            allowed = self._mode == "normal" and not self._stop.is_set()
                            if allowed:
                                self._peers[client] = upstream
                                self._peers[upstream] = client
                        if not allowed:
                            client.close()
                            upstream.close()
                    except OSError:
                        continue
                else:
                    with self._lock:
                        target = self._peers.get(source)
                        normal = self._mode == "normal"
                    if not normal or target is None:
                        continue
                    try:
                        data = source.recv(65_536)
                        if not data:
                            self._drop(source)
                        else:
                            target.sendall(data)
                    except OSError:
                        self._drop(source)

    def close(self) -> None:
        self._stop.set()
        self._listener.close()
        self._thread.join(timeout=2)
        self.cut()
        if self._thread.is_alive():
            raise RuntimeError("Loopback proxy did not stop")

    def __enter__(self) -> "LoopbackFaultProxy":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
