# Singbox EPS Node

**当前版本**: `v4.11.0`

一键部署 sing-box 多协议节点 + 自动生成订阅 + 自动维护 CDN 优选 IP + 健康检查自愈。

## 接手顺序

1. [AGENTS.md](AGENTS.md) — 项目规则唯一入口
2. [project_snapshot.md](project_snapshot.md) — 当前项目真实状态
3. [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md) — 历史踩坑记录
4. [CHANGELOG.md](CHANGELOG.md) — 最近变更
5. [VERSION.md](VERSION.md) — 当前版本号

## 文档分工

| 文件 | 职责 |
|------|------|
| [AGENTS.md](AGENTS.md) | 项目规则、行为规范、重点禁忌 |
| [README.md](README.md) | 项目入口：概况、安装、命令 |
| [project_snapshot.md](project_snapshot.md) | 当前真实状态快照 |
| [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md) | 踩坑病历 |
| [CHANGELOG.md](CHANGELOG.md) | 用户可感知变更 |
| [VERSION.md](VERSION.md) | 版本号锚点 |
| [docs/technical/](docs/technical/) | 功能模块技术细节 |
| [docs/plans/](docs/plans/) | 计划与方案 |
| [docs/archive/](docs/archive/) | 过时归档 |

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

## 子命令

```bash
bash install.sh              # 全新安装（自动优化系统+交互式配置）
bash install.sh reinstall    # 重装操作系统（需输入root密码，装完自动重启）
bash install.sh reset        # 重装 singbox 应用（保留配置和数据）
bash install.sh optimize     # 只做系统优化（BBR + FQ）
```

## 当前功能

- **7 协议**：VLESS-Reality / VLESS-gRPC / Trojan-TCP / VLESS-WS / VLESS-HTTPUpgrade / Trojan-WS / Hysteria2
- HTTPS 订阅：Base64 + sing-box JSON
- CDN 优选 IP 自动维护（IP 池 10-15 个/服务器，多 C 段分散，按评分排序淘汰高延迟IP，订阅自动同步优选IP）
- CDN 阻断自动检测与切换（403/1020 拦截检测 + 冷却机制 + 信号文件联动订阅刷新）
- 健康检查 + 一键诊断
- 按月流量统计
- TCP Fast Open 优化（降低连接延迟 30-50ms）
- BBR + FQ 网络优化
- sing-box 版本：1.15.0

## 节点列表

| 节点 | 协议 | 连接方式 |
|------|------|----------|
| `{CC}-VLESS-Reality` | VLESS | 直连 `IP:443` |
| `{CC}-VLESS-gRPC` | VLESS | 直连 `IP:随机端口` |
| `{CC}-Trojan-TCP` | Trojan | 直连 `IP:随机端口` |
| `{CC}-VLESS-WS-CDN` | VLESS + WS | CDN 优选 IP `:8443` |
| `{CC}-VLESS-HTTPUpgrade-CDN` | VLESS + HTTPUpgrade | CDN 优选 IP `:2053` |
| `{CC}-Trojan-WS-CDN` | Trojan + WS | CDN 优选 IP `:2083` |
| `{CC}-Hysteria2` | Hysteria2 | 直连 `IP:443`，端口跳跃 `21000-21200` |

## 环境变量

安装后编辑 `/root/singbox-eps-node/.env`，参考 [.env.example](.env.example)。

| 变量 | 说明 | 必填 |
|------|------|------|
| `CF_DOMAIN` | Cloudflare 域名 | 是 |
| `SERVER_IP` | 服务器公网 IP，留空可自动检测 | 否 |
| `CF_API_TOKEN` | Cloudflare API Token，用于证书申请 | 否 |
| `VLESS_GRPC_PORT` | VLESS-gRPC 端口（默认随机生成） | 否 |
| `TROJAN_TCP_PORT` | Trojan-TCP 端口（默认随机生成） | 否 |
| `AI_SOCKS5_SERVER` | AI 住宅代理地址 | 否 |
| `AI_SOCKS5_PORT` | AI 住宅代理端口 | 否 |
| `AI_SOCKS5_ROUTING` | `on/off`，默认 `off` | 否 |

## 常用命令

```bash
systemctl restart singbox singbox-sub singbox-cdn
systemctl status singbox singbox-sub singbox-cdn
journalctl -u singbox -n 50 --no-pager
bash /root/singbox-eps-node/scripts/diagnose.sh
```

## 许可证

MIT License
