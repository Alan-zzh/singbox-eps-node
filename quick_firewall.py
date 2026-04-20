#!/usr/bin/env python3
"""
快速配置防火墙
"""
import paramiko

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

print("=== 配置防火墙 ===")

# 1. 检查iptables状态
stdin, stdout, stderr = client.exec_command("iptables -L INPUT -n --line-numbers 2>/dev/null | head -30")
print("当前iptables规则:")
print(stdout.read().decode())

# 2. 直接放行所有需要的端口（使用iptables）
ports = ["22", "443", "8443", "2053", "2083", "6969", "36753"]
for port in ports:
    cmd = f"iptables -C INPUT -p tcp --dport {port} -j ACCEPT 2>/dev/null || iptables -A INPUT -p tcp --dport {port} -j ACCEPT"
    stdin, stdout, stderr = client.exec_command(cmd)
    stdout.channel.recv_exit_status()
    print(f"✅ 放行TCP端口 {port}")

# Hysteria2 UDP端口
cmd = "iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 443 -j ACCEPT"
stdin, stdout, stderr = client.exec_command(cmd)
stdout.channel.recv_exit_status()
print("✅ 放行UDP端口 443 (Hysteria2)")

cmd = "iptables -C INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT"
stdin, stdout, stderr = client.exec_command(cmd)
stdout.channel.recv_exit_status()
print("✅ 放行UDP端口 21000:21200 (Hysteria2端口跳跃)")

# 保存iptables规则
stdin, stdout, stderr = client.exec_command("iptables-save > /etc/iptables.rules 2>/dev/null || true")
stdout.channel.recv_exit_status()
print("\n✅ iptables规则已保存")

# 3. 检查订阅服务
stdin, stdout, stderr = client.exec_command("systemctl status singbox-sub --no-pager 2>&1 | head -20")
print("\n订阅服务状态:")
print(stdout.read().decode())

# 4. 检查SSL证书
stdin, stdout, stderr = client.exec_command("ls -la /root/singbox-eps-node/certs/ 2>/dev/null || echo '证书目录不存在'")
print("证书目录:")
print(stdout.read().decode())

# 5. 检查订阅服务日志
stdin, stdout, stderr = client.exec_command("journalctl -u singbox-sub --no-pager -n 10 2>&1 | tail -10")
print("订阅服务日志:")
print(stdout.read().decode())

client.close()
print("\n✅ 防火墙配置完成！")
