# Clash 订阅生成铁律

> 从 AGENTS.md 迁移而来,AGENTS.md 只保留指针。修改 `scripts/subscription_service.py` 中 Clash 相关生成逻辑时必须遵守。

---

## 1. url-test 策略组三件套与测速方案

修改 Clash url-test 生成时,必须使用:

- `lazy: false` — 后台持续测速(严禁设为 `true` 导致锁死坏节点)
- `tolerance: 150` — 电信网络波动容忍值(禁止低于 100)
- `interval: 60` — 60 秒测速一轮(严禁设为 600s 导致卡顿 10 分钟)
- `url: http://cp.cloudflare.com/generate_204` — HTTP 协议避免 TLS 握手损耗
- `timeout: 5000` — 测速超时 5 秒

违反后果:Clash 自动切换过于迟钝导致发消息卡顿,或过于频繁导致连接抖动(Bug #88)。

---

## 2. 规则 MATCH 必须指向 select 组(节点选择)

- MATCH 规则必须指向 `节点选择`(select 组),绝对不能直接指向 `自动选择`(url-test 组)
- `节点选择` 的首个 proxy 必须是 `自动选择`,用户可在 UI 自由切换(Bug #89)

---

## 3. 高风险参数禁止恢复

以下参数在丢包环境下会放大问题,禁止恢复到自动选择组:

- `keep-alive-interval` — 丢包隧道上适得其反
- `tcp-concurrent` — 频繁触发连接 RST
- `unified-delay` — 干扰判断

---

## 4. 客户端协议兼容矩阵

用户要求默认保留完整 7 节点。VLESS-HTTPUpgrade(`type=httpupgrade`)和 TUIC v5(`tuic://`)在部分 Xray-core 客户端不稳定时，只能通过 `?client=standard` 手动兜底，不能默认删节点。

| 客户端 | 节点数 | 说明 |
|--------|--------|------|
| Clash / sing-box / NekoBox | 7 | 完整协议栈 |
| v2rayN / v2rayNG / Shadowrocket / Quantumult X | 7 | 默认完整订阅，URI 参数做兼容优化 |
| `?client=standard` | 5 | 手动兜底，剔除 HTTPUpgrade + TUIC |

- `?client=full` 强制 7 节点
- `?client=standard` 强制 5 节点
- **禁止未经用户确认默认删节点**
- Shadowrocket 节点可用性判断优先看 CONNECT/HTTP 测速和真实连接；ICMP 仅作裸线路参考。

---

## 5. 订阅流量统计

- iptables 必须 INPUT + OUTPUT 双向计数:INPUT 按 `--dport`,OUTPUT 按 `--sport`
- UDP 端口(TUIC v5 QUIC 协议)独立建规则
- `get_iptables_traffic_bytes()` 必须 INPUT+OUTPUT 求和,否则下载流量被低估 50%
- 每月 14 号由订阅服务更新数据库 baseline,不清零 iptables 内核计数器

---

## 6. v2rayN 流量显示限制

v2rayN 不解析 `subscription-userinfo` header,订阅更新只显示"成功: N 个节点",永远不显示流量。

- 新增 `/info` 端点(v2rayN 浏览器能看)
- Base64 头部插入流量注释行(部分客户端可见)作为补充
- **禁止期望 v2rayN 通过 subscription 显示流量**

---

## 7. HTTP header 不能含非 ASCII 字符

Flask `Response.headers` 只能设置 latin-1 编码的值。

- `Content-Disposition: attachment; filename=香港订阅.txt` 会触发 UnicodeEncodeError 导致 500
- 修复:RFC 5987 `filename*=UTF-8''URL编码`,或 profile-title 改为纯 ASCII
- **任何通过 header 传递中文字符必须 URL-encode**
