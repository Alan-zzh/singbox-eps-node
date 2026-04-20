#!/bin/bash
# 测试脚本：验证 CDN 监控脚本在服务器上的运行状态

echo "=== 检查 CDN 监控服务状态 ==="
systemctl status singbox-cdn --no-pager

echo ""
echo "=== 检查数据库文件 ==="
ls -la /root/singbox-manager/data/

echo ""
echo "=== 检查数据库中的 CDN IP ==="
cd /root/singbox-manager
python3 -c "
import sqlite3
import os
db_path = os.path.join('data', 'singbox.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value}')
conn.close()
"

echo ""
echo "=== 手动运行一次 CDN 监控 ==="
cd /root/singbox-manager
python3 scripts/cdn_monitor.py

echo ""
echo "=== 检查更新后的数据库 ==="
python3 -c "
import sqlite3
import os
db_path = os.path.join('data', 'singbox.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for key, value in rows:
    print(f'{key}: {value}')
conn.close()
"
