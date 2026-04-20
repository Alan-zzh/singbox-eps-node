#!/usr/bin/env python3
"""
生成完整.env配置并上传到服务器
"""
import paramiko
import uuid
import secrets

SERVER_IP = '54.250.149.157'
SSH_USER = 'root'
SSH_PASS = 'oroVIG38@jh.dxclouds.com'

print("=" * 60)
print("生成完整.env配置")
print("=" * 60)

# 生成所有密钥
vless_uuid = str(uuid.uuid4())
vless_ws_uuid = str(uuid.uuid4())
trojan_password = secrets.token_urlsafe(16)
hysteria2_password = secrets.token_urlsafe(16)
reality_short_id = secrets.token_hex(8)

print(f"VLESS_UUID: {vless_uuid}")
print(f"VLESS_WS_UUID: {vless_ws_uuid}")
print(f"TROJAN_PASSWORD: {trojan_password}")
print(f"HYSTERIA2_PASSWORD: {hysteria2_password}")
print(f"REALITY_SHORT_ID: {reality_short_id}")

# 生成.env内容
env_content = f"""# 服务器配置
SERVER_IP=54.250.149.157
CF_DOMAIN=jp.290372913.xyz
COUNTRY_CODE=JP

# 订阅配置
SUB_PORT=6969
SUB_TOKEN=iKzF2SK3yhX3UfLw

# VLESS配置
VLESS_UUID={vless_uuid}
VLESS_WS_UUID={vless_ws_uuid}
VLESS_WS_PORT=8443
VLESS_UPGRADE_PORT=2053

# Reality配置
REALITY_SNI=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_PUBLIC_KEY=
REALITY_PRIVATE_KEY=
REALITY_SHORT_ID={reality_short_id}

# Trojan配置
TROJAN_PASSWORD={trojan_password}
TROJAN_WS_PORT=2083

# Hysteria2配置
HYSTERIA2_PASSWORD={hysteria2_password}

# SOCKS5配置
AI_SOCKS5_SERVER=206.163.4.241
AI_SOCKS5_PORT=36753
AI_SOCKS5_USER=4KKsLB7F
AI_SOCKS5_PASS=KgEKVmVgxJ

# 外部订阅（可选）
EXTERNAL_SUBS=
"""

# 上传到服务器
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)

sftp = client.open_sftp()
with sftp.open('/root/singbox-eps-node/.env', 'w') as f:
    f.write(env_content)
sftp.close()

client.close()

print("\n✅ .env配置已生成并上传到服务器！")
print("\n请将以下信息保存到安全位置：")
print(f"VLESS_UUID: {vless_uuid}")
print(f"VLESS_WS_UUID: {vless_ws_uuid}")
print(f"TROJAN_PASSWORD: {trojan_password}")
print(f"HYSTERIA2_PASSWORD: {hysteria2_password}")
print(f"REALITY_SHORT_ID: {reality_short_id}")
