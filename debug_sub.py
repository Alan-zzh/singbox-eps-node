#!/usr/bin/env python3
"""
Debug subscription service
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

print("=== Debug Subscription Service ===")

# 1. Check service status
print("\n[1] Service status")
run("systemctl status singbox-sub --no-pager -n 5")

# 2. Check service logs
print("\n[2] Service logs")
run("journalctl -u singbox-sub --no-pager -n 20 | tail -15")

# 3. Test direct curl
print("\n[3] Direct curl test")
run("curl -vsk https://127.0.0.1:6969/sub/JP 2>&1 | head -30")

# 4. Check if port is listening
print("\n[4] Port check")
run("ss -tlnp | grep 6969")

# 5. Test subscription_service directly
print("\n[5] Test subscription_service.py directly")
run("cd /root/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from subscription_service import generate_all_links; links=generate_all_links(); [print(l) for l in links]\"")

# 6. Check DB
print("\n[6] Check DB")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); rows=c.fetchall(); print('Total rows:', len(rows)); [print(r) for r in rows]\"")

print("\n=== Done ===")
ssh.close()
