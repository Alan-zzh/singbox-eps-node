#!/usr/bin/env python3
"""
VPS 全自动部署脚本 - 无需交互
"""
import paramiko
import uuid
import random
import string
import time

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

def run(ssh, cmd, timeout=120):
    print(f"  >>> {cmd[:120]}")
    chan = ssh.get_transport().open_session()
    chan.settimeout(timeout)
    chan.get_pty(width=200, height=50)
    chan.exec_command(cmd)
    
    output = b""
    while True:
        if chan.recv_ready():
            data = chan.recv(4096)
            output += data
            text = data.decode('utf-8', errors='ignore')
            if text.strip():
                print(f"    {text.strip()[:200]}")
        if chan.exit_status_ready():
            break
        time.sleep(0.5)
    
    # 读取剩余输出
    while chan.recv_ready():
        output += chan.recv(4096)
    
    exit_code = chan.recv_exit_status()
    out_str = output.decode('utf-8', errors='ignore')
    return exit_code, out_str

def main():
    print("=" * 60)
    print("开始自动部署 Singbox v1.0.17")
    print("=" * 60)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(HOST, port=PORT, username=USER, password=PASSWORD, timeout=15)
        print("✅ SSH 连接成功\n")
    except Exception as e:
        print(f"❌ SSH 连接失败: {e}")
        return

    VLESS_UUID = gen_uuid()
    VLESS_WS_UUID = gen_uuid()
    TROJAN_PASS = gen_pass()
    HYSTERIA2_PASS = gen_pass()
    SOCKS5_PASS = gen_pass()
    SUB_TOKEN = gen_pass(16)
    REALITY_SHORT_ID = ''.join(random.choices('0123456789abcdef', k=8))
    
    print(f"VLESS UUID: {VLESS_UUID}")
    print(f"SUB_TOKEN: {SUB_TOKEN}")
    print(f"Trojan 密码: {TROJAN_PASS}")
    print(f"Hysteria2 密码: {HYSTERIA2_PASS}")
    print(f"Reality Short ID: {REALITY_SHORT_ID}\n")

    # Step 1: 获取服务器 IP
    print("[1/10] 获取服务器 IP...")
    _, ip_out = run(ssh, "curl -s ifconfig.me || curl -s ip.sb || curl -s icanhazip.com")[:2]
    SERVER_IP = ip_out.strip().split('\n')[-1].strip()
    print(f"  服务器 IP: {SERVER_IP}\n")

    # Step 2: 清理旧环境
    print("[2/10] 清理旧环境...")
    run(ssh, "systemctl stop singbox singbox-sub singbox-cdn singbox-tgbot 2>/dev/null; systemctl disable singbox singbox-sub singbox-cdn singbox-tgbot 2>/dev/null")
    run(ssh, "rm -rf /root/singbox-eps-node /root/singbox-manager")
    print("  清理完成\n")

    # Step 3: 克隆代码
    print("[3/10] 克隆最新代码...")
    run(ssh, "cd /root && git clone https://github.com/Alan-zzh/singbox-eps-node-v2.git singbox-eps-node", timeout=120)
    print("  克隆完成\n")

    # Step 4: 更新系统并安装依赖
    print("[4/10] 更新系统并安装依赖...")
    run(ssh, "export DEBIAN_FRONTEND=noninteractive && apt-get update -y && apt-get install -y curl wget unzip python3 python3-pip cron net-tools git iproute2 iptables-persistent", timeout=300)
    run(ssh, "pip3 install flask python-dotenv requests pyyaml --break-system-packages 2>/dev/null || pip3 install flask python-dotenv requests pyyaml", timeout=120)
    print("  依赖安装完成\n")

    # Step 5: 安装 Singbox 内核
    print("[5/10] 安装 Singbox 内核...")
    run(ssh, """
ARCH=$(uname -m)
if [ "$ARCH" = "x86_64" ]; then ARCH="linux-amd64"; elif [ "$ARCH" = "aarch64" ]; then ARCH="linux-arm64"; fi
cd /tmp && wget -q https://github.com/SagerNet/sing-box/releases/latest/download/sing-box-1.10.0-$ARCH.tar.gz
tar -xzf sing-box-1.10.0-$ARCH.tar.gz
cp sing-box-1.10.0-$ARCH/sing-box /usr/local/bin/sing-box
chmod +x /usr/local/bin/sing-box
rm -rf /tmp/sing-box*
sing-box version
""", timeout=120)
    print("  Singbox 内核安装完成\n")

    # Step 6: 生成 Reality 密钥
    print("[6/10] 生成 Reality 密钥...")
    _, key_out = run(ssh, "/usr/local/bin/sing-box generate reality-keypair")[:2]
    lines = key_out.strip().split('\n')
    REALITY_PRIVATE_KEY = ""
    REALITY_PUBLIC_KEY = ""
    for line in lines:
        if line.startswith("PrivateKey"):
            REALITY_PRIVATE_KEY = line.split(':', 1)[1].strip()
        elif line.startswith("PublicKey"):
            REALITY_PUBLIC_KEY = line.split(':', 1)[1].strip()
    print(f"  Reality 私钥: {REALITY_PRIVATE_KEY[:20]}...")
    print(f"  Reality 公钥: {REALITY_PUBLIC_KEY[:20]}...\n")

    # Step 7: 生成 .env 文件
    print("[7/10] 生成配置文件...")
    env_content = f"""# Singbox Manager 配置文件 - v1.0.17
SERVER_IP={SERVER_IP}
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
    print("  配置生成完成\n")

    # Step 8: 生成证书
    print("[8/10] 生成 SSL 证书...")
    run(ssh, "cd /root/singbox-eps-node && python3 scripts/cert_manager.py", timeout=120)
    print("  证书生成完成\n")

    # Step 9: 生成 Singbox 配置
    print("[9/10] 生成 Singbox 配置...")
    run(ssh, "cd /root/singbox-eps-node && python3 scripts/config_generator.py", timeout=60)
    print("  配置生成完成\n")

    # Step 10: 创建 systemd 服务并启动
    print("[10/10] 创建服务并启动...")
    
    # singbox 服务
    run(ssh, """cat > /etc/systemd/system/singbox.service << 'EOF'
[Unit]
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
EOF
""")

    # 订阅服务
    run(ssh, """cat > /etc/systemd/system/singbox-sub.service << 'EOF'
[Unit]
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
EOF
""")

    # CDN 监控
    run(ssh, """cat > /etc/systemd/system/singbox-cdn.service << 'EOF'
[Unit]
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
EOF
""")

    # TG 机器人
    run(ssh, """cat > /etc/systemd/system/singbox-tgbot.service << 'EOF'
[Unit]
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
EOF
""")

    # 设置 Hysteria2 端口跳跃
    run(ssh, """
iptables -t nat -F PREROUTING 2>/dev/null || true
for port in $(seq 21000 21200); do
    iptables -t nat -A PREROUTING -p udp --dport $port -j REDIRECT --to-port 443
done
apt-get install -y iptables-persistent 2>/dev/null
echo y | netfilter-persistent save 2>/dev/null || true
""", timeout=60)

    # 网络优化
    run(ssh, """
echo 'net.ipv4.tcp_congestion_control = bbr' >> /etc/sysctl.conf
echo 'net.core.default_qdisc = fq' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_queue_sharing = 1' >> /etc/sysctl.conf
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

    # 检查状态
    print("\n" + "=" * 60)
    print("服务状态检查")
    print("=" * 60)
    run(ssh, "systemctl is-active singbox singbox-sub singbox-cdn singbox-tgbot")
    run(ssh, "sing-box version")
    
    # 最终信息
    print("\n" + "=" * 60)
    print("✅ 部署完成！")
    print("=" * 60)
    print(f"\n📡 订阅链接:")
    print(f"   https://{CF_DOMAIN}:6969/sub/JP")
    print(f"   https://{SERVER_IP}:6969/sub/JP")
    print(f"\n🔑 节点密码:")
    print(f"   Trojan: {TROJAN_PASS}")
    print(f"   Hysteria2: {HYSTERIA2_PASS}")
    print(f"   SOCKS5: socks5 / {SOCKS5_PASS}")
    print(f"\n🤖 TG 机器人: @{TG_BOT_TOKEN.split(':')[0]}")
    
    ssh.close()

if __name__ == '__main__':
    main()
