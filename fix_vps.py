#!/usr/bin/env python3
"""
VPS 修复脚本 - 修复部署中的问题
"""
import paramiko
import time

HOST = '54.250.149.157'
PORT = 22
USER = 'root'
PASSWORD = 'oroVIG38@jh.dxclouds.com'

def run(ssh, cmd, timeout=60):
    print(f"  >>> {cmd[:100]}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    if out.strip():
        print(f"    {out.strip()[:300]}")
    if err.strip() and 'warning' not in err.lower():
        print(f"    [ERR] {err.strip()[:200]}")
    return exit_code, out, err

def main():
    print("=" * 60)
    print("开始修复 VPS 部署问题")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        print("✅ SSH 连接成功\n")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return

    # 1. 修复 IP 地址
    print("[1] 修复 IPv4 地址...")
    run(ssh, 'sed -i "s/SERVER_IP=2406:da14:1ba5:f500:9320:7c03:2db0:1d84/SERVER_IP=54.250.149.157/" /root/singbox-eps-node/.env')
    print("  ✅ IP 已修复为 54.250.149.157\n")

    # 2. 生成 Reality 密钥
    print("[2] 生成 Reality 密钥...")
    _, key_out, _ = run(ssh, '/usr/local/bin/sing-box generate reality-keypair')
    
    private_key = ''
    public_key = ''
    for line in key_out.strip().split('\n'):
        if 'PrivateKey' in line:
            private_key = line.split(':', 1)[1].strip()
        elif 'PublicKey' in line:
            public_key = line.split(':', 1)[1].strip()
    
    print(f"  Private: {private_key[:20]}...")
    print(f"  Public: {public_key[:20]}...")
    
    if private_key and public_key:
        # 使用 Python 来安全地写入 .env
        python_script = f"""
import re
with open('/root/singbox-eps-node/.env', 'r') as f:
    content = f.read()
content = re.sub(r'REALITY_PRIVATE_KEY=.*', 'REALITY_PRIVATE_KEY={private_key}', content)
content = re.sub(r'REALITY_PUBLIC_KEY=.*', 'REALITY_PUBLIC_KEY={public_key}', content)
with open('/root/singbox-eps-node/.env', 'w') as f:
    f.write(content)
print('Done')
"""
        run(ssh, f'python3 -c "{python_script}"')
        print("  ✅ Reality 密钥已写入 .env\n")

    # 3. 安装 Flask 等依赖
    print("[3] 安装 Python 依赖...")
    run(ssh, 'pip3 install flask python-dotenv requests pyyaml --break-system-packages 2>&1 || pip3 install flask python-dotenv requests pyyaml', timeout=120)
    print("  ✅ 依赖安装完成\n")

    # 4. 检查 sing-box
    print("[4] 检查 sing-box...")
    run(ssh, 'which sing-box && sing-box version')
    
    # 检查 systemd 服务文件中的路径
    run(ssh, 'cat /etc/systemd/system/singbox.service | grep ExecStart')
    print()

    # 5. 生成证书
    print("[5] 生成 SSL 证书...")
    run(ssh, 'cd /root/singbox-eps-node && python3 scripts/cert_manager.py', timeout=120)
    run(ssh, 'ls -la /root/singbox-eps-node/cert/')
    print()

    # 6. 生成 Singbox 配置
    print("[6] 生成 Singbox 配置...")
    run(ssh, 'cd /root/singbox-eps-node && python3 scripts/config_generator.py', timeout=60)
    run(ssh, 'ls -la /root/singbox-eps-node/config.json')
    print()

    # 7. 重启所有服务
    print("[7] 重启所有服务...")
    run(ssh, 'systemctl daemon-reload')
    run(ssh, 'systemctl stop singbox singbox-sub singbox-cdn singbox-tgbot')
    time.sleep(2)
    run(ssh, 'systemctl start singbox')
    time.sleep(3)
    run(ssh, 'systemctl start singbox-sub')
    time.sleep(2)
    run(ssh, 'systemctl start singbox-cdn')
    time.sleep(2)
    run(ssh, 'systemctl start singbox-tgbot')
    print()

    # 8. 验证
    print("[8] 验证服务状态...")
    run(ssh, 'systemctl is-active singbox singbox-sub singbox-cdn singbox-tgbot')
    print()
    
    run(ssh, 'ss -tlnp | grep -E "443|6969|2053|2083"')
    print()

    # 9. 检查 .env 最终内容
    print("[9] 最终 .env 内容...")
    run(ssh, 'grep -E "SERVER_IP|CF_DOMAIN|SUB_TOKEN|COUNTRY_CODE|REALITY_PRIVATE_KEY" /root/singbox-eps-node/.env')
    print()

    print("=" * 60)
    print("✅ 修复完成！")
    print("=" * 60)
    print("\n📡 订阅链接:")
    print("   https://jp.290372913.xyz:6969/sub/JP")
    print("   https://54.250.149.157:6969/sub/JP")
    
    ssh.close()

if __name__ == '__main__':
    main()
