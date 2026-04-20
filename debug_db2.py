#!/usr/bin/env python3
"""
Debug BASE_DIR vs DATA_DIR
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=30):
    print(f">>> {cmd[:100]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip():
        print(out.strip())
    if err.strip() and 'warning' not in err.lower():
        print(f"[ERR] {err.strip()[:200]}")
    return exit_code

print("=== Debug BASE_DIR vs DATA_DIR ===")

# 1. Check BASE_DIR in config.py
print("\n[1] BASE_DIR in config.py")
run("grep -B2 -A2 'BASE_DIR' /root/singbox-eps-node/scripts/config.py | head -10")

# 2. Check what subscription_service actually uses
print("\n[2] subscription_service DATA_DIR")
run("grep -A1 'DATA_DIR' /root/singbox-eps-node/scripts/subscription_service.py | head -5")

# 3. Check cdn_monitor DATA_DIR
print("\n[3] cdn_monitor DATA_DIR")
run("grep 'DATA_DIR' /root/singbox-eps-node/scripts/cdn_monitor.py")

# 4. Direct test - what path does subscription_service use?
print("\n[4] Test subscription_service DB path")
run("cd /root/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from subscription_service import DB_PATH; print('DB_PATH:', DB_PATH)\"")

# 5. Direct test - what path does cdn_monitor use?
print("\n[5] Test cdn_monitor DB path")
run("cd /root/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from cdn_monitor import init_db; from config import DATA_DIR; print('DATA_DIR:', DATA_DIR); import os; print('DB would be:', os.path.join(DATA_DIR, 'singbox.db'))\"")

# 6. Check actual DB content with correct path
print("\n[6] Check DB with correct path")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); rows=c.fetchall(); print('Rows:', rows)\"")

print("\n=== Done ===")
ssh.close()
