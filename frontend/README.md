# Frontend Wartix

Frontend Wartix terhubung ke layanan gRPC melalui `web_gateway.py`. Gateway menyajikan halaman, membaca katalog dari `DaftarJadwal`, meneruskan pemesanan ke `PesanKursi`, dan meneruskan streaming status kursi ke browser dengan Server-Sent Events.

Jalankan dari root repository:

```bash
python web_gateway.py
```

Buka `http://localhost:8000` di browser. Gateway akan menyalakan backend gRPC lokal pada port 50051 bila belum tersedia.
