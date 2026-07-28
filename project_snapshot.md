# Singbox EPS Node 项目快照

**版本**: v4.15.28 | **更新**: 2026-07-28（JP CDN 全域规则单一所有者）

## 当前唯一有效服务器清单

| 服务器 | 域名 | IP | 模式 | 节点数 | 系统 / 内核 | sing-box |
|--------|------|----|------|--------|-------------|----------|
| JP | jp.290372913.xyz | 3.113.4.86 | CDN（橙云） | 7 | Ubuntu 24.04 / 6.18.39-x64v3-xanmod1 | 1.13.14 |
| HK1 | hk1.290372913.xyz | 47.243.72.97 | **直连**（灰云） | 4 | Ubuntu 24.04 / 6.8.0-110-generic | 1.13.13 |
| HK2 | hk2.290372913.xyz | 47.238.146.170 | **直连**（灰云） | 4 | Ubuntu 24.04 / 6.8.0-110-generic | 1.13.14 |
| HKBEIYONG | hkbeiyong.290372913.xyz | 47.242.36.160 | **直连**（灰云） | 5 | Ubuntu 24.04 / 6.8.0-110-generic | 1.13.14 |

> 旧 HKCEPIN（18.166.210.81）已由 HK2 取代。旧 HK、HKCEPIN、SG 及其 `sub-*` Cloudflare DNS 记录已删除，不得重新加入当前部署清单。
> 2026-07-28 外部复查时 HK1 主机 SSH/443/2087/2096/1080 全部超时；HK1 保留在清单等待原主机恢复，HKBEIYONG 已作为可用香港备用直连节点上线。

## 协议与运行模式

| 协议 | JP CDN | 香港直连（HK1/HK2/HKBEIYONG） |
|------|--------|----------------|
| VLESS-Reality | ✅ TCP `:443` | ✅ TCP `:443` |
| Trojan-TCP | ✅ 随机端口 | ✅ 随机端口 |
| VLESS-WS-CDN | ✅ CF 边缘 `:443`，`/api/v1/stream` 回源 `:8443` | ❌ |
| Trojan-WS-CDN | ✅ CF 边缘 `:443`，`/api/v1/data` 回源 `:2083` | ❌ |
| anyTLS | ✅ TCP `:2096` | ✅ TCP `:2096` |
| TUIC-v5 | ✅ UDP `:443` | ✅ UDP `:443` |
| 认证 SOCKS5 入站 | ✅ JP `:1080` 已外部验证 | ✅ HK2/HKBEIYONG `:1080` 已外部验证 |

- `DEPLOY_MODE` 是唯一优先判断：JP=`cdn`，HK1/HK2/HKBEIYONG=`direct`。
- `COUNTRY_CODE` 是服务器标识，不是地理码；一键安装从 `CF_DOMAIN` 首标签生成，例如 `hkbeiyong.*` → `HKBEIYONG`。
- direct 模式不启动 `singbox-cdn`，不生成 WS-CDN 节点。
- AI SOCKS5 路由与本机 SOCKS5 入站是两套独立配置。HKBEIYONG 的 AI 流量当前经 JP 认证 SOCKS5 出站；外部端到端 OpenAI 探测返回 401。

## 订阅与 Cloudflare

| 节点 | Base64 | Clash | sing-box | CDN 状态 |
|------|--------|-------|----------|----------|
| JP | `https://sub-jp.290372913.xyz:2087/sub/JP` | `/clash/JP` | `/singbox/JP` | `/api/cdn-status` |
| HK1 | `https://hk1.290372913.xyz:2087/sub/HK1` | `/clash/HK1` | `/singbox/HK1` | 无 |
| HK2 | `https://hk2.290372913.xyz:2087/sub/HK2` | `/clash/HK2` | `/singbox/HK2` | 无 |
| HKBEIYONG | `https://hkbeiyong.290372913.xyz:2087/sub/HKBEIYONG` | `/clash/HKBEIYONG` | `/singbox/HKBEIYONG` | 无 |

- JP 主域名 `jp.*` 橙云，`sub-jp.*` 灰云。
- 所有香港 direct 主域名均灰云直连，不创建 `sub-*` CDN 节点。
- JP 证书 SAN 覆盖 `jp` + `sub-jp`，各 direct 节点证书覆盖自身主域名；HKBEIYONG 已通过系统 CA 与公网 SNI 校验。
- Cloudflare custom skip/origin 规则当前只包含 `jp.290372913.xyz`；TLS 最低 1.2，不维护 DDoS L7 override。
- 新服务器安装会从落盘后的 `.env` 读取域名，自动同步/回读 DNS 和 CDN 规则，再签发 Let's Encrypt；最终从公网严格下载三类订阅，并用 sing-box 1.13 内核检查客户端 JSON。失败会恢复旧目录/证书、sing-box 二进制、systemd、crontab 与 iptables，不会打印“安装完成”。

## 资源与已知边界

| 节点 | 内存 | Swap | 拥塞控制 | 流量重置日 |
|------|------|------|----------|------------|
| JP | 910MB | 2047MB | XanMod BBRv3 + FQ | 19 |
| HK1 | 424MB | 0 | 原生内核 BBR + FQ | 1 |
| HK2 | 424MB | 约 305MB | 原生内核 BBR + FQ | 1 |
| HKBEIYONG | 424MB | 0 | 原生内核 BBR + FQ | 1 |

HK2/HKBEIYONG 系统盘仅 2GB，XanMod 内核包加安全余量无法容纳。HKBEIYONG 安装完成后根分区可用约 446MB，安装器为防止写满磁盘跳过 Swap/XanMod并保留原生 BBR+FQ；这是硬件容量边界，不得记录为 BBRv3。

## 定时任务

| 任务 | 频率 | 说明 |
|------|------|------|
| `health_check.sh` | 每 15 分钟 | 服务/端口/.env/CF 规则自愈 |
| `cert_manager.py --renew` | 每月 1 日 03:00 | SSL 证书续签 |
| `sub_domain_monitor.py` | 每 5 分钟 | 只监控当前 JP `sub-jp` |
| subscription baseline | 每月重置日 00:03 | JP=19，香港 direct=1 |

## 2026-07-28 真实验收快照

- HKBEIYONG 最终部署 10 PASS/1 direct 合理 SKIP；公网三类订阅各 5 节点，Mihomo 与 sing-box 1.13 原生配置检查均通过。
- HKBEIYONG 外部认证 SOCKS5 → 服务器 AI 路由 → JP SOCKS5 → OpenAI 的端到端探测返回 401；AI 组类型为 urltest，运行时降级标记不存在。
- JP 最终部署 13 PASS；公网三类订阅各 7 节点；Cloudflare 受管规则完整语义、TLS 与 DDoS override 均由 API 回读，外部 `/api/v1/stream` 与 `/api/v1/data` 均 HTTP 101。
- Cloudflare zone 级 skip/origin ruleset 只允许 JP CDN 模式维护；HKBEIYONG/HK2 direct 健康检查已实测跳过且不改变规则版本，模式缺失/非法会阻塞。JP 门禁现为 13/13 PASS。
- `python -m pytest -q`：`87 passed, 1 skipped`（含目录回滚、模式 fail-closed 与 Cloudflare 完整规则语义回归）；Git Bash 对 `install.sh`/`health_check.sh` 语法检查通过；HKBEIYONG/JP 定向 full audit 均 `ALL OK`。
- 流量汇总包含 4 台：JP/HK2/HKBEIYONG 3 台可达，HK1 1 台不可达。
