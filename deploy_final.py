#!/usr/bin/env python3
"""
VPS 全自动部署脚本 - 最终版
"""
import paramiko
import time
import uuid
import random
import string

HOST = '54.250.149.157'
PORT = 22
USER = 'root'
PASSWORD = 'oroVIG38@jh.dxclouds.com'

CF_API_TOKEN = '73a1fd81dd0f5087d45572135d5bf783ab26a'
CF_EMAIL = 'puzangroup@gmail.com'
CF_DOMAIN = 'jp.290372913.xyz'
TG_BOT_TOKEN = '8750158505:AAE8zlEq_b2s3dk5gOz76oRaLLoNeV-6mcw'

def gen_uuid():
    return str(uuid.uuid4())

def gen_pass(length=16):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def run(ssh, cmd, timeout=60):
    print(f"  >>> {cmd[:80]}...")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode('utf-8', errors='ignore')
    err = stderr.read().decode('utf-8', errors='ignore')
    if out.strip():
        lines = out.strip().split('\n')
        for line in lines[-5:]:
            print(f"    {line[:120]}")
    if err.strip() and 'warning' not in err.lower() and 'deprecated' not in err.lower():
        print(f"    [ERR] {err.strip()[:200]}")
    return exit_code, out, err

def main():
    print("=" * 60)
    print("开始全自动部署 Singbox v1.0.18")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        print("✅ SSH 连接成功\n")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return

    # 生成配置
    VLESS_UUID = gen_uuid()
    VLESS_WS_UUID = gen_uuid()
    TROJAN_PASS = gen_pass()
    HYSTERIA2_PASS = gen_pass()
    SOCKS5_PASS = gen_pass()
    SUB_TOKEN = gen_pass(16)
    
    print(f"VLESS UUID: {VLESS_UUID}")
    print(f"SUB_TOKEN: {SUB_TOKEN}")
    print(f"Trojan 密码: {TROJAN_PASS}")
    print(f"Hysteria2 密码: {HYSTERIA2_PASS}\n")

    # Step 1: 清理并克隆最新代码
    print("[1/8] 清理并克隆最新代码...")
    run(ssh, "systemctl stop singbox singbox-sub singbox-cdn singbox-tgbot 2>/dev/null; true")
    run(ssh, "rm -rf /root/singbox-eps-node")
    run(ssh, "cd /root && git clone https://github.com/Alan-zzh/singbox-eps-node-v2.git singbox-eps-node", timeout=120)
    print()

    # Step 2: 安装依赖
    print("[2/8] 安装系统依赖...")
    run(ssh, "export DEBIAN_FRONTEND=noninteractive && apt-get update -y && apt-get install -y curl wget unzip python3 python3-pip cron net-tools git iproute2 iptables-persistent openssl", timeout=300)
    run(ssh, "pip3 install flask python-dotenv requests pyyaml --break-system-packages", timeout=120)
    print()

    # Step 3: 安装 sing-box 内核
    print("[3/8] 安装 sing-box 内核...")
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

    # Step 4: 生成 Reality 密钥
    print("[4/8] 生成 Reality 密钥...")
    _, key_out, _ = run(ssh, '/usr/local/bin/sing-box generate reality-keypair')
    
    REALITY_PRIVATE_KEY = ''
    REALITY_PUBLIC_KEY = ''
    for line in key_out.strip().split('\n'):
        if 'PrivateKey' in line:
            REALITY_PRIVATE_KEY = line.split(':', 1)[1].strip()
        elif 'PublicKey' in line:
            REALITY_PUBLIC_KEY = line.split(':', 1)[1].strip()
    
    REALITY_SHORT_ID = ''.join(random.choices('0123456789abcdef', k=8))
    print(f"  Private: {REALITY_PRIVATE_KEY[:20]}...")
    print(f"  Public: {REALITY_PUBLIC_KEY[:20]}...")
    print(f"  Short ID: {REALITY_SHORT_ID}\n")

    # Step 5: 生成 .env 文件
    print("[5/8] 生成配置文件...")
    env_content = f"""# Singbox Manager 配置文件 - v1.0.18
SERVER_IP=54.250.149.157
CF_DOMAIN={CF_DOMAIN}
CF_API_TOKEN={CF_API_TOKEN}
CF_EMAIL={CF_EMAIL}
EXTERNAL_SUBS=
TG_BOT_TOKEN={TG_BOT_TOKEN}
VLESS_UUID={VLESS_UUID}
VLESS_WS_UUID={VLESS_WS_UUID}
VLESS_UPGRADE_PORT=2053
TROJAN_PASSWORD={TROJAN_PASS}
HYSTERIA2_PASSWORD={HYSTERIA2_PASS}
SOCKS5_USER=socks5
SOCKS5_PASS={SOCKS5_PASS}
SUB_TOKEN={SUB_TOKEN}
SUB_PORT=6969
COUNTRY_CODE=JP
VLESS_UPGRADE_PORT=2053
TROJAN_WS_PORT=2083
HYSTERIA2_PORT=443
AI_SOCKS5_SERVER=
AI_SOCKS5_PORT=
AI_SOCKS5_USER=
AI_SOCKS5_PASS=
REALITY_PRIVATE_KEY={REALITY_PRIVATE_KEY}
REALITY_PUBLIC_KEY={REALITY_PUBLIC_KEY}
REALITY_SHORT_ID={REALITY_SHORT_ID}
REALITY_DEST=www.apple.com:443
REALITY_SNI=www.apple.com
"""
    run(ssh, f"cat > /root/singbox-eps-node/.env << 'ENVEOF'\n{env_content}\nENVEOF")
    print("  ✅ .env 已生成\n")

    # Step 6: 生成证书
    print("[6/8] 生成 SSL 证书...")
    run(ssh, "mkdir -p /root/singbox-eps-node/cert")
    run(ssh, "openssl req -x509 -nodes -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -keyout /root/singbox-eps-node/cert/cert.key -out /root/singbox-eps-node/cert/cert.crt -days 3650 -subj '/CN=jp.290372913.xyz' -addext 'subjectAltName=DNS:jp.290372913.xyz,IP:54.250.149.157' 2>/dev/null")
    run(ssh, "ls -la /root/singbox-eps-node/cert/")
    print()

    # Step 7: 生成 Singbox 配置
    print("[7/8] 生成 Singbox 配置...")
    run(ssh, "cd /root/singbox-eps-node && python3 scripts/config_generator.py", timeout=60)
    run(ssh, "ls -la /root/singbox-eps-node/config.json")
    print()

    # Step 8: 创建 systemd 服务并启动
    print("[8/8] 创建服务并启动...")
    
    # 创建所有 systemd 服务文件
    services = {
        'singbox': """[Unit]
Description=Singbox Core
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/local/bin/sing-box run -c /root/singbox-eps-node/config.json
Restart=always
RestartSec=5
WorkingDirectory=/root/singbox-eps-node

[Install]
WantedBy=multi-user.target
""",
        'singbox-sub': """[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/subscription_service.py
Restart=always
RestartSec=5
WorkingDirectory=/root/singbox-eps-node

[Install]
WantedBy=multi-user.target
""",
        'singbox-cdn': """[Unit]
Description=Singbox CDN Monitor
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/cdn_monitor.py --daemon
Restart=always
RestartSec=10
WorkingDirectory=/root/singbox-eps-node

[Install]
WantedBy=multi-user.target
""",
        'singbox-tgbot': """[Unit]
Description=Singbox Telegram Bot
After=network.target

[Service]
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/tg_bot.py
Restart=always
RestartSec=10
WorkingDirectory=/root/singbox-eps-node

[Install]
WantedBy=multi-user.target
"""
    }
    
    for name, content in services.items():
        run(ssh, f"cat > /etc/systemd/system/{name}.service << 'EOF'\n{content}\nEOF")
    
    # 设置 Hysteria2 端口跳跃
    run(ssh, """
iptables -t nat -F PREROUTING 2>/dev/null || true
for port in $(seq 21000 21200); do
    iptables -t nat -A PREROUTING -p udp --dport $port -j REDIRECT --to-port 443
done
netfilter-persistent save 2>/dev/null || true
""", timeout=60)

    # 网络优化
    run(ssh, """
grep -q 'tcp_congestion_control' /etc/sysctl.conf || echo 'net.ipv4.tcp_congestion_control = bbr' >> /etc/sysctl.conf
grep -q 'default_qdisc' /etc/sysctl.conf || echo 'net.core.default_qdisc = fq' >> /etc/sysctl.conf
sysctl -p 2>/dev/null || true
""")

    # 启动所有服务
    run(ssh, "systemctl daemon-reload")
    run(ssh, "systemctl enable singbox singbox-sub singbox-cdn singbox-tgbot")
    run(ssh, "systemctl restart singbox")
    time.sleep(3)
    run(ssh, "systemctl restart singbox-sub")
    time.sleep(2)
    run(ssh, "systemctl restart singbox-cdn")
    time.sleep(2)
    run(ssh, "systemctl restart singbox-tgbot")
    print()

    # 验证
    print("=" * 60)
    print("验证服务状态")
    print("=" * 60)
    
    run(ssh, "systemctl is-active singbox singbox-sub singbox-cdn singbox-tgbot")
    print()
    
    run(ssh, "ss -tlnp | grep -E '443|6969|2053|2083|1080'")
    print()

    run(ssh, "journalctl -u singbox --no-pager -n 5")
    print()
    
    run(ssh, "journalctl -u singbox-sub --no-pager -n 5")
    print()

    # 测试订阅链接
    print("测试订阅链接...")
    run(ssh, "curl -sk https://127.0.0.1:6969/sub/JP | head -c 300")
    print()

    print("=" * 60)
    print("✅ 全自动部署完成！")
    print("=" * 60)
    print(f"\n📡 订阅链接:")
    print(f"   https://{CF_DOMAIN}:6969/sub/JP")
    print(f"   https://54.250.149.157:6969/sub/JP")
    print(f"\n🔑 节点密码:")
    print(f"   Trojan: {TROJAN_PASS}")
    print(f"   Hysteria2: {HYSTERIA2_PASS}")
    print(f"   SOCKS5: socks5 / {SOCKS5_PASS}")
    print(f"\n🤖 TG 机器人: 已配置")
    
    ssh.close()

if __name__ == '__main__':
    main()
