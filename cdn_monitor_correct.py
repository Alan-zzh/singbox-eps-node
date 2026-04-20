#!/usr/bin/env python3
"""
CDN Monitor - Correct Version
Uses user-provided verified CF IPs directly (no crawling needed)
"""

import os, sys, time, sqlite3, random, subprocess
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

# User-provided verified Cloudflare preferred IPs (China Telecom optimized)
# These are already ranked by latency/bandwidth from uouin.com
USER_CF_IPS = [
    '162.159.20.39',
    '162.159.58.151',
    '162.159.39.78',
    '162.159.38.109',
    '108.162.198.165',
    '172.64.52.191',
    '162.159.45.45',
    '172.64.53.201',
    '162.159.14.161',
    '162.159.5.5',
]

CDN_FALLBACK_IPS = [
    '104.16.1.1', '104.16.132.229', '104.17.1.1',
    '172.64.1.1', '172.67.1.1', '173.245.48.1',
]

MONITOR_INTERVAL = 3600

CDN_PROTOCOLS = [
    'vless_ws_cdn_ip',
    'vless_upgrade_cdn_ip',
    'trojan_ws_cdn_ip',
]

CF_PORTS = [8443, 2053, 2083]

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

def check_ip_connectivity(ip, ports=None):
    """Check if IP is reachable on CF ports. Returns True if at least one port works."""
    if ports is None:
        ports = CF_PORTS
    for port in ports:
        try:
            result = subprocess.run(
                ['bash', '-c', f'timeout 2 bash -c "echo > /dev/tcp/{ip}/{port}" 2>/dev/null'],
                timeout=5, capture_output=True
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False

def get_valid_ips(ip_list):
    """Filter IPs that are actually reachable, skip unreachable ones."""
    valid = []
    skipped = []
    for ip in ip_list:
        if check_ip_connectivity(ip):
            valid.append(ip)
        else:
            skipped.append(ip)
            logger.warning(f"  [SKIP] {ip} - unreachable")
    if skipped:
        logger.info(f"  Skipped {len(skipped)} unreachable IPs: {skipped}")
    return valid

def fetch_cdn_ips():
    """Get user-provided IPs, filter by connectivity."""
    logger.info(f">>> Checking {len(USER_CF_IPS)} user-provided CF IPs")
    valid_ips = get_valid_ips(USER_CF_IPS)
    if not valid_ips:
        logger.warning("[WARN] All user IPs unreachable, using fallback")
        valid_ips = get_valid_ips(CDN_FALLBACK_IPS)
    if not valid_ips:
        logger.warning("[WARN] All fallback IPs unreachable, using raw list")
        valid_ips = USER_CF_IPS
    logger.info(f"[OK] {len(valid_ips)} valid IPs available")
    return valid_ips

def assign_and_save_ips(ips):
    """Assign unique IP to each CDN protocol from valid IPs."""
    if not ips:
        return
    db_path = os.path.join(DATA_DIR, 'singbox.db')
    shuffled = ips.copy()
    random.shuffle(shuffled)
    assigned = {}
    for i, proto_key in enumerate(CDN_PROTOCOLS):
        assigned_ip = shuffled[i % len(shuffled)]
        assigned[proto_key] = assigned_ip
        logger.info(f"  {proto_key} -> {assigned_ip}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    for key, ip in assigned.items():
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", (key, ip))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_ips_list', ','.join(ips)))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"[OK] CDN IPs assigned and saved")

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
