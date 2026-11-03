"""Concurrent gRPC latency and throughput benchmark with an HTML chart report."""

import argparse
import concurrent.futures
import csv
import html
import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

import grpc

from client.engine import WartixClient


def _percentile(samples: List[float], percentile: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = min(int((len(ordered) - 1) * percentile), len(ordered) - 1)
    return ordered[index]


def benchmark_concurrency(
    client: WartixClient,
    concurrency_levels: Iterable[int] = (1, 5, 20),
    requests_per_level: int = 100,
    jadwal_id: str = "SHOW_1300_ST1",
    kursi_id: str = "A1",
) -> List[Dict[str, float]]:
    if requests_per_level < 1:
        raise ValueError("requests_per_level must be at least 1")

    results = []
    for concurrency in concurrency_levels:
        if concurrency < 1:
            raise ValueError("Concurrency levels must be at least 1")
        latencies = []
        failures = 0

        def measure_request():
            started = time.perf_counter()
            client.get_seat_status(jadwal_id, kursi_id)
            return time.perf_counter() - started

        benchmark_started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(measure_request) for _ in range(requests_per_level)]
            for future in concurrent.futures.as_completed(futures):
                try:
                    latencies.append(future.result())
                except grpc.RpcError:
                    failures += 1
        elapsed = time.perf_counter() - benchmark_started
        successful = len(latencies)
        results.append(
            {
                "clients": concurrency,
                "requests": requests_per_level,
                "successful": successful,
                "failed": failures,
                "elapsed_seconds": elapsed,
                "throughput_rps": successful / elapsed if elapsed else 0.0,
                "latency_mean_ms": statistics.mean(latencies) * 1000 if latencies else 0.0,
                "latency_p50_ms": _percentile(latencies, 0.50) * 1000,
                "latency_p95_ms": _percentile(latencies, 0.95) * 1000,
            }
        )
    return results


def _bar_chart(results: List[Dict[str, float]], metric: str, title: str, unit: str) -> str:
    width, height = 640, 280
    left, top, chart_width, chart_height = 56, 38, 550, 185
    values = [result[metric] for result in results]
    maximum = max(values, default=0) or 1
    bar_width = min(90, chart_width / max(len(results) * 2, 1))
    bars = []
    for index, result in enumerate(results):
        x = left + (index + 0.5) * chart_width / len(results) - bar_width / 2
        bar_height = result[metric] / maximum * chart_height
        y = top + chart_height - bar_height
        label = f"{result[metric]:.2f} {unit}"
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" fill="#087e8b" />'
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle">{label}</text>'
            f'<text x="{x + bar_width / 2:.1f}" y="{top + chart_height + 22}" text-anchor="middle">{int(result["clients"])} clients</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(title)}">'
        f'<text x="{left}" y="22" class="chart-title">{html.escape(title)}</text>'
        f'<line x1="{left}" y1="{top + chart_height}" x2="{left + chart_width}" y2="{top + chart_height}" stroke="#65727a" />'
        + "".join(bars)
        + "</svg>"
    )


def write_report(results: List[Dict[str, float]], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"benchmark_{stamp}.csv"
    html_path = output_dir / f"benchmark_{stamp}.html"
    fieldnames = list(results[0]) if results else []
    with csv_path.open("w", newline="", encoding="utf-8") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=fieldnames)
        if fieldnames:
            writer.writeheader()
            writer.writerows(results)

    table_rows = "".join(
        "<tr>" + "".join(f"<td>{result[key]:.2f}</td>" for key in fieldnames) + "</tr>"
        for result in results
    )
    headers = "".join(f"<th>{html.escape(key.replace('_', ' ').title())}</th>" for key in fieldnames)
    report_html = f"""<!doctype html>
<html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wartix Client Benchmark</title>
<style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:1100px;margin:32px auto;padding:0 20px;color:#18323a;background:#f2f6f5}}
h1{{font-size:28px}}.charts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}}
svg{{width:100%;background:#fff;border:1px solid #cbd9d8}}text{{font:12px system-ui,sans-serif;fill:#18323a}}.chart-title{{font-size:15px;font-weight:700}}
table{{border-collapse:collapse;width:100%;margin-top:20px;background:#fff}}th,td{{padding:9px;border:1px solid #cbd9d8;text-align:right}}th{{background:#dcebea}}
</style></head><body><h1>Wartix Client Benchmark</h1>
<p>Grafik dibuat dari request GetStatusKursi; throughput dihitung sebagai request sukses per detik.</p>
<section class="charts">{_bar_chart(results, 'throughput_rps', 'Throughput', 'req/s')}
{_bar_chart(results, 'latency_p95_ms', 'Latency p95', 'ms')}</section>
<table><thead><tr>{headers}</tr></thead><tbody>{table_rows}</tbody></table>
</body></html>"""
    html_path.write_text(report_html, encoding="utf-8")
    return csv_path, html_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Wartix client latency and throughput")
    parser.add_argument("--servers", default="localhost:50051", help="Comma-separated gRPC endpoints")
    parser.add_argument("--requests", type=int, default=100, help="Requests per concurrency level")
    parser.add_argument("--output", type=Path, default=Path("reports"), help="Report output directory")
    parser.add_argument("--jadwal", default="SHOW_1300_ST1", help="Schedule ID for status requests")
    parser.add_argument("--kursi", default="A1", help="Seat ID for status requests")
    args = parser.parse_args()
    endpoints = [endpoint.strip() for endpoint in args.servers.split(",") if endpoint.strip()]
    with WartixClient(endpoints=endpoints) as client:
        results = benchmark_concurrency(client, (1, 5, 20), args.requests, args.jadwal, args.kursi)
    csv_path, html_path = write_report(results, args.output)
    print("clients | ok | failed | throughput (req/s) | mean (ms) | p95 (ms)")
    for result in results:
        print(
            f"{int(result['clients']):7} | {int(result['successful']):2} | {int(result['failed']):6} | "
            f"{result['throughput_rps']:18.2f} | {result['latency_mean_ms']:9.2f} | {result['latency_p95_ms']:8.2f}"
        )
    print(f"CSV: {csv_path}\nGrafik: {html_path}")


if __name__ == "__main__":
    main()
