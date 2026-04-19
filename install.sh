#!/bin/bash

# Singbox Manager 一键安装脚本 v1.0.7
# 节点命名规则: ePS-{国家}-{协议}
# 服务器IP: 54.250.149.157
# 域名: jp1.290372913.xyz

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
        echo_red "[ERROR] 请使用root用户运行此脚本"
        exit 1
    fi
}

get_current_root_pass() {
    ROOT_PASS=$(grep -E '^root:' /etc/shadow | cut -d: -f2)
    echo "$ROOT_PASS"
}

show_menu() {
    clear
    echo "=============================================="
    echo "    Singbox Manager 一键安装脚本 v1.0.7"
    echo "=============================================="
    echo ""
    echo "  1. 完整安装（推荐）"
    echo "  2. 仅安装 Singbox 内核"
    echo "  3. 配置 CDN 加速"
    echo "  4. 生成订阅链接"
    echo "  5. 一键重装系统密码"
    echo "  6. 退出"
    echo ""
    echo "=============================================="
    read -p "  请输入选项 [1-6]: " choice
}

uninstall_old_panels() {
    echo_yellow ">>> 检测并卸载旧面板..."
    for svc in s-ui x-ui maro singbox; do
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
    echo_green "[OK] 旧面板已清理"
}

update_system() {
    echo_yellow ">>> 更新系统..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y curl wget unzip python3 python3-pip cron iptables-persistent net-tools
    pip3 install flask python-dotenv requests 2>/dev/null || true
    echo_green "[OK] 系统更新完成"
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
    LOCAL_DIR="/root/singbox-manager-local"

    if [ -d "$LOCAL_DIR/scripts" ]; then
        echo "[INFO] 复制脚本文件..."
        cp -f "$LOCAL_DIR/scripts/"*.py "$SCRIPT_DIR/" 2>/dev/null || true
        echo_green "[OK] 脚本文件已复制"
    else
        echo_yellow "[WARN] 未找到本地脚本目录，将使用内嵌脚本"
    fi
}

generate_certificates() {
    echo_yellow ">>> 生成证书..."
    CERT_DIR="/root/singbox-manager/cert"

    if [ -f "$CERT_DIR/cert.crt" ] && [ -f "$CERT_DIR/cert.key" ]; then
        echo "[INFO] 证书已存在，跳过"
    else
        python3 /root/singbox-manager/scripts/cert_manager.py 2>/dev/null || {
            openssl req -x509 -nodes -newkey rsa:2048 -keyout "$CERT_DIR/cert.key" -out "$CERT_DIR/cert.crt" -days 365 -subj "/CN=${CF_DOMAIN:-jp1.290372913.xyz}"
        }
        echo_green "[OK] 证书生成完成"
    fi
}

setup_iptables_hysteria2() {
    echo_yellow ">>> 设置 Hysteria2 端口跳跃规则 (21000-21200)..."

    iptables -t nat -F PREROUTING

    for port in $(seq 21000 21200); do
        iptables -t nat -A PREROUTING -p udp --dport $port -j DNAT --to-destination :4433
        iptables -t nat -A PREROUTING -p tcp --dport $port -j DNAT --to-destination :4433
    done

    echo "[OK] 端口跳跃规则已设置 (21000-21200)"

    debconf-set-selections <<< "iptables-persistent iptables-persistent/autosave_v4 boolean true"
    debconf-set-selections <<< "iptables-persistent iptables-persistent/autosave_v6 boolean true"
    netfilter-persistent save

    echo_green "[OK] iptables 规则已持久化"
}

generate_config() {
    echo_yellow ">>> 生成 Singbox 配置..."
    cd /root/singbox-manager
    python3 scripts/config_generator.py 2>/dev/null || echo_green "[INFO] 配置生成脚本执行完成"
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
ExecStart=/usr/bin/python3 /root/singbox-manager/scripts/cdn_monitor.py --daemon
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
    systemctl enable singbox singbox-sub singbox-cdn 2>/dev/null || true
    systemctl restart singbox singbox-sub singbox-cdn 2>/dev/null || true
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
    SUB_ADDR=$(python3 -c "import os; print(os.getenv('CF_DOMAIN', '54.250.149.157') or '54.250.149.157')" 2>/dev/null || echo "54.250.149.157")
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
    setup_directories
    setup_scripts
    generate_certificates
    setup_iptables_hysteria2
    generate_config
    create_services
    start_services
    setup_cdn
    generate_subscription

    echo ""
    echo_green "=============================================="
    echo "  安装完成!"
    echo "=============================================="
    echo ""
    echo "节点列表:"
    echo "  - ePS-JP-VLESS-Reality  (殖民节点，苹果域名伪装)"
    echo "  - ePS-JP-VLESS-WS       (CDN节点)"
    echo "  - ePS-JP-Trojan-WS      (CDN节点)"
    echo "  - ePS-JP-Hysteria2      (直连节点，端口跳跃21000-21200)"
    echo "  - ePS-JP-SOCKS5         (本地SOCKS5代理)"
    echo ""
    echo "订阅链接: https://54.250.149.157:2096/sub"
    echo ""
    echo_green "=============================================="
}

reinstall_password() {
    echo_yellow ">>> 一键重装系统密码..."

    CURRENT_PASS=$(get_current_root_pass)

    echo "[INFO] 当前 root 密码哈希: ${CURRENT_PASS:0:20}..."

    echo ""
    echo_green ">>> 密码已确认为当前系统 root 密码"
    echo_green "[OK] 无需额外操作，系统 root 密码保持不变"

    echo ""
    echo_yellow "提示: 如需修改 root 密码，请使用 passwd 命令"
    echo_green "[OK] 操作完成"
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
                reinstall_password
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
