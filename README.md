# Wartix - Distributed Cinema Ticket Reservation System (Multi-Jadwal)

Sistem reservasi tiket bioskop terdistribusi berbasis **Python gRPC** dengan pengelolaan **Multi-Jam Tayang & Studio**, sinkronisasi **Mutex Lock** untuk mencegah *Race Condition*, dan **Deduplication Cache** untuk semantik *At-Most-Once*.

## Arsitektur Modul

```
wartix/
├── proto/
│   └── wartix.proto             # Protocol Buffers IDL: RPC PesanKursi, GetJadwalStudio, GetStatusKursi, KonfirmasiPembayaran
├── generated/
│   ├── wartix_pb2.py            # Generated Protobuf Messages
│   └── wartix_pb2_grpc.py       # Generated gRPC Stubs
├── server/
│   ├── store.py                 # StudioStore: In-memory Data Store bertingkat (Jadwal -> 60 Kursi A1-F10)
│   ├── lock_manager.py          # LockManager: Mutex Lock & Deduplikasi Transaksi At-Most-Once
│   └── server_wartix.py         # LayananWartixServicer & gRPC Server Runner (Port 50051)
├── client/
│   ├── engine.py                # WartixClient: operasi gRPC, retry, failover, dan stream status
│   └── cli.py                   # CLI interaktif untuk melihat jadwal, memesan, dan memantau kursi
└── tests/
    ├── test_concurrency.py      # Concurrency Stress Test 50 Thread Berebut Kursi di Jam Tayang Sama
    └── test_store_lock.py       # Unit Test StudioStore Multi-Jadwal & LockManager
```

## Fitur Utama

1. **Multi-Jam Tayang & Studio**:
   - Mendukung jadwal independen seperti `"SHOW_1300_ST1"`, `"SHOW_1540_ST2"`, dan `"SHOW_1800_ST1"`.
   - Isolasi penuh: Kursi `A1` pada jam 13:00 tidak mempengaruhi kursi `A1` pada jam 15:40.
2. **Keamanan Concurrency (Mutex Lock)**:
   - Akses atomik pada saat pengecekan dan pengubahan status kursi (`AVAILABLE` -> `PENDING_PAYMENT` -> `BOOKED`).
   - Mencegah double booking meski puluhan thread memesan serentak.
3. **Semantik At-Most-Once**:
   - Menggunakan `request_id` (UUIDv4) sebagai Idempotency Key.
   - Retry request tidak akan menduplikasi pemesanan melainkan menyajikan response dari cache.
4. **Pemantauan Status Kursi**:
   - CLI dapat memantau satu kursi dalam satu jadwal lewat stream gRPC.
   - Stream mengirim status awal, lalu hanya mengirim ulang saat status atau pemilik hold berubah.
   - Tekan `Ctrl+C` untuk menghentikan pemantauan dan kembali ke menu.

## Cara Menjalankan

### 1. Menjalankan Server gRPC
```bash
python server/server_wartix.py
```

### 2. Menjalankan Concurrency Stress Test (50 Threads)
```bash
python tests/test_concurrency.py
```

### 3. Menjalankan Unit Test
```bash
python -m unittest discover tests
```

### 4. Menjalankan Client Interaktif
```bash
python -m client.cli --servers localhost:50051
```

Beberapa endpoint dapat diberikan berurutan untuk failover:
```bash
python -m client.cli --servers localhost:50051,localhost:50052
```

#### Pengujian multi-port dan failover

Buka dua terminal pada komputer server. Jalankan satu server di setiap terminal:
```bash
python server/server_wartix.py 50051
python server/server_wartix.py 50052
```

Di terminal client, arahkan client ke kedua port:
```bash
python -m client.cli --servers localhost:50051,localhost:50052
```

Pilih aksi seperti melihat jadwal atau mengecek status beberapa kali untuk mencoba kedua endpoint. Matikan server pada port pertama dengan `Ctrl+C`, lalu lakukan aksi lagi; RPC unary akan mencoba endpoint berikutnya ketika mendapat error sementara. Untuk pengujian otomatis multi-client dan failover port, jalankan:
```bash
python -m unittest tests.test_client
```

Untuk komputer berbeda dalam jaringan lokal, jalankan server dengan perintah port yang sama pada komputer server, lalu ganti `localhost` pada client dengan alamat IP komputer tersebut, misalnya `192.168.1.10:50051,192.168.1.10:50052`. Pastikan port TCP diizinkan firewall dan komputer client dapat menjangkau server. Transport saat ini menggunakan gRPC tanpa TLS; gunakan hanya pada jaringan tepercaya.

Setiap proses server menyimpan kursi dan cache deduplikasi sendiri di memori. Failover koneksi tidak mereplikasi data, sehingga jangan menganggap transaksi yang diterima server pertama otomatis terlihat di server kedua; konsistensi transaksi lintas server memerlukan state dan cache idempotensi bersama.

Setiap pemanggilan RPC unary memakai timeout 2 detik dan maksimal 3 retry tambahan untuk error sementara (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, atau `RESOURCE_EXHAUSTED`). Exponential backoff dimulai dari 0,1 detik, menjadi 0,2 dan 0,4 detik, dengan batas 1 detik. Setiap transaksi pemesanan atau pembayaran mendapat `request_id` UUIDv4 unik; ID yang sama dipakai kembali pada semua retry transaksi tersebut agar deduplikasi tetap bekerja. Pemanggilan transaksi baru mendapat ID baru.

Server saat ini menyimpan kursi dan cache deduplikasi di memori masing-masing; endpoint failover hanya menjaga koneksi, bukan mereplikasi state. Untuk failover transaksi yang konsisten, semua endpoint perlu memakai state dan idempotency store bersama.

### 5. Benchmark Latensi & Throughput
```bash
python -m client.benchmark --servers localhost:50051 --requests 100
```

Benchmark membuat 1, 5, dan 20 client gRPC terpisah yang mulai mengirim request secara serentak. `--requests` menentukan total request per tingkat konkurensi dan harus minimal 20 agar semua client aktif; hasil mencakup latensi rata-rata, p50, p95 (ms), throughput sukses (req/s), serta jumlah request gagal. Laporan CSV dan HTML bergrafik disimpan di direktori `reports/`. Gunakan `--output path/to/reports` untuk memilih lokasi lain. Beberapa endpoint dapat diberikan memakai format daftar yang sama seperti CLI.
