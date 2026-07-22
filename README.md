# Singbox EPS Node

**当前版本**: `v4.15.24`

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

| 协议 | CDN 模式（JP） | 直连模式（HK1/HK2） |
|------|--------------------------|-----------------|
| VLESS-Reality | ✅ `:443` | ✅ `:443` |
| Trojan-TCP | ✅ 随机端口 | ✅ 随机端口 |
| VLESS-WS-CDN | ✅ CF 优选 IP `:443`（按路径回源 `:8443`） | ❌ |
| Trojan-WS-CDN | ✅ CF 优选 IP `:443`（按路径回源 `:2083`） | ❌ |
| anyTLS | ✅ `:2096` | ✅ `:2096` |
| TUIC-v5 | ✅ UDP `:443` | ✅ UDP `:443` |

## 订阅端点

| 端点 | 用途 |
|------|------|
| `https://sub-jp.290372913.xyz:2087/sub/JP` | JP Base64 订阅（CDN 模式） |
| `https://{hk1|hk2}.290372913.xyz:2087/sub/{HK1|HK2}` | 香港 Base64 订阅（直连模式） |
| 同域名下 `/clash/{CC}` / `/singbox/{CC}` | Clash Meta YAML / sing-box JSON |
| 同域名下 `/info/{CC}` | 流量查询 |

> CC = 节点标识（JP/HK1/HK2）。只有 JP 走 Cloudflare CDN；JP 订阅端点走 `sub-jp` 灰云直连，CDN 节点仍使用 `jp` 主域名/优选 IP。
> HK1/HK2 均为直连模式，订阅分别走 `hk1.290372913.xyz:2087` 和 `hk2.290372913.xyz:2087`，不生成 WS-CDN 节点。HK1 仍保留旧 `/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk` 兼容路径。
> 流量重置日：JP 每月 19 号，HK1/HK2 每月 1 号。本地部署由 `{CC}_TRAFFIC_RESET_DAY` 持久同步到各服务器 `.env`。
> 订阅证书：所有用户实际访问的灰云域名必须使用 Let's Encrypt 公网可信证书；客户端不需要开启“跳过证书验证”。
> 一键安装会先按模式同步 Cloudflare DNS（JP 主域名橙云、订阅域名灰云；HK1/HK2 主域名灰云），再签发证书；最终必须用系统 CA 真实下载并校验 Base64、Clash、sing-box 三类订阅，任一失败都会以非零状态中止。
> Base64 订阅默认输出 sing-box 全量节点；只有明确识别为纯 Xray 客户端或手动加 `?client=xray` 才降级。

## 常用命令

```bash
systemctl restart singbox singbox-sub singbox-cdn
journalctl -u singbox -n 50 --no-pager
bash /root/singbox-eps-node/scripts/diagnose.sh
```

## 许可证

MIT License
