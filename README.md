# Singbox EPS Node - 全自动代理订阅系统

## 项目简介
全自动CDN优选IP管理 + 多协议订阅生成系统，支持VLESS-Reality、VLESS-WS-CDN、VLESS-HTTPUpgrade-CDN、Trojan-WS-CDN、Hysteria2、SOCKS5等协议。

## 核心功能
- **CDN优选IP自动获取**：每小时自动从国内测速网站获取最优Cloudflare边缘IP
- **IP身份伪装**：使用HTTP Header Spoofing技术，让海外服务器获取国内最优IP
- **多协议订阅**：自动生成Base64和sing-box JSON格式订阅
- **客户端自动识别**：根据User-Agent自动返回对应格式
- **SOCKS5 AI协议牵制**：集成外部SOCKS5节点实现AI流量自动分流
- **HY2端口跳跃**：支持无感端口跳跃，端口被封自动切换，无需断线重连
- **一键部署**：新VPS只需一条命令即可完成全部部署

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/gulucat/singbox-eps-node/main/install.sh)
```

安装完成后，编辑 `/root/singbox-eps-node/.env` 填入你的配置。

## 节点列表
1. {CC}-VLESS-Reality (直连)
2. {CC}-VLESS-WS-CDN (CDN优选IP)
3. {CC}-VLESS-HTTPUpgrade-CDN (CDN优选IP)
4. {CC}-Trojan-WS-CDN (CDN优选IP)
5. {CC}-Hysteria2 (直连，端口跳跃)
6. AI-SOCKS5 (外部SOCKS5节点，可选)

## 端口配置
| 端口 | 协议 | 用途 |
|------|------|------|
| 443 | VLESS-Reality/Hysteria2 | 直连节点 |
| 8443 | VLESS-WS-CDN | CDN节点 |
| 2053 | VLESS-HTTPUpgrade-CDN | CDN节点 |
| 2083 | Trojan-WS-CDN | CDN节点 |
| 2087 | 订阅服务 | HTTPS订阅（CDN支持端口） |
| 21000-21200 | Hysteria2端口跳跃 | 无感切换不掉线 |

## 环境变量配置
复制 `.env.example` 为 `.env` 并填写：

```bash
# 必填
SERVER_IP=                    # 服务器公网IP（留空自动检测）
CF_DOMAIN=                    # Cloudflare域名（用于订阅和CDN）

# 协议密码（安装时自动生成，也可手动指定）
VLESS_UUID=                   # VLESS Reality UUID
VLESS_WS_UUID=                # VLESS WS UUID
TROJAN_PASSWORD=              # Trojan密码
HYSTERIA2_PASSWORD=           # Hysteria2密码
REALITY_PRIVATE_KEY=          # Reality私钥
REALITY_PUBLIC_KEY=           # Reality公钥

# 可选
CF_API_TOKEN=                 # Cloudflare API Token（用于申请15年证书）
AI_SOCKS5_SERVER=             # AI住宅IP SOCKS5服务器
AI_SOCKS5_PORT=               # AI住宅IP SOCKS5端口
AI_SOCKS5_USER=               # AI住宅IP SOCKS5用户名
AI_SOCKS5_PASS=               # AI住宅IP SOCKS5密码
SUB_TOKEN=                    # 订阅Token（留空则无需Token）
COUNTRY_CODE=JP               # 国家代码
```

## 服务管理
```bash
systemctl status singbox        # Singbox内核
systemctl status singbox-sub    # 订阅服务
systemctl status singbox-cdn    # CDN监控

systemctl restart singbox       # 重启Singbox
systemctl restart singbox-sub   # 重启订阅服务
systemctl restart singbox-cdn   # 重启CDN监控
```

## 技术栈
- Python 3 + Flask
- SQLite数据库
- systemd服务管理
- Cloudflare CDN
- IP身份伪装技术
- iptables端口跳跃

## 注意事项
1. `.env` 文件包含敏感信息，请勿泄露或上传到公开仓库
2. CDN优选IP每小时自动更新
3. 订阅服务使用HTTPS（域名+CDN支持端口）
4. HY2端口跳跃支持无感切换，UDP+TCP双协议保障
5. 所有节点名称自动包含地区代码前缀
