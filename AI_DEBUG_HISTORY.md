# AI 踩坑病历

> **只保留已确认的、对后续 AI 有直接指导意义的真实 bug 记录。**
> 过时/错误/重复的结论已清理，所有铁律请优先看 [AGENTS.md](AGENTS.md)。

---

## 0. HK1 香港直连旧路径 `/hk` 订阅 404（v4.15.15）

**现象**: 用户使用 `https://hk1.290372913.xyz:2087/clash/hk` 和 `/sub/hk` 更新香港直连订阅失败。外部复测确认 `/clash/hk`、`/sub/hk`、`/singbox/hk`、`/info/hk` 均返回 404，但标准 HK1 路径 `/clash/HK1`、`/sub/HK1`、`/singbox/HK1` 返回 200。

**根因**:
1. HK1 服务端只注册了 `COUNTRY_CODE=HK1` 对应路由，未兼容旧客户端保存的 `/hk` 路径
2. 不能通过新增 `sub-hk1` 解决：线上证书 SAN 只包含 `hk1.290372913.xyz`，`sub-hk1` 既无 DNS，又会证书名不匹配

**修复**:
1. `subscription_service.py` 仅在 `COUNTRY_CODE=HK1` 时注册 `/sub/hk`、`/clash/hk`、`/singbox/hk`、`/info/hk` 别名
2. 已上传到 HK1 `/root/singbox-eps-node/scripts/subscription_service.py` 和 `/opt/singbox-eps-node/scripts/subscription_service.py`，重启 `singbox-sub`
3. README 补充 HK1 主域名和 `/hk` 兼容说明

**证据**:
- 修复前：`curl https://hk1.290372913.xyz:2087/clash/hk` → 404；`/sub/hk` → 404
- 本地：`python -m py_compile scripts\subscription_service.py` 通过；Flask test client 验证 `/clash/hk`、`/sub/hk`、`/singbox/hk`、`/info/hk` 均 200
- 远端：HK1 `python3 -m py_compile /root/singbox-eps-node/scripts/subscription_service.py` 通过，`systemctl is-active singbox-sub` → active
- 外部：`curl https://hk1.290372913.xyz:2087/clash/hk` → 200，`/sub/hk` → 200，`/singbox/hk` → 200，`/info/hk` → 200；`/sub/hk` 解码后 4 个 HK1 直连节点

**教训**:
1. HK1 是服务器标识 `HK1`，但客户端历史配置里可能只填 `hk`；HK1 域名下可以兼容 `/hk`，其他服务器不能泛化
2. 订阅路径兼容优先在路由层做，不要新增不在证书 SAN 内的 `sub-hk1`

---

## 0. Base64 订阅默认 UA 被误降级成 Xray 兼容模式（v4.15.14）

**现象**: 用户反馈“是不是把核心换成 XRAY 了，singbox 连接不上”。外部抓取 `/sub/JP` 时，带 `sing-box/1.13.14` UA 返回 6 个节点；默认 curl UA 只返回 4 个节点，缺 anyTLS / TUIC-v5，表现为被强制降级到 Xray 兼容订阅。`/singbox/JP` JSON 仍返回 6 个 sing-box 出站，服务端核心没有换成 Xray。

**根因**:
1. `subscription_service.py` 将未知 UA、浏览器、curl、wget、python-requests 默认识别为 `xray`
2. sing-box/GUI 拉取器可能使用空 UA、通用 UA 或 `Go-http-client`，会被误降级
3. `tests/full_audit.py` 一度把“默认 UA 被识别为 xray”写成设计行为，掩盖了默认订阅不完整的问题

**修复**:
1. 默认/未知 UA 改为 `full`
2. 浏览器、curl、wget、python-requests 改为 `full`
3. 只有明确识别为 Quantumult X / Surge / Loon / v2Box 等纯 Xray 客户端，或手动加 `?client=xray` / `?client=standard`，才输出 Xray 兼容节点
4. `tests/full_audit.py` 改回默认 UA 预期 full

**证据**:
- 修改前：`curl https://sub-jp.290372913.xyz:2087/sub/JP` 解码后 4 节点；`curl -A "sing-box/1.13.14" .../sub/JP` 解码后 6 节点
- 修改前：`curl https://sub-jp.290372913.xyz:2087/singbox/JP` JSON 输出 `JP-VLESS-Reality` / `JP-Trojan-TCP` / `JP-VLESS-WS-CDN` / `JP-Trojan-WS-CDN` / `JP-anyTLS` / `JP-TUIC-v5`
- 本地：`python -m py_compile scripts\subscription_service.py tests\full_audit.py` 通过
- 本地：订阅能力回归测试 3 项通过（支持客户端 full、查询参数别名、Base64 body 无注释行）
- 部署：JP/HK/HK1/HKCEPIN 四台有效服务器 `deploy.py` 远端 py_compile、config_generator、sing-box check、服务重启和订阅验证通过；US 服务器 SSH 超时，属项目已知离线节点
- 外部：`/sub` 默认输出 JP/HK/HKCEPIN 6 链接、HK1 4 链接；显式 `?client=xray` 仍输出 4 条标准 vless/trojan 链接
- 外部：`PYTHONUTF8=1 python tests\full_audit.py` 最终 `ALL OK`，JP/HK/HKCEPIN CDN WS 入口均 HTTP 101

**教训**:
1. 不要把“保守兼容”做成默认删节点；默认应服务项目主客户端 sing-box，全量输出
2. Xray 兼容模式只能由明确 UA 或显式 `?client=xray` 触发
3. 审计脚本不能把线上异常输出改写成“设计行为”

---

## 0. CDN 节点名后缀被误删 + CF 自愈规则假成功导致反复漂移（v4.15.13）

**现象**: 用户反馈订阅链接失败、CDN 失效，并指出 CDN 节点名被删掉 `-CDN` 后缀。线上 Clash/sing-box 订阅里 CDN 节点显示为 `JP-VLESS-WS` / `JP-Trojan-WS`，与项目既定 `{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN` 不一致。

**根因**:
1. `subscription_service.py` 的 `node_name(protocol, cdn=False)` 支持 `-CDN`，但 Base64 URI、Clash YAML、sing-box JSON、proxy-groups 和 `cdn_status_api` 调用 VLESS-WS/Trojan-WS 时未传 `cdn=True`
2. v4.15.12 的审查记录把“订阅输出无 `-CDN`”误当成统一口径，导致 `full_audit.py` 改成按无后缀匹配，掩盖了真实命名回归
3. `cloudflare_proxy_rules.py apply` 使用 delete+add 规则路径，Cloudflare Rulesets API 出现“命令返回成功但 entrypoint 仍保留旧规则”的假成功；远端 health_check 又把旧 `/vless-ws` `/trojan-ws` / 2053 / SG 表达式和 DDoS L7 override 写回

**修复**:
1. `subscription_service.py` 三种订阅格式和分组统一对 CDN WS 节点使用 `node_name(..., cdn=True)` / `share_fragment(..., cdn=True)`
2. `scripts/config.py` 兼容旧调用的 `get_node_name('vless-ws'/'trojan-ws')` 返回 `-CDN` 后缀
3. `cloudflare_proxy_rules.py` 改为 PUT phase entrypoint 稳定替换目标 skip rule，`PROXY_SUBDOMAINS` 固定为 JP/HK/HKCEPIN，删除 SG 和旧 WS 路径，正常 apply 路径确保 `ddos_l7_entrypoint=null`
4. `tests/test_cloudflare_proxy_rules.py` 和 `tests/test_disconnect_regression.py` 更新到当前 6 节点协议栈和 CDN 后缀规则
5. 临时创建的 `sub-hk1.290372913.xyz` 已删除；HK1 是 direct 模式，订阅走 `hk1.290372913.xyz:2087`，不输出 CDN 节点

**证据**:
- JP/HK/HKCEPIN 三台服务器两轮 `deploy.py --server ...`：远端 py_compile、config_generator、sing-box check、服务重启、订阅端点、凭据一致性 8 项全 PASS
- 外部订阅抓取：JP/HK/HKCEPIN Clash 和 sing-box 均输出 `{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN`
- CDN 字段检查：server 为 CF 优选 IP，Host/SNI/servername 为主域名 `jp/hk/hkcepin.290372913.xyz`，未出现 sub-* 节点降级
- 外部 WS 握手：JP/HK/HKCEPIN 的 `8443/api/v1/stream` 与 `2083/api/v1/data` 全部 HTTP 101
- Cloudflare 状态：skip rule 表达式只包含 `jp/hk/hkcepin.290372913.xyz`、端口 `2087/8443/2083`、路径 `/api/v1/stream` `/api/v1/data`，`min_tls_version=1.2`，`ddos_l7_entrypoint=null`
- `python tests/full_audit.py`：JP/HK/HKCEPIN 6 协议 + CDN 101，HK1 4 协议 direct，最终 `ALL OK`

**教训**:
1. CDN WS 节点名必须保留 `-CDN` 后缀；不能为了“统一显示”去掉，否则用户无法区分直连与 CDN
2. `sub-*` 只能是订阅入口，绝不能作为 CDN 节点 fallback；项目已有直连节点，CDN 节点必须保持真正 CDN 路径
3. Cloudflare Rulesets 修复不能只信 apply 返回值，必须立刻 `status` 验证 entrypoint 真实表达式和 `ddos_l7_entrypoint`
4. 修改 full_audit 匹配规则时不能把真实回归改成测试口径，必须以项目协议表和用户可见订阅输出为准

---

## 0. HKCEPIN/HK1 COUNTRY_CODE 错配导致订阅 404，用户误判"CDN 优选 IP 全失效"（v4.15.12）

**现象**: 用户反馈"CDN 又不行了，优选 IP 全部失效"。实际排查发现 CDN WS 全部 101 ✅，问题是 HKCEPIN/HK1 两台服务器的 `.env` 中 `COUNTRY_CODE=HK`，但订阅端点路由是 `/clash/{COUNTRY_CODE}`，所以 `/clash/HKCEPIN` `/clash/HK1` 返回 404，用户拿到空订阅误判为 CDN 故障。

**根因**:
1. `install.sh` 用 `ipinfo.io` 自动检测服务器 ISO 国家代码，HKCEPIN(aws东京)/HK1(阿里云香港) 都被检测为 `HK`，但项目用 COUNTRY_CODE 作为服务器标识（区分 HK/HK1/HKCEPIN），不是地理位置
2. 之前文档审计 agent 误判 `deploy.py` / `scripts/deploy_verify.py` 不存在（实际根目录有 deploy.py，scripts/ 有 deploy_verify.py），导致 AGENTS.md 一度被错误修改

**证据**:
- 修复前：`curl https://sub-hkcepin.290372913.xyz:2087/clash/HKCEPIN` → 404
- 修复后：`curl https://sub-hkcepin.290372913.xyz:2087/clash/HKCEPIN` → 200 + 6 节点
- `tests/full_audit.py` 重跑：JP/HK/HKCEPIN 全 6 协议 + CDN 101，HK1 4 协议（direct），ALL OK

**修复**:
1. 远程服务器 `.env`：HKCEPIN `COUNTRY_CODE=HK→HKCEPIN`，HK1 `COUNTRY_CODE=HK→HK1`
2. `install.sh` 防复发：基于 `CF_DOMAIN` 前缀推导正确 COUNTRY_CODE（`jp.*→JP` / `hk.*→HK` / `hk1.*→HK1` / `hkcepin.*→HKCEPIN`），覆盖 ipinfo.io 自动检测值
3. `tests/full_audit.py` 修复 cc 硬编码 bug（HKCEPIN/HK1 的 cc 写死为 `'HK'` 导致测试用错路径）

**教训（铁律，已写入 AGENTS.md 第 15 条扩展）**:
1. **COUNTRY_CODE 是服务器标识，不是地理位置**：多台同地区服务器必须用域名前缀区分（HK/HK1/HKCEPIN），不能依赖 ipinfo.io 自动检测
2. **install.sh 的 ipinfo.io 检测只适合单服务器场景**：多服务器部署时必须用 CF_DOMAIN 前缀推导覆盖
3. **"优选 IP 全部失效"先查订阅端点是否 404**：CDN WS 101 ✅ + 订阅 404 = COUNTRY_CODE 错配，不是 CDN 故障
4. **文档审计 agent 报告需用 Glob/Read 验证**：不能直接信任 agent 报告的"文件不存在"结论
5. **测试脚本不能硬编码 cc**：`full_audit.py` 把 HKCEPIN/HK1 的 cc 写死为 `'HK'`，掩盖了真实 bug 长达数月

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
