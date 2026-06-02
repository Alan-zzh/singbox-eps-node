
import sqlite3
import os

os.chdir("/root/singbox-eps-node")

print("===== CDN DATABASE STATUS =====")
try:
    conn = sqlite3.connect("data/singbox.db")
    c = conn.cursor()
    c.execute("SELECT key, value FROM config WHERE key LIKE '%cdn%'")
    rows = c.fetchall()
    for r in rows:
        val_preview = r[1][:300] if r[1] else "NULL"
        print(f"KEY: {r[0]}")
        print(f"VAL: {val_preview}")
        print("---")
    conn.close()
except Exception as e:
    print(f"DB error: {e}")

print("\n===== CONFIG UPDATE HISTORY =====")
try:
    conn = sqlite3.connect("data/singbox.db")
    c = conn.cursor()
    c.execute("SELECT key, value, updated_at FROM config ORDER BY updated_at DESC LIMIT 10")
    rows = c.fetchall()
    for r in rows:
        val_short = r[1][:80] if r[1] else "NULL"
        print(f"{r[0]}: {val_short} ... | {r[2]}")
    conn.close()
except Exception as e:
    print(f"DB error: {e}")

print("\n===== CDN IP POOL STATS =====")
try:
    from scripts.config import CDN_PREFERRED_IPS, CDN_IP_BLACKLIST
    print(f"CDN_PREFERRED_IPS: {len(CDN_PREFERRED_IPS)} IPs")
    print(f"CDN_IP_BLACKLIST: {len(CDN_IP_BLACKLIST)} IPs")
    print("\nBlacklist IPs:")
    for ip in CDN_IP_BLACKLIST:
        print(f"  {ip}")
except Exception as e:
    print(f"Config error: {e}")
