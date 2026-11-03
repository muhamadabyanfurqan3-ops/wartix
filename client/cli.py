"""Interactive command-line client for Wartix."""

import argparse

import grpc

from client.engine import WartixClient


def _show_schedule(client: WartixClient, jadwal_id: str) -> None:
    schedule = client.get_schedule(jadwal_id)
    print(f"\n{schedule.nama_film} | {schedule.jam_tayang} | {schedule.studio_id}")
    print(f"Kursi tersedia: {schedule.kursi_tersedia}/{schedule.total_kursi}")
    for row in "ABCDEF":
        seats = [seat for seat in schedule.kursi if seat.kursi_id.startswith(row)]
        print(" ".join(f"{seat.kursi_id}:{seat.status}" for seat in seats))


def run_cli(client: WartixClient) -> None:
    actions = {
        "1": "Lihat jadwal dan kursi",
        "2": "Cek status kursi",
        "3": "Pesan kursi",
        "4": "Konfirmasi pembayaran",
        "5": "Pantau stream status kursi",
        "0": "Keluar",
    }
    while True:
        print("\n=== Wartix Client ===")
        for key, label in actions.items():
            print(f"{key}. {label}")
        choice = input("Pilih: ").strip()
        if choice == "0":
            return
        try:
            if choice == "1":
                _show_schedule(client, input("ID jadwal: ").strip())
            elif choice == "2":
                result = client.get_seat_status(
                    input("ID jadwal: ").strip(), input("ID kursi: ").strip()
                )
                print(f"{result.kursi_id}: {result.status} (user: {result.user_id or '-'})")
            elif choice == "3":
                result = client.book_seat(
                    input("ID jadwal: ").strip(),
                    input("ID kursi: ").strip(),
                    input("ID user: ").strip(),
                )
                print(f"{'Berhasil' if result.sukses else 'Ditolak'}: {result.pesan}")
                if result.held_until:
                    print(f"Batas pembayaran: {result.held_until:.0f}")
            elif choice == "4":
                result = client.confirm_payment(
                    input("ID jadwal: ").strip(),
                    input("ID kursi: ").strip(),
                    input("ID user: ").strip(),
                )
                print(f"{'Berhasil' if result.sukses else 'Ditolak'}: {result.pesan}")
            elif choice == "5":
                jadwal_id = input("ID jadwal: ").strip()
                kursi_id = input("ID kursi: ").strip()
                print("Memantau status (Ctrl+C untuk berhenti)...")
                stream = client.stream_seat_status(jadwal_id, kursi_id)
                try:
                    for status in stream:
                        print(
                            f"{status.jadwal_id}/{status.kursi_id}: "
                            f"{status.status} (user: {status.user_id or '-'}, "
                            f"held_until: {status.held_until:.0f})"
                        )
                except KeyboardInterrupt:
                    stream.cancel()
                    print("\nPemantauan dihentikan.")
            else:
                print("Pilihan tidak dikenal.")
        except grpc.RpcError as error:
            print(f"RPC gagal ({error.code().name}): {error.details()}")
        except ValueError as error:
            print(f"Input tidak valid: {error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive Wartix gRPC client")
    parser.add_argument(
        "--servers",
        default="localhost:50051",
        help="Comma-separated gRPC endpoints in failover order",
    )
    args = parser.parse_args()
    endpoints = [endpoint.strip() for endpoint in args.servers.split(",") if endpoint.strip()]
    with WartixClient(endpoints=endpoints) as client:
        try:
            run_cli(client)
        except (EOFError, KeyboardInterrupt):
            print("\nClient ditutup.")


if __name__ == "__main__":
    main()
