"""Client engine integration tests, including endpoint failover under concurrency."""

import concurrent.futures
import socket
import tempfile
import unittest
from pathlib import Path

from client.benchmark import benchmark_concurrency, write_report
from client.engine import WartixClient
from server.server_wartix import LayananWartixServicer, create_server


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
            schedule = client.get_schedule("SHOW_0800_ST1")
            self.assertEqual(schedule.kursi_tersedia, 60)

            held = client.book_seat("SHOW_0800_ST1", "A1", "user-test")
            self.assertTrue(held.sukses)
            self.assertEqual(client.get_seat_status("SHOW_0800_ST1", "A1").status, "PENDING_PAYMENT")

            paid = client.confirm_payment("SHOW_0800_ST1", "A1", "user-test")
            self.assertTrue(paid.sukses)
            self.assertEqual(client.get_seat_status("SHOW_0800_ST1", "A1").status, "BOOKED")

    def test_multiple_clients_fail_over_to_live_endpoint(self):
        unavailable = self.unused_port()
        with WartixClient(
            [f"127.0.0.1:{unavailable}", f"127.0.0.1:{self.port}"],
            timeout=0.25,
            max_retries=1,
            backoff_initial=0,
            backoff_max=0,
        ) as client:
            def reserve(index):
                return client.book_seat("SHOW_0800_ST1", "A1", f"user-{index}").sukses

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                outcomes = list(executor.map(reserve, range(5)))

        self.assertEqual(sum(outcomes), 1)

    def test_benchmark_writes_csv_and_graph_report(self):
        with WartixClient([f"127.0.0.1:{self.port}"]) as client:
            results = benchmark_concurrency(client, (1, 5, 20), requests_per_level=3)

        self.assertEqual([result["clients"] for result in results], [1, 5, 20])
        self.assertTrue(all(result["successful"] == 3 for result in results))
        self.assertTrue(all(result["throughput_rps"] > 0 for result in results))
        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path, html_path = write_report(results, Path(temporary_directory))
            self.assertTrue(csv_path.is_file())
            self.assertIn("<svg", html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
