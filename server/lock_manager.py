"""
Modul lock_manager.py: Mutex Locking & At-Most-Once Request Deduplication.

Menyediakan mekanisme sinkronisasi thread (Mutual Exclusion / Mutex) untuk mencegah
Race Condition pada akses inventaris kursi, serta Request Deduplication Cache untuk
menerapkan semantik At-Most-Once RPC (mencegah double booking akibat client retry).
"""

import threading
from typing import Any, Dict, Optional


class LockManager:
    """
    Pengelola konkurensi (Mutex Lock) dan cache deduplikasi transaksi (At-Most-Once).
    """

    def __init__(self):
        """
        Inisialisasi thread lock dan in-memory cache transaksi.
        self.lock   : Mutex lock untuk proteksi critical section.
        self.proses : Dictionary pemetaan {request_id: response_cache}.
        """
        self.lock = threading.Lock()
        self.proses: Dict[str, Any] = {}

    def acquire_lock(self, blocking: bool = True, timeout: float = -1) -> bool:
        """
        Mengakuisisi Mutex lock secara manual.
        """
        return self.lock.acquire(blocking=blocking, timeout=timeout)

    def release_lock(self) -> None:
        """
        Melepaskan Mutex lock secara manual.
        """
        self.lock.release()

    def __enter__(self):
        """
        Mendukung penggunaan idiomatik context manager:
        with lock_manager:
            ... critical section ...
        """
        self.lock.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Memastikan Mutex lock selalu dilepaskan saat keluar dari context block,
        bahkan ketika terjadi exception di dalam critical section.
        """
        self.lock.release()

    def check_duplicate(self, request_id: Optional[str]) -> Optional[Any]:
        """
        Memeriksa apakah request_id (Idempotency Key / UUID) sudah pernah diproses.
        
        Semantik At-Most-Once:
        Jika request_id sudah ada di dalam cache 'proses', kembalikan response tersimpan
        tanpa mengeksekusi ulang transaksi bisnis (mencegah pemesanan ganda saat client retry).
        Jika belum ada, kembalikan None.
        """
        if not request_id:
            return None
        return self.proses.get(request_id)

    def save_response(self, request_id: Optional[str], response: Any) -> None:
        """
        Menyimpan hasil response transaksi ke dalam cache 'proses' berdasarkan request_id.
        Response ini akan disajikan kembali jika ada request dengan ID yang sama di kemudian hari.
        """
        if request_id:
            self.proses[request_id] = response

    def clear_cache(self) -> None:
        """
        Membersihkan seluruh cache deduplikasi transaksi (berguna saat pengujian).
        """
        self.proses.clear()

