import socket
import socketserver
import threading
from collections.abc import Iterator

import pytest

from tools.aaos_network_proxy import LoopbackFaultProxy


class Echo(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(2)
        try:
            while data := self.request.recv(1024):
                self.request.sendall(data)
        except OSError:
            return


@pytest.fixture
def upstream() -> Iterator[int]:
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Echo) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(2)
            assert not thread.is_alive()


def test_forward_pause_restore_and_cut(upstream: int) -> None:
    with LoopbackFaultProxy(port=0, upstream_port=upstream) as proxy:
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            client.sendall(b"initial")
            assert client.recv(1024) == b"initial"
            assert proxy.accepted == 1
            proxy.pause()
            client.sendall(b"retained")
            client.settimeout(0.25)
            with pytest.raises(TimeoutError):
                client.recv(1024)
            proxy.restore()
            client.settimeout(2)
            assert client.recv(1024) == b"retained"
            proxy.cut()
            assert client.recv(1024) == b""
        proxy.restore()
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            client.sendall(b"fresh")
            assert client.recv(1024) == b"fresh"
            assert proxy.accepted == 2


def test_close_releases_listener_and_connections(upstream: int) -> None:
    proxy = LoopbackFaultProxy(port=0, upstream_port=upstream)
    with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
        client.sendall(b"ready")
        assert client.recv(1024) == b"ready"
        proxy.close()
        assert client.recv(1024) == b""
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", proxy.port), timeout=0.2)


def test_broken_proxy_rejects_connections(upstream: int) -> None:
    with LoopbackFaultProxy(port=0, upstream_port=upstream) as proxy:
        proxy.cut()
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            assert client.recv(1024) == b""
        assert proxy.accepted == 1


def test_lifetime_connection_budget_is_bounded(upstream: int) -> None:
    with LoopbackFaultProxy(port=0, upstream_port=upstream) as proxy:
        for _ in range(4):
            with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                client.sendall(b"bounded")
                assert client.recv(1024) == b"bounded"
        with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
            assert client.recv(1024) == b""
        assert proxy.accepted == 5


def test_timestamp_history_is_bounded_and_immutable(upstream: int) -> None:
    with LoopbackFaultProxy(port=0, upstream_port=upstream) as proxy:
        proxy.cut()
        for _ in range(20):
            with socket.create_connection(("127.0.0.1", proxy.port), timeout=2) as client:
                assert client.recv(1024) == b""
        assert proxy.accepted == 20
        timestamps = proxy.accepted_at
        assert isinstance(timestamps, tuple)
        assert len(timestamps) == 16
        assert timestamps == tuple(sorted(timestamps))
