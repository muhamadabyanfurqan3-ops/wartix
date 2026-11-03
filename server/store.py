"""
Modul store.py: In-memory Data Store Multi-Jam Tayang & Layout Kursi.

Mengelola data inventaris bioskop bertingkat secara independen berdasarkan:
Jam Tayang & Studio (Contoh ID: "SHOW_0800_ST1", "SHOW_1000_ST2", "SHOW_1200_ST1").

Setiap jadwal memiliki layout 60 kursi (A1 - F10) dengan siklus hidup state:
1. "AVAILABLE"       : Kursi bebas dipilih.
2. "PENDING_PAYMENT" : Kursi sedang di-hold menunggu pembayaran (held_until).
3. "BOOKED"          : Pembayaran terverifikasi dan tiket resmi terjual.

Pemisahan State:
Kursi A1 pada jam 13:00 ("SHOW_0800_ST1") terpisah total dan tidak mempengaruhi
kursi A1 pada jam 15:40 ("SHOW_1000_ST2").
"""

import time
from typing import Dict, List, Optional, Tuple, Any


class StudioStore:
    """
    Kelas in-memory data store yang mengelola data bertingkat per jam tayang dan studio.
    """

    DEFAULT_ROWS = ["A", "B", "C", "D", "E", "F"]
    DEFAULT_COLS = 10

    def __init__(self):
        """
        Inisialisasi katalog demo yang dipakai oleh frontend:
        - Avengers: Endgame : Jam 08:00 dan 13:40
        - Midway : Jam 10:00 dan 16:40
        - 1917 : Jam 12:00 dan 19:00
        """
        # Struktur data bertingkat:
        # self.jadwal = {
        #     "SHOW_0800_ST1": {
        #         "jadwal_id": "SHOW_0800_ST1",
        #         "nama_film": "...",
        #         "jam_tayang": "13:00",
        #         "studio_id": "Studio 1",
        #         "seats": { "A1": {...}, "A2": {...}, ... }
        #     },
        #     ...
        # }
        self.jadwal: Dict[str, Dict[str, Any]] = {}
        self._init_default_schedules()

    def _create_seat_layout(self) -> Dict[str, Dict[str, Any]]:
        """
        Membangun layout 60 kursi independen (A1-F10) dengan status awal AVAILABLE.
        """
        seats: Dict[str, Dict[str, Any]] = {}
        for row in self.DEFAULT_ROWS:
            for col in range(1, self.DEFAULT_COLS + 1):
                kursi_id = f"{row}{col}"
                seats[kursi_id] = {
                    "kursi_id": kursi_id,
                    "status": "AVAILABLE",
                    "user_id": None,
                    "held_until": None,  # Unix epoch timestamp float
                }
        return seats

    def _init_default_schedules(self) -> None:
        """
        Menginisialisasi jadwal-jadwal film bawaan.
        """
        schedules_info = [
            ("SHOW_0800_ST1", "Avengers: Endgame", "08:00", "Studio 1"),
            ("SHOW_1340_ST1", "Avengers: Endgame", "13:40", "Studio 1"),
            ("SHOW_1000_ST2", "Midway", "10:00", "Studio 2"),
            ("SHOW_1640_ST2", "Midway", "16:40", "Studio 2"),
            ("SHOW_1200_ST1", "1917", "12:00", "Studio 1"),
            ("SHOW_1900_ST1", "1917", "19:00", "Studio 1"),
        ]
        for j_id, film, jam, studio in schedules_info:
            self.add_jadwal(jadwal_id=j_id, nama_film=film, jam_tayang=jam, studio_id=studio)

    def add_jadwal(self, jadwal_id: str, nama_film: str = "Film Bioskop", jam_tayang: str = "12:00", studio_id: str = "Studio 1") -> None:
        """
        Mendaftarkan jadwal film baru dengan layout kursi 60 kursi independen.
        """
        j_norm = jadwal_id.strip()
        self.jadwal[j_norm] = {
            "jadwal_id": j_norm,
            "nama_film": nama_film,
            "jam_tayang": jam_tayang,
            "studio_id": studio_id,
            "seats": self._create_seat_layout(),
        }

    def ensure_jadwal_exists(self, jadwal_id: str) -> None:
        """
        Memastikan jadwal_id terdaftar. Jika belum, buatkan layout kursi baru secara otomatis.
        """
        j_norm = jadwal_id.strip()
        if j_norm not in self.jadwal:
            self.add_jadwal(jadwal_id=j_norm, nama_film="Film Bioskop", jam_tayang="12:00", studio_id="Studio 1")

    def check_expired_holds(self) -> List[Tuple[str, str]]:
        """
        Memeriksa dan merilis kembali semua kursi 'PENDING_PAYMENT' di seluruh jadwal
        yang waktu held_until-nya telah kedaluwarsa menjadi 'AVAILABLE'.
        Mengembalikan daftar tuple (jadwal_id, kursi_id) yang dirilis.
        """
        now = time.time()
        released: List[Tuple[str, str]] = []

        for j_id, j_data in self.jadwal.items():
            for k_id, seat in j_data["seats"].items():
                if seat["status"] == "PENDING_PAYMENT":
                    held_until = seat.get("held_until")
                    if held_until is not None and held_until <= now:
                        # Hold kedaluwarsa: kembalikan ke AVAILABLE
                        seat["status"] = "AVAILABLE"
                        seat["user_id"] = None
                        seat["held_until"] = None
                        released.append((j_id, k_id))

        return released

    def get_jadwal(self, jadwal_id: str) -> Optional[Dict[str, Any]]:
        """
        Mengembalikan informasi jadwal film beserta denah status 60 kursi.
        """
        j_norm = jadwal_id.strip()
        if j_norm not in self.jadwal:
            return None

        # Rilis kursi expired terlebih dahulu
        self.check_expired_holds()

        j_data = self.jadwal[j_norm]
        seats_list = list(j_data["seats"].values())
        kursi_tersedia = sum(1 for s in seats_list if s["status"] == "AVAILABLE")

        return {
            "jadwal_id": j_data["jadwal_id"],
            "nama_film": j_data["nama_film"],
            "jam_tayang": j_data["jam_tayang"],
            "studio_id": j_data["studio_id"],
            "total_kursi": len(seats_list),
            "kursi_tersedia": kursi_tersedia,
            "kursi": seats_list,
        }

    def get_status(self, jadwal_id: str, kursi_id: str) -> Optional[str]:
        """
        Mengembalikan status kursi spesifik pada jadwal tertentu:
        'AVAILABLE', 'PENDING_PAYMENT', 'BOOKED', atau None jika tidak ditemukan.
        """
        j_norm = jadwal_id.strip()
        k_norm = kursi_id.upper().strip()

        j_data = self.jadwal.get(j_norm)
        if j_data is None:
            return None

        seat = j_data["seats"].get(k_norm)
        if seat is None:
            return None

        # Evaluasi kedaluwarsa secara reaktif
        if seat["status"] == "PENDING_PAYMENT":
            held_until = seat.get("held_until")
            if held_until is not None and held_until <= time.time():
                seat["status"] = "AVAILABLE"
                seat["user_id"] = None
                seat["held_until"] = None

        return seat["status"]

    def get_seat(self, jadwal_id: str, kursi_id: str) -> Optional[Dict[str, Any]]:
        """
        Mengambil objek detail kursi pada jadwal tertentu.
        """
        j_norm = jadwal_id.strip()
        k_norm = kursi_id.upper().strip()

        # Update status jika expired
        self.get_status(j_norm, k_norm)

        j_data = self.jadwal.get(j_norm)
        if j_data is None:
            return None
        return j_data["seats"].get(k_norm)

    def hold_kursi(self, jadwal_id: str, kursi_id: str, user_id: str, duration_seconds: int = 120) -> Tuple[bool, str, Optional[float]]:
        """
        Menahan (hold) kursi untuk pembayaran pada jadwal tertentu.
        Mengubah status kursi dari 'AVAILABLE' menjadi 'PENDING_PAYMENT'.
        
        Args:
            jadwal_id: ID Jam Tayang & Studio (misal 'SHOW_0800_ST1')
            kursi_id: Kode kursi (misal 'A1')
            user_id: ID pengguna pemesan
            duration_seconds: Durasi penahanan kursi dalam detik (default 120s)
            
        Returns:
            Tuple (sukses: bool, pesan: str, held_until: Optional[float])
        """
        j_norm = jadwal_id.strip()
        k_norm = kursi_id.upper().strip()

        j_data = self.jadwal.get(j_norm)
        if j_data is None:
            return False, f"Jadwal '{jadwal_id}' tidak ditemukan", None

        seat = j_data["seats"].get(k_norm)
        if seat is None:
            return False, f"Kursi '{kursi_id}' tidak valid / tidak ada di studio", None

        # Cek apakah hold sebelumnya sudah kedaluwarsa
        if seat["status"] == "PENDING_PAYMENT":
            held_until = seat.get("held_until")
            if held_until is not None and held_until <= time.time():
                seat["status"] = "AVAILABLE"
                seat["user_id"] = None
                seat["held_until"] = None

        # Validasi ketersediaan kursi
        if seat["status"] == "AVAILABLE":
            now = time.time()
            expiry = now + duration_seconds
            seat["status"] = "PENDING_PAYMENT"
            seat["user_id"] = user_id
            seat["held_until"] = expiry
            return True, f"Kursi {k_norm} pada jadwal {j_norm} berhasil di-hold untuk pembayaran ({duration_seconds}s)", expiry

        # Kursi sudah di-hold orang lain atau sudah terjual pada jadwal ini
        return False, "Kursi sedang dipesan/sudah terjual", None

    def confirm_payment(self, jadwal_id: str, kursi_id: str, user_id: Optional[str] = None) -> Tuple[bool, str]:
        """
        Mengubah status kursi dari 'PENDING_PAYMENT' menjadi 'BOOKED' pada jadwal tertentu.
        
        Args:
            jadwal_id: ID Jam Tayang & Studio (misal 'SHOW_0800_ST1')
            kursi_id: Kode kursi (misal 'A1')
            user_id: Opsional ID pengguna pemesan
            
        Returns:
            Tuple (sukses: bool, pesan: str)
        """
        j_norm = jadwal_id.strip()
        k_norm = kursi_id.upper().strip()

        j_data = self.jadwal.get(j_norm)
        if j_data is None:
            return False, f"Jadwal '{jadwal_id}' tidak ditemukan"

        seat = j_data["seats"].get(k_norm)
        if seat is None:
            return False, f"Kursi '{kursi_id}' tidak ditemukan pada jadwal {j_norm}"

        # Periksa apakah hold sudah kedaluwarsa
        if seat["status"] == "PENDING_PAYMENT":
            held_until = seat.get("held_until")
            if held_until is not None and held_until <= time.time():
                seat["status"] = "AVAILABLE"
                seat["user_id"] = None
                seat["held_until"] = None
                return False, f"Batas waktu pembayaran kursi {k_norm} telah habis"

        if seat["status"] == "PENDING_PAYMENT":
            if user_id and seat["user_id"] != user_id:
                return False, "Pembayaran ditolak: user_id tidak sesuai dengan pemesan awal"

            seat["status"] = "BOOKED"
            seat["held_until"] = None
            return True, f"Pembayaran berhasil. Kursi {k_norm} pada jadwal {j_norm} resmi terjual (BOOKED)"

        if seat["status"] == "BOOKED":
            return False, f"Kursi {k_norm} pada jadwal {j_norm} sudah berstatus BOOKED"

        return False, f"Kursi {k_norm} pada jadwal {j_norm} belum dipesan (status: AVAILABLE)"

    def cancel_hold(self, jadwal_id: str, kursi_id: str, user_id: str) -> Tuple[bool, str]:
        """Melepas hold yang masih aktif dan dimiliki user peminta."""
        j_norm = jadwal_id.strip()
        k_norm = kursi_id.upper().strip()
        j_data = self.jadwal.get(j_norm)
        if j_data is None:
            return False, f"Jadwal '{jadwal_id}' tidak ditemukan"

        seat = j_data["seats"].get(k_norm)
        if seat is None:
            return False, f"Kursi '{kursi_id}' tidak ditemukan pada jadwal {j_norm}"

        # Bersihkan hold kedaluwarsa sebelum memvalidasi kepemilikan/status.
        if seat["status"] == "PENDING_PAYMENT":
            held_until = seat.get("held_until")
            if held_until is not None and held_until <= time.time():
                seat["status"] = "AVAILABLE"
                seat["user_id"] = None
                seat["held_until"] = None
                return False, f"Hold kursi {k_norm} telah kedaluwarsa"

        if seat["status"] != "PENDING_PAYMENT":
            return False, f"Kursi {k_norm} tidak memiliki hold aktif"
        if seat["user_id"] != user_id:
            return False, "Pembatalan ditolak: user_id tidak sesuai dengan pemesan awal"

        seat["status"] = "AVAILABLE"
        seat["user_id"] = None
        seat["held_until"] = None
        return True, f"Hold kursi {k_norm} pada jadwal {j_norm} berhasil dibatalkan"

    def reset(self) -> None:
        """
        Mereset seluruh jadwal dan status kursi kembali ke kondisi awal.
        """
        self.jadwal.clear()
        self._init_default_schedules()
