# Singbox EPS Node

**当前版本**: `v4.15.6`

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
bash install.sh optimize     # 只做系统优化（BBRv3 + FQ；首次启用需重启）
```

## 当前功能

- **6 协议**(v4.15.0 优化,按客户端能力自动适配):VLESS-Reality / Trojan-TCP / VLESS-WS / Trojan-WS / anyTLS / TUIC-v5
  - v4.15.0 删除:VLESS-gRPC（与 TUIC v5 同为多路复用协议，QUIC 比 gRPC 更高效，无 TCP 层队头阻塞）
  - v4.15.0 加回:TUIC v5（`ENABLE_TUIC=true` 默认开启，提供 UDP relay + QUIC 多路复用）
  - v4.14.0 删除:VLESS-HTTPUpgrade（故障最多+兼容最窄）、TUIC v5（v4.15.0 推翻此删除决定）
  - v4.14.0 新增:anyTLS（sing-box 1.12+ 原生，端口 2096，缓解 TLS-in-TLS 指纹检测）
- **多客户端兼容**:`/sub` 默认返回 6 节点（CDN 模式）/ 4 节点（直连模式）,Clash/sing-box/NekoBox/v2rayN/v2rayNG/Shadowrocket 都拿完整订阅;`?client=full` 与 `?client=standard` 等同，保留 `standard` 参数兼容旧客户端
- **流量查询端点**:`/info` 文本端点(v2rayN 也能看流量)+ `/api/traffic` JSON + `subscription-userinfo` header;Base64 正文只放节点 URI,分享链接节点名已 URL 编码
- HTTPS 订阅:Base64 + sing-box JSON + Clash Meta
- CDN 优选 IP 自动维护(IP 池 10-15 个/服务器,用户本地实测/运营商匹配源优先,Top3 之后再做 C 段分散,`/api/cdn-status` 可查看当前IP/评分/更新时间)
- CDN 阻断自动检测与切换(403/L7 拦截检测 + 冷却机制 + 信号文件联动订阅刷新；v4.15.6 起订阅层 `CDN_EDGE_FALLBACK=auto` 会在 CF 边缘 WS 入口失败时临时用 sub-* 直连地址保可用，并保留主域名 SNI/Host)
- CDN 优选迟滞防抖:新 IP 评分必须比当前高 15% 才触发切换,避免频繁切换加剧封禁
- Cloudflare 代理入口规则自愈(按 `jp/sg/hk.290372913.xyz` + 代理端口/路径放行,不绑定用户公网 IP;最低 TLS 固定为 1.2 兼容 Windows/v2rayN;不再周期性重加 `ddos_l7 eoff` override)
- 健康检查 + 一键诊断
- 按月流量统计(iptables 内核级 INPUT `dpt` + OUTPUT `spt` 双向计数,UDP 独立统计,每月14号更新 baseline)
- BBRv3 + FQ 网络优化（XanMod BBRv3 内核；首次启用需重启）
- sing-box 版本:1.13.13(JP/SG/HK);服务端为单独 sing-box,不混装 Xray

## 节点列表

| 节点 | 协议 | 连接方式 | 客户端兼容 |
|------|------|----------|------------|
| `{CC}-VLESS-Reality` | VLESS | 直连 `IP:443` | 全平台 |
| `{CC}-Trojan-TCP` | Trojan | 直连 `IP:随机端口` | 全平台 |
| `{CC}-VLESS-WS-CDN` | VLESS + WS | CDN 优选 IP `:8443`，CF L7 阻断时自动降级 sub-* 直连 | 全平台 |
| `{CC}-Trojan-WS-CDN` | Trojan + WS | CDN 优选 IP `:2083`，CF L7 阻断时自动降级 sub-* 直连 | 全平台 |
| `{CC}-anyTLS` | anyTLS | 直连 `IP:2096` | sing-box 1.12+ / Clash Meta (mihomo) 1.18+ |
| `{CC}-TUIC-v5` | TUIC v5 | 直连 `UDP:50444`（或环境变量端口） | sing-box / mihomo / Shadowrocket |

> **v4.15.0 协议栈**：删除 VLESS-gRPC 与 VLESS-HTTPUpgrade-CDN，保留 VLESS-Reality / Trojan-TCP / VLESS-WS-CDN / Trojan-WS-CDN / anyTLS / TUIC-v5。
>
> **客户端能力自动识别**：`/sub` 端点按 User-Agent 自动返回 6 节点。`?client=full` 与 `?client=standard` 等同（HTTPUpgrade/TUIC 已下线，无差别），保留 `standard` 参数兼容旧客户端。

## 订阅端点

| 端点 | 用途 |
|------|------|
| `https://{域名}:2087/sub/{CC}` | Base64 订阅（自动识别客户端能力，默认 6 节点） |
| `https://{域名}:2087/sub/{CC}?client=full` | 强制 6 节点（v4.14.0 起 full=standard） |
| `https://{域名}:2087/sub/{CC}?client=standard` | 强制 6 节点（兼容旧客户端参数） |
| `https://{域名}:2087/sub/{CC}?client=clash` | 强制 Clash/mihomo 完整订阅 |
| `https://{域名}:2087/sub/{CC}?client=v2rayn` | 强制 v2rayN 完整订阅（6 节点） |
| `https://{域名}:2087/sub/{CC}?client=shadowrocket` | 强制 Shadowrocket 完整订阅（6 节点） |
| `https://{域名}:2087/singbox/{CC}` | sing-box JSON 配置 |
| `https://{域名}:2087/clash/{CC}` | Clash Meta YAML 配置 |
| `https://{域名}:2087/info/{CC}` | 流量查询（纯文本，v2rayN 也能看） |
| `https://{域名}:2087/api/traffic` | 流量查询（JSON） |
| `https://{域名}:2087/api/cdn-status` | CDN优选状态（当前IP、评分、更新时间） |

## 环境变量

安装后编辑 `/root/singbox-eps-node/.env`，参考 [.env.example](.env.example)。

| 变量 | 说明 | 必填 |
|------|------|------|
| `CF_DOMAIN` | Cloudflare 域名 | 是 |
| `SERVER_IP` | 服务器公网 IP，留空可自动检测 | 否 |
| `CF_API_TOKEN` | Cloudflare API Token，用于证书申请与代理入口规则自愈 | 建议 |
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
cd /root/singbox-eps-node && python3 scripts/cloudflare_proxy_rules.py apply
```

## 许可证

MIT License
