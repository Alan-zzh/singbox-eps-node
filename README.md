# Singbox EPS Node

全自动CDN优选IP管理 + 多协议代理订阅生成系统，一条命令完成部署，客户端导入订阅即可使用。

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

## 子命令

```bash
bash install.sh              # 全新安装（自动优化系统+交互式配置）
bash install.sh reinstall    # 重装操作系统（需输入root密码，装完自动重启）
bash install.sh reset        # 重装singbox应用（保留配置和数据，客户端无需重配）
bash install.sh optimize     # 一键优化系统（BBR+FQ+CAKE三合一，即时生效）
```

## 功能

- **5协议全覆盖**: VLESS-Reality / VLESS-WS-CDN / VLESS-HTTPUpgrade-CDN / Trojan-WS-CDN / Hysteria2
- **CDN优选IP自动获取**: 每小时通过指定DNS解析最优Cloudflare边缘IP
- **HY2无感端口跳跃**: UDP+TCP双协议保障，端口被封自动切换，不断线
- **AI流量自动分流**: 配置SOCKS5后，AI网站流量自动走住宅IP，用户无感
- **双格式订阅**: 根据客户端自动返回Base64或sing-box JSON
- **Telegram管理机器人**: 远程查看状态、更新CDN、配置AI住宅代理
- **按月流量统计**: 每月14号自动归零，首页和API可查看
- **BBR+FQ+CAKE加速**: 海外代理最优方案，即时生效无需重启
- **健康检查自动恢复**: 每5分钟检测，异常自动重启

## 节点列表

| 节点 | 协议 | 连接方式 |
|------|------|----------|
| {CC}-VLESS-Reality | VLESS | 直连 IP:443 |
| {CC}-VLESS-WS-CDN | VLESS+WS | CDN优选IP:8443 |
| {CC}-VLESS-HTTPUpgrade-CDN | VLESS+HTTPUpgrade | CDN优选IP:2053 |
| {CC}-Trojan-WS-CDN | Trojan+WS | CDN优选IP:2083 |
| {CC}-Hysteria2 | Hysteria2 | 直连 IP:443，端口跳跃21000-21200 |

## 环境变量

安装后编辑 `/root/singbox-eps-node/.env`：

| 变量 | 说明 | 必填 |
|------|------|------|
| CF_DOMAIN | Cloudflare域名 | ✅ |
| SERVER_IP | 服务器IP（留空自动检测） | ❌ |
| CF_API_TOKEN | Cloudflare API Token（证书申请） | ❌ |
| AI_SOCKS5_SERVER | AI住宅IP SOCKS5地址 | ❌ |
| AI_SOCKS5_PORT | AI住宅IP SOCKS5端口 | ❌ |

协议密码（VLESS_UUID、TROJAN_PASSWORD等）安装时自动生成，通常无需手动填写。

## 服务管理

```bash
systemctl restart singbox singbox-sub singbox-cdn  # 重启所有服务
systemctl status singbox singbox-sub singbox-cdn   # 查看状态
journalctl -u singbox-sub -f                       # 查看日志
```

## 技术文档

完整技术文档见 [TECHNICAL_DOC.md](TECHNICAL_DOC.md)，包含架构说明、配置管理、编码铁律、Bug修复历史。

## 许可证

MIT License
