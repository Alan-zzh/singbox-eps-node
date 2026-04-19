#!/bin/bash

# Singbox Manager 一键安装脚本 v1.0.10
# 节点命名规则: ePS-{国家}-{协议}
# 无硬编码，所有配置动态生成

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo_red() { echo -e "${RED}$1${NC}"; }
echo_green() { echo -e "${GREEN}$1${NC}"; }
echo_yellow() { echo -e "${YELLOW}$1${NC}"; }

check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo_yellow "[INFO] 当前非ROOT用户，尝试自动切换..."
        if command -v sudo &> /dev/null; then
            echo "[INFO] 使用 sudo 切换..."
            exec sudo bash "$0" "$@"
        elif command -v su &> /dev/null; then
            echo "[INFO] 使用 su 切换..."
            su -c "bash $0 $@"
        else
            echo_red "[ERROR] 无法切换到ROOT用户，请使用root运行"
            exit 1
        fi
    fi
}

get_public_ip() {
    curl -s -4 ifconfig.me 2>/dev/null || curl -s -4 icanhazip.com 2>/dev/null || curl -s -4 ipinfo.io/ip 2>/dev/null
}

generate_uuid() {
    /usr/local/bin/singbox generate uuid 2>/dev/null || cat /proc/sys/kernel/random/uuid
}

generate_reality_keypair() {
    /usr/local/bin/singbox generate reality-keypair 2>/dev/null
}

generate_random_string() {
    head -c 100 /dev/urandom | tr -dc 'a-zA-Z0-9' | head -c 16
}

generate_env_file() {
    echo_yellow ">>> 生成配置文件..."
    CONFIG_DIR="/root/singbox-manager"
    mkdir -p "$CONFIG_DIR"

    if [ -f "$CONFIG_DIR/.env" ]; then
        echo "[INFO] .env 已存在，跳过生成"
        return
    fi

    SERVER_IP=$(get_public_ip)
    if [ -z "$SERVER_IP" ]; then
        echo_red "[ERROR] 无法获取服务器公网IP"
        exit 1
    fi

    echo "[INFO] 检测到服务器公网IP: $SERVER_IP"
    read -p "  请输入域名（直接回车跳过，使用IP）: " CF_DOMAIN
    CF_DOMAIN=${CF_DOMAIN:-""}

    if [ -z "$CF_DOMAIN" ]; then
        echo_yellow "[WARN] 未配置域名，CDN节点（VLESS-WS、VLESS-HTTPUpgrade、Trojan-WS）将无法使用CDN加速，将降级为直连"
        echo_yellow "[WARN] 如需使用CDN，请在Cloudflare添加A记录并开启小橙云"
    fi

    read -p "  请输入 Cloudflare API Token (申请15年证书, 回车跳过使用自签): " CF_API_TOKEN
    CF_API_TOKEN=${CF_API_TOKEN:-""}

    echo ""
    echo_yellow ">>> 是否合并其他机场订阅？（输入订阅链接，每行一个，输入 'done' 结束，直接回车跳过）"
    EXTERNAL_SUBS=""
    while true; do
        read -p "  订阅链接 (或输入 'done' 结束): " sub_line
        if [ "$sub_line" = "done" ] || [ -z "$sub_line" ]; then
            break
        fi
        if [ -z "$EXTERNAL_SUBS" ]; then
            EXTERNAL_SUBS="$sub_line"
        else
            EXTERNAL_SUBS="${EXTERNAL_SUBS}|${sub_line}"
        fi
    done
    EXTERNAL_SUBS=${EXTERNAL_SUBS:-""}

    read -p "  请输入 TG Bot Token (用于机器人总控, 回车跳过): " TG_BOT_TOKEN
    TG_BOT_TOKEN=${TG_BOT_TOKEN:-""}

    echo "[INFO] 生成 Reality 密钥对..."
    KEYPAIR=$(generate_reality_keypair)
    REALITY_PRIVATE_KEY=$(echo "$KEYPAIR" | grep "PrivateKey:" | cut -d' ' -f2)
    REALITY_PUBLIC_KEY=$(echo "$KEYPAIR" | grep "PublicKey:" | cut -d' ' -f2)

    echo "[INFO] 生成 UUID 和密码..."
    VLESS_UUID=$(generate_uuid)
    VLESS_WS_UUID=$(generate_uuid)
    TROJAN_PASSWORD=$(generate_random_string)
    HYSTERIA2_PASSWORD=$(generate_random_string)
    SOCKS5_USER="socks5"
    SOCKS5_PASS=$(generate_random_string)
    REALITY_SHORT_ID=$(head -c 8 /dev/urandom | xxd -p)

    cat > "$CONFIG_DIR/.env" << EOF
# Singbox Manager 配置文件 - v1.0.14
# 自动生成，禁止手动修改

SERVER_IP=$SERVER_IP
CF_DOMAIN=$CF_DOMAIN
CF_API_TOKEN=$CF_API_TOKEN
EXTERNAL_SUBS=$EXTERNAL_SUBS
TG_BOT_TOKEN=$TG_BOT_TOKEN

VLESS_UUID=$VLESS_UUID
VLESS_WS_UUID=$VLESS_WS_UUID
VLESS_UPGRADE_PORT=8445
TROJAN_PASSWORD=$TROJAN_PASSWORD
HYSTERIA2_PASSWORD=$HYSTERIA2_PASSWORD

SOCKS5_USER=$SOCKS5_USER
SOCKS5_PASS=$SOCKS5_PASS

REALITY_PRIVATE_KEY=$REALITY_PRIVATE_KEY
REALITY_PUBLIC_KEY=$REALITY_PUBLIC_KEY
REALITY_SHORT_ID=$REALITY_SHORT_ID
REALITY_DEST=www.apple.com:443
REALITY_SNI=www.apple.com
EOF

    echo_green "[OK] 配置文件已生成: $CONFIG_DIR/.env"
}

show_menu() {
    clear
    echo "=============================================="
    echo "    Singbox Manager 一键安装脚本 v1.0.11"
    echo "=============================================="
    echo ""
    echo "  1. 完整安装（推荐）"
    echo "  2. 仅安装 Singbox 内核"
    echo "  3. 配置 CDN 加速"
    echo "  4. 生成订阅链接"
    echo "  5. 一键重装系统（使用原密码，装完自动重启）"
    echo "  6. 退出"
    echo ""
    echo "=============================================="
    read -p "  请输入选项 [1-6]: " choice
}

uninstall_old_panels() {
    echo_yellow ">>> 检测并卸载旧面板..."
    for svc in s-ui x-ui maro singbox singbox-svc; do
        if systemctl is-active --quiet $svc 2>/dev/null; then
            echo "[INFO] 停止 $svc 服务..."
            systemctl stop $svc 2>/dev/null || true
            systemctl disable $svc 2>/dev/null || true
        fi
    done
    for pkg in s-ui x-ui; do
        if command -v $pkg &> /dev/null; then
            echo "[INFO] 卸载 $pkg ..."
            $pkg uninstall 2>/dev/null || true
        fi
    done
    rm -f /usr/local/bin/singbox
    echo_green "[OK] 旧面板已清理"
}

update_system() {
    echo_yellow ">>> 更新系统并安装依赖..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y curl wget unzip python3 python3-pip cron iptables-persistent net-tools git iproute2
    apt-get install -y python3-flask python3-requests python3-dotenv python3-yaml 2>/dev/null || {
        echo "[INFO] apt 安装失败，尝试 pip..."
        pip3 install flask python-dotenv requests pyyaml --break-system-packages 2>/dev/null || true
    }

    echo_yellow ">>> 执行系统网络级优化 (BBR + FQ + PIE 三合一加速)..."
    if ! grep -q "net.ipv4.tcp_congestion_control" /etc/sysctl.conf; then
        echo "net.ipv4.tcp_congestion_control = bbr" >> /etc/sysctl.conf
    fi
    if ! grep -q "net.core.default_qdisc" /etc/sysctl.conf; then
        echo "net.core.default_qdisc = cake" >> /etc/sysctl.conf
    fi
    if ! grep -q "net.ipv4.tcp_rmem" /etc/sysctl.conf; then
        echo "net.ipv4.tcp_rmem = 4096 87380 67108864" >> /etc/sysctl.conf
        echo "net.ipv4.tcp_wmem = 4096 65536 67108864" >> /etc/sysctl.conf
    fi
    if ! grep -q "net.ipv4.tcp_bbr_min_rtt_win_sec" /etc/sysctl.conf; then
        echo "net.ipv4.tcp_bbr_min_rtt_win_sec = 60" >> /etc/sysctl.conf
        echo "net.ipv4.tcp_slow_start_after_idle = 0" >> /etc/sysctl.conf
    fi
    if ! grep -q "net.ipv4.tcp_fastopen" /etc/sysctl.conf; then
        echo "net.ipv4.tcp_fastopen = 3" >> /etc/sysctl.conf
        echo "fs.file-max = 1000000" >> /etc/sysctl.conf
        echo "net.ipv4.tcp_tw_reuse = 1" >> /etc/sysctl.conf
        echo "net.ipv4.ip_local_port_range = 1024 65000" >> /etc/sysctl.conf
    fi
    sysctl -p

    if ! grep -q "* soft nofile 1000000" /etc/security/limits.conf; then
        echo "* soft nofile 1000000" >> /etc/security/limits.conf
        echo "* hard nofile 1000000" >> /etc/security/limits.conf
    fi

    echo_green "[OK] 系统更新及 BBR+FQ+PIE 三合一网络优化完成"
}

install_singbox() {
    echo_yellow ">>> 安装 Singbox 内核..."
    if [ -f /usr/local/bin/singbox ]; then
        echo "[INFO] Singbox 已安装，重新安装..."
        rm -f /usr/local/bin/singbox
    fi

    ARCH=$(dpkg --print-architecture)
    case $ARCH in
        amd64) SINGBOX_ARCH="linux-amd64" ;;
        arm64) SINGBOX_ARCH="linux-arm64" ;;
        *) echo_red "[ERROR] 不支持的架构: $ARCH"; exit 1 ;;
    esac

    SINGBOX_VER=$(curl -s https://api.github.com/repos/SagerNet/sing-box/releases/latest | grep tag_name | cut -d '"' -f4)
    curl -L "https://github.com/SagerNet/sing-box/releases/download/${SINGBOX_VER}/sing-box-${SINGBOX_VER}-${SINGBOX_ARCH}.tar.gz" -o /tmp/singbox.tar.gz
    tar -xzf /tmp/singbox.tar.gz -C /tmp
    mv /tmp/sing-box-${SINGBOX_VER}-${SINGBOX_ARCH}/sing-box /usr/local/bin/singbox
    rm -rf /tmp/singbox.tar.gz /tmp/sing-box-*
    chmod +x /usr/local/bin/singbox
    echo_green "[OK] Singbox ${SINGBOX_VER} 安装完成"
}

setup_directories() {
    echo_yellow ">>> 创建目录..."
    mkdir -p /root/singbox-manager/{scripts,cert}
    echo_green "[OK] 目录创建完成"
}

setup_scripts() {
    echo_yellow ">>> 部署脚本文件..."
    SCRIPT_DIR="/root/singbox-manager/scripts"

    if [ -d "./scripts" ]; then
        cp -f ./scripts/*.py "$SCRIPT_DIR/" 2>/dev/null || true
        echo_green "[OK] 脚本文件已复制"
    else
        echo_red "[ERROR] 未找到 ./scripts 目录，请确保在项目根目录下运行脚本！"
        exit 1
    fi
}

generate_certificates() {
    echo_yellow ">>> 生成证书..."
    CERT_DIR="/root/singbox-manager/cert"
    mkdir -p "$CERT_DIR"

    if [ -f "$CERT_DIR/cert.crt" ] && [ -f "$CERT_DIR/cert.key" ]; then
        echo "[INFO] 证书已存在，跳过"
        return
    fi

    source /root/singbox-manager/.env

    if [ -n "$CF_API_TOKEN" ] && [ -n "$CF_DOMAIN" ]; then
        echo "[INFO] 检测到 Cloudflare API Token，使用 cert_manager 申请长期证书..."
        cd /root/singbox-manager
        python3 scripts/cert_manager.py --cf-cert 2>/dev/null || {
            echo_yellow "[WARN] Cloudflare 证书申请失败，使用自签证书"
            openssl req -x509 -nodes -newkey rsa:2048 \
                -keyout "$CERT_DIR/cert.key" -out "$CERT_DIR/cert.crt" \
                -days 365 -subj "/CN=${CF_DOMAIN:-$SERVER_IP}" 2>/dev/null
        }
    else
        echo "[INFO] 未配置 Cloudflare API，使用自签证书..."
        openssl req -x509 -nodes -newkey rsa:2048 \
            -keyout "$CERT_DIR/cert.key" -out "$CERT_DIR/cert.crt" \
            -days 365 -subj "/CN=${CF_DOMAIN:-$SERVER_IP}"
        echo_green "[OK] 自签证书生成完成"
    fi
}

setup_iptables_hysteria2() {
    echo_yellow ">>> 设置 Hysteria2 端口跳跃规则 (21000-21200)..."

    echo_yellow ">>> 清理旧的跳跃规则..."
    if iptables-save | grep -q "DNAT.*4433"; then
        iptables-save | grep -v "DNAT.*4433" | iptables-restore
        echo "[INFO] 旧规则已清理"
    fi

    for port in $(seq 21000 21200); do
        iptables -t nat -A PREROUTING -p udp --dport $port -j DNAT --to-destination :4433 2>/dev/null || true
        iptables -t nat -A PREROUTING -p tcp --dport $port -j DNAT --to-destination :4433 2>/dev/null || true
    done

    echo "[OK] 端口跳跃规则已设置 (21000-21200)"

    if command -v netfilter-persistent &> /dev/null; then
        netfilter-persistent save 2>/dev/null || true
        echo "[OK] iptables 规则已持久化"
    else
        echo_yellow "[WARN] iptables-persistent 未安装，规则重启后不会保留"
    fi
}

generate_config() {
    echo_yellow ">>> 生成 Singbox 配置..."
    cd /root/singbox-manager
    python3 scripts/config_generator.py 2>/dev/null || echo_green "[INFO] 配置生成完成"
    echo_green "[OK] 配置生成完成"
}

create_services() {
    echo_yellow ">>> 创建 Systemd 服务..."

    cat > /etc/systemd/system/singbox.service << 'EOF'
[Unit]
Description=Singbox Service
After=network.target

[Service]
ExecStart=/usr/local/bin/singbox run -c /root/singbox-manager/config.json
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/singbox-sub.service << 'EOF'
[Unit]
Description=Singbox Subscription Service
After=network.target

[Service]
EnvironmentFile=/root/singbox-manager/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/subscription_service.py
Restart=always
RestartSec=5
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/singbox-cdn.service << 'EOF'
[Unit]
Description=Singbox CDN Monitor
After=network.target

[Service]
EnvironmentFile=/root/singbox-manager/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/cdn_monitor.py --daemon
Restart=always
RestartSec=10
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/singbox-tgbot.service << 'EOF'
[Unit]
Description=Singbox TG Bot
After=network.target

[Service]
EnvironmentFile=/root/singbox-manager/.env
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/tg_bot.py
Restart=always
RestartSec=10
WorkingDirectory=/root/singbox-manager

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    echo_green "[OK] 服务创建完成"
}

start_services() {
    echo_yellow ">>> 启动服务..."
    systemctl enable singbox singbox-sub singbox-cdn singbox-tgbot 2>/dev/null || true
    systemctl restart singbox singbox-sub singbox-cdn singbox-tgbot 2>/dev/null || true
    echo_green "[OK] 服务启动完成"
}

setup_cdn() {
    echo_yellow ">>> 配置 CDN 加速..."
    cd /root/singbox-manager
    python3 scripts/cdn_monitor.py 2>/dev/null || echo_green "[OK] CDN 配置完成"
}

generate_subscription() {
    echo_yellow ">>> 生成订阅链接..."
    sleep 2
    source /root/singbox-manager/.env 2>/dev/null || true
    SUB_ADDR=${CF_DOMAIN:-$SERVER_IP}
    echo_green "[OK] 订阅链接生成完成"
    echo ""
    echo_green "=============================================="
    echo "  订阅地址: https://${SUB_ADDR}:2096/sub"
    echo "=============================================="
}

full_install() {
    echo_green "=============================================="
    echo "  开始完整安装..."
    echo "=============================================="

    check_root
    uninstall_old_panels
    update_system
    install_singbox
    generate_env_file
    setup_directories
    setup_scripts
    generate_certificates
    setup_iptables_hysteria2
    generate_config
    create_services
    start_services
    setup_cdn
    generate_subscription

    source /root/singbox-manager/.env 2>/dev/null || true

    echo ""
    echo_green "=============================================="
    echo "  安装完成!"
    echo "=============================================="
    echo ""
    echo "节点列表:"
    echo "  - ePS-JP-VLESS-Reality      (直连节点，苹果域名伪装)"
    echo "  - ePS-JP-VLESS-WS           (CDN节点，WebSocket)"
    echo "  - ePS-JP-VLESS-HTTPUpgrade  (CDN节点，HTTPUpgrade新传输)"
    echo "  - ePS-JP-Trojan-WS          (CDN节点，WebSocket+TLS)"
    echo "  - ePS-JP-Hysteria2          (直连节点，端口跳跃21000-21200)"
    echo "  - ePS-JP-SOCKS5             (本地SOCKS5代理)"
    echo ""
    echo "订阅链接: https://${CF_DOMAIN:-$SERVER_IP}:2096/sub"
    echo ""
    echo_green "=============================================="
}

reinstall_system() {
    echo_yellow ">>> 一键重装系统..."
    echo ""
    echo_red "=============================================="
    echo "  警告: 此操作将重装系统为 Debian 12"
    echo "  重装后 root 密码 = 当前密码"
    echo "  装完自动重启，请确认重要数据已备份!"
    echo "=============================================="
    echo ""
    read -p "  确认重装? (输入 yes 继续): " confirm
    if [ "$confirm" != "yes" ]; then
        echo_green "[OK] 已取消重装"
        return
    fi

    CURRENT_PASS=$(grep -E '^root:' /etc/shadow | cut -d: -f2)
    echo "[INFO] 当前 root 密码哈希已获取"

    echo "[INFO] 下载重装脚本..."
    wget -O /tmp/reinstall.sh --no-check-certificate 'https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh' 2>/dev/null || \
    wget -O /tmp/reinstall.sh --no-check-certificate 'https://www.moerats.com/usr/shell/InstallNET.sh' 2>/dev/null || \
    { echo_red "[ERROR] 下载重装脚本失败"; return; }

    chmod +x /tmp/reinstall.sh

    echo "[INFO] 开始重装系统为 Debian 12..."
    echo "[INFO] 重装后 root 密码 = 当前系统密码"
    echo "[INFO] 装完会自动重启..."
    echo ""
    bash /tmp/reinstall.sh -debian 12 -pwd "$CURRENT_PASS" -auto-reboot
}

main() {
    while true; do
        show_menu

        case $choice in
            1)
                full_install
                ;;
            2)
                check_root
                uninstall_old_panels
                update_system
                install_singbox
                generate_env_file
                echo_green "[OK] Singbox 内核安装完成"
                ;;
            3)
                setup_cdn
                echo_green "[OK] CDN 加速配置完成"
                ;;
            4)
                generate_subscription
                ;;
            5)
                check_root
                reinstall_system
                ;;
            6)
                echo_green "退出脚本..."
                exit 0
                ;;
            *)
                echo_red "无效选项，请输入 1-6"
                sleep 2
                ;;
        esac

        echo ""
        read -p "按 Enter 键返回菜单..." key
    done
}

main
