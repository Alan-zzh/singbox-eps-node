# Singbox EPS Node

**当前版本**: `v4.3.9`

这个项目的目标很简单：

- 一键部署 sing-box 多协议节点
- 自动生成订阅
- 自动维护 CDN 优选 IP
- 出问题时能靠健康检查和诊断脚本尽快自愈或定位

如果你是第一次接手这个项目，先看下面这几个文件，不要直接埋头改代码。

## 接手顺序

1. [project_snapshot.md](project_snapshot.md)
2. [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md)
3. [CHANGELOG.md](CHANGELOG.md)
4. [VERSION.md](VERSION.md)
5. [TECHNICAL_DOC.md](TECHNICAL_DOC.md)

## 文档分工

- [README.md](README.md)
  当前总入口。只放项目概况、安装入口、文档地图、常用命令。
- [project_snapshot.md](project_snapshot.md)
  当前版本做成了什么、线上大概是什么状态、最近修了哪些关键问题。
- [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md)
  病历本。记录真实踩坑、复发根因、禁止再犯的教训。
- [CHANGELOG.md](CHANGELOG.md)
  正式更新日志，只写“这次版本改了什么”。
- [VERSION.md](VERSION.md)
  当前项目版本号，供脚本和接手排查时统一参考。
- [TECHNICAL_DOC.md](TECHNICAL_DOC.md)
  全量技术说明，包含架构、协议、配置、部署、诊断、编码铁律。

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

## 子命令

```bash
bash install.sh              # 全新安装（自动优化系统+交互式配置）
bash install.sh reinstall    # 重装操作系统（需输入root密码，装完自动重启）
bash install.sh reset        # 重装 singbox 应用（保留配置和数据）
bash install.sh optimize     # 只做系统优化（BBR + FQ-PIE/CAKE）
```

## 当前功能

- 5 协议：VLESS-Reality / VLESS-WS / VLESS-HTTPUpgrade / Trojan-WS / Hysteria2
- HTTPS 订阅：Base64 + sing-box JSON
- CDN 优选 IP 自动维护（IP 池 10-15 个/服务器，多 C 段分散）
- CDN 阻断自动检测与切换（403/1020 拦截检测 + 冷却机制）
- 健康检查 + 一键诊断
- 按月流量统计
- 可选 AI SOCKS5 分流
- BBR + FQ-PIE/CAKE 网络优化

## 节点列表

| 节点 | 协议 | 连接方式 |
|------|------|----------|
| `{CC}-VLESS-Reality` | VLESS | 直连 `IP:443` |
| `{CC}-VLESS-WS-CDN` | VLESS + WS | CDN 优选 IP `:8443` |
| `{CC}-VLESS-HTTPUpgrade-CDN` | VLESS + HTTPUpgrade | CDN 优选 IP `:2053` |
| `{CC}-Trojan-WS-CDN` | Trojan + WS | CDN 优选 IP `:2083` |
| `{CC}-Hysteria2` | Hysteria2 | 直连 `IP:443`，端口跳跃 `21000-21200` |

## 环境变量

安装后编辑 `/root/singbox-eps-node/.env`。

推荐先参考 [.env.example](.env.example)。

最常用的几个变量：

| 变量 | 说明 | 必填 |
|------|------|------|
| `CF_DOMAIN` | Cloudflare 域名 | ✅ |
| `SERVER_IP` | 服务器公网 IP，留空可自动检测 | ❌ |
| `CF_API_TOKEN` | Cloudflare API Token，用于证书申请 | ❌ |
| `AI_SOCKS5_SERVER` | AI 住宅代理地址 | ❌ |
| `AI_SOCKS5_PORT` | AI 住宅代理端口 | ❌ |
| `AI_SOCKS5_ROUTING` | `on/off`，默认 `off` | ❌ |

协议密码和 UUID 会在安装时自动生成，通常不需要手填。

## 常用命令

```bash
systemctl restart singbox singbox-sub singbox-cdn
systemctl status singbox singbox-sub singbox-cdn
journalctl -u singbox -n 50 --no-pager
bash /root/singbox-eps-node/scripts/diagnose.sh
```

## 维护原则

- 改代码前先看 `project_snapshot.md` 和 `AI_DEBUG_HISTORY.md`
- 修改配置相关逻辑时，优先统一到 `scripts/config.py`
- 修改完要同步文档，不要只改代码
- 服务端和订阅端的同类逻辑要一起改，不能只改一边
- 推 GitHub 前必须确认没有 `.env`、密码、Token、私钥等敏感信息

## 许可证

MIT License
