# Singbox EPS Node

全自动CDN优选IP管理 + 多协议代理订阅生成系统，一条命令完成部署，客户端导入订阅即可使用。

## 功能特性

- **一键部署**：新VPS只需一条命令，自动安装依赖、生成密钥、申请证书、配置服务
- **CDN优选IP自动获取**：每小时通过指定DNS（湖南电信）解析最优Cloudflare边缘IP，确保中国用户低延迟
- **IP身份伪装**：使用HTTP Header Spoofing技术，让海外服务器获取国内最优CDN IP
- **5协议全覆盖**：VLESS-Reality（直连）、VLESS-WS-CDN、VLESS-HTTPUpgrade-CDN、Trojan-WS-CDN、Hysteria2（端口跳跃）
- **HY2无感端口跳跃**：UDP+TCP双协议保障，端口被封自动切换，无需断线重连
- **AI流量自动分流**：配置SOCKS5后，AI网站流量自动走住宅IP，用户无感，无需手动选择
- **双格式订阅**：根据客户端User-Agent自动返回Base64或sing-box JSON格式
- **Telegram管理机器人**：远程查看状态、更新CDN优选IP、配置AI住宅代理
- **健康检查自动恢复**：每5分钟检测服务状态，异常自动重启
- **按月流量统计**：每月14号自动归零，首页和API接口可查看用量
- **BBR+FQ+CAKE三合一加速**：海外代理最优方案，即时生效无需重启
- **一键重装操作系统**：输入密码两次确认，自动检测OS版本，装完自动重启

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

## 安装脚本子命令

```bash
bash install.sh              # 全新安装（自动优化系统+交互式配置）
bash install.sh reinstall    # 一键重装操作系统（需输入root密码，装完自动重启）
bash install.sh reset        # 一键重装singbox应用（保留配置和数据，客户端无需重配）
bash install.sh optimize     # 一键优化系统（BBR+FQ+CAKE三合一，即时生效无需重启）
```

- **reinstall**: 重装整个操作系统（清除硬盘所有数据），需输入root密码两次确认，自动检测当前OS版本重装为相同版本，重装后需重新运行 `bash install.sh` 部署singbox
- **reset**: 只重装singbox应用，保留.env配置、流量统计数据和SSL证书，客户端无需重新配置

安装完成后，编辑 `/root/singbox-eps-node/.env` 填入你的配置：

```bash
# 必填
CF_DOMAIN=your.domain.com        # Cloudflare域名（用于CDN和SSL证书）

# 协议密码（安装时自动生成，通常无需手动填写）
# VLESS_UUID=
# VLESS_WS_UUID=
# TROJAN_PASSWORD=
# HYSTERIA2_PASSWORD=
# REALITY_PRIVATE_KEY=
# REALITY_PUBLIC_KEY=
```

配置完成后重启所有服务：

```bash
systemctl restart singbox singbox-sub singbox-cdn
```

## 节点列表

5个用户可见节点：

| 序号 | 节点名称 | 协议 | 连接方式 | 说明 |
|------|----------|------|----------|------|
| 1 | {CC}-VLESS-Reality | VLESS | 直连 | 服务器IP:443 |
| 2 | {CC}-VLESS-WS-CDN | VLESS+WS | CDN优选IP | 优选IP:8443 |
| 3 | {CC}-VLESS-HTTPUpgrade-CDN | VLESS+HTTPUpgrade | CDN优选IP | 优选IP:2053 |
| 4 | {CC}-Trojan-WS-CDN | Trojan+WS | CDN优选IP | 优选IP:2083 |
| 5 | {CC}-Hysteria2 | Hysteria2 | 直连 | 服务器IP:443，端口跳跃21000-21200 |

AI-SOCKS5幕后路由说明：
- AI-SOCKS5不是用户可见节点，是幕后路由出站
- 仅出现在sing-box JSON的outbounds和route.rules中
- AI网站流量自动走SOCKS5代理，用户无感，无需手动选择
- 不出现在Base64订阅链接、selector可选列表或首页节点列表中

## 端口配置

| 端口 | 协议 | CDN支持 | 用途 |
|------|------|---------|------|
| 443 | VLESS-Reality / Hysteria2 | 是 | 直连节点 |
| 8443 | VLESS-WS-CDN | 是 | CDN节点 |
| 2053 | VLESS-HTTPUpgrade-CDN | 是 | CDN节点 |
| 2083 | Trojan-WS-CDN | 是 | CDN节点 |
| 2087 | HTTPS订阅服务 | 是 | 订阅链接（走CDN） |
| 21000-21200 | Hysteria2端口跳跃 | 否 | iptables DNAT到443（UDP+TCP双协议） |

Cloudflare CDN支持的HTTPS端口：443, 2053, 2083, 2087, 2096, 8443

## 环境变量配置

复制 `.env.example` 为 `.env` 并填写：

```bash
cp .env.example .env
```

### 必填

| 变量 | 说明 |
|------|------|
| `SERVER_IP` | 服务器公网IP，留空则自动检测 |
| `CF_DOMAIN` | Cloudflare域名，用于CDN和SSL证书 |

### 协议密码（安装时自动生成）

| 变量 | 说明 |
|------|------|
| `VLESS_UUID` | VLESS Reality UUID |
| `VLESS_WS_UUID` | VLESS WS / HTTPUpgrade UUID |
| `TROJAN_PASSWORD` | Trojan-WS密码 |
| `HYSTERIA2_PASSWORD` | Hysteria2密码 |
| `REALITY_PRIVATE_KEY` | Reality私钥 |
| `REALITY_PUBLIC_KEY` | Reality公钥 |

### 可选

| 变量 | 说明 |
|------|------|
| `CF_API_TOKEN` | Cloudflare API Token，用于申请15年SSL证书 |
| `COUNTRY_CODE` | 国家代码，安装时自动检测（US/JP/SG等） |
| `SUB_TOKEN` | 订阅Token，留空则无需Token验证 |
| `AI_SOCKS5_SERVER` | AI住宅IP SOCKS5服务器地址 |
| `AI_SOCKS5_PORT` | AI住宅IP SOCKS5端口 |
| `AI_SOCKS5_USER` | AI住宅IP SOCKS5用户名 |
| `AI_SOCKS5_PASS` | AI住宅IP SOCKS5密码 |
| `TG_BOT_TOKEN` | Telegram Bot Token |
| `TG_ADMIN_CHAT_ID` | 管理员Chat ID |

## 服务管理

```bash
# 查看状态
systemctl status singbox        # sing-box内核
systemctl status singbox-sub    # 订阅服务
systemctl status singbox-cdn    # CDN监控

# 重启服务（修改配置后必须重启所有相关服务）
systemctl restart singbox singbox-sub singbox-cdn

# 健康检查
bash /root/singbox-eps-node/scripts/health_check.sh

# 查看日志
journalctl -u singbox -f        # sing-box日志
journalctl -u singbox-sub -f    # 订阅服务日志
journalctl -u singbox-cdn -f    # CDN监控日志
```

## 项目结构

```
singbox-eps-node/
├── .env.example          # 环境变量模板
├── .gitignore            # Git忽略规则
├── install.sh            # 一键安装脚本
├── README.md             # 项目说明
├── TECHNICAL_DOC.md      # 技术文档
├── scripts/
│   ├── config.py         # 全局配置（唯一真相源）
│   ├── config_generator.py  # sing-box配置生成器
│   ├── subscription_service.py  # HTTPS订阅服务
│   ├── cert_manager.py   # 证书管理+端口跳跃
│   ├── cdn_monitor.py    # CDN优选IP监控
│   ├── tg_bot.py         # Telegram管理机器人
│   ├── logger.py         # 日志管理
│   └── health_check.sh   # 健康检查与自动恢复
├── docs/
│   ├── architecture.md   # 架构说明
│   └── usage.md          # 使用指南
└── data/                 # 运行时数据（gitignore）
```

## 避坑指南

以下是从实际部署中提炼的关键注意事项，每一条都来自真实的踩坑经历：

1. **HTTPS订阅必须用域名访问**：SSL证书颁发给域名，用IP访问时证书域名不匹配，V2rayN等客户端会拒绝连接。订阅链接格式必须为 `https://{域名}:2087/sub/{国家代码}`

2. **订阅端口必须在CDN支持列表中**：Cloudflare CDN只代理 443/2053/2083/2087/2096/8443 端口的HTTPS流量。使用其他端口（如9443）会导致CDN不转发，域名访问超时

3. **HY2端口跳跃必须UDP+TCP双规则**：UDP是QUIC核心协议，TCP是降级兜底。只设一种时，该协议被封则HY2完全不可用。iptables必须同时设置UDP和TCP的DNAT规则

4. **CDN IP获取必须用指定DNS**：必须使用 222.246.129.80 或 59.51.78.210（湖南电信DNS），它们返回对中国用户延迟最低的Cloudflare IP。使用日本等其他地区DNS会返回对中国延迟高的IP

5. **测试必须模拟真实客户端**：curl -k/--insecure 跳过证书验证能通，不代表V2rayN等客户端能通。测试HTTPS服务时禁止使用-k参数，必须验证SSL证书匹配

6. **禁止硬编码IP/域名/密码**：所有IP、域名、端口、凭据必须从.env读取，路径从config.py拼接。硬编码会导致新VPS部署时必须手动修改大量代码，极易遗漏

7. **修改配置必须全局搜索所有引用文件**：一个配置值可能被subscription_service.py、config_generator.py、tg_bot.py、health_check.sh等多个文件引用。修改时必须grep全局搜索，确保所有引用点同步更新

8. **服务重启必须覆盖所有相关服务**：修改任何配置后，必须同时重启 singbox + singbox-sub + singbox-cdn 三个服务。只重启其中一个会导致配置不一致

9. **.env文件包含敏感信息，禁止上传公开仓库**：.env中包含协议密码、API Token、SOCKS5凭据等敏感信息。.gitignore已排除.env，切勿手动上传

10. **SOCKS5凭据为空时不生成SOCKS5入站**：AI_SOCKS5_SERVER等变量未配置时，不应生成SOCKS5入站和路由规则。未配置SOCKS5时AI流量走默认出站

11. **端口跳跃目标端口必须与listen_port一致**：iptables DNAT的目标端口必须与sing-box配置中HY2的listen_port（当前为443）一致。目标端口不一致会导致端口跳跃功能完全无效

12. **防火墙重置必须在端口跳跃规则之前**：iptables -F会清空所有规则。如果先设置端口跳跃再重置防火墙，端口跳跃规则会被清除。安装脚本执行顺序：防火墙 -> 端口跳跃 -> 服务启动

## 技术栈

- **代理内核**：sing-box
- **后端**：Python 3 + Flask
- **数据库**：SQLite
- **服务管理**：systemd
- **CDN**：Cloudflare
- **证书**：Let's Encrypt / Cloudflare Origin CA
- **端口跳跃**：iptables DNAT
- **IP优选**：指定DNS解析 + HTTP Header Spoofing

## 许可证

MIT License