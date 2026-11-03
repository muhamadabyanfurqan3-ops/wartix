"""
Unit test untuk StudioStore (Multi-Jam Tayang) dan LockManager.
"""

import time
import unittest
from server.store import StudioStore
from server.lock_manager import LockManager


class TestStudioStoreMultiJadwal(unittest.TestCase):
    def setUp(self):
        self.store = StudioStore()

    def test_default_schedules(self):
        # 3 jadwal bawaan terdaftar
        self.assertIn("SHOW_1300_ST1", self.store.jadwal)
        self.assertIn("SHOW_1540_ST2", self.store.jadwal)
        self.assertIn("SHOW_1800_ST1", self.store.jadwal)

        # 60 kursi per jadwal
        j1 = self.store.get_jadwal("SHOW_1300_ST1")
        self.assertIsNotNone(j1)
        self.assertEqual(j1["total_kursi"], 60)
        self.assertEqual(j1["kursi_tersedia"], 60)

    def test_schedule_isolation(self):
        # Hold kursi A1 pada SHOW_1300_ST1
        sukses, _, _ = self.store.hold_kursi("SHOW_1300_ST1", "A1", "user_1300", duration_seconds=120)
        self.assertTrue(sukses)
        self.assertEqual(self.store.get_status("SHOW_1300_ST1", "A1"), "PENDING_PAYMENT")

        # Kursi A1 pada SHOW_1540_ST2 harus tetap AVAILABLE (terisolasi)
        self.assertEqual(self.store.get_status("SHOW_1540_ST2", "A1"), "AVAILABLE")

        # Bisa di-hold oleh user lain pada SHOW_1540_ST2
        sukses2, _, _ = self.store.hold_kursi("SHOW_1540_ST2", "A1", "user_1540", duration_seconds=120)
        self.assertTrue(sukses2)
        self.assertEqual(self.store.get_status("SHOW_1540_ST2", "A1"), "PENDING_PAYMENT")

    def test_hold_and_confirm_payment(self):
        # Hold dan konfirmasi pembayaran pada SHOW_1800_ST1
        sukses_hold, _, _ = self.store.hold_kursi("SHOW_1800_ST1", "B5", "user_vip", duration_seconds=120)
        self.assertTrue(sukses_hold)

        sukses_bayar, _ = self.store.confirm_payment("SHOW_1800_ST1", "B5", "user_vip")
        self.assertTrue(sukses_bayar)
        self.assertEqual(self.store.get_status("SHOW_1800_ST1", "B5"), "BOOKED")

    def test_expired_hold_multi_jadwal(self):
        # Hold durasi 0.05 detik
        self.store.hold_kursi("SHOW_1300_ST1", "C3", "user_exp", duration_seconds=0.05)
        self.assertEqual(self.store.get_status("SHOW_1300_ST1", "C3"), "PENDING_PAYMENT")

        time.sleep(0.06)
        released = self.store.check_expired_holds()
        self.assertIn(("SHOW_1300_ST1", "C3"), released)
        self.assertEqual(self.store.get_status("SHOW_1300_ST1", "C3"), "AVAILABLE")


class TestLockManager(unittest.TestCase):
    def setUp(self):
        self.lm = LockManager()

    def test_deduplication_at_most_once(self):
        self.assertIsNone(self.lm.check_duplicate("req-uuid-123"))
        sample_resp = {"sukses": True, "pesan": "OK"}
        self.lm.save_response("req-uuid-123", sample_resp)
        self.assertEqual(self.lm.check_duplicate("req-uuid-123"), sample_resp)

    def test_mutex_lock(self):
        with self.lm.lock:
            pass


if __name__ == "__main__":
    unittest.main()
