#!/bin/bash
# ============================================================
# HKCEPIN 服务器一键修复脚本 v4.15.8
# 用途：修复 Reality/anyTLS 连接失败问题
# 问题根因：
#   1. REALITY_SHORT_ID 未写入 .env → 服务端与订阅端 short_id 不一致 → Reality 握手失败
#   2. AWS 安全组可能未开放 443/2096 端口
#   3. anyTLS 密码为空时降级到 TROJAN_PASSWORD
# 用法：bash scripts/fix_hkcepin.sh
# ============================================================

set -e
BASE_DIR="/root/singbox-eps-node"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo ""
echo "=========================================="
echo "  HKCEPIN 服务器一键修复 v4.15.8"
echo "=========================================="
echo ""

# Step 1: 检查 .env 文件
if [ ! -f "$BASE_DIR/.env" ]; then
    log_error ".env 文件不存在！请先完成基础安装"
    exit 1
fi
log_info ".env 文件存在"

# Step 2: 备份当前 .env
cp "$BASE_DIR/.env" "$BASE_DIR/.env.fixbak.$(date +%Y%m%d%H%M%S)"
log_info ".env 已备份"

# Step 3: 检查并修复 REALITY_SHORT_ID
CURRENT_SHORT_ID=$(grep "^REALITY_SHORT_ID=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
if [ -z "$CURRENT_SHORT_ID" ]; then
    NEW_SHORT_ID=$(python3 -c "import secrets; print(secrets.token_hex(8))")
    echo "REALITY_SHORT_ID=${NEW_SHORT_ID}" >> "$BASE_DIR/.env"
    log_info "✅ REALITY_SHORT_ID 已补全: ${NEW_SHORT_ID}"
else
    log_info "✅ REALITY_SHORT_ID 已存在: ${CURRENT_SHORT_ID}"
fi

# Step 4: 检查并修复 REALITY_PRIVATE_KEY / REALITY_PUBLIC_KEY
REALITY_PK=$(grep "^REALITY_PRIVATE_KEY=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
REALITY_PUBK=$(grep "^REALITY_PUBLIC_KEY=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
if [ -z "$REALITY_PK" ] || [ -z "$REALITY_PUBK" ] || echo "$REALITY_PK" | grep -qi "placeholder"; then
    log_warn "Reality 密钥为空或为占位符，重新生成..."
    REALITY_OUTPUT=$(singbox generate reality-keypair 2>/dev/null || /usr/local/bin/sing-box generate reality-keypair 2>/dev/null || true)
    if [ -n "$REALITY_OUTPUT" ]; then
        NEW_PK=$(echo "$REALITY_OUTPUT" | grep "PrivateKey" | awk '{print $2}')
        NEW_PUBK=$(echo "$REALITY_OUTPUT" | grep "PublicKey" | awk '{print $2}')
        if [ -n "$NEW_PK" ] && [ -n "$NEW_PUBK" ]; then
            grep -q "^REALITY_PRIVATE_KEY=" "$BASE_DIR/.env" && \
                sed -i "s|^REALITY_PRIVATE_KEY=.*|REALITY_PRIVATE_KEY=${NEW_PK}|" "$BASE_DIR/.env" || \
                echo "REALITY_PRIVATE_KEY=${NEW_PK}" >> "$BASE_DIR/.env"
            grep -q "^REALITY_PUBLIC_KEY=" "$BASE_DIR/.env" && \
                sed -i "s|^REALITY_PUBLIC_KEY=.*|REALITY_PUBLIC_KEY=${NEW_PUBK}|" "$BASE_DIR/.env" || \
                echo "REALITY_PUBLIC_KEY=${NEW_PUBK}" >> "$BASE_DIR/.env"
            log_info "✅ Reality 密钥已重新生成"
        fi
    else
        log_error "❌ 无法生成 Reality 密钥，请检查 sing-box 是否安装"
    fi
else
    log_info "✅ Reality 密钥已存在"
fi

# Step 5: 检查并修复 anyTLS 密码
ANYTLS_PASS=$(grep "^ANYTLS_PASSWORD=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
TROJAN_PASS=$(grep "^TROJAN_PASSWORD=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
if [ -z "$ANYTLS_PASS" ]; then
    if [ -n "$TROJAN_PASS" ]; then
        echo "ANYTLS_PASSWORD=${TROJAN_PASS}" >> "$BASE_DIR/.env"
        log_info "✅ anyTLS 密码已补全（使用 TROJAN_PASSWORD）"
    else
        NEW_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
        echo "ANYTLS_PASSWORD=${NEW_PASS}" >> "$BASE_DIR/.env"
        log_info "✅ anyTLS 密码已补全（新生成）"
    fi
else
    log_info "✅ anyTLS 密码已存在"
fi

# Step 6: 检查 SERVER_IP
SERVER_IP=$(grep "^SERVER_IP=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
if [ -z "$SERVER_IP" ]; then
    NEW_IP=$(curl -s --connect-timeout 5 https://api.ipify.org 2>/dev/null || \
             curl -s --connect-timeout 3 http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo "")
    if [ -n "$NEW_IP" ]; then
        sed -i "s|^SERVER_IP=.*|SERVER_IP=${NEW_IP}|" "$BASE_DIR/.env"
        log_info "✅ SERVER_IP 已补全: ${NEW_IP}"
    else
        log_error "❌ 无法检测服务器 IP，请手动填写"
    fi
else
    log_info "✅ SERVER_IP: ${SERVER_IP}"
fi

# Step 7: 重新生成配置
log_info "重新生成 sing-box 配置..."
cd "$BASE_DIR"
python3 scripts/config_generator.py

# Step 8: 检查配置
log_info "检查 config.json..."
/usr/local/bin/sing-box check -c "$BASE_DIR/config.json" && log_info "✅ config.json 检查通过" || log_error "❌ config.json 检查失败"

# Step 9: 重启服务
log_info "重启服务..."
systemctl restart singbox singbox-sub singbox-cdn 2>/dev/null || true
sleep 3

# Step 10: 验证服务状态
echo ""
log_info "验证服务状态..."
for svc in singbox singbox-sub; do
    if systemctl is-active --quiet "$svc"; then
        log_info "✅ $svc: 运行中"
    else
        log_error "❌ $svc: 未运行"
    fi
done

# Step 11: 验证端口监听
echo ""
log_info "验证端口监听..."
for port in 443 8443 2083 2087 2096; do
    if ss -tlnp | grep -q ":$port "; then
        log_info "✅ 端口 $port: 监听中"
    else
        log_warn "⚠️  端口 $port: 未监听"
    fi
done

# 随机端口
for port_var in TROJAN_TCP_PORT TUIC_PORT; do
    vport=$(grep "^${port_var}=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2)
    if [ -n "$vport" ]; then
        if ss -tlnp | grep -q ":$vport "; then
            log_info "✅ 端口 $vport ($port_var): 监听中"
        else
            log_warn "⚠️  端口 $vport ($port_var): 未监听"
        fi
    fi
done

# Step 12: 生成新订阅并测试
echo ""
log_info "测试订阅端点..."
COUNTRY_CODE=$(grep "^COUNTRY_CODE=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "US")
SUB_RESULT=$(curl -sk --connect-timeout 5 "https://127.0.0.1:2087/sub/${COUNTRY_CODE}" 2>/dev/null | base64 -d 2>/dev/null | grep -c "://" || echo "0")
CLASH_RESULT=$(curl -sk --connect-timeout 5 "https://127.0.0.1:2087/clash/${COUNTRY_CODE}" 2>/dev/null | grep -c "proxies:" || echo "0")
if [ "$SUB_RESULT" -gt 0 ]; then
    log_info "✅ Base64 订阅: ${SUB_RESULT} 个节点"
else
    log_warn "⚠️  Base64 订阅返回异常"
fi
if [ "$CLASH_RESULT" -gt 0 ]; then
    log_info "✅ Clash 订阅: 返回正常"
else
    log_warn "⚠️  Clash 订阅返回异常"
fi

# Step 13: 验证订阅中的 Reality short_id 与服务器一致
echo ""
log_info "验证 Reality short_id 一致性..."
ENV_SHORT_ID=$(grep "^REALITY_SHORT_ID=" "$BASE_DIR/.env" 2>/dev/null | cut -d'=' -f2 || echo "")
CONFIG_SHORT_ID=$(python3 -c "
import json
with open('$BASE_DIR/config.json') as f:
    cfg = json.load(f)
for inbound in cfg.get('inbounds', []):
    if inbound.get('tag') == 'vless-reality':
        short_ids = inbound.get('tls', {}).get('reality', {}).get('short_id', [])
        print(','.join(short_ids))
        break
" 2>/dev/null || echo "")
if [ -n "$ENV_SHORT_ID" ] && [ -n "$CONFIG_SHORT_ID" ]; then
    if echo "$CONFIG_SHORT_ID" | grep -q "$ENV_SHORT_ID"; then
        log_info "✅ Reality short_id 一致（配置=${ENV_SHORT_ID}）"
    else
        log_error "❌ Reality short_id 不一致！环境=${ENV_SHORT_ID}，配置=${CONFIG_SHORT_ID}"
        log_error "请重新运行: cd $BASE_DIR && python3 scripts/config_generator.py && systemctl restart singbox"
    fi
else
    log_warn "⚠️  无法验证 Reality short_id（配置文件可能不含 Reality 入站）"
fi

echo ""
echo "=========================================="
echo "  🔧 修复完成！"
echo "=========================================="
echo ""
echo "在 v2rayN 中重新订阅即可获取修复后的节点"
echo "如果仍有问题，请检查 AWS EC2 安全组是否开放以下端口："
echo "  TCP 443  （VLESS-Reality）"
echo "  TCP 2096 （anyTLS）"
echo "  TCP 8443 （VLESS-WS-CDN）"
echo "  TCP 2083 （Trojan-WS-CDN）"
echo "  TCP 2087 （订阅服务）"
echo "  UDP 60977（TUIC v5，端口根据 .env 配置）"
echo ""
