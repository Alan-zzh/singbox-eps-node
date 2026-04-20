#!/bin/bash
# 一键安装脚本 - 在服务器上运行
# 使用方法：在服务器上执行 bash /root/install.sh

set -e

echo "============================================================"
echo "Singbox EPS Node 一键安装脚本"
echo "============================================================"

# 1. 安装依赖
echo ""
echo "【步骤1】安装系统依赖..."
apt-get update -y
apt-get install -y python3 python3-pip curl wget iptables

# 2. 安装Python依赖
echo ""
echo "【步骤2】安装Python依赖..."
pip3 install flask requests python-dotenv pyyaml

# 3. 创建目录结构
echo ""
echo "【步骤3】创建目录结构..."
mkdir -p /root/singbox-eps-node/{scripts,data,cert,geo,logs}

# 4. 创建.env文件（需要手动填写）
echo ""
echo "【步骤4】创建.env配置文件..."
cat > /root/singbox-eps-node/.env << 'EOF'
# 服务器配置
SERVER_IP=你的服务器IP
CF_DOMAIN=你的Cloudflare域名
COUNTRY_CODE=JP

# 订阅配置
SUB_PORT=6969
SUB_TOKEN=你的订阅Token

# VLESS配置
VLESS_UUID=你的VLESS UUID
VLESS_WS_UUID=你的VLESS WS UUID
VLESS_WS_PORT=8443
VLESS_UPGRADE_PORT=2053

# Reality配置
REALITY_SNI=www.apple.com
REALITY_DEST=www.apple.com:443
REALITY_PUBLIC_KEY=你的Reality公钥
REALITY_SHORT_ID=你的Reality短ID

# Trojan配置
TROJAN_PASSWORD=你的Trojan密码
TROJAN_WS_PORT=2083

# Hysteria2配置
HYSTERIA2_PASSWORD=你的Hysteria2密码

# SOCKS5配置
AI_SOCKS5_SERVER=206.163.4.241
AI_SOCKS5_PORT=36753
AI_SOCKS5_USER=4KKsLB7F
AI_SOCKS5_PASS=KgEKVmVgxJ

# 外部订阅（可选）
EXTERNAL_SUBS=
EOF

echo "  ⚠️ 请编辑 /root/singbox-eps-node/.env 文件，填入你的配置"
echo "  配置项说明："
echo "  - SERVER_IP: 你的服务器公网IP"
echo "  - CF_DOMAIN: 你的Cloudflare域名（如：jp.290372913.xyz）"
echo "  - COUNTRY_CODE: 国家代码（如：JP）"
echo "  - SUB_TOKEN: 订阅Token（随机字符串）"
echo "  - VLESS_UUID: VLESS UUID"
echo "  - 其他配置项按需填写"

# 5. 创建config.py
echo ""
echo "【步骤5】创建config.py..."
cat > /root/singbox-eps-node/scripts/config.py << 'PYEOF'
import os
from dotenv import load_dotenv

load_dotenv('/root/singbox-eps-node/.env')

# 路径配置
BASE_DIR = '/root/singbox-eps-node'
CERT_DIR = os.path.join(BASE_DIR, 'cert')
DATA_DIR = os.path.join(BASE_DIR, 'data')
GEO_DIR = os.path.join(BASE_DIR, 'geo')
LOG_DIR = os.path.join(BASE_DIR, 'logs')
ENV_FILE = os.path.join(BASE_DIR, '.env')
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
DB_FILE = os.path.join(DATA_DIR, 'singbox.db')

# 服务器配置
SERVER_IP = os.getenv('SERVER_IP', '')
CF_DOMAIN = os.getenv('CF_DOMAIN', '')

# 服务端口配置
SUB_PORT = int(os.getenv('SUB_PORT', '6969'))
SINGBOX_PORT = 443
VLESS_WS_PORT = 8443
VLESS_UPGRADE_PORT = 2053
TROJAN_WS_PORT = 2083
HYSTERIA2_PORT = 443
SOCKS5_PORT = 1080

# 其他配置
VLESS_UUID = os.getenv('VLESS_UUID', '')
VLESS_WS_UUID = os.getenv('VLESS_WS_UUID', '')
TROJAN_PASSWORD = os.getenv('TROJAN_PASSWORD', '')
HYSTERIA2_PASSWORD = os.getenv('HYSTERIA2_PASSWORD', '')
REALITY_PUBLIC_KEY = os.getenv('REALITY_PUBLIC_KEY', '')
REALITY_SHORT_ID = os.getenv('REALITY_SHORT_ID', 'abcd1234')
REALITY_DEST = os.getenv('REALITY_DEST', 'www.apple.com:443')
REALITY_SNI = os.getenv('REALITY_SNI', 'www.apple.com')
EXTERNAL_SUBS = os.getenv('EXTERNAL_SUBS', '')
SUB_TOKEN = os.getenv('SUB_TOKEN', '')
COUNTRY_CODE = os.getenv('COUNTRY_CODE', 'JP')

# SOCKS5配置
AI_SOCKS5_SERVER = os.getenv('AI_SOCKS5_SERVER', '206.163.4.241')
AI_SOCKS5_PORT = int(os.getenv('AI_SOCKS5_PORT', '36753'))
AI_SOCKS5_USER = os.getenv('AI_SOCKS5_USER', '4KKsLB7F')
AI_SOCKS5_PASS = os.getenv('AI_SOCKS5_PASS', 'KgEKVmVgxJ')

# Hysteria2 UDP端口范围
HYSTERIA2_UDP_PORTS = list(range(21000, 21201))
PYEOF

# 6. 创建logger.py
echo ""
echo "【步骤6】创建logger.py..."
cat > /root/singbox-eps-node/scripts/logger.py << 'PYEOF'
import logging
import os

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger
PYEOF

# 7. 创建systemd服务文件
echo ""
echo "【步骤7】创建systemd服务文件..."

# CDN监控服务
cat > /etc/systemd/system/singbox-cdn.service << 'EOF'
[Unit]
Description=Singbox CDN Monitor Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/singbox-eps-node/scripts
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/cdn_monitor.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 订阅服务
cat > /etc/systemd/system/singbox-sub.service << 'EOF'
[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/singbox-eps-node/scripts
EnvironmentFile=/root/singbox-eps-node/.env
ExecStart=/usr/bin/python3 /root/singbox-eps-node/scripts/subscription_service.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 8. 配置防火墙
echo ""
echo "【步骤8】配置防火墙..."
iptables -A INPUT -p tcp --dport 22 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p tcp --dport 8443 -j ACCEPT
iptables -A INPUT -p tcp --dport 2053 -j ACCEPT
iptables -A INPUT -p tcp --dport 2083 -j ACCEPT
iptables -A INPUT -p tcp --dport 6969 -j ACCEPT
iptables -A INPUT -p tcp --dport 36753 -j ACCEPT
iptables -A INPUT -p udp --dport 443 -j ACCEPT
iptables -A INPUT -p udp --dport 21000:21200 -j ACCEPT
iptables-save > /etc/iptables.rules
echo "  ✅ 防火墙已配置"

# 9. 重新加载systemd
echo ""
echo "【步骤9】重新加载systemd..."
systemctl daemon-reload
echo "  ✅ systemd配置已重新加载"

# 10. 启动服务
echo ""
echo "【步骤10】启动服务..."
systemctl enable singbox-cdn
systemctl enable singbox-sub
systemctl start singbox-cdn
systemctl start singbox-sub
echo "  ✅ 服务已启动"

# 等待服务启动
sleep 5

# 11. 检查服务状态
echo ""
echo "【步骤11】检查服务状态..."
systemctl status singbox-cdn --no-pager | head -5
systemctl status singbox-sub --no-pager | head -5

echo ""
echo "============================================================"
echo "✅ 安装完成！"
echo "============================================================"
echo ""
echo "下一步："
echo "1. 编辑配置文件: nano /root/singbox-eps-node/.env"
echo "2. 重启服务: systemctl restart singbox-cdn singbox-sub"
echo "3. 测试订阅: curl http://127.0.0.1:6969/sub"
echo ""
echo "订阅链接:"
echo "  http://你的服务器IP:6969/sub"
echo "  http://你的服务器IP:6969/sub/JP"
echo "  http://你的服务器IP:6969/你的SUB_TOKEN"
echo ""
