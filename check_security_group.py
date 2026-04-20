#!/usr/bin/env python3
"""
检查AWS安全组配置
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

print("=== 检查当前安全组规则 ===")
print("1. 检查实例元数据中的安全组信息")
exit_code, out, err = run_cmd(client, "curl -s http://169.254.169.254/latest/meta-data/security-groups")
print(f"安全组名称: {out}")

print("\n2. 检查当前开放的端口")
exit_code, out, err = run_cmd(client, "netstat -tlnp")
print("监听端口:")
for line in out.split('\n'):
    if 'LISTEN' in line:
        print(f"  {line}")

print("\n3. 检查外部网络连通性")
exit_code, out, err = run_cmd(client, "ping -c 3 8.8.8.8")
print(f"网络连通性: {out}")

print("\n4. 检查Cloudflare代理状态")
exit_code, out, err = run_cmd(client, "curl -s -I http://jp.290372913.xyz:6969/ 2>&1 | head -5")
print(f"Cloudflare访问测试: {out}")

print("\n=== 解决方案 ===")
print("1. 登录AWS控制台 → EC2 → 实例 → 安全组")
print("2. 添加入站规则: 类型=自定义TCP, 端口=6969, 来源=0.0.0.0/0")
print("3. 保存规则后，外部即可访问订阅服务")

client.close()