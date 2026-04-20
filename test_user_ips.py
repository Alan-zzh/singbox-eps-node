#!/usr/bin/env python3
"""
Test user-provided CF IPs connectivity from server
"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=10):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    return exit_code, out

# User-provided IPs from screenshot
user_ips = [
    '162.159.20.39',
    '162.159.58.151',
    '162.159.39.78',
    '162.159.38.109',
    '108.162.198.165',
    '172.64.52.191',
    '162.159.45.45',
    '172.64.53.201',
    '162.159.14.161',
    '162.159.5.5',
]

print("=== Test User-Provided CF IPs ===")
print(f"\nServer IP: 54.250.149.157 (AWS Japan)")
print(f"\nTesting connectivity to {len(user_ips)} IPs on ports 8443, 2053, 2083:\n")

results = {}
for ip in user_ips:
    results[ip] = {}
    for port in [8443, 2053, 2083]:
        exit_code, out = run(f"timeout 2 bash -c 'echo > /dev/tcp/{ip}/{port}' 2>/dev/null && echo OK || echo FAIL")
        status = "OK" if "OK" in out else "FAIL"
        results[ip][port] = status
        print(f"  {ip}:{port} -> {status}")

print("\n=== Summary ===")
valid_ips = []
for ip in user_ips:
    ok_ports = [p for p, s in results[ip].items() if s == "OK"]
    if ok_ports:
        valid_ips.append(ip)
        print(f"  [OK] {ip} - ports: {ok_ports}")
    else:
        print(f"  [FAIL] {ip} - all ports failed")

print(f"\nValid IPs: {len(valid_ips)}/{len(user_ips)}")
print(f"Valid list: {valid_ips}")

ssh.close()
