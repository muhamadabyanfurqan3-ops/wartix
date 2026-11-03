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
