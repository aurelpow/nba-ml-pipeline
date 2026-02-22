"""
Proxy diagnostic script – run this directly on the Cloud Run dev job
to isolate the current timeout issue with stats.nba.com.

Usage (Cloud Run env override):
  python scripts/test_proxy.py

Env vars read:
  NBA_PROXY_USER  – proxy username
  NBA_PROXY_PASS  – proxy password
  SAVE_MODE       – optional, just for display
"""

import os
import socket
import sys
import time
from urllib.parse import quote

# ── 1. Credential status ────────────────────────────────────────────────────
user = os.getenv("NBA_PROXY_USER", "")
pwd  = os.getenv("NBA_PROXY_PASS", "")
save_mode = os.getenv("SAVE_MODE", "unknown")

print("=" * 60)
print("  NBA Proxy Diagnostic")
print("=" * 60)
print(f"  SAVE_MODE       : {save_mode}")
print(f"  NBA_PROXY_USER  : {'SET (' + user[:4] + '***)' if user else 'NOT SET'}")
print(f"  NBA_PROXY_PASS  : {'SET (***)' if pwd else 'NOT SET'}")
print("=" * 60)

if not user or not pwd:
    print("[WARN] No proxy credentials found – running without proxy.\n")

proxy_host = "gate.decodo.com"
proxy_port = 10001
encoded_user = quote(user, safe="")
encoded_pass = quote(pwd, safe="")
proxy_url = f"http://{encoded_user}:{encoded_pass}@{proxy_host}:{proxy_port}" if user and pwd else None

# ── 2. Raw TCP connection to the proxy ──────────────────────────────────────
print(f"\n[TEST 1] Raw TCP to {proxy_host}:{proxy_port} ...")
try:
    start = time.time()
    with socket.create_connection((proxy_host, proxy_port), timeout=10):
        elapsed = time.time() - start
        print(f"  ✅ Connected in {elapsed:.2f}s")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    print("     → Proxy host is unreachable from this GCP region.")
    print("     → Check if Decodo proxy is active / not IP-blocked.")

# ── 3. HTTP through proxy → external IP check ───────────────────────────────
print("\n[TEST 2] HTTP request via proxy → https://httpbin.org/ip ...")
try:
    import requests
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else {}
    start = time.time()
    r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=15)
    elapsed = time.time() - start
    print(f"  ✅ Status {r.status_code} in {elapsed:.2f}s  →  exit IP: {r.json()}")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    print("     → Proxy can't reach internet, or proxy auth failed.")

# ── 4. Direct HTTPS to stats.nba.com (no proxy) ─────────────────────────────
print("\n[TEST 3] Direct HTTPS to stats.nba.com (no proxy) ...")
try:
    import requests
    start = time.time()
    r = requests.get(
        "https://stats.nba.com/",
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15
    )
    elapsed = time.time() - start
    print(f"  ✅ Status {r.status_code} in {elapsed:.2f}s")
except Exception as e:
    print(f"  ❌ Failed: {e}")
    print("     → stats.nba.com may be blocking GCP IPs outright (expected).")

# ── 5. NBA API call via proxy ────────────────────────────────────────────────
print("\n[TEST 4] NBA API call via proxy (scheduleleaguev2 for 2025-26) ...")
try:
    from nba_api.stats.endpoints import scheduleleaguev2
    from nba_api.stats.library.parameters import LeagueID
    start = time.time()
    df = scheduleleaguev2.ScheduleLeagueV2(
        league_id=LeagueID.nba,
        season="2025-26",
        proxy=proxy_url,
        timeout=60,
    ).get_data_frames()[0]
    elapsed = time.time() - start
    print(f"  ✅ Got {len(df)} rows in {elapsed:.2f}s")
except Exception as e:
    elapsed = time.time() - start
    print(f"  ❌ Failed after {elapsed:.2f}s: {e}")

print("\n" + "=" * 60)
print("  Diagnostic complete.")
print("=" * 60)
