#!/usr/bin/env python3
"""
检查网络连接和防火墙状态
"""
import paramiko

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

print("=== 1. 检查防火墙状态 ===")
exit_code, out, err = run_cmd(client, "ufw status 2>/dev/null || echo 'ufw未安装'")
print(out)

print("\n=== 2. 检查iptables规则 ===")
exit_code, out, err = run_cmd(client, "iptables -L -n 2>/dev/null | head -20 || echo 'iptables未安装或未配置'")
print(out)

print("\n=== 3. 检查端口监听状态 ===")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep 6969 || ss -tlnp | grep 6969")
print(out)

print("\n=== 4. 检查外部域名解析 ===")
exit_code, out, err = run_cmd(client, "nslookup jp.290372913.xyz")
print(out)

print("\n=== 5. 测试外部访问（服务器内部）===")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w '%{http_code}' http://jp.290372913.xyz:6969/sub || echo '访问失败'")
print(f"HTTP状态码: {out}")

print("\n=== 6. 检查服务器公网IP ===")
exit_code, out, err = run_cmd(client, "curl -s ifconfig.me")
print(f"服务器公网IP: {out}")

print("\n=== 7. 检查Cloudflare DNS记录 ===")
exit_code, out, err = run_cmd(client, "dig jp.290372913.xyz +short")
print(f"DNS解析结果: {out}")

client.close()