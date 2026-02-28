import urllib.request
import urllib.error
import json

BASE = "http://localhost:8000/api/v1"

def post(path, body, token=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"}
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def get(path, token=None, params=None):
    url = f"{BASE}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())

def section(title):
    print(f"\n{'='*60}")
    print(f"### {title} ###")
    print('='*60)

def label(name):
    print(f"\n--- {name} ---")

def out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))

# ── Login ──────────────────────────────────────────────────────
section("LOGIN EXISTING ACCOUNTS")

label("Login test_buyer")
r = post("/auth/login", {"username": "test_buyer", "password": "Test1234!"})
out(r)
TB = r.get("data", {}).get("access_token", "")
REFRESH_TB = r.get("data", {}).get("refresh_token", "")

label("Login test_seller")
r = post("/auth/login", {"username": "test_seller", "password": "Test1234!"})
out(r)
TS = r.get("data", {}).get("access_token", "")

label("Login test_observer")
r = post("/auth/login", {"username": "test_observer", "password": "Test1234!"})
out(r)
TO = r.get("data", {}).get("access_token", "")

print(f"\nTokens acquired:")
print(f"  TB  = {TB[:40]}...")
print(f"  TS  = {TS[:40]}...")
print(f"  TO  = {TO[:40]}...")

# ── T1 Auth Tests ──────────────────────────────────────────────
section("T1 — AUTH TESTS")

label("T1-5a: Login with wrong password")
out(post("/auth/login", {"username": "test_buyer", "password": "WrongPassword123"}))

label("T1-5b: Login with non-existent user")
out(post("/auth/login", {"username": "ghost_user_9999", "password": "Test1234!"}))

label("T1-6: Register duplicate username")
out(post("/auth/register", {"username": "test_buyer", "email": "other@test.com", "password": "Test1234!"}))

label("T1-7: Register duplicate email")
out(post("/auth/register", {"username": "other_user", "email": "test_buyer@test.com", "password": "Test1234!"}))

label("T1-8: Token refresh")
r = post("/auth/refresh", {"refresh_token": REFRESH_TB})
out(r)

label("T1-9: Access protected endpoint with no token")
out(get("/account/balance"))

label("T1-10: Access protected endpoint with invalid token")
out(get("/account/balance", token="invalid.token.here"))

# ── T2 Account Tests ───────────────────────────────────────────
section("T2 — ACCOUNT TESTS")

label("T2-1: Get balance (test_buyer)")
out(get("/account/balance", token=TB))

label("T2-2: Deposit valid amount (test_observer, 500)")
out(post("/account/deposit", {"amount": 500}, token=TO))

label("T2-3: Deposit zero amount (test_buyer)")
out(post("/account/deposit", {"amount": 0}, token=TB))

label("T2-4: Deposit negative amount (test_buyer)")
out(post("/account/deposit", {"amount": -100}, token=TB))

label("T2-5: Withdraw valid amount (test_seller, 1000)")
out(post("/account/withdraw", {"amount": 1000}, token=TS))

label("T2-6: Withdraw more than available (test_observer, 999999)")
out(post("/account/withdraw", {"amount": 999999}, token=TO))

label("T2-7: Withdraw zero (test_buyer)")
out(post("/account/withdraw", {"amount": 0}, token=TB))

label("T2-8: Get ledger (test_buyer)")
out(get("/account/ledger", token=TB))

label("T2-9: Get ledger with limit=3 (test_buyer)")
out(get("/account/ledger", token=TB, params={"limit": 3}))

# ── T3 Market Tests ────────────────────────────────────────────
section("T3 — MARKET TESTS")

label("T3-1: List all markets")
out(get("/markets", token=TB))

label("T3-2: Get market detail (MKT-BTC-100K-2026)")
out(get("/markets/MKT-BTC-100K-2026", token=TB))

label("T3-3: Get orderbook (MKT-BTC-100K-2026)")
out(get("/markets/MKT-BTC-100K-2026/orderbook", token=TB))

label("T3-4: Get non-existent market")
out(get("/markets/MKT-NONEXISTENT-9999", token=TB))

label("T3-5: Get orderbook for non-existent market")
out(get("/markets/MKT-NONEXISTENT-9999/orderbook", token=TB))

label("T3-6: List markets without auth")
out(get("/markets"))

print("\n\n=== ALL TESTS COMPLETE ===\n")
