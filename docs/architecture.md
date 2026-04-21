# Singbox EPS Node 架构设计

**版本**: v1.0.75 | **更新**: 2026-04-22

## 项目概述

全自动代理订阅系统，基于 sing-box 内核，纯脚本化管理，零面板依赖。

**设计目标**：
- 极简架构，模块化设计
- 单一订阅链接，包含所有节点
- CDN 优选 IP 自动分配（4级降级保障）
- Hysteria2 端口跳跃（无感切换，UDP+TCP双协议保障）
- Cloudflare API 支持长期证书（15年）
- BBR+FQ+CAKE三合一网络加速（即时生效，无需重启，CAKE不可用时降级FQ-PIE）
- 国家代码自动检测（IP地理位置）
- CF_DOMAIN和CF_API_TOKEN内置默认值（新VPS零配置部署）
- SOCKS5 AI流量自动路由（幕后出站，不暴露给用户）
- 按月流量统计（每月14号自动归零）

## 目录结构

```
singbox-eps-node/
├── install.sh              # 一键安装脚本（含系统优化+BBR+FQ+CAKE）
├── .env.example            # 环境变量模板
├── README.md               # 项目说明（用户版）
├── TECHNICAL_DOC.md        # 技术文档（完整版，含铁律+Bug历史+版本历史）
├── docs/
│   ├── architecture.md     # 架构设计文档（本文件）
│   └── usage.md            # 使用说明
└── scripts/
    ├── __init__.py          # 包初始化
    ├── config.py            # 统一配置管理（端口锁定+防篡改）
    ├── logger.py            # 日志管理
    ├── config_generator.py  # Singbox 服务端配置生成
    ├── subscription_service.py # 订阅服务（Base64+sing-box JSON+流量统计）
    ├── cdn_monitor.py       # CDN优选IP监控（4级降级保障）
    ├── cert_manager.py      # 证书管理+端口跳跃规则
    ├── health_check.sh      # 健康检查与自动恢复
    └── tg_bot.py            # Telegram管理机器人
```

## 节点命名规则

**格式**: `ePS-{国家代码}-{协议名称}`

国家代码根据服务器IP自动检测（US/JP/SG/HK等）

| 节点名称 | 协议 | IP类型 | 说明 |
|---------|------|--------|------|
| ePS-{CC}-VLESS-Reality | VLESS + Reality | 直连IP | 苹果域名伪装 |
| ePS-{CC}-VLESS-WS-CDN | VLESS + WebSocket | CDN优选IP | CDN节点 |
| ePS-{CC}-VLESS-HTTPUpgrade-CDN | VLESS + HTTPUpgrade | CDN优选IP | CDN节点 |
| ePS-{CC}-Trojan-WS-CDN | Trojan + WebSocket | CDN优选IP | CDN节点 |
| ePS-{CC}-Hysteria2 | Hysteria2 + 端口跳跃 | 直连IP | 无感切换，UDP+TCP双保障 |

⚠️ AI-SOCKS5是幕后路由出站，不是用户可见节点，不出现在订阅链接和selector中。

## 安装流程（两阶段）

### 阶段1-系统准备（全自动，无需操作）

1. 系统更新：apt upgrade + 语言包 + 时区
2. 安装依赖：curl/wget/python3/openssl/sqlite3/iproute2等
3. BBR+FQ+CAKE三合一加速（即时生效，无需重启）
4. 系统优化：文件描述符65535 + BBR高丢包参数

### 阶段2-部署服务（全自动配置）

5. 卸载旧面板 → 安装singbox → 部署项目
6. 自动检测国家代码 + 自动填入CF_DOMAIN和CF_API_TOKEN
7. 生成配置+证书+防火墙+端口跳跃
8. 启动服务+验证（含启动失败自动诊断）

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
- COUNTRY_CODE从.env读取，NODE_PREFIX动态生成

### 2. subscription_service.py - 订阅服务

**职责**：提供HTTPS订阅服务（Base64 + sing-box JSON）+ 流量统计

**核心功能**：
- Flask应用，监听2087端口（CDN支持端口）
- Base64编码订阅（V2rayN/NekoBox等）
- sing-box JSON完整配置（含路由规则，rule_set格式）
- CDN优选IP自动分配（每个协议独立IP）
- SOCKS5 AI路由规则（写死的域名列表，X/推特/groK排除）
- HY2端口跳跃 hop_ports 字段
- 按月流量统计（SQLite持久化，每月14号自动归零）
- /api/traffic JSON接口

### 3. config_generator.py - 服务端配置生成

**职责**：生成Singbox服务端config.json

**核心功能**：
- 5个入站配置（VLESS-Reality、VLESS-WS、VLESS-HTTPUpgrade、Trojan-WS、Hysteria2）+ SOCKS5本地代理
- 自动生成密码和UUID
- AI SOCKS5出站 + 路由规则
- 所有路径从config.py的BASE_DIR/CERT_DIR拼接
- 证书缺失时自动调用cert_manager.py生成自签名证书

### 4. cdn_monitor.py - CDN监控

**职责**：自动获取并分配CDN优选IP（4级降级保障）

**4级降级策略**：
1. 本地实测IP池（湖南电信最优，按延迟排序）
2. cf.001315.xyz/ct电信API
3. WeTest.vip电信优选DNS（每15分钟更新）
4. IPDB API bestcf

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
- 订阅接口可用性检查
- 防火墙状态检查
- 证书有效期检查
- 磁盘空间检查

## 端口配置（锁定）

| 端口 | 协议 | 用途 | CDN |
|------|------|------|-----|
| 443 | VLESS-Reality(TCP) / Hysteria2(UDP) | 直连节点 | ✅ |
| 8443 | VLESS-WS-CDN | CDN节点 | ✅ |
| 2053 | VLESS-HTTPUpgrade-CDN | CDN节点 | ✅ |
| 2083 | Trojan-WS-CDN | CDN节点 | ✅ |
| 2087 | 订阅服务 | HTTPS（CDN支持端口） | ✅ |
| 1080 | SOCKS5 | 本地代理 | ❌ |
| 21000-21200 | Hysteria2端口跳跃 | 无感切换 | ❌ |

## BBR+FQ+CAKE三合一加速

海外代理服务器最优方案：

| 加速 | 作用 | 配置 |
|------|------|------|
| BBR | 智能调节发送速率，不依赖丢包信号 | `tcp_congestion_control=bbr` |
| FQ | 公平分配带宽，BBR的pacing依赖FQ | `default_qdisc=cake`（CAKE集成FQ） |
| CAKE | 主动队列管理，集成FQ+PIE，防缓冲区膨胀 | `tc qdisc replace dev eth0 root cake` |

- 即时生效（sysctl -p + tc qdisc），无需重启
- CAKE持久化：systemd服务（cake-qdisc@网卡名），重启自动恢复
- CAKE模块主动安装：modprobe失败时自动安装linux-modules-extra
- 内核不支持CAKE时自动降级为FQ-PIE（tc qdisc replace实际应用到网卡+fq-pie-qdisc@持久化）
- 精确诊断：区分CAKE已启用/FQ-PIE降级已生效/tc应用失败/内核缺模块

## Systemd 服务

| 服务名 | 说明 |
|--------|------|
| singbox | Singbox 主服务 |
| singbox-sub | 订阅服务（Flask） |
| singbox-cdn | CDN 监控服务 |
| cake-qdisc@{网卡} | CAKE队列持久化 |
| fq-pie-qdisc@{网卡} | FQ-PIE降级持久化 |

## SOCKS5 AI路由规则

- **AI网站自动走SOCKS5**：openai/chatgpt/anthropic/claude/gemini/aistudio/perplexity/midjourney/stability/cohere/replicate/google/googleapis/gstatic
- **X/推特/groK排除**（走直连）：x.com/twitter.com/twimg.com/t.co/x.ai/grok.com
- **触发条件**：配置了AI_SOCKS5_SERVER和AI_SOCKS5_PORT环境变量
- **未配置时**：不生成任何SOCKS5相关节点和规则
- **幕后路由**：不出现在订阅链接和selector中，用户无感
