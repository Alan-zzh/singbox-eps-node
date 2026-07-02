# Singbox EPS Node

**当前版本**: `v4.15.10`

一键部署 sing-box 多协议节点 + 自动生成订阅 + 自动维护 CDN 优选 IP + 健康检查自愈。

## 接手顺序

1. [AGENTS.md](AGENTS.md) — 项目规则 + **凭据读取指引**（AI 必须先读）
2. [project_snapshot.md](project_snapshot.md) — 服务器清单 + 部署记录
3. [AI_DEBUG_HISTORY.md](AI_DEBUG_HISTORY.md) — 历史踩坑记录
4. [CHANGELOG.md](CHANGELOG.md) — 最近变更
5. [VERSION.md](VERSION.md) — 当前版本号

## 快速安装

```bash
bash <(curl -sL https://raw.githubusercontent.com/Alan-zzh/singbox-eps-node/main/install.sh)
```

## 协议

| 协议 | CDN 模式（JP/HK/HKCEPIN） | 直连模式（HK1） |
|------|--------------------------|-----------------|
| VLESS-Reality | ✅ `:443` | ✅ `:443` |
| Trojan-TCP | ✅ 随机端口 | ✅ 随机端口 |
| VLESS-WS-CDN | ✅ CF 优选 IP `:8443` | ❌ |
| Trojan-WS-CDN | ✅ CF 优选 IP `:2083` | ❌ |
| anyTLS | ✅ `:2096` | ✅ `:2096` |
| TUIC-v5 | ✅ UDP 随机端口 | ✅ UDP 随机端口 |

## 订阅端点

| 端点 | 用途 |
|------|------|
| `https://sub-{CC}.290372913.xyz:2087/sub/{CC}` | Base64 订阅（自动识别客户端） |
| `https://sub-{CC}.290372913.xyz:2087/clash/{CC}` | Clash Meta YAML |
| `https://sub-{CC}.290372913.xyz:2087/singbox/{CC}` | sing-box JSON |
| `https://sub-{CC}.290372913.xyz:2087/info/{CC}` | 流量查询 |

> CC = 国家代码（JP/HK/HKCEPIN）。订阅端点走 sub-* 灰云直连绕过 CF DDoS L7。

## 常用命令

```bash
systemctl restart singbox singbox-sub singbox-cdn
journalctl -u singbox -n 50 --no-pager
bash /root/singbox-eps-node/scripts/diagnose.sh
```

## 许可证

MIT License
