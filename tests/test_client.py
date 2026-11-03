"""Client engine integration tests, including endpoint failover under concurrency."""

import concurrent.futures
import socket
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import grpc

from client.benchmark import benchmark_concurrency, write_report
from client.engine import WartixClient
from generated import wartix_pb2 as pb
from server.server_wartix import LayananWartixServicer, create_server


class RetryableRpcError(grpc.RpcError):
    def code(self):
        return grpc.StatusCode.UNAVAILABLE


class TestWartixClient(unittest.TestCase):
    def setUp(self):
        self.port = self.unused_port()
        self.server, _ = create_server(port=self.port, max_workers=10, servicer=LayananWartixServicer())
        self.server.start()

    def tearDown(self):
        self.server.stop(grace=0).wait()

    @staticmethod
    def unused_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def test_interactive_client_operations(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            schedule = client.get_schedule("SHOW_1300_ST1")
            self.assertEqual(schedule.kursi_tersedia, 60)

            held = client.book_seat("SHOW_1300_ST1", "A1", "user-test")
            self.assertTrue(held.sukses)
            self.assertEqual(client.get_seat_status("SHOW_1300_ST1", "A1").status, "PENDING_PAYMENT")

            paid = client.confirm_payment("SHOW_1300_ST1", "A1", "user-test")
            self.assertTrue(paid.sukses)
            self.assertEqual(client.get_seat_status("SHOW_1300_ST1", "A1").status, "BOOKED")

    def test_stream_seat_status_reports_initial_and_changed_statuses(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            stream = client.stream_seat_status(
                "SHOW_1300_ST1", "A1", timeout=5.0
            )
            try:
                self.assertEqual(next(stream).status, "AVAILABLE")

                held = client.book_seat("SHOW_1300_ST1", "A1", "stream-user")
                self.assertTrue(held.sukses)
                self.assertEqual(next(stream).status, "PENDING_PAYMENT")

                paid = client.confirm_payment("SHOW_1300_ST1", "A1", "stream-user")
                self.assertTrue(paid.sukses)
                self.assertEqual(next(stream).status, "BOOKED")
            finally:
                stream.cancel()

    def test_stream_seat_status_rejects_unknown_seat(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            stream = client.stream_seat_status(
                "SHOW_1300_ST1", "Z99", timeout=2.0
            )
            with self.assertRaises(grpc.RpcError) as error:
                next(stream)
            self.assertEqual(error.exception.code().name, "NOT_FOUND")

    def test_multiple_clients_fail_over_to_live_endpoint(self):
        unavailable = self.unused_port()
        endpoints = [f"127.0.0.1:{unavailable}", f"127.0.0.1:{self.port}"]

        def reserve(index):
            with WartixClient(
                endpoints,
                timeout=0.25,
                max_retries=1,
                backoff_initial=0,
                backoff_max=0,
            ) as client:
                return client.book_seat(
                    "SHOW_1300_ST1", "A1", f"user-{index}"
                ).sukses

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            outcomes = list(executor.map(reserve, range(5)))

        self.assertEqual(sum(outcomes), 1)

    def test_multi_port_failover_after_primary_server_stops(self):
        secondary_port = self.unused_port()
        secondary_server, _ = create_server(port=secondary_port, max_workers=10)
        secondary_server.start()
        endpoints = [
            f"127.0.0.1:{self.port}",
            f"127.0.0.1:{secondary_port}",
        ]
        try:
            with WartixClient(endpoints, max_retries=1, backoff_initial=0) as client:
                self.assertEqual(
                    client.get_seat_status("SHOW_1300_ST1", "A1").status,
                    "AVAILABLE",
                )
                self.assertEqual(
                    client.get_seat_status("SHOW_1300_ST1", "A1").status,
                    "AVAILABLE",
                )

            self.server.stop(grace=0).wait()
            with WartixClient(
                endpoints,
                timeout=0.25,
                max_retries=1,
                backoff_initial=0,
                backoff_max=0,
            ) as failover_client:
                status = failover_client.get_seat_status(
                    "SHOW_1300_ST1", "A1"
                )
            self.assertEqual(status.status, "AVAILABLE")
        finally:
            secondary_server.stop(grace=0).wait()

    def test_transaction_retries_use_timeout_backoff_and_stable_request_id(self):
        class RecordingStub:
            def __init__(self):
                self.requests = []
                self.timeouts = []
                self.failures_remaining = 3

            def PesanKursi(self, request, timeout):
                self.requests.append(request)
                self.timeouts.append(timeout)
                if self.failures_remaining:
                    self.failures_remaining -= 1
                    raise RetryableRpcError()
                return pb.PesanKursiResponse(sukses=True)

        with WartixClient(
            [f"127.0.0.1:{self.port}"],
            backoff_initial=0.1,
            backoff_max=0.25,
        ) as client:
            stub = RecordingStub()
            client._stubs = [stub]
            with patch("client.engine.time.sleep") as sleep:
                first = client.book_seat("SHOW_1300_ST1", "A1", "retry-user")
                second = client.book_seat("SHOW_1300_ST1", "A2", "retry-user")

        self.assertTrue(first.sukses)
        self.assertTrue(second.sukses)
        first_request_ids = {request.request_id for request in stub.requests[:4]}
        self.assertEqual(len(first_request_ids), 1)
        first_request_id = first_request_ids.pop()
        self.assertEqual(uuid.UUID(first_request_id).version, 4)
        self.assertNotEqual(first_request_id, stub.requests[4].request_id)
        self.assertEqual(stub.timeouts, [2.0] * 5)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [0.1, 0.2, 0.25],
        )

    def test_benchmark_writes_csv_and_graph_report(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            results = benchmark_concurrency(client, (1, 5, 20), requests_per_level=20)

        self.assertEqual([result["clients"] for result in results], [1, 5, 20])
        self.assertTrue(all(result["successful"] == 20 for result in results))
        self.assertTrue(all(result["throughput_rps"] > 0 for result in results))
        self.assertTrue(all(result["latency_mean_ms"] > 0 for result in results))
        self.assertTrue(all(result["latency_p50_ms"] > 0 for result in results))
        self.assertTrue(all(result["latency_p95_ms"] > 0 for result in results))
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path, html_path = write_report(results, Path(temporary_directory))
            self.assertTrue(csv_path.is_file())
            self.assertIn("<svg", html_path.read_text(encoding="utf-8"))

    def test_benchmark_requires_enough_requests_for_all_clients(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            with self.assertRaisesRegex(ValueError, "at least 5"):
                benchmark_concurrency(client, (1, 5), requests_per_level=4)


if __name__ == "__main__":
    unittest.main()
