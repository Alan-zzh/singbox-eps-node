import sqlite3
db = sqlite3.connect('data/singbox.db')
c = db.cursor()

c.execute("SELECT value FROM cdn_settings WHERE key='cdn_ips_list'")
row = c.fetchone()
if row:
    ips = [ip.strip() for ip in row[0].split(',') if ip.strip()]
    print(f'CDN IP列表 ({len(ips)}个):')
    for ip in ips:
        print(f'  {ip}')
else:
    print('无CDN IP列表')

for key in ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']:
    c.execute(f"SELECT value FROM cdn_settings WHERE key='{key}'")
    row = c.fetchone()
    print(f'{key}: {row[0] if row else None}')

c.execute('SELECT ip, total_tests, success_count, fail_count, avg_latency, speed_mbps, source FROM ip_performance ORDER BY avg_latency ASC LIMIT 30')
rows = c.fetchall()
if rows:
    print(f'\nIP性能 (按延迟排序，前30):')
    for r in rows:
        spd = r[5] if r[5] else 0
        src = r[6] or ''
        print(f'  {r[0]:<20} t={r[1]:>3} ok={r[2]:>3} f={r[3]:>3} lat={r[4]:>7.1f}ms spd={spd:>7.1f}Mbps src={src}')
else:
    print('无IP性能数据')

c.execute('SELECT key, value FROM cdn_settings')
rows = c.fetchall()
if rows:
    print(f'\nCDN配置:')
    for r in rows:
        val = r[1][:100] if r[1] and len(r[1])>100 else r[1]
        print(f'  {r[0]}: {val}')

db.close()
