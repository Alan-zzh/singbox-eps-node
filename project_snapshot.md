# Singbox EPS Node 项目快照

**版本**: v4.15.24 | **更新**: 2026-07-23（新服务器一键安装可信订阅闭环）

## 当前唯一有效服务器清单

| 服务器 | 域名 | IP | 模式 | 节点数 | 系统 / 内核 | sing-box |
|--------|------|----|------|--------|-------------|----------|
| JP | jp.290372913.xyz | 3.113.4.86 | CDN（橙云） | 6 | Ubuntu 24.04 / 6.18.39-x64v3-xanmod1 | 1.13.14 |
| HK1 | hk1.290372913.xyz | 47.243.72.97 | **直连**（灰云） | 4 | Ubuntu 24.04 / 6.8.0-110-generic | 1.13.13 |
| HK2 | hk2.290372913.xyz | 47.238.146.170 | **直连**（灰云） | 4 | Ubuntu 24.04 / 6.8.0-110-generic | 1.13.14 |

> 旧 HKCEPIN（18.166.210.81）已由 HK2 取代。旧 HK、HKCEPIN、SG 及其 `sub-*` Cloudflare DNS 记录已删除，不得重新加入当前部署清单。

## 协议与运行模式

| 协议 | JP CDN | HK1/HK2 直连 |
|------|--------|----------------|
| VLESS-Reality | ✅ TCP `:443` | ✅ TCP `:443` |
| Trojan-TCP | ✅ 随机端口 | ✅ 随机端口 |
| VLESS-WS-CDN | ✅ CF 边缘 `:443`，`/api/v1/stream` 回源 `:8443` | ❌ |
| Trojan-WS-CDN | ✅ CF 边缘 `:443`，`/api/v1/data` 回源 `:2083` | ❌ |
| anyTLS | ✅ TCP `:2096` | ✅ TCP `:2096` |
| TUIC-v5 | ✅ UDP `:443` | ✅ UDP `:443` |
| 认证 SOCKS5 入站 | 按各机 `.env` | ✅ HK2 `:1080` 已外部验证 |

- `DEPLOY_MODE` 是唯一优先判断：JP=`cdn`，HK1/HK2=`direct`。
- direct 模式不启动 `singbox-cdn`，不生成 WS-CDN 节点。
- AI SOCKS5 路由与本机 SOCKS5 入站是两套配置：前者由 `AI_SOCKS5_*` 控制，后者由 `SOCKS5_*` 控制。

## 订阅与 Cloudflare

| 节点 | Base64 | Clash | sing-box | CDN 状态 |
|------|--------|-------|----------|----------|
| JP | `https://sub-jp.290372913.xyz:2087/sub/JP` | `/clash/JP` | `/singbox/JP` | `/api/cdn-status` |
| HK1 | `https://hk1.290372913.xyz:2087/sub/HK1` | `/clash/HK1` | `/singbox/HK1` | 无 |
| HK2 | `https://hk2.290372913.xyz:2087/sub/HK2` | `/clash/HK2` | `/singbox/HK2` | 无 |

- JP 主域名 `jp.*` 橙云，`sub-jp.*` 灰云。
- HK1/HK2 主域名均灰云直连，不创建 `sub-hk1`/`sub-hk2` CDN 节点。
- JP 证书 SAN 覆盖 `jp` + `sub-jp`，HK1/HK2 各覆盖自身主域名；三个订阅入口均通过系统 CA 校验。
- Cloudflare custom skip/origin 规则当前只包含 `jp.290372913.xyz`；TLS 最低 1.2，不维护 DDoS L7 override。
- 新服务器安装会从落盘后的 `.env` 读取域名，自动同步/回读 DNS，再签发 Let's Encrypt；最终用系统 CA 对三类订阅做本机真实 HTTPS 下载和格式验证，失败不会打印“安装完成”。

## 资源与已知边界

| 节点 | 内存 | Swap | 拥塞控制 | 流量重置日 |
|------|------|------|----------|------------|
| JP | 910MB | 2047MB | XanMod BBRv3 + FQ | 19 |
| HK1 | 424MB | 0 | 原生内核 BBR + FQ | 1 |
| HK2 | 424MB | 约 305MB | 原生内核 BBR + FQ | 1 |

HK2 系统盘仅 2GB，XanMod 内核包加安全余量无法容纳。安装器会明确降级为原生内核 BBR+FQ，这是硬件容量边界，不得记录为 BBRv3。

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| `health_check.sh` | 每 15 分钟 | 服务/端口/.env/CF 规则自愈 |
| `cert_manager.py --renew` | 每月 1 日 03:00 | SSL 证书续签 |
| `sub_domain_monitor.py` | 每 5 分钟 | 只监控当前 JP `sub-jp` |
| subscription baseline | 每月重置日 00:03 | JP=19，HK1/HK2=1 |

## 2026-07-23 真实验收快照

- `python deploy.py --all`：JP/HK1/HK2 全部成功，CDN/direct 按远端 `.env` 判定。
- `python tests/full_audit.py`：`ALL OK`；JP 6 节点且两个 WS 路径均 101，HK1/HK2 各 4 直连节点。
- 流量汇总：3/3 可达，`TRAFFIC_AGGREGATE_ENDPOINTS` 仅包含 `sub-jp`/`hk1`/`hk2`。
- HK2 本机订阅四端点与公网访问均 HTTP 200；认证 SOCKS5 端到端出口 IP 匹配。
