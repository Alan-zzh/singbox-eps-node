# Singbox EPS Node 项目规则

## Clash 订阅生成规则

### 1. url-test 策略组三件套与测速方案
修改 `subscription_service.py` 中 Clash url-test 生成时，必须使用：
- `lazy: false` — 后台持续测速（必须为 `false` 确保 Clash 拥有最新延迟数据，能立即执行故障切换，严禁设为 `true` 导致锁死坏节点）
- `tolerance: 150` — 电信网络波动容忍值，防止由于普通延迟抖动引起频繁切换（禁止低于 100，推荐 150）
- `interval: 60` — 60 秒测速一轮（必须为 60s 以保证丢包或断线时 1 分钟内自动切换，严禁设为 600s 导致卡顿 10 分钟）
- `url: http://cp.cloudflare.com/generate_204` — 测速源使用 HTTP 协议避免 TLS 握手损耗，利用 Cloudflare 优化线路进行极速、精准测速
- `timeout: 5000` — 测速超时限制设为 5 秒

违反后果：Clash 自动切换过于迟钝导致发消息卡顿，或过于频繁导致连接不断抖动（Bug #88）。

### 2. 规则 MATCH 必须指向 select 组（节点选择）
- 所有的 MATCH 规则必须指向 `节点选择`（select 组），绝对不能直接指向 `自动选择`（url-test 组）。
- `节点选择` 的首个 proxy 必须是 `自动选择`，这样用户可在 UI 界面在“自动测速切换”和“锁定固定单节点”之间自由切换。如果 MATCH 直接指向 url-test，用户的 UI 手动选择将直接失效（Bug #89）。
