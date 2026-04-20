#!/usr/bin/env python3
"""
Debug CDN IP issue
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

print("=== Debug CDN IP ===")

# 1. Check DB
print("\n[1] Check DB")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute('SELECT * FROM cdn_settings'); [print(r) for r in c.fetchall()]\"")

# 2. Check SERVER_IP
print("\n[2] Check SERVER_IP in config")
run("grep SERVER_IP /root/singbox-eps-node/scripts/config.py")

# 3. Test get_cdn_ip logic
print("\n[3] Test get_cdn_ip logic")
run("python3 -c \"import sqlite3; conn=sqlite3.connect('/root/singbox-eps-node/singbox.db'); c=conn.cursor(); c.execute(\\\"SELECT value FROM cdn_settings WHERE key='cdn_ip'\\\"); row=c.fetchone(); print('cdn_ip:', row[0] if row else 'NOT FOUND'); print('is not server:', row[0] != '54.250.149.157' if row else False)\"")

# 4. Check subscription_service get_ws_address
print("\n[4] Check get_ws_address in subscription_service")
run("grep -A8 'def get_ws_address' /root/singbox-eps-node/scripts/subscription_service.py")

# 5. Check CF_DOMAIN
print("\n[5] Check CF_DOMAIN")
run("grep CF_DOMAIN /root/singbox-eps-node/scripts/config.py")

# 6. Full test
print("\n[6] Full test of subscription_service logic")
run("cd /root/singbox-eps-node && python3 -c \"import sys; sys.path.insert(0,'scripts'); from subscription_service import get_cdn_ip, get_ws_address, SERVER_IP, CF_DOMAIN; print('SERVER_IP:', SERVER_IP); print('CF_DOMAIN:', CF_DOMAIN); print('cdn_ip:', get_cdn_ip()); print('ws_addr:', get_ws_address())\"")

print("\n=== Done ===")
ssh.close()
