"""Integration checks for the gRPC seat status stream."""

import socket
import unittest
import uuid

import grpc

from generated import wartix_pb2 as pb
from generated import wartix_pb2_grpc as pb_grpc
from server.server_wartix import create_server


class TestStreamStatusKursi(unittest.TestCase):
    def test_stream_emits_hold_and_cancel_transitions(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]

        server, _ = create_server(port=port)
        server.start()
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = pb_grpc.LayananWartixStub(channel)
        stream = None
        try:
            stream = stub.StreamStatusKursi(
                pb.StreamStatusKursiRequest(jadwal_id="SHOW_1200_ST1", kursi_id="A1"),
                timeout=10,
            )
            initial = next(stream)
            hold = stub.PesanKursi(
                pb.PesanKursiRequest(
                    request_id=str(uuid.uuid4()),
                    jadwal_id="SHOW_1200_ST1",
                    kursi_id="A1",
                    user_id="stream-check",
                ),
                timeout=3,
            )
            after_hold = next(stream)
            cancel = stub.BatalPesanan(
                pb.BatalPesananRequest(
                    request_id=str(uuid.uuid4()),
                    jadwal_id="SHOW_1200_ST1",
                    kursi_id="A1",
                    user_id="stream-check",
                ),
                timeout=3,
            )
            after_cancel = next(stream)

            self.assertEqual(initial.status, "AVAILABLE")
            self.assertTrue(hold.sukses)
            self.assertEqual(after_hold.status, "PENDING_PAYMENT")
            self.assertTrue(cancel.sukses)
            self.assertEqual(after_cancel.status, "AVAILABLE")
        finally:
            if stream is not None:
                stream.cancel()
            channel.close()
            server.stop(grace=0).wait()


if __name__ == "__main__":
    unittest.main()
