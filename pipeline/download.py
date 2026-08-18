"""Download monthly BTS On-Time Performance extracts.

Source: Bureau of Transportation Statistics, "Reporting Carrier On-Time
Performance (1987-present)". Public domain, no authentication, no rate limit
published. One zip per calendar month, roughly 25-30 MB compressed.

Idempotent: a month already on disk with a size matching the server's
Content-Length is skipped, so an interrupted run can simply be re-run.

Downloads run concurrently. BTS throttles hard per connection -- a single
stream measured at ~0.16 MB/s, which is close to three hours for the full
window -- but it does not appear to throttle per client, so the wall time
falls roughly linearly with worker count.
"""

import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.config import BASE_URL, RAW_DIR, months

TIMEOUT = 300
RETRIES = 3
WORKERS = 8


def target(year: int, month: int):
    return RAW_DIR / f"{year}_{month}.zip"


def remote_size(url: str) -> int | None:
    try:
        r = requests.head(url, timeout=30, allow_redirects=True)
        if r.status_code == 200 and "Content-Length" in r.headers:
            return int(r.headers["Content-Length"])
    except requests.RequestException:
        pass
    return None


def fetch(year: int, month: int) -> str:
    """Download one month. Returns 'skipped', 'downloaded', or raises."""
    url = BASE_URL.format(year=year, month=month)
    path = target(year, month)
    expected = remote_size(url)

    if path.exists() and expected and path.stat().st_size == expected:
        return "skipped"

    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            with requests.get(url, timeout=TIMEOUT, stream=True) as r:
                r.raise_for_status()
                tmp = path.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
                tmp.replace(path)
            return "downloaded"
        except requests.RequestException as e:
            last_error = e
            # BTS occasionally drops long connections; back off and retry.
            time.sleep(5 * attempt)

    raise RuntimeError(f"{year}-{month:02d} failed after {RETRIES} attempts: {last_error}")


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    todo = list(months())
    failures = []
    started = time.time()

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch, y, m): (y, m) for y, m in todo}
        for i, future in enumerate(as_completed(futures), 1):
            year, month = futures[future]
            try:
                status = future.result()
            except RuntimeError as e:
                failures.append(str(e))
                status = "FAILED"
            path = target(year, month)
            size = path.stat().st_size / 1e6 if path.exists() else 0
            print(f"[{i:2d}/{len(todo)}] {year}-{month:02d}  {status:<10} "
                  f"{size:6.1f} MB  ({time.time() - started:5.0f}s elapsed)", flush=True)

    if failures:
        print("\nFailures:", file=sys.stderr)
        for f in failures:
            print(" ", f, file=sys.stderr)
        return 1

    total = sum(p.stat().st_size for p in RAW_DIR.glob("*.zip")) / 1e9
    print(f"\n{len(todo)} months on disk, {total:.2f} GB compressed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
