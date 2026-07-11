# Singbox EPS Node 技术文档
**版本**: v4.15.15 | **更新**: 2026-07-05

> 版本历史以 CHANGELOG.md 为准。本文档描述当前 v4.15.13 架构和模块说明。
> 已删除/已下线的协议在末尾「已删除协议清单」明确标注，避免后续 AI 基于过时文档犯错。

---

## 一、项目概况
全自动 CDN 优选 IP 管理 + 多协议代理订阅生成系统。一条命令完成部署，客户端导入订阅即可使用。

- **代理内核**: sing-box 1.13.11+（JP=1.13.14，HK/HKCEPIN=1.13.13；默认含 gRPC transport，但本项目不使用 gRPC 协议）
- **后端**: Python 3 + Flask
- **数据库**: SQLite（WAL 模式）
- **CDN**: Cloudflare（SSL 模式必须为 `full`，自签证书场景下 strict 导致 526）
- **证书**: Let's Encrypt / Cloudflare Origin CA / 自签证书（含 SAN）
- **部署模式**: cdn（默认）/ direct（HK1 强制）

---

## 二、架构

### 双模式（v4.15.0 引入）

| 模式 | 节点数 | 协议 | singbox-cdn | 适用场景 |
|------|--------|------|-------------|----------|
| `cdn`（默认） | 6 | 4 直连 + 2 WS-CDN | 启动 | JP/HK/HKCEPIN，抗封锁 |
| `direct` | 4 | 纯直连 | 不启动 | HK1（hk1.* 域名强制），无 CDN 依赖 |

- `DEPLOY_MODE` 显式设置优先级最高
- 未设置时 fallback 用 `CF_DOMAIN.startswith('hk1.')` 判断（**禁止用 COUNTRY_CODE**，HK 与 HK1 都在香港，COUNTRY_CODE 无法区分）
- 代码入口：`scripts/config.py` 的 `DEPLOY_MODE` / `CDN_MODE_ENABLED` / `DIRECT_MODE_ENABLED`

### 服务列表

| 服务 | 端口 | 说明 |
|------|------|------|
| singbox | 443, 8443, 2083, 2096, TROJAN_TCP_PORT, TUIC_PORT(UDP) | 代理内核（6 协议 CDN 模式 / 4 协议 direct 模式） |
| singbox-sub | 2087 | HTTPS 订阅（CDN 服务器走 sub-* 灰云直连源站；HK1 direct 走主域名） |
| singbox-cdn | - | CDN 优选 IP 监控（v4.0 用户反馈驱动版，30 分钟存活检测） |

### 节点列表（v4.15.13 真实架构）

**CDN 模式 6 节点**：

| 节点 | 地址 | 方式 | 说明 |
|------|------|------|------|
| {CC}-VLESS-Reality | {IP}:443 | 直连 | 苹果域名伪装 |
| {CC}-Trojan-TCP | {IP}:TROJAN_TCP_PORT | 直连 | TCP+TLS，随机端口 |
| {CC}-anyTLS | {IP}:2096 | 直连 | TLS-in-TLS 加密（v4.14.0 新增） |
| {CC}-TUIC-v5 | {IP}:TUIC_PORT(UDP) | 直连 | QUIC 多路复用 + UDP relay（v4.15.0 加回） |
| {CC}-VLESS-WS-CDN | 优选IP:8443 | CDN | 主域名橙云代理，WS 路径 `/api/v1/stream` |
| {CC}-Trojan-WS-CDN | 优选IP:2083 | CDN | 主域名橙云代理，WS 路径 `/api/v1/data` |

**direct 模式 4 节点**（HK1）：去掉 VLESS-WS-CDN / Trojan-WS-CDN / singbox-cdn，保留 VLESS-Reality / Trojan-TCP / anyTLS / TUIC-v5。

> ⚠️ AI-SOCKS5 是幕后路由出站，不是用户可见节点，不出现在订阅链接和 selector 中。

### 端口分配

| 端口 | 用途 | CDN |
|------|------|-----|
| 443 | VLESS-Reality | ❌（直连源站） |
| 2083 | Trojan-WS-CDN | ✅ |
| 2087 | 订阅服务（CDN 服务器 sub-*；HK1 主域名） | ❌ |
| 8443 | VLESS-WS-CDN | ✅ |
| 2096 | anyTLS | ❌（直连源站） |
| TROJAN_TCP_PORT | Trojan-TCP（随机 10000-65535） | ❌ |
| TUIC_PORT(UDP) | TUIC-v5（随机 10000-65535） | ❌ |
| 1080 | SOCKS5 本地代理（幕后路由） | ❌ |

### 域名用途铁律（AGENTS.md 铁律 10）

| 用途 | 域名 | 云色 | 说明 |
|------|------|------|------|
| CDN 代理节点（VLESS-WS/Trojan-WS 入站） | 主域名 `jp/hk/hkcepin.290372913.xyz` | 橙云 `proxied=true` | 走 CF CDN |
| 订阅端点（/clash /sub /singbox） | CDN: `sub-jp/sub-hk/sub-hkcepin.290372913.xyz`；HK1: `hk1.290372913.xyz` | 灰云/直连 | 订阅入口，不是 CDN 节点 fallback |

> 两类严格分离，**CDN 节点不得用 sub-***。
> v4.15.13 铁律：CDN WS 节点名必须保留 `-CDN` 后缀，`sub-*` 不得作为 CDN 节点降级地址。

### 4 台服务器

| 服务器 | IP | 域名 | 模式 | 协议数 | 备注 |
|--------|----|----|------|--------|------|
| JP | 43.207.152.47 | jp.290372913.xyz | CDN | 6 | sing-box 1.13.14 |
| HK | 43.249.174.222 | hk.290372913.xyz | CDN | 6 | Debian 12，sing-box 1.13.13 |
| HK1 | 47.243.72.97 | hk1.290372913.xyz | direct | 4 | 阿里云 200GB/月 |
| HKCEPIN | 18.166.210.81 | hkcepin.290372913.xyz | CDN | 6 | Ubuntu 24.04，414MB+2GB Swap |

> ❌ SG（13.212.37.11）已废弃，域名已不解析。

### 文件结构
```
/root/singbox-eps-node/
├── .env                    # 环境变量（所有配置集中管理，gitignored）
├── config.json             # singbox 配置（自动生成）
├── deploy.py               # 部署入口（根目录）
├── cert/                   # SSL 证书（cert.pem/fullchain.pem + key.pem）
├── data/
│   ├── singbox.db          # SQLite 数据库（WAL 模式）
│   └── .port_lock          # 端口锁定文件
├── scripts/
│   ├── config.py           # 全局配置（唯一真相源）
│   ├── config_generator.py # sing-box config.json 生成器
│   ├── subscription_service.py # HTTPS 订阅服务（Base64/sing-box JSON/Clash YAML 三格式）
│   ├── cloudflare_proxy_rules.py # CF 规则维护（skip 规则 + TLS 1.2，不维护 ddos_l7 eoff）
│   ├── cdn_monitor.py      # CDN 优选 IP 监控
│   ├── sub_domain_monitor.py # sub-* 直连路径监控
│   ├── cert_manager.py     # 证书管理
│   ├── deploy_verify.py    # 部署后验证模块（8 项标准化验证）
│   ├── tg_bot.py           # Telegram 机器人
│   ├── logger.py           # 日志管理
│   ├── health_check.sh     # 健康检查（每 15 分钟，含 .env 巡检）
│   └── diagnose.sh         # 一键诊断脚本
├── logs/
└── backups/
```

---

## 三、核心模块

### config.py — 配置中心
- 全局配置唯一真相源，所有 IP/域名/凭据/路径从 .env 读取
- 服务器 IP 自动检测（`_detect_server_ip()`）
- 域名/IP 动态判断（`get_sub_domain()`）
- 端口硬编码锁定 + SHA256 校验和防篡改
- `DEPLOY_MODE` 显式设置最高优先级，fallback 用 `CF_DOMAIN.startswith('hk1.')` 判断（v4.15.2 铁律：**禁止用 COUNTRY_CODE**）
- `COUNTRY_CODE` 从 .env 读取（install.sh 基于 CF_DOMAIN 前缀推导，见下文）
- `.env` 解析优先 `python-dotenv`，降级时兼容历史 `KEY=  # 注释` 遗留格式
- TUIC 规避配置，SOCKS5 凭据从环境变量读取

### subscription_service.py — 订阅服务
- Flask 应用，监听 2087 端口
- 三格式订阅：Base64（V2rayN/NekoBox 等）、sing-box JSON（含路由规则，rule_set 格式）、Clash Meta YAML
- CDN 优选 IP 自动分配（每个协议独立 IP）
- CDN 纠错机制：`get_cdn_ip_for_protocol()` 连通性检测，连不上自动回退域名（Bug #57）
- SOCKS5 AI 路由规则（可选项，默认关闭）
- TUIC v5 端口配置
- 按月流量统计（SQLite 持久化，每月 14 号自动归零）
- `/api/traffic` JSON 接口，`/api/cdn-status` CDN 状态接口
- `subscription-userinfo` 响应头（v2rayN 不解析，新增 `/info` 端点兜底）

### config_generator.py — 服务端配置生成
- 6 个入站配置（CDN 模式）+ SOCKS5 本地代理
- 自动生成密码和 UUID
- AI SOCKS5 出站 + 路由规则
- 所有路径从 config.py 的 BASE_DIR/CERT_DIR 拼接
- 证书缺失时自动调用 cert_manager.py 生成自签名证书（必须含 SAN，否则 CF 回源 520）
- DNS 已迁移到 sing-box 新格式（`type/server`），显式写 `route.default_domain_resolver`
- 协议增删必须三层同步（见部署流程）

### cloudflare_proxy_rules.py — CF 规则维护
- `apply` 只维护 custom skip 规则和 TLS 1.2，确保删除 ddos_l7 override
- CF 免费版 DDoS L7 无法通过 skip 规则绕过
- WS 路径已改为非代理特征路径（`/api/v1/stream` `/api/v1/data`）以降低 ML 误报率
- CDN 节点始终使用主域名橙云代理，**不降级到 sub-***

### cdn_monitor.py — CDN 优选 IP 学习系统（v4.0 用户反馈驱动版）
**核心理念**：一切以用户反馈为准，服务器只做存活检测。

| 维度 | v3.x（旧） | v4.0（新） |
|------|-----------|-----------|
| 测试方式 | 全量 HTTP 延迟测试（250+次） | TCP 存活检测（~100 次） |
| 延迟判断 | 服务器主观测延迟 | 不测延迟，以用户反馈为准 |
| IP 优先级 | 外部 API+本地池公平竞争 | 用户 IP 优先，外部 IP 备胎 |
| 速度 | 几分钟 | 2 秒完成 |

**工作流程**：
1. 用户投喂 IP 池（config.py 的 `CDN_PREFERRED_IPS`）→ 真理来源
2. 外部 API 补充候选（仅当用户 IP 不足时）
3. TCP 存活检测（443 端口，3 秒超时）
4. 优先选用户 IP，不足再补外部 IP
5. 写入数据库（key: `vless_ws_cdn_ip` / `trojan_ws_cdn_ip`）

**自动同步**：cdn_monitor 每 30 分钟更新 IP → subscription_service 实时读取 → 用户更新订阅即可。

> ⚠️ v3.x 评分规则（数据源可信度分+排名加分+交叉验证+IP 段参考分）已废弃。
> ⚠️ HTTP 真实延迟测试已废弃，改为 TCP 存活检测。

### health_check.sh — 健康检查与自动恢复（每 15 分钟）
- **config.json 自愈**：缺失时自动运行 config_generator.py 恢复
- **JSON 语法校验**：损坏时自动重新生成
- **CF 全局设置漂移巡检**：`security_level/browser_check/bot_fight_mode/ssl/min_tls_version` 不符合自动修复
- 端口完整性校验、服务状态检查与自动重启
- 订阅接口可用性检查（从 config.py 读取 SUB_PORT）
- 防火墙状态检查、证书有效期检查、磁盘空间检查
- Swap 检查、iptables 流量计数器检查
- `.env` 已知问题检测（v4.15.10 新增）

### 三层自愈机制

| 层级 | 机制 | 说明 |
|------|------|------|
| 第 1 层 | systemd ExecStartPre | singbox 启动前自动检查 config.json，缺失则生成 |
| 第 2 层 | health_check.sh | 每 15 分钟检查 config.json+服务状态+CF 设置，异常自动恢复 |
| 第 3 层 | StartLimitBurst=5 | singbox 连续崩溃 30 秒内最多重启 5 次 |

> ⚠️ ExecStartPre 中禁止 `pkill -f "服务名.py"`（自杀陷阱），改用 `fuser -k 端口/tcp`。

### cert_manager.py — 证书管理
- Cloudflare API 源证书（15 年有效期）
- 自签证书备用（必须含 SAN：`openssl -addext "subjectAltName=DNS:域名"`，否则 CF 回源 520）
- 自动续签检查（acme.sh + cron，每月 1 号凌晨 3 点）
- iptables 持久化

### sub_domain_monitor.py — sub-* 直连路径监控（每 5 分钟）
- 监控 sub-* 灰云直连路径可用性
- 异常时告警

### deploy_verify.py — 部署后验证（v4.15.10 新增）
- 8 项标准化验证
- `deploy.py --fix/--verify/--all` 多模式

### tg_bot.py — Telegram 管理机器人
- 可用命令：/状态 /续签 /订阅 /重启 /优化 /设置住宅 /删除住宅
- `batch_update_env()` 批量更新 .env，避免多次服务重启
- 异常信息写日志不返回用户，Token 不打印

---

## 四、功能清单

### 1. HTTPS 订阅服务
- CDN 服务器 Base64: `https://sub-{CC}:2087/sub/{CC}`（JP/HK/HKCEPIN）
- CDN 服务器 Clash Meta YAML: `https://sub-{CC}:2087/clash/{CC}`
- CDN 服务器 sing-box JSON: `https://sub-{CC}:2087/singbox/{CC}`
- HK1 direct 订阅: `https://hk1.290372913.xyz:2087/sub/HK1` / `/clash/HK1` / `/singbox/HK1`；兼容旧路径 `/sub/hk` / `/clash/hk` / `/singbox/hk`
- 流量查询: `https://sub-{CC}:2087/api/traffic`（HK1 使用主域名）
- CDN 状态: `https://sub-{CC}:2087/api/cdn-status`（仅 CDN 服务器）
- ⚠️ 必须用域名访问，IP 访问证书不匹配

### 2. TUIC v5 协议（v4.15.0 加回，已启用）
- **协议原理**：基于 QUIC（UDP）传输，内置 TLS 1.3，TCP+UDP 双栈代理
- **配置参数**：
  - `congestion_control: bbr` — BBR 拥塞控制
  - `alpn: h3` — HTTP/3 ALPN 协商
  - `uuid + password` 认证（.env 读取，安装时自动生成）
  - 随机端口（10000-65535），避免固定端口被识别
- **与 Hysteria2 的区别**：
  - 无端口跳跃：QUIC 自带连接迁移（Connection ID）
  - 无 obfs 混淆：TUIC v5 指纹更低调
  - 不复用 443：独立随机端口，不与 VLESS-Reality 共享
  - TCP+UDP 双栈：同时代理 TCP 和 UDP 流量
- **证书复用**：使用 `cert/fullchain.pem`（与 CDN 协议共享自签证书）
- **一键回退**：HK 某 ISP 阻断 UDP 时，`ENABLE_TUIC=false` 可禁用

### 3. anyTLS 协议（v4.14.0 新增）
- TLS-in-TLS 加密，缓解 TLS-in-TLS 指纹问题
- 端口 2096，直连源站
- 凭据从 .env 读取（ANYTLS_PASSWORD）

### 4. CDN 优选 IP（v4.0 用户反馈驱动版）
- 用户投喂 IP 池（config.py 的 `CDN_PREFERRED_IPS`）→ 真理来源
- 外部 API 补充候选（仅当用户 IP 不足时）
- TCP 存活检测（443 端口，3 秒超时）
- 优先选用户 IP，不足再补外部 IP
- 30 分钟存活检测
- 评分算法：存活率评分 = alive_count / total_checks * 100

### 5. SOCKS5 AI 路由（v4.1.0 可选项）
- **触发条件**: `AI_SOCKS5_ROUTING=on`（默认 off）
- **AI 网站走 SOCKS5**: openai/anthropic/gemini/perplexity/google
- **X/推特/groK 排除**: 走正常代理
- **幕后路由，用户无需手动选择**
- **关闭时**: 所有流量走正常协议（VLESS/Trojan/TUIC），不经过 SOCKS5

### 6. 按月流量统计（v3.1.1 重构）
- **数据来源**: iptables 内核级流量计数器（sing-box 各入站端口，INPUT + OUTPUT 双向）
- **统计维度**: 所有 sing-box 入站端口的 TCP+UDP 流量总和
- 每月 14 号自动归零（更新 baseline，不清零 iptables 内核计数器）
- API: `/api/traffic`（返回 JSON）
- `subscription-userinfo` 响应头（v2rayN 不解析，新增 `/info` 端点兜底）

### 7. SSL 证书
- 优先级：fullchain.pem > cert.pem
- 自动续签: acme.sh + cron（每月 1 号凌晨 3 点）
- 所有引用点统一路径
- 自签证书必须含 SAN（否则 CF 回源 520）

### 8. BBR+FQ+CAKE 网络加速
- BBR: Google 拥塞控制，不依赖丢包
- FQ: 公平队列，BBR 的 pacing 依赖
- CAKE: 集成 FQ+PIE，防缓冲区膨胀，抗丢包
- 降级: 内核不支持 CAKE 时自动降级 FQ-PIE（`tc qdisc replace` 实际应用到网卡）
- 持久化: systemd 服务（cake-qdisc@ / fq-pie-qdisc@）

### 9. sing-box rule_set（1.12+ 格式）
- geoip/geosite 已移除，改用 rule_set 远程 .rs 规则集
- 客户端: geosite-cn.srs / geoip-cn.srs / geosite-geolocation-!cn.srs
- 服务端: 不需要 geoip/geosite（catch-all 处理 direct）

### 10. COUNTRY_CODE 防复发（v4.15.12）
install.sh 基于 CF_DOMAIN 前缀推导正确的 COUNTRY_CODE：
- `jp.*` → JP
- `hk.*` → HK
- `hk1.*` → HK1
- `hkcepin.*` → HKCEPIN

不再依赖 ipinfo.io 自动检测（曾导致 HKCEPIN/HK1 被错写为 HK，订阅路由 `/clash/HKCEPIN` 返回 404）。

---

## 五、.env 配置

### 必填
| 变量 | 说明 |
|------|------|
| SERVER_IP | 服务器 IP（留空自动检测） |
| CF_DOMAIN | Cloudflare 主域名（如 jp.290372913.xyz） |
| DEPLOY_MODE | 部署模式（cdn/direct，留空时 hk1.* 默认 direct） |

### 协议开关
| 变量 | 说明 |
|------|------|
| ENABLE_VLESS_REALITY | VLESS-Reality 开关 |
| ENABLE_TROJAN_TCP | Trojan-TCP 开关 |
| ENABLE_ANYTLS | anyTLS 开关 |
| ENABLE_TUIC | TUIC-v5 开关（v4.15.0 加回） |
| ENABLE_VLESS_WS_CDN | VLESS-WS-CDN 开关 |
| ENABLE_TROJAN_WS_CDN | Trojan-WS-CDN 开关 |

### 协议凭据（安装时自动生成，禁止明文写入文档）
| 变量 | 说明 |
|------|------|
| VLESS_UUID | VLESS Reality UUID |
| VLESS_WS_UUID | VLESS WS UUID |
| TROJAN_PASSWORD | Trojan 密码 |
| TUIC_UUID / TUIC_PASSWORD | TUIC v5 凭据 |
| ANYTLS_PASSWORD | anyTLS 密码 |
| REALITY_PRIVATE_KEY / REALITY_PUBLIC_KEY | Reality 密钥对 |
| REALITY_SHORT_ID | Reality Short ID（v4.15.8 从硬编码改为 .env 读取） |
| REALITY_DEST / REALITY_SNI | Reality 伪装目标（v4.15.8 从硬编码改为 .env 读取） |

### 端口配置
| 变量 | 说明 |
|------|------|
| TROJAN_TCP_PORT | Trojan-TCP 端口（随机 10000-65535） |
| TUIC_PORT | TUIC-v5 端口（随机 10000-65535，UDP） |
| SUB_PORT | 订阅服务端口（默认 2087） |

### 可选
| 变量 | 说明 |
|------|------|
| CF_API_TOKEN | Cloudflare API Token（37/40/48 字均合法，证书申请+规则维护） |
| CF_ZONE_ID | Cloudflare Zone ID |
| COUNTRY_CODE | 服务器标识（JP/HK/HK1/HKCEPIN，install.sh 基于 CF_DOMAIN 推导） |
| SUB_TOKEN | 订阅 Token |
| AI_SOCKS5_SERVER / PORT / USER / PASS | AI SOCKS5 凭据 |
| AI_SOCKS5_ROUTING | AI 路由开关（on/off，默认 off） |
| TG_BOT_TOKEN / TG_ADMIN_CHAT_ID | Telegram 机器人配置 |

### .env 书写规则
- 注释必须单独成行，禁止继续写 `KEY=value # 注释`
- 当前代码已兼容历史遗留的行内注释格式，但这只是兜底，不是推荐写法
- **CRLF 换行污染**：Windows → Linux 的 .env 文件行尾 `\r` 会导致 hex 校验失败，所有 .env 读取命令加 `tr -d "\r"`

---

## 六、部署流程

### 安装脚本子命令
| 命令 | 功能 |
|------|------|
| `bash install.sh` | 全新安装（自动优化系统+交互式配置） |
| `bash install.sh reinstall` | 重装操作系统（需 root 密码，装完自动重启） |
| `bash install.sh reset` | 重装 singbox 应用（保留配置和数据，客户端无需重配置） |
| `bash install.sh optimize` | 一键优化系统（BBR+FQ+CAKE 三合一，即时生效） |

### 部署入口
- `deploy.py`（根目录）：部署入口，支持 `--fix/--verify/--all` 多模式
- `scripts/deploy_verify.py`：部署后 8 项标准化验证

### 协议增删三层同步铁律（AGENTS.md 铁律 2）
协议增删必须三层同步：
1. **订阅层** `subscription_service.py`（Base64 URI + sing-box JSON + Clash YAML 三处生成 + CLIENT_CAPABILITIES + CDN_PROTOCOL_KEYS + cdn_status_api）
2. **服务端层** `config_generator.py`（入站块完全删除，不能条件保留 `if enable_xxx`）
3. **辅助脚本** `install.sh` + `health_check.sh` + `diagnose.sh` + `cdn_monitor.py` + `cloudflare_proxy_rules.py` + `diagnose_disconnect.py`（端口/防火墙/iptables/CDN IP/诊断字典）

- 加回协议时用 `grep -rn "ENABLE_xxx\|enable_xxx"` 扫描所有变量引用点，确认每处都有条件包裹
- 推荐 `*([{...}] if enable_xxx else [])` 解包语法
- 每次协议增删强制 `grep` 检查 `node_name("...")` 参数不能含空格（如 `"TUIC-v5"` 不是 `"TUIC v5"`）

### 本地代码修改未部署 = 线上不生效
改完必须走 `deploy.py` 全流程部署 → 重跑 config_generator → 重启服务。仅 SFTP 同步文件不算完成。

### 服务管理
```bash
systemctl restart singbox singbox-sub singbox-cdn  # 重启所有服务
systemctl status singbox singbox-sub singbox-cdn   # 查看状态
journalctl -u singbox-sub -f                       # 查看日志
```

### 证书管理
```bash
python3 /root/singbox-eps-node/scripts/cert_manager.py --cf-cert  # Cloudflare API 申请 15 年证书
python3 /root/singbox-eps-node/scripts/cert_manager.py --renew    # 手动续签
```

### CDN 优选 IP 手动更新
```bash
python3 /root/singbox-eps-node/scripts/cdn_monitor.py
```

### 卸载
```bash
systemctl stop singbox singbox-sub singbox-cdn
systemctl disable singbox singbox-sub singbox-cdn
rm /etc/systemd/system/singbox*.service /etc/systemd/system/cake-qdisc*.service /etc/systemd/system/fq-pie-qdisc*.service
systemctl daemon-reload
rm -rf /root/singbox-eps-node
netfilter-persistent save
```

---

## 七、故障排查

### CDN WS 验证标准 SOP（防假阳性，AGENTS.md 铁律 14）
```powershell
curl.exe -s -4 --max-time 10 -k --noproxy "*" -o NUL -w "%{http_code}" `
  -H "Upgrade: websocket" -H "Connection: Upgrade" `
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" `
  "https://{domain}:8443/api/v1/stream"
```
- **期望值**：`101`（∉403/520）
- **铁律**：
  - ❌ 禁止 `-o /dev/null`（Windows 不识别，假 403）
  - ❌ 禁止服务器自测（CF 拦服务器 IP，假 403）
  - ❌ 禁止单次 403 就判 CDN 损坏（CF 瞬断重试即可）
- **真实标准**：`tests/full_audit.py` 全 101 ✅；客户端实际能通 ✅

### CF SSL 模式
必须为 `full`（非 strict/full_strict），自签证书场景下 strict 导致 526。

### CF 全局设置漂移
免费版 Managed Rules 自动启用拦截设置。`health_check.sh` 每 15 分钟巡检 `security_level/browser_check/bot_fight_mode/ssl/min_tls_version`，不符合自动修复。

### L7 DDoS eoff 不作为 health_check 修复目标
`cloudflare_proxy_rules.py apply` 只维护 custom skip 规则和 TLS 1.2，确保删除 ddos_l7 override。CF 免费版 DDoS L7 无法通过 skip 规则绕过，WS 路径已改为非代理特征路径（`/api/v1/stream` `/api/v1/data`）以降低 ML 误报率。CDN 节点始终使用主域名橙云代理，不降级到 sub-*。

### 健康检查
```bash
bash /root/singbox-eps-node/scripts/health_check.sh  # 手动运行
```
每 15 分钟自动运行，检查端口/服务/订阅/防火墙/证书/磁盘/CF 设置。

### 编码铁律（避坑指南精选）
1. **HTTPS 订阅必须用域名访问**，禁止用 IP（证书不匹配，SEC_E_WRONG_PRINCIPAL）
2. **订阅端口必须在 CF CDN 支持列表**：443, 2053, 2083, 2087, 2096, 8443
3. **TUIC v5 使用随机端口**，不需要端口跳跃（QUIC 自带连接迁移）
4. **CDN IP 获取必须用指定 DNS**：222.246.129.80 / 59.51.78.210（湖南电信 DNS）或阿里 DoH
5. **测试必须模拟真实客户端环境**：禁止 `-k/--insecure`
6. **禁止硬编码 IP/域名/凭据/路径**：所有从 .env 读
7. **修改配置必须全局搜索所有引用文件**：`grep -r "关键字" scripts/ *.md`
8. **服务重启必须覆盖所有相关服务**：singbox + singbox-sub + singbox-cdn
9. **AI-SOCKS5 是幕后路由出站**，不是用户可见节点
10. **改代码必须同步更新文档**
11. **防火墙重置必须在端口跳跃之后**
12. **降级方案必须实际应用到网卡**：`tc qdisc replace dev $MAIN_IF root fq_pie`
13. **数据库连接必须在 finally 中关闭**
14. **异常信息禁止返回给用户**：logger.error 记录，返回通用错误
15. **禁止裸 except**：必须指定 Exception
16. **小内存 VPS 必须配 Swap**：414MB 机器创建 2GB Swap
17. **日志必须配 logrotate**：daily + rotate 7 + maxsize 50M
18. **免费版 CF 禁止主动创建 DDoS L7 override**（v4.12.12 教训）

---

## 八、已删除协议清单（防复发）

> 以下协议/功能已从 v4.15.13 架构中移除，文档中禁止恢复描述，AI 接手时若发现引用必须删除。

| 协议/功能 | 删除版本 | 原因 | 替代方案 |
|----------|----------|------|----------|
| **VLESS-gRPC** | v4.15.0 | 与 TUIC-v5 重叠，gRPC 指纹特征明显 | TUIC-v5（QUIC 多路复用） |
| **VLESS-HTTPUpgrade-CDN** | v4.14.0 | 故障最多，兼容最窄 | VLESS-WS-CDN |
| **TUIC v5**（曾下线） | v4.14.0 下线 → v4.15.0 加回 | UDP 易被 QoS，QUIC 被 ISP 阻断 | 现已重新启用，文档原标"已下线"是错的 |
| **CDN_EDGE_FALLBACK** | v4.15.6 移除（v4.15.11 彻底） | 服务器从 AWS/阿里云 IP 测 CF WS 永远假阴性（CF L7 DDoS 只拦中国 ISP，不拦服务器 IP）→ 探针从未触发降级 → 用户拿到死节点 | CDN 节点始终使用主域名橙云代理，不降级到 sub-* |
| **旧 WS 路径 `/vless-ws` `/trojan-ws`** | v4.15.11 | 代理特征明显，CF L7 DDoS ML 模型识别率高 | `/api/v1/stream` `/api/v1/data`（非代理特征路径） |
| **HYSTERIA2** | 早期版本 | 已废弃，保留 .env 变量仅为兼容 | TUIC-v5 |
| **geoip/geosite** | sing-box 1.12+ | 格式移除 | rule_set 远程 .rs 规则集 |

---

## 九、版本历史（最近）

| 版本 | 日期 | 更新 |
|------|------|------|
| v4.15.13 | 2026-07-03 | CDN 节点名恢复 `-CDN` 后缀；Cloudflare 自愈改为 PUT phase entrypoint 防止旧规则漂回；确认 CDN 节点不使用 sub-* 降级，外部 WS 6/6 HTTP 101，full_audit ALL OK |
| v4.15.12 | 2026-07-03 | 审查修复 5 项遗留问题：删除废弃 test_cdn_edge_fallback.py；full_audit.py WS 路径更新；cdn_status_api() 去掉不一致后缀；deploy.py --fix 新增孤儿 CDN_EDGE_FALLBACK 变量清理；远程服务器 .env 清理 |
| v4.15.11 | 2026-07-02 | 移除服务器端 CDN 健康探针和假降级（`_probe_cdn_ws()` / `is_cdn_edge_blocked()` / `_cdn_edge_fallback_mode()` / `CDN_EDGE_FALLBACK` 全部移除）；CDN WS 路径改名 `/api/v1/stream` `/api/v1/data`；Skip Rule 补充 hkcepin 域名 |
| v4.15.10 | 2026-07-02 | 综合修复四台服务器；防复发架构升级（deploy.py 多模式 + deploy_verify.py 8 项验证 + health_check.sh .env 检测）；项目瘦身；CDN 假阳性根除（AGENTS.md 新增 CDN WS 验证 SOP） |
| v4.15.8 | 2026-07-02 | 修复 Reality 连接彻底失败（REALITY_SHORT_ID 未写入 .env）；config.py REALITY_SHORT_ID/DEST/SNI 从硬编码改为 .env 读取；install.sh REALITY_SHORT_ID 持久化 |
| v4.15.6 | 2026-06-30 | 订阅/CDN 反复失效修复；cloudflare_proxy_rules.py apply 删除 ddos_l7 override；CDN_EDGE_FALLBACK 自动降级（后于 v4.15.11 移除） |
| v4.15.0 | - | 引入双模式（cdn/direct）；TUIC-v5 加回；VLESS-gRPC 删除 |
| v4.14.0 | 2026-06-27 | 精简协议；anyTLS 新增；VLESS-HTTPUpgrade-CDN 删除；TUIC v5 曾下线 |

---

## 十、使用说明

### 安装
```bash
bash install.sh              # 全新安装
bash install.sh reset        # 重装 singbox 应用（保留配置）
bash install.sh optimize      # 一键优化系统
bash install.sh reinstall     # 重装操作系统（需 root 密码）
```

### 流量统计
- 首页: `https://sub-{CC}:2087/`
- API: `https://sub-{CC}:2087/api/traffic`
- 重置: 每月 14 号自动归零

### Telegram 机器人
.env 中配置 `TG_BOT_TOKEN` 和 `TG_ADMIN_CHAT_ID`，可用命令：/状态 /续签 /订阅 /重启 /优化 /设置住宅 /删除住宅

---

# Clash 订阅生成铁律

> 修改 `scripts/subscription_service.py` 的 Clash 相关生成逻辑时必须遵守。

## 1. url-test 策略组三件套与测速方法
- `lazy: false` — 后台持续测速，严禁设为 `true` 导致锁死坏节点
- `tolerance: 150` — 电信网络波动容忍度，禁止低于 100
- `interval: 60` — 60 秒测速一次，严禁设为 600s 导致卡顿 10 分钟
- `url: http://cp.cloudflare.com/generate_204` — HTTP 协议避免 TLS 握手损耗
- `timeout: 5000` — 测速超时 5 秒

## 2. 规则 MATCH 必须指向 select（节点选择）
- MATCH 规则必须指向 `节点选择`（select 组），绝对不能直接指向 `自动选择`（url-test 组）
- `节点选择` 的首个 proxy 必须是 `自动选择`，用户可在 UI 自由切换

## 3. 高风险参数禁止恢复
- `keep-alive-interval` — 丢包隧道上适得其反
- `tcp-concurrent` — 频繁触发连接 RST
- `unified-delay` — 干扰判断

## 4. 客户端协议兼容矩阵
v4.15.14 默认 6 节点（CDN 模式）/ 4 节点（direct 模式）。

| 客户端 | 节点数 | 说明 |
|--------|--------|------|
| Clash / sing-box / NekoBox | 6 / 4 | 完整协议栈 |
| v2rayN / v2rayNG / Shadowrocket | 6 / 4 | 默认完整订阅，URI 参数做兼容优化 |
| Quantumult X / Surge / Loon / v2Box | 4 / 2 | 明确识别为纯 Xray 兼容客户端，不输出 anyTLS/TUIC |
| `?client=xray` / `?client=standard` | 4 / 2 | 手动兜底，剔除 anyTLS/TUIC（如客户端不稳定） |
| `?client=full` | 6 / 4 | 强制完整节点 |

- **禁止未经用户确认默认删节点**
- Shadowrocket 节点可用性判断优先看 CONNECT/HTTP 测速和真实连接；ICMP 仅作裸线路参考

## 5. 订阅流量统计
- iptables 必须 INPUT + OUTPUT 双向计数：INPUT 用 `--dport`，OUTPUT 用 `--sport`
- UDP 端口（TUIC v5 QUIC 协议）独立建规则
- `get_iptables_traffic_bytes()` 必须 INPUT+OUTPUT 求和，否则下载流量被低估 50%
- 每月 14 号由订阅服务更新数据库 baseline，不清零 iptables 内核计数器

## 6. v2rayN 流量显示限制
v2rayN 不解析 `subscription-userinfo` header，订阅更新只显示"成功: N 个节点"，永远不显示流量。
- 新增 `/info` 端点（v2rayN 浏览器能开）
- Base64 头部插入流量注释（部分客户端可读，作为补充）
- **禁止期望 v2rayN 通过 subscription 显示流量**

## 7. HTTP header 不能含非 ASCII 字符
Flask `Response.headers` 只能设置 latin-1 编码的值。
- `Content-Disposition: attachment; filename=香港订阅.txt` 会触发 UnicodeEncodeError 导致 500
- 修复：RFC 5987 `filename*=UTF-8''URL编码`，或 profile-title 改为纯 ASCII
- **任何通过 header 传递中文字符必须 URL-encode**
