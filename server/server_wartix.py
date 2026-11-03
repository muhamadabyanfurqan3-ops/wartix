"""
Modul server_wartix.py: Core gRPC Servicer & Server Runner Wartix Multi-Jam Tayang.

Mengimplementasikan LayananWartixServicer:
1. GetJadwalStudio: Menampilkan ketersediaan 60 kursi pada jam tayang & studio tertentu.
2. PesanKursi: Menahan (hold) kursi secara atomik (Mutex Lock) dan aman dari retry (At-Most-Once).
3. KonfirmasiPembayaran: Mengonfirmasi pembayaran kursi yang di-hold menjadi BOOKED.
4. Server Runner di port 50051 dengan ThreadPoolExecutor(max_workers=10).
"""

import os
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
        cached_response = self.lock_manager.check_duplicate(request.request_id)
        if cached_response is not None:
            return cached_response

        # =====================================================================
        # 2. MUTEX LOCK CRITICAL SECTION (PENCEGAHAN RACE CONDITION)
        # =====================================================================
        with self.lock_manager.lock:
            # Double-check deduplikasi di dalam lock untuk mengantisipasi concurrent retries
            cached_response = self.lock_manager.check_duplicate(request.request_id)
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
                response = pb.PesanKursiResponse(
                    sukses=False,
                    pesan="Kursi sedang dipesan/sudah terjual",
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    held_until=0.0
                )

            else:
                # Jadwal atau nomor kursi tidak terdaftar
                response = pb.PesanKursiResponse(
                    sukses=False,
                    pesan=f"Jadwal '{request.jadwal_id}' atau kursi '{request.kursi_id}' tidak valid",
                    jadwal_id=request.jadwal_id,
                    kursi_id=request.kursi_id,
                    held_until=0.0
                )

            # Simpan hasil akhir transaksi ke dalam cache proses deduplikasi
            self.lock_manager.save_response(request.request_id, response)
            return response

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

    def StreamStatusKursi(self, request, context):
        """Stream status awal dan perubahan status untuk satu kursi."""
        last_state = None
        while context.is_active():
            with self.lock_manager.lock:
                seat = self.store.get_seat(request.jadwal_id, request.kursi_id)
                if seat is None:
                    context.abort(
                        grpc.StatusCode.NOT_FOUND,
                        f"Kursi '{request.kursi_id}' pada jadwal "
                        f"'{request.jadwal_id}' tidak ditemukan",
                    )

                state = (
                    seat["status"],
                    seat["user_id"] or "",
                    seat["held_until"] or 0.0,
                )
                response = pb.KursiStatusResponse(
                    jadwal_id=request.jadwal_id,
                    kursi_id=seat["kursi_id"],
                    status=state[0],
                    user_id=state[1],
                    held_until=state[2],
                )

            if state != last_state:
                yield response
                last_state = state
            time.sleep(0.25)

    def KonfirmasiPembayaran(self, request, context):
        """
        RPC KonfirmasiPembayaran: Mengubah status 'PENDING_PAYMENT' menjadi 'BOOKED'
        pada jadwal dan studio yang bersangkutan.
        """
        cached_response = self.lock_manager.check_duplicate(request.request_id)
        if cached_response is not None:
            return cached_response

        with self.lock_manager.lock:
            cached_response = self.lock_manager.check_duplicate(request.request_id)
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
            self.lock_manager.save_response(request.request_id, response)
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
