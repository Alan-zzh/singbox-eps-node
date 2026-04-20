#!/usr/bin/env python3
"""
Upload cdn_monitor_correct.py to server and test
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

sftp = ssh.open_sftp()

# Upload the correct cdn monitor
local_file = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\cdn_monitor_correct.py'
remote_file = '/root/singbox-eps-node/scripts/cdn_monitor_correct.py'
sftp.put(local_file, remote_file)
print(f"[OK] Uploaded cdn_monitor_correct.py")

# Backup old one
ssh.exec_command('cp /root/singbox-eps-node/scripts/cdn_monitor_final.py /root/singbox-eps-node/scripts/cdn_monitor_final.py.bak')
print("[OK] Backed up old cdn_monitor_final.py")

# Replace old with new
ssh.exec_command('cp /root/singbox-eps-node/scripts/cdn_monitor_correct.py /root/singbox-eps-node/scripts/cdn_monitor_final.py')
print("[OK] Replaced cdn_monitor_final.py with correct version")

sftp.close()

# Test it
print("\n=== Test cdn_monitor_final.py ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/singbox-eps-node && python3 scripts/cdn_monitor_final.py once', timeout=60)
exit_code = stdout.channel.recv_exit_status()
out = stdout.read().decode()
err = stderr.read().decode()
print(out)
if err:
    print("STDERR:", err)

# Check DB
print("\n=== Check DB ===")
stdin, stdout, stderr = ssh.exec_command('cd /root/singbox-eps-node && python3 -c "import sqlite3; conn=sqlite3.connect(\'data/singbox.db\'); c=conn.cursor(); c.execute(\'SELECT * FROM cdn_settings\'); [print(r) for r in c.fetchall()]; conn.close()"', timeout=10)
out = stdout.read().decode()
print(out)

ssh.close()
