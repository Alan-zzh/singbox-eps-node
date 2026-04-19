#!/usr/bin/env python3
"""
VPS 深度修复脚本 - 解决所有遗留问题
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
        print(f"    {out.strip()[:400]}")
    if err.strip() and 'warning' not in err.lower() and 'deprecated' not in err.lower():
        print(f"    [ERR] {err.strip()[:300]}")
    return exit_code, out, err

def main():
    print("=" * 60)
    print("开始深度修复 VPS 部署")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        print("✅ SSH 连接成功\n")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return

    # 1. 安装 sing-box 内核
    print("[1] 安装 sing-box 内核...")
    run(ssh, """
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then ARCH_LABEL="linux-amd64"; elif [ "$ARCH" = "aarch64" ]; then ARCH_LABEL="linux-arm64"; fi
cd /tmp
wget -q "https://github.com/SagerNet/sing-box/releases/download/v1.10.0/sing-box-1.10.0-$ARCH_LABEL.tar.gz"
tar -xzf "sing-box-1.10.0-$ARCH_LABEL.tar.gz"
cp "sing-box-1.10.0-$ARCH_LABEL/sing-box" /usr/local/bin/sing-box
chmod +x /usr/local/bin/sing-box
rm -rf "sing-box-1.10.0-$ARCH_LABEL" "sing-box-1.10.0-$ARCH_LABEL.tar.gz"
/usr/local/bin/sing-box version
""", timeout=120)
    print()

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
    print(f"  Public: {public_key[:20]}...\n")

    # 3. 修复 Flask 安装
    print("[3] 修复 Flask 安装...")
    run(ssh, 'apt-get install -y python3-flask python3-requests python3-yaml python3-dotenv 2>/dev/null', timeout=120)
    # 如果 apt 失败，尝试 pip
    run(ssh, 'pip3 install flask python-dotenv requests pyyaml --break-system-packages 2>/dev/null || pip3 install flask python-dotenv requests pyyaml --user 2>/dev/null || true', timeout=120)
    # 验证 Flask 是否可用
    run(ssh, 'python3 -c "import flask; print(f\"Flask {flask.__version__} OK\")"')
    print()

    # 4. 修复 config_generator.py 路径
    print("[4] 修复 config_generator.py 路径...")
    run(ssh, 'sed -i "s|/root/singbox-manager/.env|/root/singbox-eps-node/.env|g" /root/singbox-eps-node/scripts/config_generator.py')
    run(ssh, 'grep ".env" /root/singbox-eps-node/scripts/config_generator.py | head -3')
    print()

    # 5. 创建证书目录并生成自签证书
    print("[5] 生成自签 SSL 证书...")
    run(ssh, 'mkdir -p /root/singbox-eps-node/cert')
    run(ssh, """
openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 \
  -keyout /root/singbox-eps-node/cert/cert.key \
  -out /root/singbox-eps-node/cert/cert.crt \
  -days 3650 \
  -subj "/CN=jp.290372913.xyz" \
  -addext "subjectAltName=DNS:jp.290372913.xyz,DNS:*.jp.290372913.xyz,IP:54.250.149.157"
ls -la /root/singbox-eps-node/cert/
""", timeout=30)
    print()

    # 6. 写入 Reality 密钥到 .env
    print("[6] 写入 Reality 密钥到 .env...")
    if private_key and public_key:
        python_script = f"""
import re
with open('/root/singbox-eps-node/.env', 'r') as f:
    content = f.read()
content = re.sub(r'REALITY_PRIVATE_KEY=.*', 'REALITY_PRIVATE_KEY={private_key}', content)
content = re.sub(r'REALITY_PUBLIC_KEY=.*', 'REALITY_PUBLIC_KEY={public_key}', content)
with open('/root/singbox-eps-node/.env', 'w') as f:
    f.write(content)
print('Reality keys written to .env')
"""
        run(ssh, f'python3 -c "{python_script}"')
    print()

    # 7. 生成 Singbox 配置
    print("[7] 生成 Singbox 配置...")
    run(ssh, 'cd /root/singbox-eps-node && python3 scripts/config_generator.py', timeout=60)
    run(ssh, 'ls -la /root/singbox-eps-node/config.json')
    run(ssh, 'head -30 /root/singbox-eps-node/config.json')
    print()

    # 8. 重启所有服务
    print("[8] 重启所有服务...")
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

    # 9. 验证
    print("[9] 验证服务状态...")
    run(ssh, 'systemctl is-active singbox singbox-sub singbox-cdn singbox-tgbot')
    print()
    
    run(ssh, 'ss -tlnp | grep -E "443|6969|2053|2083"')
    print()

    # 10. 检查日志
    print("[10] 检查服务日志...")
    run(ssh, 'journalctl -u singbox --no-pager -n 10')
    print()
    run(ssh, 'journalctl -u singbox-sub --no-pager -n 10')
    print()

    print("=" * 60)
    print("✅ 深度修复完成！")
    print("=" * 60)
    print("\n📡 订阅链接:")
    print("   https://jp.290372913.xyz:6969/sub/JP")
    print("   https://54.250.149.157:6969/sub/JP")
    
    ssh.close()

if __name__ == '__main__':
    main()
