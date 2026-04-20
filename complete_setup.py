#!/usr/bin/env python3
"""
创建.env文件并完成安装
"""
import paramiko
import time

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
print("创建.env文件并完成安装")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
print("✅ 服务器连接成功")

# 1. 创建.env文件
print("\n【创建.env文件】...")
env_content = """# 服务器配置
SERVER_IP=54.250.149.157
CF_DOMAIN=jp.290372913.xyz
COUNTRY_CODE=JP

# 订阅配置
SUB_PORT=6969
SUB_TOKEN=iKzF2SK3yhX3UfLw

# VLESS配置
VLESS_UUID=
VLESS_WS_UUID=
VLESS_WS_PORT=8443
VLESS_UPGRADE_PORT=2053

# Reality配置
REALITY_SNI=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_PUBLIC_KEY=
REALITY_SHORT_ID=

# Trojan配置
TROJAN_PASSWORD=
TROJAN_WS_PORT=2083

# Hysteria2配置
HYSTERIA2_PASSWORD=

# SOCKS5配置
AI_SOCKS5_SERVER=206.163.4.241
AI_SOCKS5_PORT=36753
AI_SOCKS5_USER=4KKsLB7F
AI_SOCKS5_PASS=KgEKVmVgxJ

# 外部订阅（可选）
EXTERNAL_SUBS=
"""

sftp = client.open_sftp()
with sftp.open('/root/singbox-eps-node/.env', 'w') as f:
    f.write(env_content)
sftp.close()
print("  ✅ .env文件已创建")

# 2. 重启服务
print("\n【重启服务】...")
run_cmd(client, "systemctl daemon-reload")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

time.sleep(5)

run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(5)

# 3. 检查服务状态
print("\n【检查服务状态】...")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

# 4. 测试订阅
print("\n【测试订阅】...")
exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo '无法访问'")
print(f"  订阅访问: {out}")

# 5. 检查日志
print("\n【订阅服务日志】...")
exit_code, out, err = run_cmd(client, "journalctl -u singbox-sub --no-pager -n 10 2>&1 | tail -10")
print(f"  {out}")

client.close()

print("\n" + "=" * 60)
print("✅ 安装完成！")
print("=" * 60)
print("\n注意：.env文件中的UUID、密钥等配置项需要填入你的实际值")
print("编辑命令: nano /root/singbox-eps-node/.env")
print("\n测试订阅链接:")
print("  http://jp.290372913.xyz:6969/sub")
print("  http://jp.290372913.xyz:6969/sub/JP")
print("  http://jp.290372913.xyz:6969/iKzF2SK3yhX3UfLw")
