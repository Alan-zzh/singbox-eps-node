import sqlite3
db = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
keys = ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip', 'cdn_updated_at']
for k in keys:
    row = db.execute('SELECT value FROM cdn_settings WHERE key=?', (k,)).fetchone()
    print(f'{k} = {row[0] if row else "NOT FOUND"}')
