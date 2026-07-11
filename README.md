# Singbox EPS Node

**当前版本**: `v4.15.15`

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

> CC = 节点标识（JP/HK/HKCEPIN）。CDN 服务器订阅端点走 sub-* 灰云直连；CDN 节点仍只使用主域名/优选 IP，不使用 sub-* 降级。
> HK1 是直连模式，不使用 `sub-hk1`。香港直连订阅固定使用 `https://hk1.290372913.xyz:2087/sub/HK1`、`https://hk1.290372913.xyz:2087/clash/HK1`、`https://hk1.290372913.xyz:2087/singbox/HK1`；为兼容旧客户端，`/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk` 在 HK1 域名下也会映射到 HK1。
> Base64 订阅默认输出 sing-box 全量节点；只有明确识别为纯 Xray 客户端或手动加 `?client=xray` 才降级。

## 常用命令

```bash
systemctl restart singbox singbox-sub singbox-cdn
journalctl -u singbox -n 50 --no-pager
bash /root/singbox-eps-node/scripts/diagnose.sh
```

## 许可证

MIT License
