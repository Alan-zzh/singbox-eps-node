#!/usr/bin/env python3
"""
配置防火墙并修复订阅服务
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

print("=== 1. 安装并配置 UFW 防火墙 ===")
# 安装ufw
exit_code, out, err = run_cmd(client, "apt-get update && apt-get install -y ufw")
print("UFW安装完成")

# 放行所有需要的端口
ports = [
    ("22", "SSH"),
    ("443/tcp", "VLESS-Reality/Hysteria2"),
    ("8443/tcp", "VLESS-WS-CDN"),
    ("2053/tcp", "VLESS-HTTPUpgrade-CDN"),
    ("2083/tcp", "Trojan-WS-CDN"),
    ("6969/tcp", "订阅服务"),
    ("36753/tcp", "SOCKS5"),
]

print("\n放行端口:")
for port, desc in ports:
    exit_code, out, err = run_cmd(client, f"ufw allow {port}")
    print(f"  ✅ {port} ({desc})")

# 放行Hysteria2端口跳跃范围
exit_code, out, err = run_cmd(client, "ufw allow 21000:21200/udp")
print(f"  ✅ 21000:21200/udp (Hysteria2端口跳跃)")

# 启用UFW
exit_code, out, err = run_cmd(client, "echo 'y' | ufw enable")
print(f"\nUFW启用状态: {out}")

# 检查UFW状态
exit_code, out, err = run_cmd(client, "ufw status verbose")
print(f"\n防火墙状态:\n{out}")

print("\n=== 2. 检查SSL证书状态 ===")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/certs/")
print(f"证书目录:\n{out}")

exit_code, out, err = run_cmd(client, "test -f /root/singbox-eps-node/certs/cert.pem && echo '存在' || echo '不存在'")
print(f"cert.pem: {out}")

exit_code, out, err = run_cmd(client, "test -f /root/singbox-eps-node/certs/key.pem && echo '存在' || echo '不存在'")
print(f"key.pem: {out}")

print("\n=== 3. 检查订阅服务配置 ===")
exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env | grep -E 'SUB_PORT|SUB_TOKEN|COUNTRY_CODE'")
print(f"环境变量:\n{out}")

print("\n=== 4. 重启订阅服务 ===")
exit_code, out, err = run_cmd(client, "systemctl restart singbox-sub")
print("订阅服务已重启")

exit_code, out, err = run_cmd(client, "systemctl status singbox-sub --no-pager")
print(f"服务状态:\n{out}")

print("\n=== 5. 测试本地访问 ===")
exit_code, out, err = run_cmd(client, "curl -s http://127.0.0.1:6969/sub | head -c 100")
print(f"HTTP访问: {out}")

exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub | head -c 100")
print(f"HTTPS访问: {out}")

print("\n=== 6. 检查端口监听 ===")
exit_code, out, err = run_cmd(client, "netstat -tlnp | grep -E '443|6969|8443|2053|2083|36753'")
print(f"监听端口:\n{out}")

client.close()
print("\n✅ 防火墙配置完成！")
