# Singbox EPS Node 架构设计

## 项目概述

全自动代理订阅系统，基于 Singbox 内核，纯脚本化管理，零面板依赖。

**设计目标**：
- 极简架构，模块化设计
- 单一订阅链接，包含所有节点
- CDN 优选 IP 自动分配（指定DNS解析）
- Hysteria2 端口跳跃（无感切换，UDP+TCP双协议保障）
- Cloudflare API 支持长期证书（15年）
- 域名/IP 自动判断，新VPS零配置部署
- SOCKS5 AI流量自动路由

## 目录结构

```
singbox-eps-node/
├── install.sh              # 一键安装脚本
├── .env.example            # 环境变量模板
├── README.md               # 项目说明
├── TECHNICAL_DOC.md        # 技术文档
├── project_snapshot.md     # 项目状态快照
├── AI_DEBUG_HISTORY.md     # Bug病历本
├── docs/
│   ├── architecture.md     # 架构设计文档
│   └── usage.md            # 使用说明
└── scripts/
    ├── __init__.py          # 包初始化
    ├── config.py            # 统一配置管理（端口锁定+防篡改）
    ├── logger.py            # 日志管理
    ├── config_generator.py  # Singbox 服务端配置生成
    ├── subscription_service.py # 订阅服务（Base64+sing-box JSON）
    ├── cdn_monitor.py       # CDN优选IP监控（指定DNS解析）
    ├── cert_manager.py      # 证书管理+端口跳跃规则
    ├── health_check.sh      # 健康检查与自动恢复
    └── tg_bot.py            # Telegram管理机器人
```

## 节点命名规则

**格式**: `ePS-{国家}-{协议名称}`

| 节点名称 | 协议 | IP类型 | 说明 |
|---------|------|--------|------|
| ePS-JP-VLESS-Reality | VLESS + Reality | 直连IP | 苹果域名伪装 |
| ePS-JP-VLESS-WS | VLESS + WebSocket | CDN IP | CDN节点 |
| ePS-JP-VLESS-HTTPUpgrade | VLESS + HTTPUpgrade | CDN IP | CDN节点 |
| ePS-JP-Trojan-WS | Trojan + WebSocket | CDN IP | CDN节点 |
| ePS-JP-Hysteria2 | Hysteria2 + 端口跳跃 | 直连IP | 无感切换，UDP+TCP双保障 |
| AI-SOCKS5 | SOCKS5 | 外部 | AI流量自动路由（可选） |

## 核心模块

### 1. config.py - 配置中心

**职责**：集中管理所有配置参数，端口锁定防篡改

**核心功能**：
- 服务器IP自动检测（`_detect_server_ip()`）
- 域名/IP动态判断（`get_sub_domain()`）
- 端口硬编码锁定 + SHA256校验和防篡改
- .env文件读取
- HY2规避配置完整说明（6条铁律）
- SOCKS5 AI路由凭据从环境变量读取

### 2. subscription_service.py - 订阅服务

**职责**：提供HTTPS订阅服务（Base64 + sing-box JSON）

**核心功能**：
- Flask应用，监听2087端口（CDN支持端口）
- Base64编码订阅（V2rayN/NekoBox等）
- sing-box JSON完整配置（含路由规则）
- CDN优选IP自动分配（每个协议独立IP）
- SOCKS5 AI路由规则（写死的域名列表）
- HY2端口跳跃 hop_ports 字段
- 客户端User-Agent自动识别格式

### 3. config_generator.py - 服务端配置生成

**职责**：生成Singbox服务端config.json

**核心功能**：
- 6个入站配置（VLESS-Reality、VLESS-WS、VLESS-HTTPUpgrade、Trojan-WS、Hysteria2、SOCKS5）
- 自动生成密码和UUID
- AI SOCKS5出站 + 路由规则
- 所有路径从config.py的BASE_DIR/CERT_DIR拼接

### 4. cdn_monitor.py - CDN监控

**职责**：自动获取并分配CDN优选IP

**核心功能**：
- 指定DNS解析（222.246.129.80 | 59.51.78.210 湖南电信DNS）
- 降级方案：固定优选IP池 → 114DNS
- 每个协议独立IP
- 守护进程模式，每小时更新

### 5. cert_manager.py - 证书管理

**职责**：SSL证书管理 + Hysteria2端口跳跃规则

**核心功能**：
- Cloudflare API源证书（15年有效期）
- 自签证书备用（365天）
- 自动续签检查
- Hysteria2端口跳跃iptables规则（UDP+TCP双协议）
- iptables持久化

### 6. health_check.sh - 健康检查

**职责**：定期健康检查与自动恢复

**核心功能**：
- 端口完整性校验
- 服务状态检查与自动重启
- 端口监听检查
- 订阅接口可用性检查
- 防火墙状态检查
- 证书有效期检查
- 磁盘空间检查

## 端口配置（锁定）

| 端口 | 协议 | 用途 |
|------|------|------|
| 443 | VLESS-Reality / Hysteria2 | 直连节点 |
| 8443 | VLESS-WS-CDN | CDN节点 |
| 2053 | VLESS-HTTPUpgrade-CDN | CDN节点 |
| 2083 | Trojan-WS-CDN | CDN节点 |
| 2087 | 订阅服务 | HTTPS（CDN支持端口） |
| 1080 | SOCKS5 | 本地代理 |
| 21000-21200 | Hysteria2端口跳跃 | 无感切换 |

## .env 配置

```bash
# 必填
SERVER_IP=                    # 服务器公网IP（留空自动检测）
CF_DOMAIN=                    # Cloudflare域名

# 协议密码（安装时自动生成）
VLESS_UUID=
VLESS_WS_UUID=
TROJAN_PASSWORD=
HYSTERIA2_PASSWORD=
REALITY_PRIVATE_KEY=
REALITY_PUBLIC_KEY=

# 可选
CF_API_TOKEN=                 # Cloudflare API Token（15年证书）
AI_SOCKS5_SERVER=             # AI住宅IP
AI_SOCKS5_PORT=
AI_SOCKS5_USER=
AI_SOCKS5_PASS=
SUB_TOKEN=
COUNTRY_CODE=JP
```

## 订阅地址选择逻辑

| 配置情况 | 订阅服务地址 | CDN节点地址 |
|---------|------------|-----------|
| 只有IP | IP:2087 | CDN IP 或 IP |
| 有域名 | 域名:2087（走CDN） | CDN IP 或 域名 |

## Systemd 服务

| 服务名 | 说明 |
|--------|------|
| singbox | Singbox 主服务 |
| singbox-sub | 订阅服务（Flask） |
| singbox-cdn | CDN 监控服务 |

## iptables 端口跳跃

```bash
# Hysteria2端口跳跃：21000-21200 → 443（UDP+TCP双协议保障）
iptables -t nat -A PREROUTING -p udp --dport 21000:21200 -j DNAT --to-destination :443
iptables -t nat -A PREROUTING -p tcp --dport 21000:21200 -j DNAT --to-destination :443
netfilter-persistent save
```

## SOCKS5 AI路由规则

- **AI网站自动走SOCKS5**：openai/chatgpt/anthropic/claude/gemini/aistudio/perplexity/midjourney/stability/cohere/replicate/google/googleapis/gstatic
- **X/推特/groK排除**（走直连）：x.com/twitter.com/twimg.com/t.co/x.ai/grok.com
- **触发条件**：配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量
- **未配置时**：不生成任何SOCKS5相关节点和规则
