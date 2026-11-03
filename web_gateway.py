"""Same-origin HTTP gateway for the Wartix frontend and gRPC service."""

import json
import os
import sys
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import grpc

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
GRPC_HOST = os.environ.get("WARTIX_GRPC_HOST", "127.0.0.1")
GRPC_PORT = int(os.environ.get("WARTIX_GRPC_PORT", "50051"))
HTTP_HOST = os.environ.get("WARTIX_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("WARTIX_HTTP_PORT", "8000"))

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from generated import wartix_pb2 as pb
from generated import wartix_pb2_grpc as pb_grpc
from server.server_wartix import create_server


def _schedule_json(schedule):
    return {
        "jadwal_id": schedule.jadwal_id,
        "nama_film": schedule.nama_film,
        "jam_tayang": schedule.jam_tayang,
        "studio_id": schedule.studio_id,
        "total_kursi": schedule.total_kursi,
        "kursi_tersedia": schedule.kursi_tersedia,
        "kursi": [
            {
                "kursi_id": seat.kursi_id,
                "status": seat.status,
                "user_id": seat.user_id,
                "held_until": seat.held_until,
            }
            for seat in schedule.kursi
        ],
    }


def _status_json(status):
    return {
        "jadwal_id": status.jadwal_id,
        "kursi_id": status.kursi_id,
        "status": status.status,
        "user_id": status.user_id,
        "held_until": status.held_until,
    }


class WartixRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, stub, **kwargs):
        self.stub = stub
        super().__init__(*args, directory=str(FRONTEND_ROOT), **kwargs)

    def _json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    @staticmethod
    def _required(query, key):
        value = query.get(key, [""])[0].strip()
        if not value:
            raise ValueError(f"Parameter '{key}' wajib diisi")
        return value

    def _grpc_error(self, error):
        status = {
            grpc.StatusCode.NOT_FOUND: 404,
            grpc.StatusCode.INVALID_ARGUMENT: 400,
            grpc.StatusCode.FAILED_PRECONDITION: 409,
            grpc.StatusCode.ALREADY_EXISTS: 409,
            grpc.StatusCode.UNAVAILABLE: 503,
            grpc.StatusCode.DEADLINE_EXCEEDED: 504,
        }.get(error.code(), 502)
        self._json({"error": error.details() or error.code().name}, status)

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return super().do_GET()

        query = self._query()
        try:
            if path == "/api/schedules":
                schedules = self.stub.DaftarJadwal(pb.DaftarJadwalRequest(), timeout=5)
                self._json([_schedule_json(schedule) for schedule in schedules])
                return

            if path == "/api/schedule":
                jadwal_id = self._required(query, "jadwal_id")
                result = self.stub.GetJadwalStudio(pb.JadwalRequest(jadwal_id=jadwal_id), timeout=5)
                self._json(_schedule_json(result))
                return

            if path == "/api/status":
                jadwal_id = self._required(query, "jadwal_id")
                kursi_id = self._required(query, "kursi_id")
                result = self.stub.GetStatusKursi(
                    pb.KursiRequest(jadwal_id=jadwal_id, kursi_id=kursi_id), timeout=5
                )
                self._json(_status_json(result))
                return

            if path == "/api/stream-status":
                self._stream_status(query)
                return

            self._json({"error": "Endpoint API tidak ditemukan"}, 404)
        except ValueError as error:
            self._json({"error": str(error)}, 400)
        except grpc.RpcError as error:
            self._grpc_error(error)

    def _stream_status(self, query):
        jadwal_id = self._required(query, "jadwal_id")
        kursi_id = self._required(query, "kursi_id")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        stream = self.stub.StreamStatusKursi(
            pb.StreamStatusKursiRequest(jadwal_id=jadwal_id, kursi_id=kursi_id)
        )
        try:
            for status in stream:
                event = json.dumps(_status_json(status), ensure_ascii=False)
                self.wfile.write(f"data: {event}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, grpc.RpcError):
            pass
        finally:
            stream.cancel()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/book", "/api/cancel", "/api/confirm"}:
            self._json({"error": "Endpoint API tidak ditemukan"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("Ukuran request tidak valid")
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            request_id = str(body.get("request_id") or uuid.uuid4())
            jadwal_id = str(body.get("jadwal_id", "")).strip()
            kursi_id = str(body.get("kursi_id", "")).strip()
            user_id = str(body.get("user_id", "")).strip()
            if not jadwal_id or not kursi_id or not user_id:
                raise ValueError("jadwal_id, kursi_id, dan user_id wajib diisi")

            if path == "/api/book":
                result = self.stub.PesanKursi(
                    pb.PesanKursiRequest(
                        request_id=request_id,
                        jadwal_id=jadwal_id,
                        kursi_id=kursi_id,
                        user_id=user_id,
                    ),
                    timeout=5,
                )
                self._json({
                    "sukses": result.sukses,
                    "pesan": result.pesan,
                    "jadwal_id": result.jadwal_id,
                    "kursi_id": result.kursi_id,
                    "held_until": result.held_until,
                }, 200 if result.sukses else 409)
                return

            if path == "/api/cancel":
                result = self.stub.BatalPesanan(
                    pb.BatalPesananRequest(
                        request_id=request_id,
                        jadwal_id=jadwal_id,
                        kursi_id=kursi_id,
                        user_id=user_id,
                    ),
                    timeout=5,
                )
            else:
                result = self.stub.KonfirmasiPembayaran(
                    pb.BayarRequest(
                        request_id=request_id,
                        jadwal_id=jadwal_id,
                        kursi_id=kursi_id,
                        user_id=user_id,
                    ),
                    timeout=5,
                )
            self._json({
                "sukses": result.sukses,
                "pesan": result.pesan,
                "jadwal_id": result.jadwal_id,
                "kursi_id": result.kursi_id,
            }, 200 if result.sukses else 409)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as error:
            self._json({"error": str(error)}, 400)
        except grpc.RpcError as error:
            self._grpc_error(error)


def _connect_backend():
    target = f"{GRPC_HOST}:{GRPC_PORT}"
    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=1.5)
        return channel, None
    except grpc.FutureTimeoutError:
        channel.close()

    backend, _ = create_server(port=GRPC_PORT, max_workers=20)
    backend.start()
    channel = grpc.insecure_channel(target)
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
    except grpc.FutureTimeoutError:
        backend.stop(grace=0)
        channel.close()
        raise RuntimeError(f"Backend gRPC tidak tersedia pada {target}")
    return channel, backend


def main():
    channel, backend = _connect_backend()
    stub = pb_grpc.LayananWartixStub(channel)
    handler = lambda *args, **kwargs: WartixRequestHandler(*args, stub=stub, **kwargs)
    httpd = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), handler)
    httpd.daemon_threads = True
    print(f"Wartix aktif di http://localhost:{HTTP_PORT}")
    print(f"Gateway HTTP terhubung ke gRPC {GRPC_HOST}:{GRPC_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Menutup gateway Wartix...")
    finally:
        httpd.shutdown()
        httpd.server_close()
        channel.close()
        if backend is not None:
            backend.stop(grace=1)


if __name__ == "__main__":
    main()
