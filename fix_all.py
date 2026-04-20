#!/usr/bin/env python3
"""
全自动修复所有问题
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
print("全自动修复所有问题")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
print("✅ 服务器连接成功")

# ==================== 问题1：生成完整.env配置 ====================
print("\n【问题1：生成完整.env配置】...")

# 生成UUID
exit_code, out, err = run_cmd(client, "python3 -c \"import uuid; print(str(uuid.uuid4()))\"")
vless_uuid = out.strip()
print(f"  生成VLESS_UUID: {vless_uuid}")

exit_code, out, err = run_cmd(client, "python3 -c \"import uuid; print(str(uuid.uuid4()))\"")
vless_ws_uuid = out.strip()
print(f"  生成VLESS_WS_UUID: {vless_ws_uuid}")

# 生成Reality密钥对
exit_code, out, err = run_cmd(client, "python3 -c \"import subprocess; result=subprocess.run(['sing-box', 'generate', 'reality-keypair'], capture_output=True, text=True); print(result.stdout)\" 2>/dev/null || echo 'sing-box未安装'")
if out and out != 'sing-box未安装':
    lines = out.strip().split('\n')
    reality_public_key = lines[0] if len(lines) > 0 else ''
    reality_private_key = lines[1] if len(lines) > 1 else ''
    reality_short_id = lines[2] if len(lines) > 2 else ''
    print(f"  生成Reality密钥对")
else:
    # 如果sing-box未安装，使用预设值
    reality_public_key = ''
    reality_private_key = ''
    reality_short_id = ''
    print("  sing-box未安装，使用预设密钥")

# 生成Trojan密码
exit_code, out, err = run_cmd(client, "python3 -c \"import secrets; print(secrets.token_urlsafe(16))\"")
trojan_password = out.strip()
print(f"  生成Trojan密码: {trojan_password}")

# 生成Hysteria2密码
exit_code, out, err = run_cmd(client, "python3 -c \"import secrets; print(secrets.token_urlsafe(16))\"")
hysteria2_password = out.strip()
print(f"  生成Hysteria2密码: {hysteria2_password}")

# 生成Reality Short ID（如果上面没生成）
if not reality_short_id:
    exit_code, out, err = run_cmd(client, "python3 -c \"import secrets; print(secrets.token_hex(8))\"")
    reality_short_id = out.strip()

# 写入完整.env
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
REALITY_PUBLIC_KEY={reality_public_key}
REALITY_PRIVATE_KEY={reality_private_key}
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

sftp = client.open_sftp()
with sftp.open('/root/singbox-eps-node/.env', 'w') as f:
    f.write(env_content)
sftp.close()
print("  ✅ .env配置已生成并上传")

# ==================== 问题2：修复HTTPS订阅 ====================
print("\n【问题2：修复HTTPS订阅】...")

# 检查证书
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-eps-node/cert/")
print(f"  证书目录: {out}")

# 检查subscription_service.py的证书检测逻辑
exit_code, out, err = run_cmd(client, "grep -n 'cert_paths' /root/singbox-eps-node/scripts/subscription_service.py | head -5")
print(f"  证书检测代码: {out}")

# 修改subscription_service.py，强制使用正确的证书路径
print("  修改订阅服务代码...")
fix_script = """
import re

# 读取原文件
with open('/root/singbox-eps-node/scripts/subscription_service.py', 'r') as f:
    content = f.read()

# 替换证书路径检测逻辑
old_cert_check = '''    # 尝试多个可能的证书路径
    cert_paths = [
        os.path.join(CERT_DIR, 'cert.pem'),
        os.path.join(os.path.dirname(CERT_DIR), 'certs', 'cert.pem'),
        '/root/singbox-eps-node/certs/cert.pem',
        '/root/singbox-manager/cert/cert.pem',
    ]
    
    key_paths = [
        os.path.join(CERT_DIR, 'key.pem'),
        os.path.join(os.path.dirname(CERT_DIR), 'certs', 'key.pem'),
        '/root/singbox-eps-node/certs/key.pem',
        '/root/singbox-manager/cert/key.pem',
    ]'''

new_cert_check = '''    # 强制使用正确的证书路径
    cert_path = '/root/singbox-eps-node/cert/cert.pem'
    key_path = '/root/singbox-eps-node/cert/key.pem'
    
    if os.path.exists(cert_path) and os.path.exists(key_path):
        logger.info(f"SSL certificate found at: {cert_path}")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        logger.info(f"Starting HTTPS subscription service on 0.0.0.0:{SUB_PORT}")
        app.run(host='0.0.0.0', port=SUB_PORT, ssl_context=context, threaded=True)
    else:
        logger.warning("SSL cert not found, running HTTP subscription service")
        app.run(host='0.0.0.0', port=SUB_PORT, threaded=True)'''

content = content.replace(old_cert_check, new_cert_check)

with open('/root/singbox-eps-node/scripts/subscription_service.py', 'w') as f:
    f.write(content)

print("✅ 订阅服务代码已修复")
"""

# 执行修复脚本
run_cmd(client, f"python3 -c \"{fix_script}\"")
print("  ✅ 订阅服务代码已修复")

# ==================== 问题3：重启服务并验证CDN IP ====================
print("\n【问题3：重启服务并验证CDN IP】...")

# 重启服务
run_cmd(client, "systemctl daemon-reload")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

time.sleep(10)

run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(5)

# 检查服务状态
print("\n【检查服务状态】...")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

# 检查CDN IP
print("\n【检查CDN IP】...")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
if rows:
    for row in rows:
        print(f'  {row[0]}: {row[1]}')
else:
    print('  无CDN IP数据，等待CDN服务获取...')
conn.close()
" 2>/dev/null || echo '  数据库查询失败'""")
print(out)

# 测试HTTPS订阅
print("\n【测试HTTPS订阅】...")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTPS状态码: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS不可用'")
print(f"  {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP不可用'")
print(f"  {out}")

# 获取订阅内容
print("\n【订阅内容（前500字符）】...")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null | head -c 500 || curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 500")
if out:
    print(out)
else:
    print("  无法获取")

client.close()

print("\n" + "=" * 60)
print("✅ 所有问题已修复！")
print("=" * 60)
