#!/usr/bin/env python3
"""Seed CDN IP database with user's preferred IPs and simple connectivity test"""
import sys, os, json, sqlite3, socket

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts'))
from config import CDN_PREFERRED_IPS

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'singbox.db')

def tcp_test(ip, port=443, timeout=3):
    """Simple TCP connectivity test"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        result = s.connect_ex((ip, port))
        s.close()
        return result == 0
    except:
        return False

def seed_db(ips):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Test each IP - quick TCP test
    working_ips = []
    for ip in ips[:30]:  # Test first 30 from preferred list
        alive = tcp_test(ip)
        print(f"  {ip}: {'alive' if alive else 'dead'}")
        if alive:
            working_ips.append(ip)
    
    if not working_ips:
        print("No working IPs found, using fallback")
        working_ips = ['104.21.96.1', '172.67.140.1', '104.21.112.1']
    
    # Build scored_ips list for cdn_ips_list
    scored_ips = []
    # Top 3 get assigned to protocols
    selected = working_ips[:3]
    while len(selected) < 3:
        selected.append(working_ips[0] if working_ips else '0.0.0.0')
    
    # All working IPs go into the pool
    all_scored = [(ip, 100 - i * 2) for i, ip in enumerate(working_ips[:20])]
    
    # Write individual protocol IPs
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", 
                   ('vless_ws_cdn_ip', selected[0]))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", 
                   ('vless_upgrade_cdn_ip', selected[1]))
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", 
                   ('trojan_ws_cdn_ip', selected[2]))
    
    # Write cdn_ips_list as JSON
    ips_json = json.dumps([{
        'ip': ip, 'score': score,
        'latency': 50,  # We don't know from server side
        'speed_mbps': 50,
        'cross_isp_score': 50
    } for ip, score in all_scored], ensure_ascii=False)
    
    cursor.execute("INSERT OR REPLACE INTO cdn_settings (key, value) VALUES (?, ?)", 
                   ('cdn_ips_list', ips_json))
    
    conn.commit()
    conn.close()
    
    print(f"\n[OK] DB seeded: {len(all_scored)} IPs in pool")
    print(f"  VLESS-WS: {selected[0]}")
    print(f"  VLESS-HTTPUpgrade: {selected[1]}")
    print(f"  Trojan-WS: {selected[2]}")

if __name__ == '__main__':
    seed_db(CDN_PREFERRED_IPS)
