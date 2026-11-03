# Desain IDL dan Protocol Buffers Wartix

## Tujuan

IDL mendefinisikan kontrak antara client dan server Wartix. `package wartix` menjadi namespace gRPC, sedangkan `LayananWartix` mengelompokkan operasi reservasi. Semua operasi membawa identifier jadwal dan kursi yang diperlukan agar kursi pada jam tayang berbeda tetap terisolasi.

## Daftar RPC

| RPC | Pola | Request → Response | Tujuan |
|---|---|---|---|
| `PesanKursi` | Unary | `PesanKursiRequest` → `PesanKursiResponse` | Menahan satu kursi untuk pembayaran. `request_id` menjadi kunci idempotensi. |
| `GetJadwalStudio` | Unary | `JadwalRequest` → `JadwalResponse` | Mengambil metadata jadwal dan denah/ketersediaan kursi untuk satu jadwal. |
| `GetStatusKursi` | Unary | `KursiRequest` → `KursiStatusResponse` | Memeriksa status satu kursi pada satu jadwal. |
| `KonfirmasiPembayaran` | Unary | `BayarRequest` → `KonfirmasiResponse` | Mengonfirmasi pembayaran dan menyelesaikan hold menjadi pemesanan. `request_id` mendukung deduplikasi retry. |
| `DaftarJadwal` | Server streaming | `DaftarJadwalRequest` → stream `JadwalResponse` | Menerima semua jadwal sebagai pesan terpisah, satu jadwal per elemen stream. |

Dengan demikian interface mencakup empat operasi unary dan satu server-streaming. `DaftarJadwalRequest` kosong karena client meminta keseluruhan katalog, sementara server mengirim satu `JadwalResponse` untuk setiap jadwal yang tersedia. Client selesai membaca ketika stream ditutup oleh server.

## Alur data utama

1. Client meminta denah dengan `GetJadwalStudio(jadwal_id)` dan memilih kursi berstatus `AVAILABLE`.
2. Client mengirim `PesanKursi` dengan `request_id`, `jadwal_id`, `kursi_id`, dan `user_id`. Server mengembalikan hasil hold dan batas waktu pembayaran.
3. Setelah pembayaran, client mengirim `KonfirmasiPembayaran`; server menjawab apakah kursi berubah menjadi `BOOKED`.
4. Client dapat memakai `GetStatusKursi` untuk melihat status terkini. Untuk menjelajah katalog, client memakai `DaftarJadwal` dan membaca respons sampai stream berakhir.

## Aturan evolusi kontrak

- Nomor field protobuf yang sudah dipakai tidak boleh digunakan ulang atau diganti maknanya.
- Perubahan nama field/RPC harus diselaraskan dengan implementasi server dan client.
- Setelah mengubah `proto/wartix.proto`, generate ulang stub Python dengan perintah di README.
