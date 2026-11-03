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
├── frontend/                     # UI pemesanan film, jadwal, dan kursi
├── web_gateway.py                # HTTP/SSE gateway ke service gRPC
└── tests/
    ├── test_concurrency.py      # Concurrency Stress Test 50 Thread Berebut Kursi di Jam Tayang Sama
    └── test_store_lock.py       # Unit Test StudioStore Multi-Jadwal & LockManager
```

## Fitur Utama

1. **Multi-Jam Tayang & Studio**:
   - Mendukung dua jadwal independen untuk setiap film: Avengers: Endgame (08:00, 13:40), Midway (10:00, 16:40), dan 1917 (12:00, 19:00).
   - Isolasi penuh: status kursi dikelola terpisah untuk setiap jam tayang.
2. **Keamanan Concurrency (Mutex Lock)**:
   - Akses atomik pada saat pengecekan dan pengubahan status kursi (`AVAILABLE` -> `PENDING_PAYMENT` -> `BOOKED`).
   - Mencegah double booking meski puluhan thread memesan serentak.
3. **Semantik At-Most-Once**:
   - Menggunakan `request_id` (UUIDv4) sebagai Idempotency Key.
   - Retry request tidak akan menduplikasi pemesanan melainkan menyajikan response dari cache.

## Desain Interface Protocol Buffers

Kontrak lengkap dan alasan pemilihan pola komunikasi tercatat di [`docs/idl-proto.md`](docs/idl-proto.md).
File sumber IDL berada di `proto/wartix.proto`; stub Python di `generated/` dibuat dari file tersebut.

Untuk membuat ulang stub setelah mengubah IDL:

```bash
python -m grpc_tools.protoc -I proto --python_out=generated --grpc_python_out=generated proto/wartix.proto
```

## Cara Menjalankan

### 1. Menjalankan Website + Backend
```bash
python web_gateway.py
```

Buka `http://localhost:8000`. Gateway menyajikan frontend dan menyalakan backend gRPC lokal pada port 50051 jika belum berjalan.

### 2. Menjalankan Server gRPC saja
```bash
python server/server_wartix.py
```

### 3. Menjalankan Concurrency Stress Test (50 Threads)
```bash
python tests/test_concurrency.py
```

### 4. Menjalankan Unit Test
```bash
python -m unittest discover tests
```

### 5. Menjalankan Client Interaktif
```bash
python -m client.cli --servers localhost:50051
```

Beberapa endpoint dapat diberikan berurutan untuk failover:
```bash
python -m client.cli --servers localhost:50051,localhost:50052
```

Setiap RPC memakai timeout 2 detik dan maksimal 3 retry dengan exponential backoff. Retry transaksi memakai `request_id` yang sama. Server saat ini menyimpan kursi dan cache deduplikasi di memori masing-masing; endpoint failover hanya menjaga koneksi, bukan mereplikasi state. Untuk failover transaksi yang konsisten, semua endpoint perlu memakai state dan idempotency store bersama.

### 6. Benchmark Latensi & Throughput
```bash
python -m client.benchmark --servers localhost:50051 --requests 100
```

Benchmark menguji 1, 5, dan 20 client paralel, lalu membuat file CSV dan laporan HTML bergrafik di direktori `reports/`. Gunakan `--output path/to/reports` untuk memilih lokasi lain. Beberapa endpoint dapat diberikan memakai format daftar yang sama seperti CLI.
