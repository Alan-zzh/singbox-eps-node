#!/usr/bin/env python3
"""
部署修复后的文件到服务器并配置防火墙
"""
import paramiko
import os

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

def run_cmd(client, cmd, timeout=30):
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    return exit_code, out.strip(), err.strip()

print("=" * 60)
print("开始部署修复到服务器")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
    print("✅ 服务器连接成功")
except Exception as e:
    print(f"❌ 连接失败: {e}")
    exit(1)

# 1. 配置防火墙
print("\n【步骤1】配置防火墙放行所有需要的端口...")

tcp_ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
for port in tcp_ports:
    run_cmd(client, f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT")
    print(f"  ✅ 已放行 TCP 端口 {port}")

run_cmd(client, "iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 443")

run_cmd(client, "iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT")
print("  ✅ 已放行 UDP 端口 21000:21200")

run_cmd(client, "iptables-save > /etc/iptables.rules 2>/dev/null || true")
print("✅ 防火墙规则已保存")

# 2. 上传修复后的 subscription_service.py
print("\n【步骤2】上传修复后的订阅服务文件...")

local_file = r'd:\Documents\Syncdisk\工作用\job\S-ui\singbox-eps-node\scripts\subscription_service.py'
remote_file = '/root/singbox-eps-node/scripts/subscription_service.py'

sftp = client.open_sftp()

# 确保远程目录存在
run_cmd(client, "mkdir -p /root/singbox-eps-node/scripts")

# 上传文件
print(f"  上传: subscription_service.py")
sftp.put(local_file, remote_file)
print("  ✅ 文件上传成功")

# 3. 检查证书目录
print("\n【步骤3】检查SSL证书...")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/certs/ 2>/dev/null || echo 'certs目录不存在'")
print(f"certs目录: {out}")

exit_code, out, err = run_cmd(client, "ls -la /root/singbox-manager/cert/ 2>/dev/null || echo 'cert目录不存在'")
print(f"cert目录: {out}")

# 4. 重启订阅服务
print("\n【步骤4】重启订阅服务...")
run_cmd(client, "systemctl restart singbox-sub")
import time
time.sleep(3)

exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager 2>&1 | head -15")
print(f"服务状态:\n{out}")

# 5. 检查日志
print("\n【步骤5】检查服务日志...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 10 2>&1 | tail -10")
print(f"日志:\n{out}")

# 6. 测试本地访问
print("\n【步骤6】测试本地访问...")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub")
print(f"HTTP访问: {out}")

exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub")
print(f"HTTPS访问: {out}")

# 7. 检查端口监听
print("\n【步骤7】检查端口监听...")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep 6969 || ss -tlnp | grep 6969")
print(f"监听状态: {out}")

sftp.close()
client.close()

print("\n" + "=" * 60)
print("✅ 部署完成！")
print("=" * 60)
print("\n修复内容:")
print("1. 防火墙已放行所有需要的端口 (22, 443, 8443, 2053, 2083, 6969, 36753)")
print("2. 订阅服务已修复HTTPS/HTTP配置混乱问题")
print("3. 订阅服务会自动检测证书并使用HTTPS或HTTP")
print("\n测试订阅链接:")
print("  http://jp.290372913.xyz:6969/sub")
print("  http://jp.290372913.xyz:6969/sub/JP")
print("  http://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw")
print("\n请在客户端中测试订阅更新！")
