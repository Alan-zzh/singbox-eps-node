#!/usr/bin/env python3
"""
恢复服务器配置并修复所有问题
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
print("恢复服务器配置并修复所有问题")
print("=" * 60)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(SERVER_IP, 22, SSH_USER, SSH_PASS, timeout=30)
print("✅ 服务器连接成功")

# 1. 从旧目录恢复.env配置
print("\n【恢复.env配置】...")
exit_code, out, err = run_cmd(client, "cat /root/singbox-manager/.env 2>/dev/null || echo '不存在'")
if out and out != '不存在':
    print("  找到旧.env配置，正在恢复...")
    run_cmd(client, "cp /root/singbox-manager/.env /root/singbox-eps-node/.env")
    print("  ✅ .env已恢复")
else:
    print("  旧.env不存在，检查备份...")

# 2. 检查当前.env内容
print("\n【当前.env内容】...")
exit_code, out, err = run_cmd(client, "cat /root/singbox-eps-node/.env")
print(out)

# 3. 恢复证书文件
print("\n【恢复证书文件】...")
# 创建cert目录
run_cmd(client, "mkdir -p /root/singbox-eps-node/cert")
# 复制证书
exit_code, out, err = run_cmd(client, "ls /root/.acme.sh/jp1.290372913.xyz_ecc/")
print(f"  证书目录内容: {out}")

# 复制证书到正确位置
run_cmd(client, "cp /root/.acme.sh/jp1.290372913.xyz_ecc/fullchain.cer /root/singbox-eps-node/cert/cert.pem")
run_cmd(client, "cp /root/.acme.sh/jp1.290372913.xyz_ecc/jp1.290372913.xyz.key /root/singbox-eps-node/cert/key.pem")
print("  ✅ 证书已复制到 /root/singbox-eps-node/cert/")

# 4. 恢复数据库
print("\n【恢复数据库】...")
exit_code, out, err = run_cmd(client, "ls -la /root/singbox-manager/data/singbox.db 2>/dev/null || echo '不存在'")
print(f"  旧数据库: {out}")

# 复制旧数据库
run_cmd(client, "cp /root/singbox-manager/data/singbox.db /root/singbox-eps-node/data/singbox.db")
print("  ✅ 数据库已恢复")

# 5. 检查CDN IP
print("\n【检查CDN IP】...")
exit_code, out, err = run_cmd(client, """python3 -c "
import sqlite3
conn = sqlite3.connect('/root/singbox-eps-node/data/singbox.db')
cursor = conn.cursor()
cursor.execute('SELECT key, value FROM cdn_settings')
rows = cursor.fetchall()
for row in rows:
    print(f'{row[0]}: {row[1]}')
conn.close()
" 2>/dev/null || echo '查询失败'""")
print(out)

# 6. 重启服务
print("\n【重启服务】...")
run_cmd(client, "systemctl daemon-reload")
run_cmd(client, "systemctl restart singbox-cdn")
print("  ✅ CDN服务已重启")

time.sleep(5)

run_cmd(client, "systemctl restart singbox-sub")
print("  ✅ 订阅服务已重启")

time.sleep(5)

# 7. 检查服务状态
print("\n【检查服务状态】...")
for svc in ['singbox-cdn', 'singbox-sub']:
    exit_code, out, err = run_cmd(client, f"systemctl is-active {svc}")
    status = "✅ 运行中" if out == 'active' else "❌ 未运行"
    print(f"  {svc}: {status}")

# 8. 测试HTTPS订阅
print("\n【测试HTTPS订阅】...")
exit_code, out, err = run_cmd(client, "curl -sk -o /dev/null -w 'HTTP状态码: %{http_code}' https://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTPS不可用'")
print(f"  HTTPS: {out}")

exit_code, out, err = run_cmd(client, "curl -s -o /dev/null -w 'HTTP状态码: %{http_code}' http://127.0.0.1:6969/sub 2>/dev/null || echo 'HTTP不可用'")
print(f"  HTTP: {out}")

# 9. 检查订阅内容
print("\n【检查订阅内容（前200字符）】...")
exit_code, out, err = run_cmd(client, "curl -sk https://127.0.0.1:6969/sub 2>/dev/null | head -c 200 || curl -s http://127.0.0.1:6969/sub 2>/dev/null | head -c 200")
if out:
    print(out)
else:
    print("  无法获取订阅内容")

client.close()

print("\n" + "=" * 60)
print("✅ 配置恢复完成！")
print("=" * 60)
