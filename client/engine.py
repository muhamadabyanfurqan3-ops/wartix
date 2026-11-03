"""gRPC client with bounded timeouts, retries, and endpoint failover."""

import threading
import time
import uuid
from typing import Iterable, Optional

import grpc

from generated import wartix_pb2 as pb
from generated import wartix_pb2_grpc as pb_grpc


class WartixClient:
    RETRYABLE_STATUS_CODES = {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
    }

    def __init__(
        self,
        endpoints: Iterable[str] = ("localhost:50051",),
        timeout: float = 2.0,
        max_retries: int = 3,
        backoff_initial: float = 0.1,
        backoff_max: float = 1.0,
    ):
        self.endpoints = tuple(endpoint.strip() for endpoint in endpoints if endpoint.strip())
        if not self.endpoints:
            raise ValueError("At least one gRPC endpoint is required")
        if timeout <= 0 or max_retries < 0 or backoff_initial < 0 or backoff_max < 0:
            raise ValueError("Timeout and retry settings must be non-negative; timeout must be positive")

        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self._channels = [grpc.insecure_channel(endpoint) for endpoint in self.endpoints]
        self._stubs = [pb_grpc.LayananWartixStub(channel) for channel in self._channels]
        self._rotation_lock = threading.Lock()
        self._next_endpoint = 0

    def _call(self, method_name: str, request):
        with self._rotation_lock:
            first_endpoint = self._next_endpoint
            self._next_endpoint = (self._next_endpoint + 1) % len(self._stubs)

        last_error = None
        for attempt in range(self.max_retries + 1):
            endpoint_index = (first_endpoint + attempt) % len(self._stubs)
            method = getattr(self._stubs[endpoint_index], method_name)
            try:
                return method(request, timeout=self.timeout)
            except grpc.RpcError as error:
                last_error = error
                if error.code() not in self.RETRYABLE_STATUS_CODES or attempt == self.max_retries:
                    raise
                delay = min(self.backoff_initial * (2 ** attempt), self.backoff_max)
                if delay:
                    time.sleep(delay)

        raise last_error

    def get_schedule(self, jadwal_id: str):
        return self._call("GetJadwalStudio", pb.JadwalRequest(jadwal_id=jadwal_id))

    def get_seat_status(self, jadwal_id: str, kursi_id: str):
        request = pb.KursiRequest(jadwal_id=jadwal_id, kursi_id=kursi_id)
        return self._call("GetStatusKursi", request)

    def book_seat(self, jadwal_id: str, kursi_id: str, user_id: str, request_id: Optional[str] = None):
        request = pb.PesanKursiRequest(
            request_id=request_id or str(uuid.uuid4()),
            jadwal_id=jadwal_id,
            kursi_id=kursi_id,
            user_id=user_id,
        )
        return self._call("PesanKursi", request)

    def confirm_payment(self, jadwal_id: str, kursi_id: str, user_id: str, request_id: Optional[str] = None):
        request = pb.BayarRequest(
            request_id=request_id or str(uuid.uuid4()),
            jadwal_id=jadwal_id,
            kursi_id=kursi_id,
            user_id=user_id,
        )
        return self._call("KonfirmasiPembayaran", request)

    def close(self) -> None:
        for channel in self._channels:
            channel.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
