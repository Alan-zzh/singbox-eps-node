#!/usr/bin/env python3
"""
CDN Monitor - Final Correct Version
Uses static China-optimized CF IP sources (not affected by server location)
Plus API for manual IP updates
"""

import os, sys, time, sqlite3, random, subprocess, json, re
from datetime import datetime
from flask import Flask, request, jsonify

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

# Static China-optimized CF IP sources (GitHub raw files, not affected by GeoIP)
STATIC_IP_SOURCES = [
    'https://raw.githubusercontent.com/ymyuuu/IPDB/main/bestproxy.txt',
    'https://raw.githubusercontent.com/Alvin9999/pac2/master/cloudflare/ip.txt',
    'https://raw.githubusercontent.com/badafans/better-cloudflare-ip/master/platforms/Cloudflare/IPv4.txt',
]

# Default fallback IPs
DEFAULT_CF_IPS = [
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

MONITOR_INTERVAL = 3600  # Check connectivity every hour

CDN_PROTOCOLS = [
    'vless_ws_cdn_ip',
    'vless_upgrade_cdn_ip',
    'trojan_ws_cdn_ip',
]

CF_PORTS = [8443, 2053, 2083]

app = Flask(__name__)

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

def get_user_ips():
    """Get user-provided IPs from database, fallback to default."""
    try:
        conn = sqlite3.connect(os.path.join(DATA_DIR, 'singbox.db'))
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM cdn_settings WHERE key='user_cf_ips'")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0].split(',')
    except Exception:
        pass
    return DEFAULT_CF_IPS

def fetch_static_ips():
    """Fetch IPs from static GitHub sources (China-optimized, not affected by GeoIP)."""
    all_ips = []
    import urllib.request
    
    for url in STATIC_IP_SOURCES:
        try:
            logger.info(f">>> Fetching from: {url}")
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            with urllib.request.urlopen(req, timeout=15) as response:
                text = response.read().decode('utf-8')
                # Extract IPs
                ips = re.findall(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', text)
                # Validate IPs
                valid_ips = [ip for ip in ips if all(0 <= int(x) <= 255 for x in ip.split('.'))]
                all_ips.extend(valid_ips)
                logger.info(f"  Got {len(valid_ips)} IPs from {url}")
        except Exception as e:
            logger.warning(f"  Failed to fetch from {url}: {e}")
    
    # Deduplicate while preserving order
    unique_ips = list(dict.fromkeys(all_ips))
    logger.info(f"[OK] Total unique IPs from static sources: {len(unique_ips)}")
    return unique_ips[:50]  # Keep top 50

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
    """Get IPs from static sources, filter by connectivity."""
    # First try static sources
    static_ips = fetch_static_ips()
    if static_ips:
        logger.info(f">>> Checking {len(static_ips)} static source IPs")
        valid_ips = get_valid_ips(static_ips)
        if valid_ips:
            logger.info(f"[OK] {len(valid_ips)} valid IPs from static sources")
            return valid_ips
    
    # Fallback to user-provided IPs
    user_ips = get_user_ips()
    logger.info(f">>> Fallback: Checking {len(user_ips)} user-provided CF IPs")
    valid_ips = get_valid_ips(user_ips)
    if not valid_ips:
        logger.warning("[WARN] All user IPs unreachable, using fallback")
        valid_ips = get_valid_ips(CDN_FALLBACK_IPS)
    if not valid_ips:
        logger.warning("[WARN] All fallback IPs unreachable, using raw list")
        valid_ips = user_ips
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

@app.route('/api/update-cdn-ips', methods=['POST'])
def update_cdn_ips():
    """API endpoint to update user-provided CF IPs."""
    try:
        data = request.get_json()
        if not data or 'ips' not in data:
            return jsonify({'error': 'Missing ips field'}), 400
        
        ips = data['ips']
        if not isinstance(ips, list) or len(ips) < 3:
            return jsonify({'error': 'ips must be a list with at least 3 IPs'}), 400
        
        # Validate IPs
        valid_ips = []
        for ip in ips:
            if re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', ip):
                valid_ips.append(ip)
        
        if len(valid_ips) < 3:
            return jsonify({'error': 'At least 3 valid IPs required'}), 400
        
        # Save to database
        conn = sqlite3.connect(os.path.join(DATA_DIR, 'singbox.db'))
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('user_cf_ips', ','.join(valid_ips)))
        cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", ('cdn_updated_at', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        logger.info(f"[OK] Updated user CF IPs: {valid_ips}")
        
        # Re-assign IPs
        valid_connected = get_valid_ips(valid_ips)
        if valid_connected:
            assign_and_save_ips(valid_connected)
        
        return jsonify({
            'message': 'CDN IPs updated successfully',
            'ips': valid_ips,
            'valid_count': len(valid_connected) if valid_connected else 0
        })
    except Exception as e:
        logger.error(f"[ERROR] Update CDN IPs failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/cdn-status', methods=['GET'])
def cdn_status():
    """API endpoint to check CDN IP status."""
    try:
        user_ips = get_user_ips()
        conn = sqlite3.connect(os.path.join(DATA_DIR, 'singbox.db'))
        cursor = conn.cursor()
        
        status = {}
        for proto in CDN_PROTOCOLS:
            cursor.execute("SELECT value FROM cdn_settings WHERE key=?", (proto,))
            row = cursor.fetchone()
            status[proto] = row[0] if row else None
        
        cursor.execute("SELECT value FROM cdn_settings WHERE key='cdn_updated_at'")
        row = cursor.fetchone()
        status['updated_at'] = row[0] if row else None
        
        conn.close()
        
        return jsonify({
            'user_ips': user_ips,
            'assigned': status,
            'valid_count': len(get_valid_ips(user_ips))
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    elif len(sys.argv) > 1 and sys.argv[1] == 'api':
        init_db()
        app.run(host='0.0.0.0', port=8081, debug=False)
    else:
        monitor_loop()
