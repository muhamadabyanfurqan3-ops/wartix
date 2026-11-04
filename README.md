# Wartix — Reservasi Tiket Bioskop dengan gRPC

Wartix adalah aplikasi reservasi tiket bioskop berbasis Python dan gRPC. Aplikasi menyediakan katalog film dan jadwal, denah kursi, pemesanan hold, pembatalan hold, konfirmasi pembayaran simulasi, serta pemantauan status kursi.

## Kebutuhan

- Python 3.10 atau lebih baru.
- Koneksi internet saat memasang dependensi.
- Untuk client pada laptop berbeda: kedua laptop dapat saling terhubung melalui jaringan, dan firewall server mengizinkan koneksi ke port gRPC `50051`.

## Persiapan lingkungan Python

Jika repository belum tersedia di laptop, clone branch proyek lalu masuk ke direktori repository:

```powershell
git clone --branch default-branch https://github.com/muhamadabyanfurqan3-ops/wartix.git wartix
cd wartix
```

Jalankan langkah berikut dari direktori utama repository (direktori yang berisi folder `client`, `server`, `generated`, dan file `web_gateway.py`).

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install grpcio==1.85.1 "protobuf>=7.35.1,<8"
```

Jika aktivasi virtual environment ditolak oleh PowerShell, izinkan script hanya untuk sesi terminal saat ini, lalu aktifkan kembali:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install grpcio==1.85.1 'protobuf>=7.35.1,<8'
```

## Menjalankan website dan backend

Dari direktori utama repository, jalankan:

```powershell
python web_gateway.py
```

Buka `http://localhost:8000` pada browser laptop yang sama. Gateway menyajikan frontend dan API HTTP, lalu menggunakan layanan gRPC di port `50051`. Jika belum ada server gRPC, gateway akan menjalankan backend lokal secara otomatis. Biarkan terminal ini tetap terbuka selama aplikasi digunakan.

### Membuka website dari laptop lain di jaringan lokal

Pada PowerShell laptop server, izinkan gateway menerima koneksi jaringan sebelum menjalankannya:

```powershell
$env:WARTIX_HTTP_HOST = "0.0.0.0"
python web_gateway.py
```

Cari IPv4 laptop server dengan `ipconfig`, kemudian buka `http://IP-SERVER:8000` dari browser laptop client. Contoh: `http://192.168.100.228:8000`. Izinkan port `8000` pada Windows Firewall jika koneksi terhalang. Kedua laptop harus berada pada jaringan yang dapat saling menjangkau.

## Menjalankan server gRPC dan client CLI

Untuk demo client/server, gunakan dua terminal pada laptop server dan satu terminal pada laptop client. Pastikan virtual environment dan dependensi sudah disiapkan di setiap laptop yang menjalankan program Python.

### Terminal 1 — server gRPC

Dari direktori utama repository pada laptop server:

```powershell
python -m server.server_wartix
```

Server mendengarkan pada port `50051`. Biarkan terminal tetap terbuka. Catat IPv4 laptop server dengan `ipconfig` dan pastikan firewall mengizinkan koneksi masuk pada port `50051`.

### Terminal 2 — client CLI di laptop server

```powershell
python -m client.cli --servers localhost:50051
```

### Client CLI di laptop berbeda

Clone repository pada laptop client dan siapkan dependensinya. Jalankan dari direktori utama hasil clone, dengan alamat IPv4 laptop server:

```powershell
python -m client.cli --servers 192.168.100.228:50051
```

Ganti alamat contoh tersebut jika IPv4 server berbeda. Menu CLI menyediakan pilihan melihat jadwal/kursi, memesan kursi, dan mengonfirmasi pembayaran. Hold kursi berlaku selama dua menit. Konfirmasi pembayaran di proyek ini adalah simulasi; tidak ada transaksi uang sungguhan.

Untuk beberapa endpoint gRPC, berikan alamat dalam urutan failover, dipisahkan koma:

```powershell
python -m client.cli --servers 192.168.100.228:50051,192.168.100.229:50051
```

Setiap proses server saat ini menyimpan data kursi dan cache deduplikasi di memorinya sendiri. Endpoint failover tidak mereplikasi atau menyinkronkan state antarmesin.

## Benchmark kinerja

Jalankan dari direktori utama repository pada laptop client. Server gRPC harus aktif dan port `50051` dapat dijangkau:

```powershell
python -m client.benchmark --servers 192.168.100.228:50051 --requests 100 --output reports
```

Benchmark menjalankan concurrency `1`, `5`, dan `20`. Hasil CSV dan HTML disimpan ke `reports/`. Gunakan angka CSV untuk mengisi jumlah request, waktu, throughput, mean, p50, dan p95 pada laporan.

## Menjalankan pengujian otomatis

Dari direktori utama repository:

```powershell
python -m unittest discover tests
```

## Kontrak Protobuf

Definisi service dan message berada pada [`proto/wartix.proto`](proto/wartix.proto). Stub Python hasil kompilasi tersedia pada folder `generated/`. Untuk membuat ulang stub setelah mengubah file `.proto`, pasang `grpcio-tools`, lalu jalankan:

```powershell
python -m pip install grpcio-tools
python -m grpc_tools.protoc -I proto --python_out=generated --grpc_python_out=generated proto/wartix.proto
```

## Catatan penyimpanan

Jadwal, status kursi, dan cache deduplikasi disimpan di memori proses. Data kembali ke kondisi awal setelah server dimulai ulang. `KonfirmasiPembayaran` pada aplikasi hanya mengubah status hold menjadi `BOOKED`; aplikasi belum terhubung ke penyedia pembayaran.
