# Singbox EPS Node 项目快照

**版本**: v4.15.15 | **更新**: 2026-07-05（HK1 兼容 /hk 旧订阅路径）

## 服务器清单

| 服务器 | 域名 | IP | 模式 | 协议数 | 系统 | sing-box |
|--------|------|----|------|--------|------|----------|
| JP | jp.290372913.xyz | 43.207.152.47 | CDN（橙云） | 6 | - | 1.13.14 |
| HK | hk.290372913.xyz | 43.249.174.222 | CDN（橙云） | 6 | Debian 12 | 1.13.13 |
| HKCEPIN | hkcepin.290372913.xyz | 18.166.210.81 | CDN（橙云） | 6 | Ubuntu 24.04 (414MB+2GB Swap) | 1.13.13 |
| HK1 | hk1.290372913.xyz | 47.243.72.97 | **直连**（灰云） | 4 | - | - |

> ❌ SG（13.212.37.11）已放弃维护

## 协议列表

| 协议 | CDN 模式（JP/HK/HKCEPIN） | 直连模式（HK1） |
|------|--------------------------|-----------------|
| VLESS-Reality | ✅ `:443` | ✅ `:443` |
| Trojan-TCP | ✅ 随机端口 | ✅ 随机端口 |
| VLESS-WS-CDN | ✅ CF 优选 IP `:8443` 路径 `/api/v1/stream` | ❌ |
| Trojan-WS-CDN | ✅ CF 优选 IP `:2083` 路径 `/api/v1/data` | ❌ |
| anyTLS | ✅ `:2096` | ✅ `:2096` |
| TUIC-v5 | ✅ UDP `:50444`（默认，install.sh 随机生成） | ✅ UDP `:50444`（默认，install.sh 随机生成） |

## 订阅端点

| 端点 | 路径 | 说明 |
|------|------|------|
| `/sub/{CC}` | CDN: sub-*.290372913.xyz:2087；HK1: hk1.290372913.xyz:2087 | Base64 订阅（自动识别客户端） |
| `/clash/{CC}` | CDN: sub-*.290372913.xyz:2087；HK1: hk1.290372913.xyz:2087 | Clash Meta YAML |
| `/singbox/{CC}` | CDN: sub-*.290372913.xyz:2087；HK1: hk1.290372913.xyz:2087 | sing-box JSON |
| `/info/{CC}` / `/api/traffic` | CDN: sub-*.290372913.xyz:2087；HK1: hk1.290372913.xyz:2087 | 流量查询 |
| `/api/cdn-status` | CDN: sub-*.290372913.xyz:2087 | CDN 优选 IP 状态 |

> CC = COUNTRY_CODE（JP/HK/HKCEPIN/HK1）。sub-* 只用于 CDN 服务器订阅入口，不是 CDN 节点降级地址；HK1 direct 模式订阅走主域名。

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| health_check.sh | 每15分钟 | 内存/服务/端口/CF 规则自愈 + .env 巡检 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL 证书自动续签 |
| sub_domain_monitor.py | 每5分钟 | sub-* 直连路径可用性监控 |
| subscription baseline | 每月重置日00:03 | 流量基线更新 |

## 部署记录

### 日本服务器（43.207.152.47）
- 域名：jp.290372913.xyz | 部署：2026-06-26
- CDN 模式（6 协议），trojan-tcp 端口: 56888，anytls 端口: 2096

### 香港服务器 HK（43.249.174.222）
- 域名：hk.290372913.xyz | 部署：2026-06-04
- CDN 模式（6 协议），trojan-tcp 端口: 65004，anytls 端口: 2096

### 香港服务器 HKCEPIN（18.166.210.81 AWS）
- 域名：hkcepin.290372913.xyz | 部署：2026-07-02
- CDN 模式（6 协议），414MB 内存 + 2GB Swap
- 订阅直连子域名：sub-hkcepin.290372913.xyz
- v4.15.12 修复：COUNTRY_CODE=HK→HKCEPIN（原错配导致 /clash/HKCEPIN 404），已装 crontab（health_check + cert_manager + sub_domain_monitor）
- v4.15.13 修复：订阅输出恢复 `HKCEPIN-VLESS-WS-CDN` / `HKCEPIN-Trojan-WS-CDN` 后缀，Cloudflare 自愈规则固定为新 WS 路径且无 DDoS L7 override

### 香港服务器 HK1（47.243.72.97 阿里云）
- 域名：hk1.290372913.xyz | 部署：2026-06-28 | 200GB/月
- **直连模式**（4 协议：VLESS-Reality, Trojan-TCP, anyTLS, TUIC-v5）
- ⚠️ 判断依据 `CF_DOMAIN.startswith('hk1.')`，**禁止用 COUNTRY_CODE**
- 订阅入口走 `hk1.290372913.xyz:2087`；不创建/依赖 `sub-hk1`，不输出 CDN 节点
- v4.15.15 修复：HK1 域名下兼容 `/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk` 旧路径，映射到 HK1 直连订阅
