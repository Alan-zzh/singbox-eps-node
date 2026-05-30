#!/usr/bin/env python3
import sqlite3, json, sys, traceback

try:
    db = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')

    # Check all keys
    rows = db.execute('SELECT key, length(value) FROM cdn_settings').fetchall()
    with open('/tmp/ip_result.txt', 'w') as f:
        for k, v in rows:
            f.write(f'KEY:{k} LEN:{v}\n')

        # Try to parse cdn_ips_list
        r = db.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'").fetchone()
        if r and r[0]:
            f.write(f'\ncdn_ips_list first 500 chars:\n{r[0][:500]}\n')
            try:
                ips = json.loads(r[0])
                f.write(f'\nParsed OK, count={len(ips)}\n')
                for i, info in enumerate(ips):
                    ip = info.get('ip', '?')
                    score = info.get('score', 0)
                    lat = info.get('latency', 0)
                    speed = info.get('speed_mbps', 0)
                    f.write(f'{i+1}|{ip}|{score}|{lat}|{speed}\n')
            except Exception as e:
                f.write(f'\nJSON parse error: {e}\n')
                f.write(f'Raw first 200: {r[0][:200]}\n')
        else:
            f.write('\ncdn_ips_list is empty or missing\n')

        # Protocol assignments
        f.write('\n--- Protocol Assignments ---\n')
        for key in ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']:
            row = db.execute(f"SELECT value FROM cdn_settings WHERE key='{key}'").fetchone()
            f.write(f'{key}={row[0] if row else "NONE"}\n')

    db.close()
    print('OK')
except Exception as e:
    with open('/tmp/ip_result.txt', 'w') as f:
        f.write(f'ERROR: {e}\n')
        traceback.print_exc(file=f)
    print(f'ERROR: {e}')
