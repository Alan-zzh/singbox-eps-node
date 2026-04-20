#!/usr/bin/env python3
"""
Upload fixed cdn_monitor.py and test
"""
import paramiko
import time

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
        print(out.strip()[-500:])
    if err.strip() and 'warning' not in err.lower():
        print(f"[ERR] {err.strip()[:200]}")
    return exit_code

print("=== Upload Fixed CDN Monitor ===")

# 1. Upload via SFTP
print("\n[1] Upload cdn_monitor.py")
sftp = ssh.open_sftp()
sftp.put('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\cdn_monitor_fixed.py', '/root/singbox-eps-node/scripts/cdn_monitor.py')
sftp.close()
print("[OK] Uploaded")

# 2. Verify
print("\n[2] Verify")
run("head -3 /root/singbox-eps-node/scripts/cdn_monitor.py")
run("grep 'fetch_cdn_ips' /root/singbox-eps-node/scripts/cdn_monitor.py")

# 3. Run once
print("\n[3] Run once to fetch IPs")
run("cd /root/singbox-eps-node && python3 scripts/cdn_monitor.py once")

# 4. Check DB
print("\n[4] Check DB")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); [print(r) for r in c.fetchall()]\"")

# 5. Restart services
print("\n[5] Restart services")
run("systemctl restart singbox-cdn")
time.sleep(2)
run("systemctl restart singbox-sub")
time.sleep(2)

# 6. Test subscription
print("\n[6] Test subscription")
run("curl -sk https://127.0.0.1:6969/sub/JP | base64 -d | grep -E 'WS|Trojan' | head -3")

print("\n=== Done ===")
ssh.close()
