"""
Modul server_wartix.py: Core gRPC Servicer & Server Runner Wartix Multi-Jam Tayang.

Mengimplementasikan LayananWartixServicer:
1. GetJadwalStudio: Menampilkan ketersediaan 60 kursi pada jam tayang & studio tertentu.
2. PesanKursi: Menahan (hold) kursi secara atomik (Mutex Lock) dan aman dari retry (At-Most-Once).
3. StreamStatusKursi: Mengirim status awal dan perubahan kursi sebagai server stream.
4. KonfirmasiPembayaran & BatalPesanan: Menyelesaikan atau melepas hold.
5. Server Runner di port 50051 dengan ThreadPoolExecutor.
"""

import os
import queue
import sys
import time
from concurrent import futures
from typing import Optional

# Pastikan root direktori proyek ada di sys.path agar impor package berjalan mulus
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import grpc
from server.store import StudioStore
from server.lock_manager import LockManager
from generated import wartix_pb2 as pb
from generated import wartix_pb2_grpc as pb_grpc


class LayananWartixServicer(pb_grpc.LayananWartixServicer):
    """
    Implementasi gRPC Servicer untuk sistem pemesanan tiket bioskop Wartix.
    Mendukung isolasi multi-jam tayang dan studio film.
    """

    def __init__(self, store: Optional[StudioStore] = None, lock_manager: Optional[LockManager] = None):
        """
        Inisialisasi Servicer dengan StudioStore (data bertingkat jadwal) dan LockManager (Mutex & Cache).
        """
        self.store = store if store is not None else StudioStore()
        self.lock_manager = lock_manager if lock_manager is not None else LockManager()
        # Subscriber menerima status yang cocok dengan jadwal dan kursinya.
        self._status_subscribers = {}

    @staticmethod
    def _request_cache_key(method: str, request_id: str) -> Optional[str]:
        return f"{method}:{request_id}" if request_id else None

    @staticmethod
    def _status_message(jadwal_id: str, seat) -> pb.KursiStatusResponse:
        return pb.KursiStatusResponse(
            jadwal_id=jadwal_id.strip(),
            kursi_id=seat["kursi_id"],
            status=seat["status"],
            user_id=seat["user_id"] or "",
            held_until=seat["held_until"] or 0.0,
        )

    def _broadcast_status(self, status: pb.KursiStatusResponse) -> None:
        """Broadcast perubahan status ke subscriber yang sudah terfilter.

        Caller harus memegang lock_manager.lock agar status publikasi dan mutasi
        kursi memiliki urutan konsisten.
        """
        for subscriber, (jadwal_id, kursi_id) in list(self._status_subscribers.items()):
            if jadwal_id == status.jadwal_id.strip() and kursi_id == status.kursi_id.upper().strip():
                subscriber.put_nowait(status)

    def GetJadwalStudio(self, request, context):
        """
        RPC GetJadwalStudio: Menerima jadwal_id dan mengembalikan denah serta
        ketersediaan kursi pada jam tayang dan studio bersangkutan.
        """
        with self.lock_manager.lock:
            j_data = self.store.get_jadwal(request.jadwal_id)
            if j_data is None:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Jadwal '{request.jadwal_id}' tidak ditemukan")

            kursi_proto = [
                pb.KursiInfo(
                    kursi_id=k["kursi_id"],
                    status=k["status"],
                    user_id=k["user_id"] or "",
                    held_until=k["held_until"] or 0.0
                )
                for k in j_data["kursi"]
            ]

            return pb.JadwalResponse(
                jadwal_id=j_data["jadwal_id"],
                nama_film=j_data["nama_film"],
                jam_tayang=j_data["jam_tayang"],
                studio_id=j_data["studio_id"],
                total_kursi=j_data["total_kursi"],
                kursi_tersedia=j_data["kursi_tersedia"],
                kursi=kursi_proto
            )

    def DaftarJadwal(self, request, context):
        """Mengirim snapshot katalog jadwal sebagai server stream."""
        # Salin response di dalam lock agar snapshot konsisten, lalu yield di luar
        # lock supaya client yang lambat tidak menahan transaksi reservasi.
        with self.lock_manager.lock:
            jadwal_ids = list(self.store.jadwal.keys())
            responses = []
            for jadwal_id in jadwal_ids:
                j_data = self.store.get_jadwal(jadwal_id)
                if j_data is None:
                    continue
                kursi_proto = [
                    pb.KursiInfo(
                        kursi_id=k["kursi_id"],
                        status=k["status"],
                        user_id=k["user_id"] or "",
                        held_until=k["held_until"] or 0.0,
                    )
                    for k in j_data["kursi"]
                ]
                responses.append(
                    pb.JadwalResponse(
                        jadwal_id=j_data["jadwal_id"],
                        nama_film=j_data["nama_film"],
                        jam_tayang=j_data["jam_tayang"],
                        studio_id=j_data["studio_id"],
                        total_kursi=j_data["total_kursi"],
                        kursi_tersedia=j_data["kursi_tersedia"],
                        kursi=kursi_proto,
                    )
                )

        yield from responses

    def PesanKursi(self, request, context):
        """
        RPC PesanKursi: Menahan (hold) kursi untuk pembayaran pada jadwal tertentu.
        
        Alur Eksekusi:
        1. Di dalam Mutex Lock (with lock_manager.lock), periksa apakah request_id duplikat
           (semantik At-Most-Once untuk client retry).
        2. Periksa ketersediaan kursi pada jadwal_id yang bersangkutan via StudioStore.
        3. Jika kursi 'AVAILABLE', ubah status menjadi 'PENDING_PAYMENT' via hold_kursi(),
           simpan response ke cache deduplikasi, dan kembalikan sukses=True.
        4. Jika kursi 'PENDING_PAYMENT' atau 'BOOKED', kembalikan sukses=False dengan pesan:
           'Kursi sedang dipesan/sudah terjual'.
        """
        # =====================================================================
        # 1. CEK DEDUPLIKASI REQUEST AWAL (FAST-PATH)
        # =====================================================================
        cache_key = self._request_cache_key("PesanKursi", request.request_id)
        with self.lock_manager.lock:
            # Check dan perubahan status berada di lock yang sama; retry serentak
            # tidak dapat melewati pemeriksaan ketersediaan yang sama-sama kosong.
            cached_response = self.lock_manager.check_duplicate(cache_key)
            if cached_response is not None:
                return cached_response

            # Bersihkan hold yang telah kedaluwarsa secara berkala
            self.store.check_expired_holds()

            # Periksa ketersediaan kursi pada jadwal dan studio bersangkutan
            status_kursi = self.store.get_status(request.jadwal_id, request.kursi_id)

            # =================================================================
            # 3. LOGIKA BISNIS STATUS KURSI PER JAM TAYANG
            # =================================================================
            if status_kursi == "AVAILABLE":
                # Kursi kosong pada jadwal ini: hold selama 120 detik untuk pembayaran
                sukses, pesan, held_until = self.store.hold_kursi(
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    user_id=request.user_id,
                    duration_seconds=120
                )
                response = pb.PesanKursiResponse(
                    sukses=sukses,
                    pesan=pesan,
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    held_until=held_until if held_until is not None else 0.0
                )

            elif status_kursi in ("PENDING_PAYMENT", "BOOKED"):
                # Kursi pada jadwal ini sedang di-hold orang lain atau sudah terjual
                sukses = False
                response = pb.PesanKursiResponse(
                    sukses=False,
                    pesan="Kursi sedang dipesan/sudah terjual",
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    held_until=0.0
                )

            else:
                # Jadwal atau nomor kursi tidak terdaftar
                sukses = False
                response = pb.PesanKursiResponse(
                    sukses=False,
                    pesan=f"Jadwal '{request.jadwal_id}' atau kursi '{request.kursi_id}' tidak valid",
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    held_until=0.0
                )

            # Simpan hasil akhir transaksi ke dalam cache proses deduplikasi
            self.lock_manager.save_response(cache_key, response)
            if sukses:
                seat = self.store.get_seat(request.jadwal_id, request.kursi_id)
                if seat is not None:
                    self._broadcast_status(self._status_message(request.jadwal_id, seat))
            return response

    def BatalPesanan(self, request, context):
        """Membatalkan hold pembayaran secara atomik dan idempoten."""
        cache_key = self._request_cache_key("BatalPesanan", request.request_id)
        with self.lock_manager.lock:
            cached_response = self.lock_manager.check_duplicate(cache_key)
            if cached_response is not None:
                return cached_response

            sukses, pesan = self.store.cancel_hold(
                jadwal_id=request.jadwal_id,
                kursi_id=request.kursi_id,
                user_id=request.user_id,
            )
            response = pb.BatalPesananResponse(
                sukses=sukses,
                pesan=pesan,
                jadwal_id=request.jadwal_id,
                kursi_id=request.kursi_id,
            )
            self.lock_manager.save_response(cache_key, response)
            if sukses:
                seat = self.store.get_seat(request.jadwal_id, request.kursi_id)
                if seat is not None:
                    self._broadcast_status(self._status_message(request.jadwal_id, seat))
            return response

    def StreamStatusKursi(self, request, context):
        """Stream status awal dan perubahan kursi sampai client menutup stream."""
        jadwal_id = request.jadwal_id.strip()
        kursi_id = request.kursi_id.upper().strip()
        updates = queue.Queue()

        # Daftarkan subscriber dan ambil status awal dalam critical section yang
        # sama agar tidak ada perubahan yang terlewat di antara keduanya.
        with self.lock_manager.lock:
            seat = self.store.get_seat(jadwal_id, kursi_id)
            if seat is None:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Kursi '{kursi_id}' pada jadwal '{jadwal_id}' tidak ditemukan",
                )
            self._status_subscribers[updates] = (jadwal_id, kursi_id)
            current = self._status_message(jadwal_id, seat)

        last_state = (current.status, current.user_id, current.held_until)
        try:
            yield current
            while context.is_active():
                try:
                    update = updates.get(timeout=0.5)
                except queue.Empty:
                    # Hold dapat kedaluwarsa tanpa ada RPC lain yang menyentuh
                    # kursi. Poll ringan ini menerbitkan transisi ke AVAILABLE.
                    with self.lock_manager.lock:
                        seat = self.store.get_seat(jadwal_id, kursi_id)
                        if seat is None:
                            return
                        update = self._status_message(jadwal_id, seat)

                state = (update.status, update.user_id, update.held_until)
                if state != last_state:
                    last_state = state
                    yield update
        finally:
            with self.lock_manager.lock:
                self._status_subscribers.pop(updates, None)

    def GetStatusKursi(self, request, context):
        """
        RPC GetStatusKursi: Mengecek status satu kursi spesifik pada jadwal tertentu.
        """
        with self.lock_manager.lock:
            seat = self.store.get_seat(request.jadwal_id, request.kursi_id)
            if seat is None:
                context.abort(grpc.StatusCode.NOT_FOUND, f"Kursi '{request.kursi_id}' pada jadwal '{request.jadwal_id}' tidak ditemukan")
            return pb.KursiStatusResponse(
                jadwal_id=request.jadwal_id,
                kursi_id=seat["kursi_id"],
                status=seat["status"],
                user_id=seat["user_id"] or "",
                held_until=seat["held_until"] or 0.0
            )

    def KonfirmasiPembayaran(self, request, context):
        """
        RPC KonfirmasiPembayaran: Mengubah status 'PENDING_PAYMENT' menjadi 'BOOKED'
        pada jadwal dan studio yang bersangkutan.
        """
        cache_key = self._request_cache_key("KonfirmasiPembayaran", request.request_id)
        with self.lock_manager.lock:
            cached_response = self.lock_manager.check_duplicate(cache_key)
            if cached_response is not None:
                return cached_response

            sukses, pesan = self.store.confirm_payment(
                jadwal_id=request.jadwal_id,
                kursi_id=request.kursi_id,
                user_id=request.user_id
            )
            response = pb.KonfirmasiResponse(
                sukses=sukses,
                pesan=pesan,
                jadwal_id=request.jadwal_id,
                kursi_id=request.kursi_id
            )
            self.lock_manager.save_response(cache_key, response)
            if sukses:
                seat = self.store.get_seat(request.jadwal_id, request.kursi_id)
                if seat is not None:
                    self._broadcast_status(self._status_message(request.jadwal_id, seat))
            return response


def create_server(port: int = 50051, max_workers: int = 10, servicer: Optional[LayananWartixServicer] = None):
    """
    Fungsi factory pembuat instance gRPC server Wartix.
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    if servicer is None:
        servicer = LayananWartixServicer()
    pb_grpc.add_LayananWartixServicer_to_server(servicer, server)
    server.add_insecure_port(f"[::]:{port}")
    return server, servicer


def serve(port: int = 50051, max_workers: int = 10):
    """
    Fungsi runner untuk menjalankan gRPC server Wartix pada port 50051.
    """
    server, servicer = create_server(port=port, max_workers=max_workers)
    server.start()
    print("==================================================================")
    print(f"   SERVER gRPC WARTIX MULTI-JADWAL BERJALAN DI PORT {port}")
    print(f"   ThreadPool Max Workers : {max_workers}")
    print(f"   Jadwal Terdaftar       : {list(servicer.store.jadwal.keys())}")
    print("==================================================================")
    print("Menunggu permintaan reservasi tiket dari client...")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[INFO] Menghentikan Server gRPC Wartix...")
        server.stop(grace=0)
        print("[INFO] Server berhasil dihentikan.")


if __name__ == "__main__":
    target_port = int(sys.argv[1]) if len(sys.argv) > 1 else 50051
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    serve(port=target_port, max_workers=workers)
