"""
Modul test_concurrency.py: Stress Test 50 Thread Berebut Kursi di Jam Tayang Sama.

Menguji ketahanan sistem Wartix terhadap Race Condition menggunakan
concurrent.futures.ThreadPoolExecutor(max_workers=50).

Skenario Pengujian:
1. 50 thread client dijalankan serentak untuk memesan kursi yang sama ("A1")
   pada jadwal yang sama ("SHOW_0800_ST1").
2. Setiap thread dibekali request_id unik berupa UUIDv4 dan disinkronkan dengan threading.Barrier
   agar menembak gRPC server pada milidetik yang persis bersamaan.
3. Kriteria Kelulusan (Assertions):
   - Jumlah Transaksi BERHASIL : Wajib TEPAT 1.
   - Jumlah Transaksi DITOLAK  : Wajib TEPAT 49.
   - Status Akhir Kursi "A1" di "SHOW_0800_ST1" : Harus berstatus "PENDING_PAYMENT".
4. Verifikasi Isolasi Antar-Jam Tayang:
   - Kursi "A1" pada "SHOW_1000_ST2" harus tetap "AVAILABLE" (terpisah total).
"""

import os
import sys
import time
import uuid
import threading
from concurrent import futures
from typing import List, Dict, Any

# Pastikan root direktori proyek ada di sys.path agar impor modul berjalan
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import grpc
from generated import wartix_pb2 as pb
from generated import wartix_pb2_grpc as pb_grpc


def run_concurrency_test(
    host: str = "localhost",
    port: int = 50051,
    num_threads: int = 50,
    target_jadwal: str = "SHOW_0800_ST1",
    target_seat: str = "A1"
):
    """
    Menjalankan pengujian konkurensi 50 thread berebut kursi yang sama pada jadwal tertentu.
    """
    server_address = f"{host}:{port}"
    print("=" * 75)
    print("   WARTIX CONCURRENCY & RACE CONDITION STRESS TEST (MULTI-JADWAL)")
    print(f"   Target Server   : {server_address}")
    print(f"   Target Jadwal   : {target_jadwal}")
    print(f"   Target Kursi    : {target_seat}")
    print(f"   Jumlah Thread   : {num_threads} Threads Simultan")
    print("=" * 75)

    # Buat channel gRPC
    channel = grpc.insecure_channel(server_address)
    stub = pb_grpc.LayananWartixStub(channel)

    # Pastikan server responsif dan cek status awal
    try:
        status_awal = stub.GetStatusKursi(
            pb.KursiRequest(jadwal_id=target_jadwal, kursi_id=target_seat),
            timeout=3.0
        )
        print(f"[PRE-TEST] Status awal kursi '{target_seat}' pada jadwal '{target_jadwal}': {status_awal.status}")
        if status_awal.status != "AVAILABLE":
            print(f"[PERINGATAN] Kursi '{target_seat}' saat ini berstatus {status_awal.status}.")
            print("             Disarankan me-restart server agar kursi kembali 'AVAILABLE'.")
    except grpc.RpcError as e:
        print(f"[ERROR] Gagal terhubung ke server gRPC Wartix di {server_address}: {e.details()}")
        print("Pastikan server gRPC telah berjalan dengan perintah: python server/server_wartix.py")
        sys.exit(1)

    # Barrier untuk menyinkronkan 50 thread agar start menembak secara serentak
    barrier = threading.Barrier(num_threads)
    results: List[Dict[str, Any]] = []
    results_lock = threading.Lock()

    def client_worker(thread_idx: int) -> Dict[str, Any]:
        """
        Pekerja thread client yang menyimulasikan 1 pengguna memesan tiket bioskop.
        """
        request_id = str(uuid.uuid4())
        user_id = f"user_{thread_idx:02d}"

        # Tunggu seluruh 50 thread siap di garis start
        barrier.wait()

        # Eksekusi RPC PesanKursi serentak
        try:
            req = pb.PesanKursiRequest(
                request_id=request_id,
                jadwal_id=target_jadwal,
                kursi_id=target_seat,
                user_id=user_id
            )
            response = stub.PesanKursi(req, timeout=10.0)
            res_dict = {
                "thread_idx": thread_idx,
                "user_id": user_id,
                "request_id": request_id,
                "jadwal_id": target_jadwal,
                "kursi_id": target_seat,
                "sukses": response.sukses,
                "pesan": response.pesan,
                "held_until": response.held_until,
                "error": None
            }
        except Exception as e:
            res_dict = {
                "thread_idx": thread_idx,
                "user_id": user_id,
                "request_id": request_id,
                "jadwal_id": target_jadwal,
                "kursi_id": target_seat,
                "sukses": False,
                "pesan": f"RPC Error: {str(e)}",
                "held_until": 0.0,
                "error": str(e)
            }

        with results_lock:
            results.append(res_dict)
        return res_dict

    print(f"\n[START] Melepaskan {num_threads} thread secara bersamaan menembak kursi '{target_seat}' pada '{target_jadwal}'...")
    start_time = time.time()

    with futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures_list = [executor.submit(client_worker, i + 1) for i in range(num_threads)]
        futures.wait(futures_list)

    elapsed = time.time() - start_time
    print(f"[SELESAI] Seluruh {num_threads} request selesai dieksekusi dalam {elapsed:.3f} detik.")

    # Analisis Statistik Hasil
    berhasil = [r for r in results if r["sukses"]]
    ditolak = [r for r in results if not r["sukses"]]

    # Periksa status akhir kursi pada jadwal target via gRPC
    status_akhir = stub.GetStatusKursi(pb.KursiRequest(jadwal_id=target_jadwal, kursi_id=target_seat))

    # Tampilkan Hasil di Terminal
    print("\n" + "=" * 75)
    print("                    STATISTIK PENGUJIAN AKHIR")
    print("=" * 75)
    print(f"Jadwal Pengujian           : {target_jadwal}")
    print(f"Kursi Pengujian            : {target_seat}")
    print(f"Total Request Dikirim      : {len(results)}")
    print(f"Jumlah Transaksi BERHASIL  : {len(berhasil)} (Target: TEPAT 1)")
    print(f"Jumlah Transaksi DITOLAK   : {len(ditolak)} (Target: TEPAT 49)")
    print(f"Status Akhir Kursi '{target_seat}'   : {status_akhir.status}")
    print(f"User Pemilik Hold Kursi    : {status_akhir.user_id}")
    print("-" * 75)

    # Validasi Ketat Sesuai Kriteria Spesifikasi
    test_passed = True

    if len(berhasil) == 1:
        pemenang = berhasil[0]
        print(f"[OK] Kriteria 1: Transaksi BERHASIL = 1 TERCAPAI! (Oleh {pemenang['user_id']})")
    else:
        print(f"[GAGAL] Kriteria 1: Transaksi BERHASIL = {len(berhasil)} (Diharapkan tepat 1, terdeteksi Race Condition!)")
        test_passed = False

    if len(ditolak) == num_threads - 1:
        print(f"[OK] Kriteria 2: Transaksi DITOLAK = {len(ditolak)} TERCAPAI!")
    else:
        print(f"[GAGAL] Kriteria 2: Transaksi DITOLAK = {len(ditolak)} (Diharapkan {num_threads - 1})")
        test_passed = False

    if status_akhir.status == "PENDING_PAYMENT":
        print(f"[OK] Kriteria 3: Status akhir kursi '{target_seat}' pada {target_jadwal} = PENDING_PAYMENT TERCAPAI!")
    else:
        print(f"[GAGAL] Kriteria 3: Status akhir kursi '{target_seat}' = {status_akhir.status} (Diharapkan PENDING_PAYMENT)")
        test_passed = False

    # =========================================================================
    # UJI ISOLASI MULTI-JAM TAYANG
    # =========================================================================
    print("\n--- UJI ISOLASI ANTAR-JAM TAYANG ---")
    other_jadwal = "SHOW_1000_ST2"
    status_other = stub.GetStatusKursi(pb.KursiRequest(jadwal_id=other_jadwal, kursi_id=target_seat))
    print(f"Memeriksa kursi '{target_seat}' pada jadwal berbeda ('{other_jadwal}'): {status_other.status}")
    if status_other.status == "AVAILABLE":
        print(f"[OK] Isolasi Berhasil: Kursi '{target_seat}' pada {other_jadwal} tetap AVAILABLE dan tidak terpengaruh!")
    else:
        print(f"[GAGAL] Kebocoran State: Kursi '{target_seat}' pada {other_jadwal} ikut terpengaruh ({status_other.status})")
        test_passed = False

    # Uji Pemesanan Kursi A1 pada Jadwal Lain (Membuktikan independensi)
    req_other = pb.PesanKursiRequest(
        request_id=str(uuid.uuid4()),
        jadwal_id=other_jadwal,
        kursi_id=target_seat,
        user_id="user_jam_1540"
    )
    res_other = stub.PesanKursi(req_other)
    if res_other.sukses:
        print(f"[OK] Pembuktian Sukses: Kursi '{target_seat}' pada '{other_jadwal}' berhasil di-hold oleh user lain secara independen!")
    else:
        print(f"[GAGAL] Gagal memesan kursi '{target_seat}' pada jadwal berbeda.")
        test_passed = False

    # =========================================================================
    # UJI DEDUPLIKASI AT-MOST-ONCE (CLIENT RETRY)
    # =========================================================================
    if len(berhasil) == 1:
        print("\n--- UJI DEDUPLIKASI (AT-MOST-ONCE RETRY) ---")
        pemenang = berhasil[0]
        print(f"Mengirim ulang request_id pemenang ({pemenang['request_id'][:8]}...) untuk kursi '{target_seat}'...")
        req_retry = pb.PesanKursiRequest(
            request_id=pemenang["request_id"],
            jadwal_id=target_jadwal,
            kursi_id=target_seat,
            user_id=pemenang["user_id"]
        )
        res_retry = stub.PesanKursi(req_retry)
        if res_retry.sukses:
            print("[OK] Deduplikasi Terbukti: Request retry menghasilkan response sukses yang sama dari cache!")
        else:
            print("[GAGAL] Deduplikasi gagal: Server menolak retry dengan request_id yang sama.")
            test_passed = False

    print("=" * 75)
    if test_passed:
        print("KESIMPULAN: PENGUJIAN CONCURRENCY & MULTI-JADWAL LULUS 100%!")
        print("Sistem Wartix terbukti AMAN dari Race Condition, mengisolasi jam tayang, dan konsisten At-Most-Once.")
    else:
        print("KESIMPULAN: PENGUJIAN GAGAL.")
    print("=" * 75)

    channel.close()
    return test_passed


def main():
    """
    Entry point pengujian. Menyalakan in-process test server jika server lokal belum aktif.
    """
    host = "localhost"
    port = 50051

    server_running = False
    try:
        test_channel = grpc.insecure_channel(f"{host}:{port}")
        grpc.channel_ready_future(test_channel).result(timeout=1.0)
        test_channel.close()
        server_running = True
    except Exception:
        server_running = False

    background_server = None
    if not server_running:
        print("[INFO] Server belum aktif di localhost:50051. Menyalakan In-Process Test Server...")
        from server.server_wartix import create_server
        background_server, _ = create_server(port=port, max_workers=10)
        background_server.start()
        time.sleep(0.5)

    try:
        sukses = run_concurrency_test(
            host=host,
            port=port,
            num_threads=50,
            target_jadwal="SHOW_0800_ST1",
            target_seat="A1"
        )
        if not sukses:
            sys.exit(1)
    finally:
        if background_server is not None:
            print("\n[INFO] Menghentikan background test server...")
            background_server.stop(grace=0)


if __name__ == "__main__":
    main()
