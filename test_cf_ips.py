#!/usr/bin/env python3
"""
Test connectivity of top 10 Cloudflare IPs from server
"""
import paramiko
import time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('54.250.149.157', port=22, username='root', password='oroVIG38@jh.dxclouds.com', timeout=10)

def run(cmd, timeout=30):
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=== Test Cloudflare IP Connectivity from Server ===")

# Fetch IPs from uouin.com
code, out, err = run("python3 -c \"import requests,re; r=requests.get('https://api.uouin.com/cloudflare.html',timeout=10); ips=re.findall(r'\\b(?:\\d{1,3}\\.){3}\\d{1,3}\\b',r.text); ips=[ip for ip in ips if all(0<=int(x)<=255 for x in ip.split('.'))]; print('\\n'.join(list(dict.fromkeys(ips))[:10]))\"")
top_10_ips = [ip for ip in out.split('\n') if ip.strip()]

print(f"\nTop 10 IPs from uouin.com:")
for i, ip in enumerate(top_10_ips, 1):
    print(f"  {i}. {ip}")

# Test connectivity to each IP on common CF ports
print("\n\nTesting connectivity (ports 8443, 2053, 2083):")
results = []
for ip in top_10_ips:
    for port in [8443, 2053, 2083]:
        exit_code, out, err = run(f"timeout 3 bash -c 'echo > /dev/tcp/{ip}/{port}' 2>/dev/null && echo OK || echo FAIL")
        status = "OK" if "OK" in out else "FAIL"
        results.append((ip, port, status))
        print(f"  {ip}:{port} -> {status}")

# Summary
print("\n\n=== Summary ===")
for ip in top_10_ips:
    ports_ok = [str(p) for _, p, s in results if _ == ip and s == "OK"]
    ports_fail = [str(p) for _, p, s in results if _ == ip and s == "FAIL"]
    if ports_ok:
        print(f"  {ip}: OK on ports {','.join(ports_ok)}")
    else:
        print(f"  {ip}: ALL FAILED")

ssh.close()
