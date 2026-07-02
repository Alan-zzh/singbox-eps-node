# AI 踩坑病历

> **只保留已确认的、对后续 AI 有直接指导意义的真实 bug 记录。**
> 过时/错误/重复的结论已清理，所有铁律请优先看 [AGENTS.md](AGENTS.md)。

---

## 1. REALITY_SHORT_ID 字面值写入 .env（v4.15.10）

**现象**: sing-box 校验失败报 `invalid byte: U+0024 '$'`，`.env` 中 `REALITY_SHORT_ID=$(openssl rand -hex 8)` 是字面值未被 shell 展开。

**根因**: 跨脚本写入 `.env` 时，shell 命令字面量未被展开。install.sh 修复只覆盖新部署，已有部署残留。

**修复**: 删旧行 → `openssl rand -hex 8` 生成实际值 → 重跑 config_generator → 校验通过。

**教训**:
1. `.env` 值写入时必须确保 shell 展开（Python/paramiko 写入时要预展开 `$(...)`）
2. `config_generator.py` 运行后必须 `sing-box check -c config.json` 验证
3. 任何 hex 值读取时做合法性校验（16 位 hex）

---

## 2. CRLF 换行导致 hex 校验失败（v4.15.10）

**现象**: deploy_verify.py 的 `grep -qE '^[0-9a-f]{16}$'` 返回 false，但值看起来正确。

**根因**: `.env` 含 CRLF（`\r\n`），`cut -d= -f2` 提取值尾部含 `\r`，实际为 `cf76f0d642c995fc\r`。Windows 编辑器写入 CRLF → sftp 上传到 Linux → 未转换。

**修复**: 所有 `.env` 读取命令加 `tr -d "\r"`。全局修复：deploy_verify.py、pre-flight check、health_check.sh。

**教训**:
1. 跨平台 `.env` 必须处理 CRLF，任何从 `.env` 提取值的脚本都要 `tr -d "\r"`
2. hex 校验必须 strip 后再检查（通用做法：`tr -d "'\"\r\n\t "`）

---

## 3. curl `-o /dev/null` 在 Windows 失效 → 假 403（v4.15.10 铁律）

**现象**: SSH 远程执行 `curl -o /dev/null -w '%{http_code}' https://jp...:8443/vless-ws` 返回 403，但同命令本地用 `-o NUL` 返回 101。CDN "故障"是测试工具误报。

**根因**: Windows curl.exe 不识别 `/dev/null`，创建名为 `null` 的文件，输出被吞 → 假 403。

**证据**:
- PowerShell: `curl -s -4 -o NUL -w '%{http_code}' https://jp.290372913.xyz:8443/vless-ws` → `101`
- 远程 SSH 同命令用 `-o /dev/null` → `403`（假阳性）
- 改用 `-D -` dump headers → 实际 101

**教训（铁律，已写入 AGENTS.md）**:
1. **Windows 上永远用 `-o NUL`，不能用 `-o /dev/null`**
2. **CDN WS 验证必须从外部执行**，不能依赖服务器自测（CF 拦服务器 IP → 假 403）
3. 单次 403 不是 CDN 损坏（CF 瞬断/重试即可）

---

## 4. 服务器端 CDN 探针假阴性导致周期性"订阅/CDN 失效"（v4.15.11 已移除）

> ⚠️ **该功能已在 v4.15.11 移除，此处记录供历史回溯。**

**现象**: CDN 通过 CF 橙云周期性不可用（中国用户 403），但订阅服务日志和 health_check 全部 OK。用户反复遇到 CDN 节点连不上。

**根因（GraphQL 防火墙事件证实）**:
1. CF L7 DDoS ML（自适应，7 日滑动窗口）周期性拦截中国 ISP（CHINANET/中国移动）到 `/*-ws` 路径的 WebSocket 升级请求
2. 服务器端 `_probe_cdn_ws()` 从 AWS/阿里云 IP 测 CF 主域名 → **永远 101（不被 ML 拦截）**
3. 探针永远假阴性 → `CDN_EDGE_FALLBACK` 从不触发 → 订阅一直吐主域名 CDN 节点 → 中国用户连 → 403

**为什么是周期性的**：
- CF L7 DDoS ML 在流量突发时 (多个中国用户同时连接) 触发封锁
- 流量下降后 ML 解封（GraphQL 证实 2-3 分钟内恢复）
- 但探针只在被订阅请求调用时才探测（缓存 TTL=300s），且从服务器测永远 OK
- 用户下次流量突发 → 再次封锁 → 无限循环

**移除原因**: 服务器端探针从错误位置测试（AWS IP vs 中国用户 IP）永远不能测到真实问题。`CDN_EDGE_FALLBACK` 写入 sub-* 直连地址到 CDN 节点，违背了 CDN 节点必须用主域名橙云代理的架构铁律。

**替代方案**: 改用非代理特征路径 `/api/v1/stream` `/api/v1/data` 降低 CF ML 误报率；优选 IP 自动选择不变；用户客户端在多协议间自动 fallback。

---

## 4. HK1 部署模式误判（v4.15.2 铁律）

**现象**: 修复脚本把 HK1（直连）当成 CDN 模式处理，添加 WS-CDN 节点导致不可用。

**根因**: 用 `COUNTRY_CODE == 'HK'` 判断部署模式，但 HK 和 HK1 地理都在香港。

**铁律（已写入 AGENTS.md 第29条）**:
- `.env` 显式 `DEPLOY_MODE=direct` 为最高优先级
- Fallback：`CF_DOMAIN.startswith('hk1.')` 才是直连
- **绝对禁止**用 `COUNTRY_CODE` 判断

---

## 5. TUIC v5 凭据不匹配静默失败（v4.15.0）

**现象**: `ENABLE_TUIC=true` 时，用户拿到节点但无法连接。

**根因**: config_generator.py 在 `TUIC_UUID` 为空时生成随机 UUID，subscription_service.py 用空字符串 → 凭据不一致。

**铁律（已写入 AGENTS.md 第24条）**:
- 订阅端实现凭据降级：`ENABLE_xxx=true` 且凭据为空时自动 `ENABLE_xxx=False`
- 服务端生成随机凭据时必须写入 `.env` 并被订阅端读取

---

## 6. sub-* 域名扩散到 CDN 节点（v4.15.1 伪 CDN 化）

**现象**: CDN 节点 server/Host 被改为 sub-* 直连域名，丧失抗 IP 封锁能力。

**铁律（已写入 AGENTS.md 第28条）**:
- CDN 代理节点（VLESS-WS/Trojan-WS）必须用主域名 `cf_domain`（橙云 `proxied=true`）
- 订阅端点（/clash /sub /singbox）用 sub-* 子域名（灰云 `proxied=false`）
- **两类用途严格分离，不能混淆**

---

> **完整项目规则见 [AGENTS.md](AGENTS.md)**。本文件仅保留历史 bug 供回溯参考，日常开发以 AGENTS.md 铁律为准。
