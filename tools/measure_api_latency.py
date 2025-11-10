"""
measure_api_latency.py

Простий скрипт для вимірювання затримки (RTT) до кількох REST endpoint.
- За замовчуванням тестує публічні Binance REST endpoints (time, exchangeInfo, markPrice)
- Виводить статистику: count, mean, std, p50, p90, p95, p99, min, max

Запуск (PowerShell):
python tools\\measure_api_latency.py --count 100 --symbols BTCUSDT ETHUSDT

Параметри:
  --count N        кількість запитів на endpoint (default 50)
  --symbols S1 S2  список символів для exchangeInfo/markPrice
  --endpoints E1   додаткові endpoint (необхідно вказати повні URL)

Примітки:
- Цей скрипт використовує лише публічні REST endpoint, щоб не вимагати ключів.
- Для вимірювання приватних endpoint (positionRisk, openOrders) можна додати окремий режим,
  що використовує проєктний adapter, але це може потребувати конфігурації/ключів.
"""

import argparse
import requests
import time
import statistics
from typing import List, Dict

DEFAULT_BINANCE_FUTURES = "https://fapi.binance.com"

ENDPOINTS = {
    "time": ("/fapi/v1/time", "GET"),
    "exchangeInfo": ("/fapi/v1/exchangeInfo", "GET"),
    "markPrice": ("/fapi/v1/premiumIndex", "GET"),
}


def measure_url(url: str, method: str = "GET", params: Dict = None, timeout: float = 10.0, retries: int = 2, verify_ssl: bool = True) -> float:
    """Виконати один запит та повернути RTT у мс; у випадку помилки повернути None"""
    for attempt in range(retries + 1):
        try:
            t0 = time.perf_counter()
            if method.upper() == "GET":
                r = requests.get(url, params=params,
                                 timeout=timeout, verify=verify_ssl)
            else:
                r = requests.post(url, json=params,
                                  timeout=timeout, verify=verify_ssl)
            t1 = time.perf_counter()
            # Не перевіряємо код відповіді детально — метрика RTT
            return (t1 - t0) * 1000.0
        except KeyboardInterrupt:
            # Не ловимо KeyboardInterrupt - дозволимо користувачу перервати
            raise
        except Exception as e:
            # Для інших помилок - спробуємо ще раз після невеликої паузи
            if attempt < retries:
                time.sleep(0.1 * (attempt + 1))  # Пауза 0.1s, 0.2s, ...
                continue
            # Повертаємо None для помилкових запитів після всіх спроб
            return None


def stats_from_samples(samples: List[float]) -> Dict:
    s_valid = [s for s in samples if s is not None]
    s_failed = len(samples) - len(s_valid)
    if not s_valid:
        return {
            "count": 0,
            "failed": s_failed,
        }
    return {
        "count": len(s_valid),
        "failed": s_failed,
        "mean_ms": statistics.mean(s_valid),
        "stdev_ms": statistics.stdev(s_valid) if len(s_valid) > 1 else 0.0,
        "p50_ms": percentile(s_valid, 50),
        "p90_ms": percentile(s_valid, 90),
        "p95_ms": percentile(s_valid, 95),
        "p99_ms": percentile(s_valid, 99),
        "min_ms": min(s_valid),
        "max_ms": max(s_valid),
    }


def percentile(data: List[float], p: float) -> float:
    data_sorted = sorted(data)
    k = (len(data_sorted) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(data_sorted) - 1)
    if f == c:
        return data_sorted[int(k)]
    d0 = data_sorted[f] * (c - k)
    d1 = data_sorted[c] * (k - f)
    return d0 + d1


def run_measurement(base_url: str, symbols: List[str], count: int, verify_ssl: bool = True):
    results = {}

    print(f"Testing {count} requests per endpoint...")

    # time
    print("Testing /fapi/v1/time...", end="", flush=True)
    samples = []
    for i in range(count):
        if i % 20 == 0 and i > 0:
            print(f" {i}/{count}", end="", flush=True)
        url = base_url + ENDPOINTS["time"][0]
        samples.append(measure_url(url, verify_ssl=verify_ssl))
    print(" done")
    results["time"] = stats_from_samples(samples)

    # exchangeInfo per symbol
    for sym in symbols:
        print(
            f"Testing /fapi/v1/exchangeInfo for {sym}...", end="", flush=True)
        samples = []
        for i in range(count):
            if i % 20 == 0 and i > 0:
                print(f" {i}/{count}", end="", flush=True)
            url = base_url + ENDPOINTS["exchangeInfo"][0]
            samples.append(measure_url(
                url, params={"symbol": sym}, verify_ssl=verify_ssl))
        print(" done")
        results[f"exchangeInfo:{sym}"] = stats_from_samples(samples)

    # markPrice (premiumIndex) per symbol
    for sym in symbols:
        print(
            f"Testing /fapi/v1/premiumIndex for {sym}...", end="", flush=True)
        samples = []
        for i in range(count):
            if i % 20 == 0 and i > 0:
                print(f" {i}/{count}", end="", flush=True)
            url = base_url + ENDPOINTS["markPrice"][0]
            samples.append(measure_url(
                url, params={"symbol": sym}, verify_ssl=verify_ssl))
        print(" done")
        results[f"markPrice:{sym}"] = stats_from_samples(samples)

    return results


def pretty_print(results: Dict):
    for key, st in results.items():
        print(f"--- {key} ---")
        if st.get("count", 0) == 0:
            print(f"  no successful samples (failed={st.get('failed', 0)})")
            continue
        print(f"  samples: {st['count']}  failed: {st['failed']}")
        print(
            f"  mean: {st['mean_ms']:.1f} ms  p50: {st['p50_ms']:.1f} ms  p95: {st['p95_ms']:.1f} ms  p99: {st['p99_ms']:.1f} ms")
        print(
            f"  min: {st['min_ms']:.1f} ms  max: {st['max_ms']:.1f} ms  stdev: {st['stdev_ms']:.1f} ms")
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=50,
                        help="кількість запитів на endpoint")
    parser.add_argument("--symbols", nargs="*",
                        default=["BTCUSDT", "ETHUSDT"], help="символи для тесту")
    parser.add_argument("--base-url", default=DEFAULT_BINANCE_FUTURES,
                        help="базовий URL для futures API")
    parser.add_argument("--no-verify", action="store_true",
                        help="вимкнути SSL верифікацію (якщо проблеми з SSL)")

    args = parser.parse_args()

    print(
        f"Measuring API RTT to {args.base_url} (count={args.count}, ssl_verify={not args.no_verify})")
    res = run_measurement(args.base_url, args.symbols,
                          args.count, verify_ssl=not args.no_verify)
    pretty_print(res)
