#!/usr/bin/env python3
"""
CDN Monitor Script - Fixed Version
"""

import os, sys, time, sqlite3, random, re, requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config import SERVER_IP, DATA_DIR
    from logger import get_logger
except ImportError:
    def get_logger(name):
        import logging
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(name)

logger = get_logger('cdn_monitor')

CDN_IP_SOURCES = [
    'https://cf.090227.xyz/',
    'https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt',
]

CDN_FALLBACK_IPS = [
    '104.16.1.1', '104.16.132.229', '104.17.1.1',
    '172.64.1.1', '172.67.1.1', '173.245.48.1',
]

CDN_TOP_IPS_COUNT = 5
MONITOR_INTERVAL = 3600

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(os.path.join(DATA_DIR, 'singbox.db'))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cdn_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()
    return os.path.join(DATA_DIR, 'singbox.db')

def fetch_cdn_ips():
    for url in CDN_IP_SOURCES:
        try:
            logger.info(f">>> Try fetch preferred IP: {url}")
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                text = response.text
                ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
                ips = [ip for ip in ips if all(0 <= int(x) <= 255 for x in ip.split('.'))]
                if ips:
                    unique_ips = list(dict.fromkeys(ips))
                    logger.info(f"[OK] Got {len(unique_ips)} IPs from {url}")
                    return unique_ips[:20]
        except Exception as e:
            logger.warning(f"[WARN] {url} failed: {e}")
            continue
    logger.warning("[WARN] All sources failed, using fallback IPs")
    return CDN_FALLBACK_IPS

def assign_and_save_ips(ips):
    if not ips:
        return
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    selected_ip = random.choice(ips[:5]) if len(ips) >= 5 else ips[0]
    logger.info(f"\n>>> CDN Preferred IP:")
    logger.info(f"  Candidates: {ips[:5]}")
    logger.info(f"  Selected: {selected_ip}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ip', selected_ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips[:5])))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"[OK] CDN preferred IP saved: {selected_ip}")

def monitor_loop():
    init_db()
    while True:
        try:
            ips = fetch_cdn_ips()
            assign_and_save_ips(ips)
        except Exception as e:
            logger.error(f"[ERROR] Monitor exception: {e}")
        time.sleep(MONITOR_INTERVAL)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'once':
        init_db()
        ips = fetch_cdn_ips()
        assign_and_save_ips(ips)
    else:
        monitor_loop()
