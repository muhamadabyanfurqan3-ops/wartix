# Frontend Wartix

Frontend statis untuk pratinjau alur memilih film, jadwal, dan kursi. Film, jam tayang, serta kursi terisi pada `app.js` adalah data simulasi; halaman ini belum terhubung ke server gRPC. Integrasi browser memerlukan gateway HTTP atau gRPC-Web.

Jalankan dari root repository:

```bash
python -m http.server 8000 --directory frontend
```

Buka `http://localhost:8000` di browser.
