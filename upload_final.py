#!/usr/bin/env python3
"""
Upload fixed files and test CDN IP assignment
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
        print(out.strip())
    if err.strip() and 'warning' not in err.lower():
        print(f"[ERR] {err.strip()[:200]}")
    return exit_code

print("=== Upload & Test CDN IP ===")

# 1. Upload cdn_monitor.py
print("\n[1] Upload cdn_monitor.py")
sftp = ssh.open_sftp()
sftp.put('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\cdn_monitor_final.py', '/root/singbox-eps-node/scripts/cdn_monitor.py')
sftp.close()
print("[OK] cdn_monitor.py uploaded")

# 2. Upload subscription_service.py
print("\n[2] Upload subscription_service.py")
sftp = ssh.open_sftp()
sftp.put('d:\\Documents\\Syncdisk\\工作用\\job\\S-ui\\singbox-eps-node\\scripts\\subscription_service.py', '/root/singbox-eps-node/scripts/subscription_service.py')
sftp.close()
print("[OK] subscription_service.py uploaded")

# 3. Run cdn_monitor once to assign IPs
print("\n[3] Run cdn_monitor once")
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
run("systemctl is-active singbox-cdn")
run("systemctl is-active singbox-sub")

# 6. Test subscription
print("\n[6] Test subscription (Base64)")
run("curl -sk https://127.0.0.1:6969/sub/JP | base64 -d")

# 7. Check if IPs are different
print("\n[7] Verify IPs are different")
run("curl -sk https://127.0.0.1:6969/sub/JP | base64 -d | grep -oP '@[^:]+:' | sort -u")

print("\n=== Done ===")
ssh.close()
