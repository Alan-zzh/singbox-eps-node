#!/bin/bash
# ============================================================
# Singbox EPS Node 一键安装脚本
# 版本: v4.15.0
# 用途: 新VPS全自动部署（含双部署模式+系统优化+CDN优选+流量统计）
# 使用: bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
#
# 【部署模式】
#   - CDN混合模式（推荐）：6节点（4直连+2WS-CDN），抗封锁能力强，需要CF域名
#   - 纯直连模式：4节点（全直连），极简无CDN依赖，IP被封即不可用
#
# 【自动化功能清单】
# 阶段1-系统准备（全自动，无需用户操作）：
#   1. 系统更新：apt upgrade + 语言包 + 时区
#   2. 安装依赖：curl/wget/python3/openssl/sqlite3等
#   3. BBRv3+FQ 网络加速（安装 XanMod BBRv3 内核；首次启用需重启）
#   4. 系统优化：文件描述符+内核参数
# 阶段2-部署服务（交互式配置）：
#   5. 卸载旧面板 → 安装singbox → 部署项目
#   6. 交互式配置：部署模式选择+AI代理+域名
#   7. 生成配置+证书+防火墙
#   8. 启动服务+验证
# ============================================================

set -e

# 非root用户检查 [Trae CN] 2026-06-04
if [ "$EUID" -ne 0 ]; then
    echo "[错误] 此脚本必须以root用户运行"
    exit 1
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

BASE_DIR="/root/singbox-eps-node"
REPO_URL="https://github.com/Alan-zzh/singbox-eps-node"

CF_DEFAULT_DOMAIN="${CF_DOMAIN:-}"
CF_DEFAULT_API_TOKEN="${CF_API_TOKEN:-}"

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${CYAN}>>> $1${NC}"; }

cleanup_broken_xanmod_source() {
    if [ -f /etc/apt/sources.list.d/xanmod-release.list ]; then
        if [ ! -f /etc/apt/keyrings/xanmod-archive-keyring.gpg ] \
            || ! gpg --show-keys /etc/apt/keyrings/xanmod-archive-keyring.gpg >/dev/null 2>&1; then
            log_warn "检测到损坏的 XanMod APT key/source，先清理后重建"
            rm -f /etc/apt/sources.list.d/xanmod-release.list /etc/apt/keyrings/xanmod-archive-keyring.gpg
        fi
    fi
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        log_error "请使用root用户运行此脚本"
        exit 1
    fi
}

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        OS="unknown"
    fi
    if [[ "$OS" != "ubuntu" && "$OS" != "debian" ]]; then
        log_warn "此脚本针对Ubuntu/Debian优化，当前系统: $OS"
        log_warn "继续安装可能需要手动调整部分配置"
    fi
}

update_system() {
    log_step "【阶段1-步骤1/4】更新系统+安装语言包..."
    cleanup_broken_xanmod_source
    log_info "更新软件源..."
    apt-get update -y
    log_info "升级系统已安装的包..."
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
    log_info "安装语言包和基础工具..."
    if [ "$OS" = "ubuntu" ]; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            locales language-pack-en-base language-pack-zh-hans \
            sudo gnupg2 ca-certificates lsb-release
    else
        DEBIAN_FRONTEND=noninteractive apt-get install -y \
            locales sudo gnupg2 ca-certificates lsb-release
    fi
    locale-gen en_US.UTF-8 2>/dev/null || true
    update-locale LANG=en_US.UTF-8 2>/dev/null || true
    timedatectl set-timezone Asia/Shanghai 2>/dev/null || true
    log_info "系统更新完成（apt upgrade + 语言包 + 时区）"
}

install_dependencies() {
    log_step "【阶段1-步骤2/4】安装运行依赖..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
        curl wget unzip python3 python3-pip python3-venv \
        cron iptables-persistent sqlite3 dnsutils openssl \
        net-tools procps iproute2 psmisc
    log_info "运行依赖安装完成"
}

uninstall_old_panels() {
    log_step "检查并卸载旧面板..."
    for panel in x-ui marzban 3x-ui; do
        if systemctl is-active --quiet "$panel" 2>/dev/null; then
            log_warn "检测到 $panel 正在运行，正在卸载..."
            systemctl stop "$panel" 2>/dev/null || true
            systemctl disable "$panel" 2>/dev/null || true
        fi
        rm -f /etc/systemd/system/"$panel".service
        rm -f /etc/systemd/system/multi-user.target.wants/"$panel".service
    done
    for panel_dir in /usr/local/x-ui /usr/local/3x-ui /usr/local/marzban; do
        if [ -d "$panel_dir" ]; then
            rm -rf "$panel_dir"
        fi
    done
    systemctl daemon-reload
    log_info "旧面板卸载完成"
}

set_default_qdisc_cake() {
    # 兼容旧调用名，当前项目基线统一为 FQ。
    set_default_qdisc_fq
}

set_default_qdisc_fq() {
    if grep -q "^net.core.default_qdisc=" /etc/sysctl.conf 2>/dev/null; then
        sed -i 's|^net.core.default_qdisc=.*|net.core.default_qdisc=fq|' /etc/sysctl.conf
    else
        echo "net.core.default_qdisc=fq" >> /etc/sysctl.conf
    fi
}

detect_x86_64_psabi_level() {
    if [ "$(uname -m)" != "x86_64" ]; then
        echo ""
        return
    fi

    local loader
    for loader in /lib64/ld-linux-x86-64.so.2 /lib/x86_64-linux-gnu/ld-linux-x86-64.so.2; do
        if [ -x "$loader" ]; then
            if "$loader" --help 2>/dev/null | grep -q "x86-64-v4 (supported"; then
                echo "x64v4"
                return
            fi
            if "$loader" --help 2>/dev/null | grep -q "x86-64-v3 (supported"; then
                echo "x64v3"
                return
            fi
            if "$loader" --help 2>/dev/null | grep -q "x86-64-v2 (supported"; then
                echo "x64v2"
                return
            fi
        fi
    done

    echo "x64v1"
}

select_xanmod_bbrv3_package() {
    local level
    level="$(detect_x86_64_psabi_level)"
    case "$level" in
        x64v4|x64v3)
            echo "linux-xanmod-lts-x64v3"
            ;;
        x64v2)
            echo "linux-xanmod-lts-x64v2"
            ;;
        x64v1)
            echo "linux-xanmod-lts-x64v1"
            ;;
        *)
            echo ""
            ;;
    esac
}

install_bbrv3_kernel() {
    log_info "加速1/4：安装/确认 BBRv3 内核（XanMod）..."

    if uname -r | grep -qi "xanmod"; then
        log_info "当前已运行 XanMod 内核，按 BBRv3 内核路径处理: $(uname -r)"
        return 0
    fi

    if [ "$(uname -m)" != "x86_64" ]; then
        log_warn "当前架构 $(uname -m) 暂不自动安装 XanMod BBRv3；保留系统 BBR+FQ"
        return 0
    fi

    local pkg
    pkg="$(select_xanmod_bbrv3_package)"
    if [ -z "$pkg" ]; then
        log_warn "无法选择 XanMod BBRv3 包，保留系统 BBR+FQ"
        return 0
    fi

    DEBIAN_FRONTEND=noninteractive apt-get install -y gnupg ca-certificates curl >/dev/null 2>&1 || true
    install -d -m 0755 /etc/apt/keyrings
    if [ -f /etc/apt/keyrings/xanmod-archive-keyring.gpg ] \
        && ! gpg --show-keys /etc/apt/keyrings/xanmod-archive-keyring.gpg >/dev/null 2>&1; then
        rm -f /etc/apt/keyrings/xanmod-archive-keyring.gpg
    fi
    if [ ! -f /etc/apt/keyrings/xanmod-archive-keyring.gpg ]; then
        local key_tmp="/tmp/xanmod-archive.key"
        local xanmod_key_id="86F7D09EE734E623"
        rm -f "$key_tmp"
        if curl -A "Mozilla/5.0" -fsSL https://dl.xanmod.org/archive.key -o "$key_tmp" \
            || wget -qO "$key_tmp" https://dl.xanmod.org/archive.key \
            || curl -A "Mozilla/5.0" -fsSL https://dl.xanmod.org/gpg.key -o "$key_tmp" \
            || wget -qO "$key_tmp" https://dl.xanmod.org/gpg.key; then
            gpg --dearmor --yes --output /etc/apt/keyrings/xanmod-archive-keyring.gpg "$key_tmp"
        else
            log_warn "XanMod key URL 拉取失败，改用 keyserver.ubuntu.com 获取公钥 $xanmod_key_id"
            GNUPGHOME="$(mktemp -d)"
            export GNUPGHOME
            gpg --batch --keyserver hkps://keyserver.ubuntu.com --recv-keys "$xanmod_key_id"
            gpg --batch --export "$xanmod_key_id" | gpg --dearmor --yes --output /etc/apt/keyrings/xanmod-archive-keyring.gpg
            rm -rf "$GNUPGHOME"
            unset GNUPGHOME
        fi
        rm -f "$key_tmp"
    fi
    if ! gpg --show-keys --with-colons /etc/apt/keyrings/xanmod-archive-keyring.gpg 2>/dev/null | grep -q "86F7D09EE734E623"; then
        log_error "XanMod APT key 校验失败，无法安全安装 BBRv3 内核"
        return 1
    fi
    local codename
    codename="$(lsb_release -sc 2>/dev/null || true)"
    if [ -z "$codename" ] && [ -f /etc/os-release ]; then
        . /etc/os-release
        codename="${VERSION_CODENAME:-}"
    fi
    codename=${codename:-bookworm}
    echo "deb [signed-by=/etc/apt/keyrings/xanmod-archive-keyring.gpg] http://deb.xanmod.org ${codename} main" > /etc/apt/sources.list.d/xanmod-release.list

    apt-get update -y
    if DEBIAN_FRONTEND=noninteractive apt-get install -y "$pkg"; then
        log_info "BBRv3 内核包已安装: $pkg"
        if ! uname -r | grep -qi "xanmod"; then
            touch /var/run/reboot-required 2>/dev/null || true
            log_warn "BBRv3 内核已安装但尚未运行；需要重启后生效。当前内核: $(uname -r)"
        fi
    else
        log_warn "安装 $pkg 失败，保留系统 BBR+FQ"
    fi
}

setup_fq_qdisc() {
    local iface="${1:-$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)}"
    iface=${iface:-eth0}

    set_default_qdisc_fq

    if ! command -v tc &>/dev/null; then
        log_warn "tc命令不可用，仅设置sysctl默认队列"
        return
    fi

    FQ_OK=false
    tc qdisc replace dev "$iface" root fq 2>/dev/null && FQ_OK=true || true

    if [ "$FQ_OK" = true ]; then
        log_info "FQ队列已应用到 $iface（BBR推荐组合）"
    else
        log_warn "FQ应用失败，仅设置sysctl默认队列"
        return
    fi

    rm -f /etc/systemd/system/fq-pie-qdisc.service "/etc/systemd/system/fq-pie-qdisc@${iface}.service" 2>/dev/null || true

    cat > /etc/systemd/system/fq-qdisc@.service << 'EOF'
[Unit]
Description=FQ Queue Discipline (BBR推荐组合)
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/tc qdisc replace dev %i root fq
ExecStop=/sbin/tc qdisc del dev %i root 2>/dev/null || true

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload 2>/dev/null || true
    systemctl disable "fq-pie-qdisc@${iface}" 2>/dev/null || true
    systemctl enable "fq-qdisc@${iface}" 2>/dev/null || true
    log_info "FQ持久化服务已创建（fq-qdisc@$iface，重启自动恢复）"
}

optimize_system() {
    log_step "【阶段1-步骤3/4】启用BBRv3+FQ网络加速..."

    install_bbrv3_kernel

    if ! sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        log_info "加速2/4：启用BBR拥塞控制（XanMod 内核重启后为 BBRv3）..."
        grep -q "^net.ipv4.tcp_congestion_control=bbr" /etc/sysctl.conf 2>/dev/null || echo "net.ipv4.tcp_congestion_control=bbr" >> /etc/sysctl.conf
    else
        log_info "加速2/4：BBR已启用，跳过"
    fi

    log_info "加速3/4：启用FQ公平队列（为每个TCP连接独立缓冲，BBR pacing 依赖FQ）..."
    set_default_qdisc_fq

    log_info "加速4/4：固化网卡FQ队列（避免旧qdisc残留覆盖当前基线）..."
    setup_fq_qdisc

    log_info "TCP调优（缓冲区+连接队列+保活+BBR高丢包参数）..."
    TCP_PARAMS="net.ipv4.tcp_fastopen=3
net.ipv4.tcp_tw_reuse=1
net.ipv4.ip_local_port_range=1024 65535
net.ipv4.tcp_max_syn_backlog=65536
net.core.somaxconn=65536
net.core.netdev_max_backlog=65536
net.ipv4.tcp_rmem=4096 87380 67108864
net.ipv4.tcp_wmem=4096 65536 67108864
net.ipv4.tcp_mtu_probing=1
net.ipv4.tcp_keepalive_time=30
net.ipv4.tcp_keepalive_intvl=10
net.ipv4.tcp_keepalive_probes=3
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_bbr_min_rtt_win_sec=60
net.ipv4.tcp_no_metrics_save=1
net.ipv4.tcp_sack=1
net.ipv4.tcp_max_tw_buckets=5000
net.core.rmem_default=2097152
net.core.wmem_default=2097152
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.core.optmem_max=65536
net.ipv4.udp_mem=65536 131072 262144
net.ipv4.tcp_fastopen_blackhole_timeout_sec=0"
    echo "$TCP_PARAMS" | while IFS='=' read -r key value; do
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | xargs)
        if [ -n "$key" ] && [ -n "$value" ]; then
            if grep -q "^${key}=" /etc/sysctl.conf 2>/dev/null; then
                sed -i "s|^${key}=.*|${key}=${value}|" /etc/sysctl.conf
            else
                echo "${key}=${value}" >> /etc/sysctl.conf
            fi
        fi
    done

    sysctl -p 2>/dev/null || true
    if uname -r | grep -qi "xanmod"; then
        log_info "BBRv3+FQ网络加速已启用（当前运行 XanMod 内核: $(uname -r)）"
    else
        log_warn "BBR+FQ参数已启用；BBRv3 内核需重启后生效（当前内核: $(uname -r)）"
    fi

    # ============ 新增：内存与系统服务优化 ============
    log_info "【系统优化】限制 journald 日志大小（防止日志堆积占满磁盘/内存）..."
    mkdir -p /etc/systemd/journald.conf.d
    cat > /etc/systemd/journald.conf.d/size-limit.conf << 'JEOF'
[Journal]
SystemMaxUse=50M
RuntimeMaxUse=20M
MaxRetentionSec=7day
Compress=yes
JEOF
    journalctl --vacuum-size=50M 2>/dev/null || true
    systemctl restart systemd-journald 2>/dev/null || true
    log_info "journald 日志限制为 50MB（永久生效，自动轮转覆盖）"

    log_info "【系统优化】禁用不必要的系统服务（释放 ~30MB 内存）..."
    for svc in networkd-dispatcher irqbalance apport apparmor rsyslog; do
        if systemctl is-enabled "$svc" 2>/dev/null | grep -q enabled; then
            systemctl stop "$svc" 2>/dev/null || true
            systemctl disable "$svc" 2>/dev/null || true
            log_info "  已禁用: $svc"
        fi
    done

    log_info "【系统优化】启用 systemd 服务启动前端口清理..."
    # 确保 singbox-sub.service 有 ExecStartPre 端口清理（在 setup_subscription_service 中添加）
    # 这里只做通用优化：限制 conntrack 超时
    grep -q "^net.netfilter.nf_conntrack_tcp_timeout_established=" /etc/sysctl.conf 2>/dev/null || \
        echo "net.netfilter.nf_conntrack_tcp_timeout_established=432000" >> /etc/sysctl.conf
    grep -q "^nf_conntrack_max=" /etc/sysctl.conf 2>/dev/null || \
        echo "net.netfilter.nf_conntrack_max=1048576" >> /etc/sysctl.conf
    sysctl -p 2>/dev/null || true
    log_info "conntrack 连接跟踪已优化（支持 100 万并发连接）"
    # ============ 优化结束 ============

    if ! grep -q "65535" /etc/security/limits.conf 2>/dev/null; then
        log_info "【阶段1-步骤4/4】提升文件描述符限制到65535..."
        cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
root soft nofile 65535
root hard nofile 65535
EOF
    fi

    log_info "阶段1完成：系统更新+依赖+BBRv3+FQ+优化（BBRv3 内核首次启用需重启）"
}

setup_cake_qdisc() {
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1) || true
    MAIN_IF=${MAIN_IF:-eth0}
    log_warn "setup_cake_qdisc 已退役，当前统一改为 FQ 基线"
    setup_fq_qdisc "$MAIN_IF"
}

install_singbox() {
    log_step "安装 Singbox 内核..."
    if command -v singbox &>/dev/null; then
        CURRENT_VER=$(singbox version 2>/dev/null | head -1 || echo '未知版本')
        log_info "检测到 Singbox 已安装: $CURRENT_VER"
        echo ""
        echo -e "  ${YELLOW}Singbox 已安装，请选择操作：${NC}"
        echo -e "  1) 卸载重装（清除所有数据：配置/证书/流量记录/服务，全新安装）"
        echo -e "  2) 保留当前版本（默认，直接继续）"
        echo ""
        read -p "  请输入选择 [1/2]（默认2）: " SINGBOX_CHOICE
        SINGBOX_CHOICE=${SINGBOX_CHOICE:-2}

        if [ "$SINGBOX_CHOICE" = "1" ]; then
            log_info "卸载当前 Singbox 及所有关联数据（保留密码和密钥）..."
            mkdir -p "${BASE_DIR}/.backup"
            chmod 700 "${BASE_DIR}/.backup"
            PASSWORD_BACKUP="${BASE_DIR}/.backup/passwords_backup.env"
            > "$PASSWORD_BACKUP"
            chmod 600 "$PASSWORD_BACKUP"
            if [ -f "$BASE_DIR/.env" ]; then
                for FIELD in VLESS_UUID VLESS_WS_UUID TROJAN_PASSWORD TUIC_PASSWORD ANYTLS_PASSWORD \
                             REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY REALITY_SHORT_ID \
                             COUNTRY_CODE DEPLOY_MODE \
                             CF_DOMAIN CF_API_TOKEN AI_SOCKS5_SERVER AI_SOCKS5_PORT \
                             AI_SOCKS5_USER AI_SOCKS5_PASS AI_SOCKS5_ROUTING SERVER_IP SUB_TOKEN TG_BOT_TOKEN \
                             TG_ADMIN_CHAT_ID WARP_UNLOCK WARP_PRIVATE_KEY WARP_PEER_PUBLIC_KEY \
                             WARP_PEER_ENDPOINT WARP_CLIENT_IPV4 WARP_CLIENT_IPV6 WARP_RESERVED \
                             ENABLE_TUIC; do
                    VALUE=$(grep "^${FIELD}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
                    if [ -n "$VALUE" ]; then
                        echo "${FIELD}=${VALUE}" >> "$PASSWORD_BACKUP"
                    fi
                done
                log_info "密码和密钥已备份到 ${PASSWORD_BACKUP}"
            fi
            systemctl stop singbox singbox-sub singbox-cdn 2>/dev/null || true
            systemctl disable singbox singbox-sub singbox-cdn 2>/dev/null || true
            rm -f /etc/systemd/system/singbox.service
            rm -f /etc/systemd/system/singbox-sub.service
            rm -f /etc/systemd/system/singbox-cdn.service
            systemctl daemon-reload 2>/dev/null || true
            rm -f /usr/local/bin/singbox
            if [ -d "$BASE_DIR" ]; then
                log_info "删除项目目录 $BASE_DIR（配置/证书/流量记录/日志全部清除）..."
                rm -rf "$BASE_DIR"
            fi
            crontab -l 2>/dev/null | grep -v "health_check.sh" | grep -v "cert_manager.py" | crontab - 2>/dev/null || true
            iptables -D INPUT -p udp --dport 21000:21200 -j ACCEPT 2>/dev/null || true
            iptables -D INPUT -p tcp --dport 21000:21200 -j ACCEPT 2>/dev/null || true
            netfilter-persistent save 2>/dev/null || true
            log_info "已完全卸载（二进制+配置+数据+证书+服务+定时任务+防火墙规则全部清除）"
            log_info "密码和密钥已备份，安装时将自动恢复"
            log_info "开始全新安装..."
        else
            log_info "保留当前 Singbox: $CURRENT_VER"
            return
        fi
    fi

    ARCH=$(uname -m)
    case $ARCH in
        x86_64)  SINGBOX_ARCH="amd64" ;;
        aarch64) SINGBOX_ARCH="arm64" ;;
        *)       log_error "不支持的架构: $ARCH"; exit 1 ;;
    esac

    SINGBOX_VER="1.13.13"
    SINGBOX_URL="https://github.com/SagerNet/sing-box/releases/download/v${SINGBOX_VER}/sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}.tar.gz"
    log_info "下载 Singbox v${SINGBOX_VER} (${SINGBOX_ARCH})..."
    cd /tmp
    if ! wget -q "$SINGBOX_URL" -O singbox.tar.gz; then
        log_error "下载 Singbox v${SINGBOX_VER} 失败: $SINGBOX_URL"
        exit 1
    fi
    tar -xzf singbox.tar.gz
    cp "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}/sing-box" /usr/local/bin/sing-box
    chmod +x /usr/local/bin/sing-box
    ln -sf /usr/local/bin/sing-box /usr/local/bin/singbox
    rm -rf singbox.tar.gz "sing-box-${SINGBOX_VER}-linux-${SINGBOX_ARCH}"
    log_info "Singbox 安装完成: $(sing-box version | head -1)"
}

clone_repo() {
    log_step "部署项目文件..."
    if [ -d "$BASE_DIR" ]; then
        log_warn "$BASE_DIR 已存在，备份后重新部署..."
        mv "$BASE_DIR" "${BASE_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    if command -v git &>/dev/null; then
        git clone "$REPO_URL" "$BASE_DIR"
    else
        apt-get install -y git
        git clone "$REPO_URL" "$BASE_DIR"
    fi
    mkdir -p "$BASE_DIR/logs" "$BASE_DIR/data" "$BASE_DIR/cert" "$BASE_DIR/backups"
    log_info "目录结构已创建（logs/data/cert/backups）"
}

setup_python_env() {
    log_step "配置Python环境..."
    cd "$BASE_DIR"
    pip3 install --break-system-packages --quiet flask python-dotenv pyyaml 2>/dev/null || pip3 install --quiet flask python-dotenv pyyaml 2>/dev/null || apt-get install -y -qq python3-flask python3-dotenv python3-yaml 2>/dev/null || echo "[警告] pip安装flask/python-dotenv/pyyaml失败，部分功能可能异常"
    # 安装gevent（优先apt，降级pip）[Trae CN] 2026-06-04
    apt-get install -y -qq python3-gevent 2>/dev/null || \
        pip3 install --break-system-packages --quiet gevent 2>/dev/null || \
        pip3 install --quiet gevent 2>/dev/null || \
        echo "[警告] gevent安装失败，订阅服务将使用Flask开发服务器"
    log_info "Python依赖已安装（flask + python-dotenv + pyyaml + gevent）"
}

generate_uuids_and_passwords() {
    log_step "生成协议密码和UUID..."
    # v4.15.8: 使用 root 私有目录替代 /tmp，避免凭据泄露
    PASSWORD_BACKUP="${BASE_DIR}/.backup/passwords_backup.env"
    mkdir -p "${BASE_DIR}/.backup"
    chmod 700 "${BASE_DIR}/.backup"
    if [ -f "$PASSWORD_BACKUP" ]; then
        log_info "检测到密码备份，恢复旧密码（客户端无需重新配置）..."
        while IFS='=' read -r key value; do
            case "$key" in
                VLESS_UUID) VLESS_UUID="$value" ;;
                VLESS_WS_UUID) VLESS_WS_UUID="$value" ;;
                TROJAN_PASSWORD) TROJAN_PASSWORD="$value" ;;
                TUIC_PASSWORD) TUIC_PASSWORD="$value" ;;
                TUIC_UUID) TUIC_UUID="$value" ;;
                ANYTLS_PASSWORD) ANYTLS_PASSWORD="$value" ;;
                REALITY_SHORT_ID) REALITY_SHORT_ID="$value" ;;
                COUNTRY_CODE) COUNTRY_CODE="$value" ;;
                DEPLOY_MODE) DEPLOY_MODE="$value" ;;
            esac
        done < "$PASSWORD_BACKUP"
        chmod 600 "$PASSWORD_BACKUP"
        log_info "密码已从备份恢复"
    fi
    VLESS_UUID=${VLESS_UUID:-$(python3 -c "import uuid; print(uuid.uuid4())")}
    VLESS_WS_UUID=${VLESS_WS_UUID:-$(python3 -c "import uuid; print(uuid.uuid4())")}
    TROJAN_PASSWORD=${TROJAN_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_hex(16))")}
    TUIC_PASSWORD=${TUIC_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_hex(32))")}
    TUIC_UUID=${TUIC_UUID:-$(python3 -c "import uuid; print(uuid.uuid4())")}
    # v4.14.0 新增：anyTLS 协议密码（独立于 TROJAN_PASSWORD，向后兼容）
    ANYTLS_PASSWORD=${ANYTLS_PASSWORD:-$(python3 -c "import secrets; print(secrets.token_hex(16))")}
    # v4.15.8: REALITY_SHORT_ID（若 .env 已有则保留，否则生成随机值）
    REALITY_SHORT_ID=${REALITY_SHORT_ID:-$(python3 -c "import secrets; print(secrets.token_hex(8))")}
    # 随机端口生成（10000-65535 之间，避免常用端口）
    TROJAN_TCP_PORT=${TROJAN_TCP_PORT:-$(python3 -c "import secrets; print(secrets.randbelow(55536) + 10000)")}
    TUIC_PORT=${TUIC_PORT:-$(python3 -c "import secrets; print(secrets.randbelow(55536) + 10000)")}
    # v4.15.8: VLESS_GRPC_PORT 已删除（v4.15.0 移除 gRPC 协议），不再生成
    # 尝试多次获取 SERVER_IP（DNS/网络刚初始化可能失败）
    SERVER_IP=""
    for _ in 1 2 3; do
        SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "")
        [ -n "$SERVER_IP" ] && break
        sleep 2
    done
    # EC2 环境兜底（169.254.169.254 是 AWS 实例元数据端点）
    if [ -z "$SERVER_IP" ]; then
        SERVER_IP=$(curl -s --connect-timeout 3 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    fi
    if [ -n "$SERVER_IP" ]; then
        COUNTRY_CODE=$(curl -s --connect-timeout 5 "https://ipinfo.io/${SERVER_IP}/country" 2>/dev/null | tr -d '[:space:]' || echo "")
    fi
    COUNTRY_CODE=${COUNTRY_CODE:-US}
    if [ -z "$SERVER_IP" ]; then
        log_error "无法检测服务器 IP，请确保网络连通后手动设置 .env 中的 SERVER_IP"
        log_error "订阅链接将生成空地址导致全部节点不可用"
    fi
    log_info "服务器IP: ${SERVER_IP:-未检测到}，国家代码: ${COUNTRY_CODE}"
    log_info "UUID和密码已生成"
    log_info "Trojan-TCP端口: ${TROJAN_TCP_PORT}，TUIC端口: ${TUIC_PORT}，anyTLS端口: 2096"
}

generate_reality_keys() {
    log_step "生成Reality密钥对..."
    PASSWORD_BACKUP="${BASE_DIR}/.backup/passwords_backup.env"
    if [ -f "$PASSWORD_BACKUP" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                REALITY_PRIVATE_KEY) REALITY_PRIVATE_KEY="$value" ;;
                REALITY_PUBLIC_KEY) REALITY_PUBLIC_KEY="$value" ;;
                REALITY_SHORT_ID) REALITY_SHORT_ID="$value" ;;
            esac
        done < "$PASSWORD_BACKUP"
    fi
    if [ -z "$REALITY_PRIVATE_KEY" ] || [ -z "$REALITY_PUBLIC_KEY" ]; then
        REALITY_OUTPUT=$(singbox generate reality-keypair 2>/dev/null)
        REALITY_PRIVATE_KEY=$(echo "$REALITY_OUTPUT" | grep "PrivateKey" | awk '{print $2}')
        REALITY_PUBLIC_KEY=$(echo "$REALITY_OUTPUT" | grep "PublicKey" | awk '{print $2}')
    fi
    if [ -z "$REALITY_PRIVATE_KEY" ] || [ -z "$REALITY_PUBLIC_KEY" ]; then
        log_error "Reality 密钥对生成失败！安装中止。"
        log_error "请检查 sing-box 是否正确安装: 'singbox version'"
        exit 1
    fi
    # 校验密钥是否为合法 base64（长度约 44，不能是占位符）
    _pbk_len=${#REALITY_PUBLIC_KEY}
    if [ "$_pbk_len" -lt 40 ] || echo "$REALITY_PUBLIC_KEY" | grep -qi "placeholder"; then
        log_error "Reality 公钥格式异常（长度=$_pbk_len），安装中止"
        exit 1
    fi
    log_info "Reality密钥对已生成"
    log_info "Reality Short ID: ${REALITY_SHORT_ID:-（将由 generate_uuids_and_passwords 生成）}"
}

select_deploy_mode() {
    # v4.15.2 铁律：HK1 香港阿里云（域名 hk1.* ）必须直连模式，禁止 CDN
    # HK（hk.*）和 HK1（hk1.*）地理都在香港，COUNTRY_CODE 无法区分，只能靠域名前缀
    _hk1_domain=""
    if [ -n "${CF_DOMAIN:-}" ]; then
        _hk1_domain="$CF_DOMAIN"
    elif [ -f "$BASE_DIR/.env" ]; then
        _hk1_domain=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
    fi
    if [ -n "$_hk1_domain" ] && echo "$_hk1_domain" | grep -qi '^hk1\.'; then
        log_info "检测到 HK1 香港阿里云域名 ($_hk1_domain)，强制使用纯直连模式（4节点，无CDN依赖）"
        DEPLOY_MODE="direct"
        return
    fi

    # 如果已从备份恢复 DEPLOY_MODE，或已有 .env 中存在 DEPLOY_MODE，直接使用旧值不询问
    if [ -n "$DEPLOY_MODE" ]; then
        if [ "$DEPLOY_MODE" = "direct" ]; then
            log_info "检测到已有部署模式：纯直连模式（4节点精简，无CDN依赖）"
        else
            DEPLOY_MODE="cdn"
            log_info "检测到已有部署模式：CDN混合模式（6节点全量，推荐）"
        fi
        return
    fi
    if [ -f "$BASE_DIR/.env" ]; then
        OLD_DEPLOY_MODE=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        if [ -n "$OLD_DEPLOY_MODE" ]; then
            DEPLOY_MODE="$OLD_DEPLOY_MODE"
            if [ "$DEPLOY_MODE" = "direct" ]; then
                log_info "从已有配置读取部署模式：纯直连模式（4节点精简，无CDN依赖）"
            else
                DEPLOY_MODE="cdn"
                log_info "从已有配置读取部署模式：CDN混合模式（6节点全量，推荐）"
            fi
            return
        fi
    fi
    if [ "${AUTO_YES:-0}" = "1" ]; then
        DEPLOY_MODE="cdn"
        log_info "非交互模式，默认选择：CDN混合模式（6节点全量，推荐）"
        return
    fi
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  🚀 选择部署模式${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  ${GREEN}1) CDN混合模式（推荐）${NC} - 6节点（4直连+2WS-CDN），抗封锁能力强，需要CF域名"
    echo -e "  ${YELLOW}2) 纯直连模式${NC}        - 4节点（全直连），极简无CDN依赖，IP被封即不可用"
    echo ""
    read -p "  请选择部署模式 [1/2]（默认1）: " DEPLOY_MODE_CHOICE
    DEPLOY_MODE_CHOICE=${DEPLOY_MODE_CHOICE:-1}
    if [ "$DEPLOY_MODE_CHOICE" = "2" ]; then
        DEPLOY_MODE="direct"
        log_info "已选择：纯直连模式（4节点精简，无CDN依赖）"
    else
        DEPLOY_MODE="cdn"
        log_info "已选择：CDN混合模式（6节点全量，推荐）"
    fi
}

create_env_file() {
    log_step "创建.env配置文件..."
    SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "")
    # 确保 DEPLOY_MODE 有值（向后兼容：旧版本无此字段时默认cdn）
    DEPLOY_MODE=${DEPLOY_MODE:-cdn}
    AI_SOCKS5_SERVER=""
    AI_SOCKS5_PORT=""
    AI_SOCKS5_USER=""
    AI_SOCKS5_PASS=""
    AI_SOCKS5_ROUTING="off"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  AI住宅代理配置（可选）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  配置后，AI网站（ChatGPT/Claude/Gemini等）流量自动走SOCKS5代理"
    echo -e "  X/推特/groK不走代理，直连"
    echo -e "  如果没有代理节点，直接回车跳过即可"
    echo ""
    read -p "  是否配置AI住宅代理？(y/N): " SETUP_AI
    if [[ "$SETUP_AI" =~ ^[Yy]$ ]]; then
        read -p "  SOCKS5服务器地址: " AI_SOCKS5_SERVER
        read -p "  SOCKS5端口: " AI_SOCKS5_PORT
        read -p "  SOCKS5用户名: " AI_SOCKS5_USER
        read -p "  SOCKS5密码: " AI_SOCKS5_PASS
        if [ -n "$AI_SOCKS5_SERVER" ] && [ -n "$AI_SOCKS5_PORT" ]; then
            log_info "AI住宅代理已配置: ${AI_SOCKS5_SERVER}:${AI_SOCKS5_PORT}"
            read -p "  是否开启AI路由？(y/N): " ENABLE_AI_ROUTING
            if [[ "$ENABLE_AI_ROUTING" =~ ^[Yy]$ ]]; then
                AI_SOCKS5_ROUTING="on"
                log_info "AI路由已开启"
            else
                AI_SOCKS5_ROUTING="off"
                log_info "AI路由已关闭（代理配置保留，但不启用路由）"
            fi
        else
            log_warn "SOCKS5地址或端口为空，跳过AI代理配置"
            AI_SOCKS5_SERVER=""
            AI_SOCKS5_PORT=""
            AI_SOCKS5_USER=""
            AI_SOCKS5_PASS=""
        fi
    else
        log_info "跳过AI住宅代理配置（后续可手动编辑.env）"
    fi
    WARP_UNLOCK="off"
    if [ "${AUTO_YES:-0}" != "1" ]; then
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}  🚀 Cloudflare WARP DNS解锁（AI+流媒体，零成本）${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "  方案: sing-box内置WireGuard直连Cloudflare WARP，零额外进程"
        echo -e "  解锁: OpenAI/ChatGPT/Gemini/Claude/TikTok/Netflix"
        echo -e "  直连: X/Twitter/Google/YouTube/其他所有网站（不影响速度）"
        echo -e "  成本: 完全免费，无需额外VPS或代理"
        echo ""
        read -p "  是否启用WARP DNS解锁？(y/N): " SETUP_WARP
        if [[ "$SETUP_WARP" =~ ^[Yy]$ ]]; then
            WARP_UNLOCK="on"
            log_info "WARP解锁已启用，安装完成后将自动配置"
        else
            log_info "跳过WARP解锁配置（后续可运行 bash install.sh warp-unlock 单独安装）"
        fi
    fi
    # v4.5 用户DDNS锚点配置
    if [ "${AUTO_YES:-0}" != "1" ]; then
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo -e "${CYAN}  用户DDNS域名配置（v4.5 区域化CDN优选）${NC}"
        echo -e "${CYAN}  提供DDNS域名后，服务器可感知你的网络位置和质量${NC}"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        read -p "  用户DDNS域名（留空跳过）: " USER_DDNS_DOMAIN
        if [ -n "$USER_DDNS_DOMAIN" ]; then
            read -p "  用户预期运营商（默认：电信）: " USER_EXPECTED_ISP
            USER_EXPECTED_ISP=${USER_EXPECTED_ISP:-电信}
            log_info "DDNS锚点已配置: ${USER_DDNS_DOMAIN} (${USER_EXPECTED_ISP})"
        else
            USER_DDNS_DOMAIN=""
            USER_EXPECTED_ISP="电信"
        fi
    fi
    CF_DOMAIN_INPUT="${CF_DEFAULT_DOMAIN}"
    CF_API_TOKEN_INPUT="${CF_DEFAULT_API_TOKEN}"
    if [ -f "$BASE_DIR/.env" ]; then
        OLD_CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        OLD_CF_TOKEN=$(grep "^CF_API_TOKEN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
        [ -n "$OLD_CF_DOMAIN" ] && CF_DOMAIN_INPUT="$OLD_CF_DOMAIN"
        [ -n "$OLD_CF_TOKEN" ] && CF_API_TOKEN_INPUT="$OLD_CF_TOKEN"
    fi
    if [ -z "$CF_DOMAIN_INPUT" ] && [ "${AUTO_YES:-0}" != "1" ]; then
        echo ""
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        if [ "$DEPLOY_MODE" = "direct" ]; then
            echo -e "${CYAN}  域名配置（直连模式下可选）${NC}"
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            echo -e "  直连模式下域名可选，无域名则使用自签名证书"
            read -p "  域名（留空使用IP+自签名证书）: " CF_DOMAIN_INPUT
        else
            echo -e "${CYAN}  Cloudflare 域名配置（推荐配置，用于CDN和SSL证书）${NC}"
            echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
            read -p "  Cloudflare域名（留空跳过）: " CF_DOMAIN_INPUT
        fi
        if [ -n "$CF_DOMAIN_INPUT" ]; then
            read -p "  Cloudflare API Token（留空则使用自签名证书）: " CF_API_TOKEN_INPUT
        fi
    fi
    # v4.15.2 铁律：HK1 香港阿里云（域名 hk1.* ）必须直连模式，二次确认防止用户选错
    if [ -n "$CF_DOMAIN_INPUT" ] && echo "$CF_DOMAIN_INPUT" | grep -qi '^hk1\.'; then
        if [ "$DEPLOY_MODE" != "direct" ]; then
            log_warn "检测到 HK1 香港阿里云域名 ($CF_DOMAIN_INPUT)，强制切换为纯直连模式（HK1 禁用 CDN）"
            DEPLOY_MODE="direct"
        else
            log_info "已确认 HK1 香港阿里云域名 ($CF_DOMAIN_INPUT) 使用纯直连模式"
        fi
    fi
    log_info "CF_DOMAIN: ${CF_DOMAIN_INPUT}"
    log_info "CF_API_TOKEN: ${CF_API_TOKEN_INPUT:0:8}..."
    # v4.15.13 防复发:基于 CF_DOMAIN 前缀推导正确的 COUNTRY_CODE(服务器标识)
    # 根因:ipinfo.io 返回 ISO 国家代码(如 HK),但项目 COUNTRY_CODE 是服务器标识(JP/HK/HK1/HKCEPIN)
    # HKCEPIN/HK1 服务器都在香港→ipinfo 返回 HK,但项目需要 HKCEPIN/HK1
    # 历史故障:v4.15.x 部署 HKCEPIN/HK1 时 COUNTRY_CODE=HK 导致订阅路由 /clash/HKCEPIN 返回 404
    if [ -n "$CF_DOMAIN_INPUT" ]; then
        case "$CF_DOMAIN_INPUT" in
            jp.*)       COUNTRY_CODE="JP" ;;
            hk1.*)      COUNTRY_CODE="HK1" ;;
            hkcepin.*)  COUNTRY_CODE="HKCEPIN" ;;
            hk.*)       COUNTRY_CODE="HK" ;;
            *)          log_warn "未知 CF_DOMAIN 前缀($CF_DOMAIN_INPUT),COUNTRY_CODE 保持自动检测值: $COUNTRY_CODE" ;;
        esac
        log_info "基于域名前缀修正 COUNTRY_CODE: $COUNTRY_CODE (原 ipinfo 值已覆盖)"
    fi
    cat > "$BASE_DIR/.env" << EOF
# Singbox EPS Node 环境变量配置
# 由安装脚本自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

# ============ 部署模式 ============
# cdn: CDN混合模式（6节点，推荐）；direct: 纯直连模式（4节点，无CDN依赖）
DEPLOY_MODE=${DEPLOY_MODE}

# ============ 必填 ============
SERVER_IP=${SERVER_IP}
CF_DOMAIN=${CF_DOMAIN_INPUT}

# ============ 协议凭据 ============
VLESS_UUID=${VLESS_UUID}
VLESS_WS_UUID=${VLESS_WS_UUID}
TROJAN_PASSWORD=${TROJAN_PASSWORD}
TUIC_PASSWORD=${TUIC_PASSWORD}
TUIC_UUID=${TUIC_UUID}
# v4.15.0: TUIC v5 加回（用户要求 TCP+UDP 双协议支持），默认开启
ENABLE_TUIC=true
# v4.14.0 新增：anyTLS 协议密码（独立于 TROJAN_PASSWORD）
ANYTLS_PASSWORD=${ANYTLS_PASSWORD}
REALITY_PRIVATE_KEY=${REALITY_PRIVATE_KEY}
REALITY_PUBLIC_KEY=${REALITY_PUBLIC_KEY}
# v4.15.8: Reality short_id（持久化写入，确保服务端与订阅端使用同一 short_id）
# 若缺失会导致 Reality 连接失败（config_generator.py 与 subscription_service.py 各自生成随机值）
REALITY_SHORT_ID=${REALITY_SHORT_ID}

# ============ 协议端口（直连协议随机生成，避免被封）=========
# v4.15.8: VLESS_GRPC_PORT 已删除（v4.15.0 移除 gRPC 协议）
TROJAN_TCP_PORT=${TROJAN_TCP_PORT}
TUIC_PORT=${TUIC_PORT}
# v4.14.0 新增：anyTLS 端口（固定 2096，CF CDN 支持端口）
ANYTLS_PORT=2096

# ============ 可选 ============
CF_API_TOKEN=${CF_API_TOKEN_INPUT}
COUNTRY_CODE=${COUNTRY_CODE}
SUB_TOKEN=
AI_SOCKS5_SERVER=${AI_SOCKS5_SERVER}
AI_SOCKS5_PORT=${AI_SOCKS5_PORT}
AI_SOCKS5_USER=${AI_SOCKS5_USER}
AI_SOCKS5_PASS=${AI_SOCKS5_PASS}
AI_SOCKS5_ROUTING=${AI_SOCKS5_ROUTING}
TG_BOT_TOKEN=
TG_ADMIN_CHAT_ID=

# ============ 用户DDNS锚点（v4.5 区域化CDN优选）============
USER_DDNS_DOMAIN=${USER_DDNS_DOMAIN}
USER_EXPECTED_ISP=${USER_EXPECTED_ISP:-电信}
USER_PROBE_INTERVAL=300
USER_LATENCY_SPIKE_THRESHOLD=0.5

# ============ Cloudflare WARP DNS解锁（v4.13 AI+流媒体零成本解锁）============
WARP_UNLOCK=${WARP_UNLOCK}
WARP_PRIVATE_KEY=
WARP_PEER_PUBLIC_KEY=bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=
WARP_PEER_ENDPOINT=162.159.193.10:2408
WARP_CLIENT_IPV4=
WARP_CLIENT_IPV6=
WARP_RESERVED=
EOF
    chmod 600 "$BASE_DIR/.env"
    # v4.15.8: 验证关键变量不为空
    _CRITICAL_VARS="SERVER_IP VLESS_UUID TROJAN_PASSWORD REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY REALITY_SHORT_ID ANYTLS_PASSWORD"
    _VALIDATION_FAILED=false
    for _var in $_CRITICAL_VARS; do
        _val=$(grep "^${_var}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
        if [ -z "$_val" ]; then
            log_warn ".env 中 $_var 为空，可能导致协议功能异常"
            _VALIDATION_FAILED=true
        fi
    done
    if [ "$_VALIDATION_FAILED" = "true" ]; then
        log_warn ".env 存在空值变量，请检查后手动填充"
    fi
    log_info ".env 已创建 (服务器IP: ${SERVER_IP:-未检测到，请手动填写})"
}

generate_config() {
    log_step "生成Singbox配置..."
    cd "$BASE_DIR"
    python3 scripts/config_generator.py
}

setup_certificate() {
    log_step "配置SSL证书..."
    cd "$BASE_DIR"
    python3 scripts/cert_manager.py --cf-cert || python3 scripts/cert_manager.py
}

# v4.15.8: setup_tuic_firewall 已合并到 setup_iptables_traffic_counter
# 保留空函数作为兼容桩（防止旧 cmd_reset 调用报错）
setup_tuic_firewall() {
    log_info "setup_tuic_firewall 已弃用，规则在 setup_iptables_traffic_counter 中统一管理"
}

create_systemd_services() {
    log_step "创建Systemd服务..."
    cat > /etc/systemd/system/singbox.service << EOF
[Unit]
Description=Singbox Proxy Service
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=/usr/local/bin/sing-box run -c ${BASE_DIR}/config.json
Restart=on-failure
RestartSec=5s
LimitNOFILE=65535
MemoryMin=64M
Environment=GOMEMLIMIT=128MiB

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/singbox-sub.service << EOF
[Unit]
Description=Singbox Subscription Service (含流量统计)
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=/usr/bin/python3 ${BASE_DIR}/scripts/subscription_service.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
MemoryMin=32M
Environment=GOMEMLIMIT=80MiB

[Install]
WantedBy=multi-user.target
EOF
    cat > /etc/systemd/system/singbox-cdn.service << EOF
[Unit]
Description=Singbox CDN Monitor Service (多源聚合评分排序)
After=network.target singbox.service

[Service]
Type=simple
WorkingDirectory=${BASE_DIR}
ExecStart=/usr/bin/python3 ${BASE_DIR}/scripts/cdn_monitor.py --daemon
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
MemoryMin=32M
Environment=GOMEMLIMIT=80MiB

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    log_info "Systemd服务已创建"
}

setup_firewall() {
    log_step "配置防火墙（默认全放行）..."
    iptables -P INPUT ACCEPT
    iptables -P FORWARD ACCEPT
    iptables -P OUTPUT ACCEPT
    iptables -F
    netfilter-persistent save 2>/dev/null || true
    log_info "防火墙已配置为全放行"
}

setup_health_check_cron() {
    log_step "配置定时任务..."
    chmod +x "${BASE_DIR}/scripts/health_check.sh" "${BASE_DIR}/scripts/diagnose.sh" "${BASE_DIR}/scripts/reset_iptables.sh" 2>/dev/null || true
    (crontab -l 2>/dev/null | grep -v "health_check.sh"; echo "*/15 * * * * ${BASE_DIR}/scripts/health_check.sh >> ${BASE_DIR}/logs/health_check.log 2>&1") | crontab -
    (crontab -l 2>/dev/null | grep -v "cert_manager.py"; echo "0 3 1 * * /usr/bin/python3 ${BASE_DIR}/scripts/cert_manager.py --renew >> /var/log/singbox.log 2>&1") | crontab -
    (crontab -l 2>/dev/null | grep -v "reset_iptables.sh") | crontab -
    log_info "定时任务已配置（健康检查每15分钟 + 证书续签每月1号凌晨3点；流量每月14号由订阅服务baseline重置，不清零iptables）"
}

setup_swap_and_optimize() {
    log_step "检查内存和Swap..."
    local total_mem=$(free -m | awk '/^Mem:/{print $2}')
    if [ "$total_mem" -lt 1024 ] && [ ! -f /swapfile ]; then
        log_info "内存 ${total_mem}MB < 1GB，创建2GB Swap..."
        dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
        chmod 600 /swapfile
        mkswap /swapfile
        swapon /swapfile
        echo '/swapfile none swap sw 0 0' >> /etc/fstab
        sysctl vm.swappiness=10 >> /dev/null 2>&1 || true
        grep -q 'vm.swappiness' /etc/sysctl.conf && sed -i 's/vm.swappiness=.*/vm.swappiness=10/' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
        log_info "2GB Swap已创建并启用"
    elif [ -f /swapfile ]; then
        log_info "Swap已存在，跳过"
    else
        log_info "内存 ${total_mem}MB >= 1GB，无需Swap"
    fi
    systemctl stop fwupd.service fwupd-refresh.service fwupd-refresh.timer 2>/dev/null || true
    systemctl disable fwupd.service fwupd-refresh.service fwupd-refresh.timer 2>/dev/null || true
    systemctl mask fwupd.service fwupd-refresh.service fwupd-refresh.timer 2>/dev/null || true
    pkill -9 fwupd 2>/dev/null || true
    for svc in ModemManager udisks2 unattended-upgrades multipathd caddy; do
        systemctl stop $svc 2>/dev/null || true
        systemctl disable $svc 2>/dev/null || true
        systemctl mask $svc 2>/dev/null || true
    done
    systemctl stop multipathd.socket 2>/dev/null || true
    systemctl disable multipathd.socket 2>/dev/null || true
    mkdir -p /etc/systemd/journald.conf.d
    cat > /etc/systemd/journald.conf.d/size-limit.conf << 'JEOF'
[Journal]
SystemMaxUse=50M
RuntimeMaxUse=20M
JEOF
    systemctl restart systemd-journald 2>/dev/null || true
    if [ ! -f /etc/logrotate.d/singbox ]; then
        cat > /etc/logrotate.d/singbox << 'EOF'
/var/log/singbox.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    maxsize 50M
}
EOF
        log_info "singbox日志轮转已配置"
    fi
}

clean_crontab_conflicts() {
    log_step "清理crontab冲突定时任务..."
    local old_cron
    old_cron=$(crontab -l 2>/dev/null || echo "")
    if echo "$old_cron" | grep -q "restart singbox-cdn"; then
        echo "$old_cron" | grep -v "restart singbox-cdn" | crontab -
        log_info "已删除冲突的 singbox-cdn 定时重启任务（由systemd管理，无需crontab）"
    else
        log_info "无crontab冲突任务"
    fi
}

setup_iptables_traffic_counter() {
    log_step "配置iptables流量计数器（sing-box各入站端口）..."
    # 从 .env 读取端口配置和部署模式
    DEPLOY_MODE_IPT="cdn"
    if [ -f "$BASE_DIR/.env" ]; then
        VLESS_GRPC_PORT=$(grep "^VLESS_GRPC_PORT=" "$BASE_DIR/.env" | cut -d'=' -f2)
        TROJAN_TCP_PORT=$(grep "^TROJAN_TCP_PORT=" "$BASE_DIR/.env" | cut -d'=' -f2)
        DEPLOY_MODE_IPT=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" | cut -d'=' -f2 || echo "cdn")
    fi
    # 默认值
    VLESS_GRPC_PORT=${VLESS_GRPC_PORT:-50051}
    TROJAN_TCP_PORT=${TROJAN_TCP_PORT:-50443}

    iptables -F INPUT 2>/dev/null || true
    iptables -A INPUT -p tcp --dport 443 -j ACCEPT
    iptables -A INPUT -p udp --dport 443 -j ACCEPT
    if [ "$DEPLOY_MODE_IPT" != "direct" ]; then
        iptables -A INPUT -p tcp --dport 8443 -j ACCEPT
        iptables -A INPUT -p udp --dport 8443 -j ACCEPT
        iptables -A INPUT -p tcp --dport 2083 -j ACCEPT
        iptables -A INPUT -p udp --dport 2083 -j ACCEPT
    fi
    iptables -A INPUT -p tcp --dport 2087 -j ACCEPT
    iptables -A INPUT -p udp --dport 2087 -j ACCEPT
    # v4.14.0 新增：anyTLS 端口（替换已下线的 2053 HTTPUpgrade）
    iptables -A INPUT -p tcp --dport 2096 -j ACCEPT
    iptables -A INPUT -p udp --dport 2096 -j ACCEPT
    # 动态端口
    iptables -A INPUT -p tcp --dport $VLESS_GRPC_PORT -j ACCEPT
    iptables -A INPUT -p udp --dport $VLESS_GRPC_PORT -j ACCEPT
    iptables -A INPUT -p tcp --dport $TROJAN_TCP_PORT -j ACCEPT
    iptables -A INPUT -p udp --dport $TROJAN_TCP_PORT -j ACCEPT
    # TUIC v5 端口（仅 ENABLE_TUIC=true 时添加）
    TUIC_PORT_IPT=$(grep "^TUIC_PORT=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "50444")
    _enable_tuic_ipt=$(grep "^ENABLE_TUIC=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr '[:upper:]' '[:lower:]')
    if [ "${_enable_tuic_ipt:-true}" = "true" ]; then
        iptables -A INPUT -p tcp --dport $TUIC_PORT_IPT -j ACCEPT
        iptables -A INPUT -p udp --dport $TUIC_PORT_IPT -j ACCEPT
        log_info "TUIC v5 防火墙规则已配置 (端口: $TUIC_PORT_IPT, TCP+UDP)"
    else
        log_info "TUIC v5 已关闭（ENABLE_TUIC=false），跳过防火墙规则"
    fi
    # v4.15.8: 清理旧端口跳跃规则（21000-21200）
    iptables-save 2>/dev/null | grep -v "21000:21200" | iptables-restore 2>/dev/null || true
    netfilter-persistent save 2>/dev/null || iptables-save > /etc/iptables/rules.v4 2>/dev/null || true
    if [ "$DEPLOY_MODE_IPT" = "direct" ]; then
        log_info "iptables流量计数器已配置（纯直连模式：端口443/2087/2096/$TROJAN_TCP_PORT/$TUIC_PORT_IPT）"
    else
        log_info "iptables流量计数器已配置（CDN混合模式：端口443/8443/2083/2087/2096/$TROJAN_TCP_PORT/$TUIC_PORT_IPT）"
    fi
}

start_services() {
    log_step "启动所有服务..."
    DEPLOY_MODE_START="cdn"
    if [ -f "$BASE_DIR/.env" ]; then
        DEPLOY_MODE_START=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" | cut -d'=' -f2 || echo "cdn")
    fi
    if [ ! -f "${BASE_DIR}/config.json" ]; then
        log_error "config.json 不存在！重新生成..."
        cd "$BASE_DIR" && python3 scripts/config_generator.py
    fi
    if ! python3 -c "import json; json.load(open('${BASE_DIR}/config.json'))" 2>/dev/null; then
        log_error "config.json 语法错误！重新生成..."
        cd "$BASE_DIR" && python3 scripts/config_generator.py
    fi
    # v4.11.1 修复：config_generator.py 升级后必须强制重跑 + check，避免新协议入站缺失（Bug #90 教训）
    # 之前条件是"config.json 缺失或损坏"才重跑，导致 v4.11.0 升级 scripts/config_generator.py 新增 trojan-tcp 后，
    # 服务器 config.json 仍是 5-入站旧版，singbox 实际没监听新端口，但订阅服务已生成 7 节点 → 用户连不上"协议配置错"（实际入站缺失）
    # 现在无条件重跑 config_generator.py（生成在毫秒级，零成本）
    log_info "重跑 config_generator.py 以确保入站配置与代码版本一致..."
    cd "$BASE_DIR" && python3 scripts/config_generator.py
    # 立即 check 一次，配置错误早暴露
    if ! /usr/local/bin/sing-box check -c "${BASE_DIR}/config.json" >/dev/null 2>&1; then
        log_warn "config.json 检查失败，详情："
        /usr/local/bin/sing-box check -c "${BASE_DIR}/config.json" 2>&1 | head -20
    fi
    CERT_DIR_PATH="${BASE_DIR}/cert"
    if [ ! -f "${CERT_DIR_PATH}/cert.pem" ] && [ ! -f "${CERT_DIR_PATH}/fullchain.pem" ]; then
        log_warn "证书文件缺失，重新生成自签名证书..."
        cd "$BASE_DIR" && python3 scripts/cert_manager.py
    fi
    systemctl stop singbox-cdn 2>/dev/null || true
    systemctl disable singbox-cdn 2>/dev/null || true
    systemctl enable singbox singbox-sub 2>/dev/null || true
    systemctl start singbox
    sleep 3
    if ! systemctl is-active --quiet singbox; then
        log_error "singbox 启动失败！诊断信息："
        journalctl -u singbox --no-pager -n 20 2>/dev/null || true
        echo ""
        log_warn "尝试检查config.json..."
        /usr/local/bin/sing-box check -c "${BASE_DIR}/config.json" 2>&1 || true
        echo ""
        log_warn "singbox启动失败，但订阅服务仍可运行"
        log_warn "请检查上方错误信息，修复后运行: systemctl restart singbox"
    fi
    systemctl start singbox-sub
    sleep 2
    if [ "$DEPLOY_MODE_START" = "direct" ]; then
        log_info "纯直连模式：singbox 和 singbox-sub 已启动（singbox-cdn 已禁用）"
    else
        systemctl enable singbox-cdn 2>/dev/null || true
        systemctl start singbox-cdn
        log_info "CDN混合模式：所有服务（singbox/singbox-sub/singbox-cdn）已启动"
    fi
}

verify_installation() {
    log_step "验证安装..."
    DEPLOY_MODE_VERIFY="cdn"
    if [ -f "$BASE_DIR/.env" ]; then
        DEPLOY_MODE_VERIFY=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" | cut -d'=' -f2 || echo "cdn")
    fi
    echo ""
    echo -e "  部署模式: $( [ "$DEPLOY_MODE_VERIFY" = "direct" ] && echo "纯直连模式（4节点）" || echo "CDN混合模式（6节点，推荐）" )"
    echo ""
    ALL_OK=true

    # v4.15.8: 验证 .env 关键变量
    echo -e "  环境变量检查:"
    _CRITICAL_VARS="SERVER_IP VLESS_UUID TROJAN_PASSWORD REALITY_PRIVATE_KEY REALITY_PUBLIC_KEY REALITY_SHORT_ID"
    for _var in $_CRITICAL_VARS; do
        _val=$(grep "^${_var}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2- || echo "")
        if [ -z "$_val" ]; then
            echo -e "    ${RED}❌${NC} $_var: (空)"
            ALL_OK=false
        elif echo "$_val" | grep -qi "placeholder"; then
            echo -e "    ${RED}❌${NC} $_var: 占位符（未正确生成）"
            ALL_OK=false
        else
            echo -e "    ${GREEN}✅${NC} $_var: 已设置"
        fi
    done

    for svc in singbox singbox-sub; do
        if systemctl is-active --quiet "$svc"; then
            echo -e "  ${GREEN}✅${NC} $svc: 运行中"
        else
            echo -e "  ${RED}❌${NC} $svc: 未运行"
            ALL_OK=false
        fi
    done
    if [ "$DEPLOY_MODE_VERIFY" = "direct" ]; then
        echo -e "  ${YELLOW}⏸️${NC} singbox-cdn: 已禁用（纯直连模式）"
    else
        if systemctl is-active --quiet singbox-cdn; then
            echo -e "  ${GREEN}✅${NC} singbox-cdn: 运行中"
        else
            echo -e "  ${RED}❌${NC} singbox-cdn: 未运行"
            ALL_OK=false
        fi
    fi
    echo ""
    echo -e "  端口监听:"
    # v4.14.0: 2053(HTTPUpgrade) 已下线，新增 2096(anyTLS)
    if [ "$DEPLOY_MODE_VERIFY" = "direct" ]; then
        CHECK_PORTS="443 2087 2096"
    else
        CHECK_PORTS="443 8443 2083 2087 2096"
    fi
    for port in $CHECK_PORTS; do
        if ss -tlnp | grep -q ":$port "; then
            echo -e "    ${GREEN}✅${NC} 端口 $port: 监听中"
        else
            echo -e "    ${RED}❌${NC} 端口 $port: 未监听"
            ALL_OK=false
        fi
    done
    # v4.15.8: 验证随机端口协议监听
    for port_var in TROJAN_TCP_PORT; do
        vport=$(grep "^${port_var}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2)
        if [ -n "$vport" ]; then
            if ss -tlnp | grep -q ":$vport "; then
                echo -e "    ${GREEN}✅${NC} 端口 $vport ($port_var): 监听中"
            else
                echo -e "    ${RED}❌${NC} 端口 $vport ($port_var): 未监听"
                ALL_OK=false
            fi
        fi
    done
    # v4.15.0: TUIC 验证（ENABLE_TUIC=true 默认开启，加回 TUIC v5 协议）
    enable_tuic_check=$(grep "^ENABLE_TUIC=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 | tr '[:upper:]' '[:lower:]')
    if [ "$enable_tuic_check" = "true" ]; then
        tuic_vport=$(grep "^TUIC_PORT=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2)
        if [ -n "$tuic_vport" ]; then
            if ss -tulnp | grep -q ":$tuic_vport "; then
                echo -e "    ${GREEN}✅${NC} 端口 $tuic_vport (TUIC_PORT): TCP+UDP 监听中"
            else
                echo -e "    ${RED}❌${NC} 端口 $tuic_vport (TUIC_PORT): 未监听"
                ALL_OK=false
            fi
        fi
    else
        echo -e "    ${YELLOW}⏸️${NC} TUIC v5: 已关闭（ENABLE_TUIC=false）"
    fi
    echo ""
    echo -e "  系统优化:"
    if sysctl net.ipv4.tcp_congestion_control 2>/dev/null | grep -q "bbr"; then
        if uname -r | grep -qi "xanmod"; then
            echo -e "    ${GREEN}✅${NC} BBRv3加速: 已启用（XanMod $(uname -r)）"
        else
            echo -e "    ${YELLOW}⚠️${NC} BBR加速: 已启用；BBRv3 内核需重启后生效（当前 $(uname -r)）"
        fi
    else
        echo -e "    ${YELLOW}⚠️${NC} BBR/BBRv3加速: 未启用"
    fi
    VERIFY_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    VERIFY_IF=${VERIFY_IF:-eth0}
    if tc qdisc show dev "$VERIFY_IF" 2>/dev/null | grep -q "fq"; then
        echo -e "    ${GREEN}✅${NC} FQ队列: 已启用（$VERIFY_IF）"
    else
        echo -e "    ${YELLOW}⚠️${NC} FQ队列: 未启用（建议重新运行 optimize）"
    fi
    echo ""
    if [ "$ALL_OK" = true ]; then
        echo -e "  ${GREEN}🎉 所有服务运行正常！${NC}"
    else
        echo -e "  ${YELLOW}⚠️ 部分服务异常，请检查日志${NC}"
        echo -e "  查看日志: journalctl -u singbox-sub -f"
    fi
}

print_summary() {
    SERVER_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || echo "YOUR_SERVER_IP")
    CF_DOMAIN=$(grep "^CF_DOMAIN=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
    COUNTRY=$(grep "^COUNTRY_CODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "US")
    DEPLOY_MODE_SUMMARY="cdn"
    if [ -f "$BASE_DIR/.env" ]; then
        DEPLOY_MODE_SUMMARY=$(grep "^DEPLOY_MODE=" "$BASE_DIR/.env" | cut -d'=' -f2 || echo "cdn")
    fi
    echo ""
    echo "=========================================="
    echo -e "${CYAN}  Singbox EPS Node 安装完成！${NC}"
    echo "=========================================="
    echo ""
    if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
        echo "  部署模式: 纯直连模式（4节点，无CDN依赖）"
    else
        echo "  部署模式: CDN混合模式（6节点，推荐）"
    fi
    echo "📋 配置文件: $BASE_DIR/.env"
    echo ""
    if [ -n "$CF_DOMAIN" ]; then
        if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
            SUB_HOST="$CF_DOMAIN"
            echo "🔗 订阅链接:"
        else
            SUB_HOST="sub-${CF_DOMAIN}"
            echo "🔗 订阅链接（sub-* 直连源站，绕过 CF DDoS L7）:"
        fi
        echo "  Base64:    https://${SUB_HOST}:2087/sub/${COUNTRY}"
        echo "  sing-box:  https://${SUB_HOST}:2087/singbox/${COUNTRY}"
        echo "  Clash:     https://${SUB_HOST}:2087/clash/${COUNTRY}"
    else
        echo "🔗 订阅链接:"
        echo "  Base64:    https://${SERVER_IP}:2087/sub/${COUNTRY}"
        echo "  sing-box:  https://${SERVER_IP}:2087/singbox/${COUNTRY}"
        if [ "$DEPLOY_MODE_SUMMARY" != "direct" ]; then
            echo ""
            echo "⚠️  建议配置CF_DOMAIN以启用CDN和SSL证书匹配"
        fi
    fi
    echo ""
    echo "📊 流量统计:"
    if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
        STATS_HOST="${CF_DOMAIN:-$SERVER_IP}"
    else
        STATS_HOST="${CF_DOMAIN:+sub-}${CF_DOMAIN:-$SERVER_IP}"
    fi
    echo "  首页查看:  https://${STATS_HOST}:2087/"
    echo "  API接口:   https://${CF_DOMAIN:-$SERVER_IP}:2087/api/traffic"
    echo "  重置规则:  每月14号更新baseline（不清零iptables计数器）"
    echo ""
    if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
        echo "📡 纯直连模式，无CDN依赖"
        echo "  节点: 4个（VLESS-Reality + Trojan-TCP + anyTLS + TUIC v5）"
    else
        echo "🌐 CDN优选IP（4级降级保障）:"
        echo "  主方案:    本地实测IP池（湖南电信最优）"
        echo "  备选1:     cf.001315.xyz/ct电信API"
        echo "  备选2:     WeTest.vip电信优选DNS"
        echo "  备选3:     IPDB API bestcf"
        echo "  节点: 6个（4直连 + 2WS-CDN）"
    fi
    echo ""
    echo "⚡ 系统优化（已自动完成；BBRv3 内核首次启用需重启）:"
    if uname -r | grep -qi "xanmod"; then
        echo "  BBRv3加速:    已启用（XanMod $(uname -r)）"
    else
        echo "  BBRv3加速:    内核已安装则重启后生效（当前 $(uname -r)）"
    fi
    echo "  FQ公平队列:   已启用（为每个TCP连接独立缓冲）"
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1) || true
    MAIN_IF=${MAIN_IF:-eth0}
    if tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "fq"; then
        echo "  FQ队列:       已启用（BBR推荐组合，网卡$MAIN_IF）"
    else
        echo "  FQ队列:       未启用（建议运行 bash install.sh optimize 重新优化）"
    fi
    echo "  TCP调优:       已优化（含BBRv3/BBR高丢包参数）"
    echo "  文件描述符:    65535"
    echo "  时区:          Asia/Shanghai"
    echo ""
    echo "📝 下一步:"
    echo "  1. 检查配置: cat /root/singbox-eps-node/.env"
    echo "  2. 如需修改: nano /root/singbox-eps-node/.env"
    if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
        echo "  3. 重启服务: systemctl restart singbox singbox-sub"
    else
        echo "  3. 重启服务: systemctl restart singbox singbox-sub singbox-cdn"
    fi
    echo ""
    echo "🔧 服务管理:"
    if [ "$DEPLOY_MODE_SUMMARY" = "direct" ]; then
        echo "  查看状态: systemctl status singbox singbox-sub"
    else
        echo "  查看状态: systemctl status singbox singbox-sub singbox-cdn"
    fi
    echo "  查看日志: journalctl -u singbox-sub -f"
    echo ""
}

cmd_reset() {
    echo ""
    echo -e "${YELLOW}⚠️  一键重装singbox应用（保留.env配置和数据）${NC}"
    echo -e "${YELLOW}    数据库(data/)和证书(cert/)不会被删除${NC}"
    echo -e "${YELLOW}    客户端无需重新配置（密码和密钥保持不变）${NC}"
    read -p "  确认重装？(y/N): " CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
        log_info "已取消"
        exit 0
    fi
    log_step "停止所有服务..."
    systemctl stop singbox singbox-sub singbox-cdn 2>/dev/null || true
    systemctl disable singbox singbox-sub singbox-cdn 2>/dev/null || true
    BACKUP_DIR="${BASE_DIR}.reset_backup.$(date +%Y%m%d%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    [ -f "$BASE_DIR/.env" ] && cp "$BASE_DIR/.env" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/data" ] && cp -r "$BASE_DIR/data" "$BACKUP_DIR/"
    [ -d "$BASE_DIR/cert" ] && cp -r "$BASE_DIR/cert" "$BACKUP_DIR/"
    log_info "配置和数据已备份到 $BACKUP_DIR"
    rm -rf "$BASE_DIR"
    log_info "旧代码已删除"
    clone_repo
    setup_python_env
    [ -f "$BACKUP_DIR/.env" ] && cp "$BACKUP_DIR/.env" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/data" ] && cp -r "$BACKUP_DIR/data" "$BASE_DIR/"
    [ -d "$BACKUP_DIR/cert" ] && cp -r "$BACKUP_DIR/cert" "$BASE_DIR/"
    log_info "配置和数据已恢复"
    generate_config
    create_systemd_services
    setup_firewall
    setup_tuic_firewall
    setup_swap_and_optimize
    clean_crontab_conflicts
    setup_iptables_traffic_counter
    setup_health_check_cron
    start_services
    verify_installation
    echo ""
    log_info "🎉 重装完成！配置和数据已保留"
}

cmd_reinstall() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ⚠️  一键重装操作系统（将清除硬盘所有数据！）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  重装后需重新运行 ${GREEN}bash install.sh${NC} 部署singbox"
    echo ""
    check_root
    while true; do
        read -s -p "  请输入root密码: " ROOT_PASSWORD
        echo ""
        read -s -p "  请再次输入root密码: " ROOT_PASSWORD_CONFIRM
        echo ""
        if [ -z "$ROOT_PASSWORD" ]; then
            log_warn "密码不能为空，请重新输入"
            echo ""
            continue
        fi
        if [ "$ROOT_PASSWORD" != "$ROOT_PASSWORD_CONFIRM" ]; then
            log_warn "两次密码不一致，请重新输入"
            echo ""
            continue
        fi
        break
    done
    log_info "密码确认成功"
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        CURRENT_OS=$ID
        CURRENT_VERSION=$VERSION_ID
    else
        log_error "无法检测当前操作系统版本"
        exit 1
    fi
    case "$CURRENT_OS" in
        ubuntu)      REINSTALL_OS="ubuntu" ;;
        debian)      REINSTALL_OS="debian" ;;
        centos)      REINSTALL_OS="centos" ;;
        rocky)       REINSTALL_OS="rocky" ;;
        almalinux)   REINSTALL_OS="alma" ;;
        alpine)      REINSTALL_OS="alpine" ;;
        opensuse-leap) REINSTALL_OS="opensuse" ;;
        opensuse-tumbleweed) REINSTALL_OS="opensuse" ;;
        fedora)      REINSTALL_OS="fedora" ;;
        arch)        REINSTALL_OS="arch" ;;
        gentoo)      REINSTALL_OS="gentoo" ;;
        *)           REINSTALL_OS="$CURRENT_OS" ;;
    esac
    log_info "当前系统: $CURRENT_OS $CURRENT_VERSION"
    log_info "将重装为: $REINSTALL_OS $CURRENT_VERSION（保持当前版本）"
    log_info "下载系统重装脚本..."
    cd /tmp
    REINSTALL_SCRIPT=""
    curl -sS -O https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        log_info "GitHub下载失败，尝试国内镜像..."
        curl -sS -O https://cnb.cool/bin456789/reinstall/-/git/raw/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    fi
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        wget -q -O reinstall.sh https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null && REINSTALL_SCRIPT="reinstall.sh" || true
    fi
    if [ -z "$REINSTALL_SCRIPT" ] || [ ! -f "reinstall.sh" ]; then
        log_error "下载重装脚本失败，请检查网络连接"
        exit 1
    fi
    echo ""
    log_warn "即将开始重装操作系统，重装完成后将自动重启"
    log_warn "重启后请用新root密码SSH连接，然后运行 bash install.sh 部署singbox"
    echo ""
    log_info "开始重装 $REINSTALL_OS $CURRENT_VERSION ..."
    bash reinstall.sh "$REINSTALL_OS" "$CURRENT_VERSION" --password "$ROOT_PASSWORD"
}

safe_update_env() {
    local key="$1"
    local value="$2"
    local envfile="$3"
    python3 - "$key" "$value" "$envfile" << 'PYEOF'
import sys, re
key, value, envfile = sys.argv[1], sys.argv[2], sys.argv[3]
lines = []
replaced = False
with open(envfile, 'r', encoding='utf-8') as f:
    for line in f:
        if re.match(rf'^{re.escape(key)}=', line):
            lines.append(f'{key}={value}\n')
            replaced = True
        else:
            lines.append(line)
if not replaced:
    lines.append(f'{key}={value}\n')
with open(envfile, 'w', encoding='utf-8') as f:
    f.writelines(lines)
PYEOF
}

cmd_warp_unlock() {
    local ACTION="${1:-install}"
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    if [ "$ACTION" = "uninstall" ] || [ "$ACTION" = "off" ]; then
        echo -e "${CYAN}  关闭WARP DNS解锁${NC}"
    else
        echo -e "${CYAN}  🚀 Cloudflare WARP DNS解锁安装${NC}"
    fi
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    check_root

    local WGCF_DIR="/opt/wgcf"
    local WGCF_BIN="/usr/local/bin/wgcf"
    trap 'rm -rf "$WGCF_DIR" 2>/dev/null || true' EXIT INT TERM

    if [ ! -d "$BASE_DIR" ]; then
        log_error "项目目录不存在: $BASE_DIR，请先运行 bash install.sh 完成基础安装"
        exit 1
    fi

    if [ "$ACTION" = "uninstall" ] || [ "$ACTION" = "off" ]; then
        log_info "正在关闭WARP DNS解锁..."
        if [ -f "$BASE_DIR/.env" ]; then
            safe_update_env "WARP_UNLOCK" "off" "$BASE_DIR/.env"
            safe_update_env "WARP_PRIVATE_KEY" "" "$BASE_DIR/.env"
            safe_update_env "WARP_PEER_PUBLIC_KEY" "" "$BASE_DIR/.env"
            safe_update_env "WARP_PEER_ENDPOINT" "" "$BASE_DIR/.env"
            safe_update_env "WARP_CLIENT_IPV4" "" "$BASE_DIR/.env"
            safe_update_env "WARP_CLIENT_IPV6" "" "$BASE_DIR/.env"
            safe_update_env "WARP_RESERVED" "" "$BASE_DIR/.env"
            log_info "WARP配置已清空，WARP_UNLOCK设置为off"
        fi
        rm -rf "$WGCF_DIR" 2>/dev/null || true
        rm -f "$WGCF_BIN" 2>/dev/null || true
        cd "$BASE_DIR" && python3 scripts/config_generator.py
        systemctl restart singbox singbox-sub 2>/dev/null || true
        sleep 2
        if systemctl is-active --quiet singbox; then
            echo -e "${GREEN}✅ WARP DNS解锁已关闭，所有流量恢复服务器直连${NC}"
        else
            log_error "服务重启失败，请检查日志"
        fi
        return
    fi

    log_info "安装依赖..."
    apt-get update -qq
    apt-get install -y -qq curl jq file > /dev/null 2>&1 || true

    mkdir -p "$WGCF_DIR"
    chmod 700 "$WGCF_DIR"

    if [ ! -f "$WGCF_BIN" ]; then
        log_info "下载wgcf工具..."
        ARCH=$(uname -m)
        if [ "$ARCH" = "x86_64" ] || [ "$ARCH" = "amd64" ]; then
            WGCF_URL="https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_amd64"
        elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
            WGCF_URL="https://github.com/ViRb3/wgcf/releases/download/v2.2.22/wgcf_2.2.22_linux_arm64"
        else
            log_error "不支持的架构: $ARCH"
            exit 1
        fi
        if ! curl -fSL --connect-timeout 15 --max-time 60 "$WGCF_URL" -o "$WGCF_BIN"; then
            log_error "下载wgcf失败"
            exit 1
        fi
        chmod 700 "$WGCF_BIN"
        if ! file "$WGCF_BIN" | grep -q "ELF"; then
            log_error "下载的wgcf不是有效二进制文件"
            rm -f "$WGCF_BIN"
            exit 1
        fi
        if ! "$WGCF_BIN" --help >/dev/null 2>&1; then
            log_error "下载的wgcf二进制无法执行"
            rm -f "$WGCF_BIN"
            exit 1
        fi
        log_info "wgcf二进制验证通过"
    fi

    log_info "注册WARP账户..."
    cd "$WGCF_DIR"
    rm -f wgcf-account.toml wgcf-profile.conf
    REGISTER_OK=false
    for i in 1 2 3; do
        if "$WGCF_BIN" register --accept-tos >/dev/null 2>&1; then
            REGISTER_OK=true
            break
        fi
        log_warn "第${i}次注册失败，重试..."
        sleep 3
    done
    if [ "$REGISTER_OK" != "true" ]; then
        log_error "WARP账户注册失败（3次尝试均失败），请检查网络连接"
        exit 1
    fi
    chmod 600 wgcf-account.toml 2>/dev/null || true

    log_info "生成WireGuard配置..."
    if ! "$WGCF_BIN" generate >/dev/null 2>&1; then
        log_error "生成WireGuard配置失败"
        exit 1
    fi
    chmod 600 wgcf-profile.conf 2>/dev/null || true

    if [ ! -f wgcf-profile.conf ]; then
        log_error "生成WARP配置失败，请检查网络连接"
        exit 1
    fi

    log_info "解析WARP配置..."
    PRIVATE_KEY=$(grep '^PrivateKey' wgcf-profile.conf | awk -F' = ' '{print $2}' | tr -d '[:space:]')
    PEER_PUBLIC_KEY=$(grep '^PublicKey' wgcf-profile.conf | awk -F' = ' '{print $2}' | tr -d '[:space:]')
    ENDPOINT=$(grep '^Endpoint' wgcf-profile.conf | awk -F' = ' '{print $2}' | tr -d '[:space:]')
    # wgcf-profile.conf 可能是一行逗号分隔或两行分别写IPv4/IPv6
    # 用grep直接提取，避免tr去掉换行导致地址拼接
    ADDRESS=$(grep '^Address' wgcf-profile.conf | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/[0-9]+' | head -1)
    ADDRESS_V6=$(grep '^Address' wgcf-profile.conf | grep -oE '[0-9a-fA-F]{1,4}:[0-9a-fA-F:]+/[0-9]+' | head -1)

    if [ -z "$PRIVATE_KEY" ] || [ -z "$PEER_PUBLIC_KEY" ] || [ -z "$ENDPOINT" ] || [ -z "$ADDRESS" ]; then
        log_error "解析配置失败"
        exit 1
    fi

    log_info "更新.env配置..."
    safe_update_env "WARP_UNLOCK" "on" "$BASE_DIR/.env"
    safe_update_env "WARP_PRIVATE_KEY" "$PRIVATE_KEY" "$BASE_DIR/.env"
    safe_update_env "WARP_PEER_PUBLIC_KEY" "$PEER_PUBLIC_KEY" "$BASE_DIR/.env"
    safe_update_env "WARP_PEER_ENDPOINT" "$ENDPOINT" "$BASE_DIR/.env"
    safe_update_env "WARP_CLIENT_IPV4" "$ADDRESS" "$BASE_DIR/.env"
    safe_update_env "WARP_CLIENT_IPV6" "$ADDRESS_V6" "$BASE_DIR/.env"
    safe_update_env "WARP_RESERVED" "" "$BASE_DIR/.env"

    chmod 600 "$BASE_DIR/.env"

    log_info "重新生成sing-box配置..."
    cd "$BASE_DIR" && python3 scripts/config_generator.py

    if ! /usr/local/bin/sing-box check -c "${BASE_DIR}/config.json" >/dev/null 2>&1; then
        log_error "config.json检查失败："
        /usr/local/bin/sing-box check -c "${BASE_DIR}/config.json" 2>&1 | head -20
        exit 1
    fi

    log_info "重启服务..."
    systemctl restart singbox singbox-sub 2>/dev/null || true
    sleep 3

    echo ""
    if systemctl is-active --quiet singbox; then
        echo -e "${GREEN}=========================================${NC}"
        echo -e "${GREEN}  ✅ WARP DNS解锁安装成功！${NC}"
        echo -e "${GREEN}=========================================${NC}"
        echo ""
        echo -e "${GREEN}分流规则(走WARP住宅IP):${NC}"
        echo -e "  ✅ OpenAI / ChatGPT"
        echo -e "  ✅ Anthropic / Claude"
        echo -e "  ✅ Gemini / Google AI"
        echo -e "  ✅ TikTok"
        echo -e "  ✅ Netflix"
        echo ""
        echo -e "${GREEN}直连规则(走服务器本地IP):${NC}"
        echo -e "  ✅ X / Twitter"
        echo -e "  ✅ Google / YouTube"
        echo -e "  ✅ 其他所有网站（不影响速度）"
        echo ""
        echo -e "${YELLOW}关闭解锁: bash install.sh warp-unlock off${NC}"
    else
        log_error "服务启动失败，请检查日志：journalctl -u singbox -n 30"
        exit 1
    fi
}

cmd_optimize() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  一键优化系统（BBRv3+FQ 网络加速）${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  1. BBRv3内核 — 安装 XanMod BBRv3 内核（首次启用需重启）"
    echo -e "  2. BBR拥塞控制 — sysctl 启用 bbr，XanMod 内核运行为 BBRv3"
    echo -e "  3. FQ公平队列 — 为每个TCP连接独立缓冲，贴合 BBR pacing"
    echo -e "  4. TCP参数 — 保活、队列、缓冲区、TFO 等参数即时生效"
    echo ""
    check_root
    update_system
    optimize_system
    echo ""
    echo -e "${GREEN}✅ 系统优化完成！BBRv3+FQ 网络加速已配置：${NC}"
    echo -e "  拥塞控制:     $(sysctl net.ipv4.tcp_congestion_control 2>/dev/null | awk '{print $3}' || echo '未知')"
    echo -e "  当前内核:     $(uname -r)"
    if uname -r | grep -qi "xanmod"; then
        echo -e "  BBRv3状态:    已运行 XanMod BBRv3 内核"
    else
        echo -e "  BBRv3状态:    需重启后运行新内核"
    fi
    echo -e "  默认队列:     $(sysctl net.core.default_qdisc 2>/dev/null | awk '{print $3}' || echo '未知')"
    MAIN_IF=$(ip route show default 2>/dev/null | awk '{print $5}' | head -1)
    MAIN_IF=${MAIN_IF:-eth0}
    if tc qdisc show dev "$MAIN_IF" 2>/dev/null | grep -q "fq"; then
        echo -e "  FQ队列:       已启用（$MAIN_IF，BBR推荐组合）"
    else
        echo -e "  FQ队列:       未启用（$MAIN_IF，建议检查 tc 配置）"
    fi
    echo -e "  文件描述符:    65535"
    echo -e "  时区:          Asia/Shanghai"
    echo ""
}

cmd_help() {
    echo ""
    echo -e "${CYAN}Singbox EPS Node 一键脚本 v4.15.0${NC}"
    echo ""
    echo "用法:"
    echo "  bash install.sh              全新安装（自动优化系统+交互式配置）"
    echo "  bash install.sh reinstall    一键重装操作系统（需输入root密码，装完自动重启）"
    echo "  bash install.sh reset        一键重装singbox（保留配置和数据，客户端无需重配）"
    echo "  bash install.sh optimize     一键优化系统（BBRv3+FQ；BBRv3 内核首次启用需重启）"
    echo "  bash install.sh warp-unlock  安装WARP DNS解锁（AI+流媒体零成本解锁）"
    echo "  bash install.sh warp-unlock off  关闭WARP DNS解锁"
    echo "  bash install.sh help         显示此帮助"
    echo ""
    echo "子命令说明:"
    echo "  reinstall  重装操作系统（bin456789/reinstall）"
    echo "             - 自动检测当前OS版本，重装为相同版本"
    echo "             - 需输入root密码（两次确认），作为新系统登录密码"
    echo "             - 重装后需重新运行 bash install.sh 部署singbox"
    echo "  reset      重装singbox应用（保留.env配置和数据库）"
    echo "             - 保留所有密码和密钥，客户端无需重新配置"
    echo "             - 保留流量统计数据和证书"
    echo "  warp-unlock  Cloudflare WARP DNS解锁（AI+流媒体，零成本）"
    echo "             - 解锁: OpenAI/ChatGPT/Gemini/Claude/TikTok/Netflix"
    echo "             - 直连: X/Twitter/Google/YouTube/其他所有网站（不影响速度）"
    echo "             - 技术: sing-box内置WireGuard直连，零额外进程，低延迟"
    echo "             - 可随时开启/关闭，不影响原有节点"
    echo ""
    echo "安装流程（全自动，无需手动操作）："
    echo "  阶段1: 系统更新 → 安装依赖 → BBRv3+FQ 网络加速 → 系统优化"
    echo "  阶段2: 卸载旧面板 → 安装singbox → 交互式配置 → 启动服务"
    echo ""
    echo "BBRv3+FQ 网络加速（当前项目基线）："
    echo "  1. BBRv3内核  — XanMod BBRv3，改善高延迟/丢包 TCP 链路"
    echo "  2. BBR拥塞控制 — sysctl 名称仍是 bbr，XanMod 内核中为 BBRv3"
    echo "  3. FQ公平队列 — 为每个TCP连接独立排队，贴合 BBR pacing"
    echo "  ⚠️ 内核切换需重启后生效；sysctl/FQ 参数即时生效"
    echo ""
}

main() {
    case "${1:-}" in
        --yes|-y)
            export AUTO_YES=1
            shift
            ;;
    esac
    
    local subcmd="${1:-}"
    local subcmd_arg="${2:-}"
    
    case "$subcmd" in
        reset)
            cmd_reset
            ;;
        reinstall)
            cmd_reinstall
            ;;
        optimize)
            cmd_optimize
            ;;
        warp-unlock|warp)
            cmd_warp_unlock "$subcmd_arg"
            ;;
        help|--help|-h)
            cmd_help
            ;;
        install|--yes|"")
            echo ""
            echo "=========================================="
            echo -e "${CYAN}  Singbox EPS Node 一键安装脚本 v4.15.0${NC}"
            echo "=========================================="
            echo ""
            check_root
            detect_os
            update_system
            install_dependencies
            optimize_system
            uninstall_old_panels
            install_singbox
            clone_repo
            setup_python_env
            generate_uuids_and_passwords
            generate_reality_keys
            select_deploy_mode
            create_env_file
            generate_config
            setup_certificate
            setup_firewall
            setup_tuic_firewall
            create_systemd_services
            setup_swap_and_optimize
            clean_crontab_conflicts
            setup_iptables_traffic_counter
            setup_health_check_cron
            start_services
            verify_installation
            if grep -q "^WARP_UNLOCK=on" "$BASE_DIR/.env" 2>/dev/null; then
                echo ""
                log_info "检测到WARP解锁已启用，正在自动配置WARP..."
                cmd_warp_unlock install
            fi
            print_summary
            ;;
        *)
            log_error "未知命令: $subcmd"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
