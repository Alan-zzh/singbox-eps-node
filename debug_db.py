#!/usr/bin/env python3
"""
Debug DB path issue
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

print("=== Debug DB Path ===")

# 1. Check DB_PATH in subscription_service
print("\n[1] DB_PATH in subscription_service")
run("grep 'DB_PATH\\|DB_FILE\\|DATA_DIR' /root/singbox-eps-node/scripts/subscription_service.py | head -10")

# 2. Check DATA_DIR in config
print("\n[2] DATA_DIR in config")
run("grep DATA_DIR /root/singbox-eps-node/scripts/config.py")

# 3. Check .env DATA_DIR
print("\n[3] .env DATA_DIR")
run("grep DATA_DIR /root/singbox-eps-node/.env")

# 4. Find all singbox.db files
print("\n[4] Find all singbox.db")
run("find /root/singbox-eps-node -name 'singbox.db' -exec ls -la {} \\;")

# 5. Check content of each DB
print("\n[5] Check each DB content")
run("for db in $(find /root/singbox-eps-node -name 'singbox.db'); do echo \"=== $db ===\"; python3 -c \"import sqlite3; conn=sqlite3.connect('$db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); [print(r) for r in c.fetchall()]\"; done")

# 6. Check config.py DATA_DIR value
print("\n[6] config.py DATA_DIR")
run("grep -A2 'DATA_DIR' /root/singbox-eps-node/scripts/config.py")

print("\n=== Done ===")
ssh.close()
