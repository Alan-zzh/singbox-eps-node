# Singbox EPS Node 项目规则

## 接手流程

新 AI 接手本项目时,按以下顺序阅读:

1. **AGENTS.md**(本文件)— 项目规则唯一入口
2. **project_snapshot.md** — 当前项目真实状态
3. **AI_DEBUG_HISTORY.md** — 历史踩坑记录,禁止重复犯错
4. **CHANGELOG.md** — 最近变更
5. **VERSION.md** — 当前版本号
6. **docs/technical/** — 功能模块技术细节

## 凭据读取（AI 必备，禁止问用户）

本项目所有凭据在 `.env`（gitignored，本地工作区有副本）：

| 凭据 | 读取方式 | 说明 |
|------|----------|------|
| CF API Token/Email | `Get-Content .env \| Select-String "CF_API_TOKEN\|CF_API_EMAIL"` | CF API 访问；Global Key 需要 Email，scoped token 不需要 |
| CF Zone ID | `Get-Content .env \| Select-String "CF_ZONE_ID"` | CF 域名区域 ID |
| 各协议密码/UUID | `Get-Content .env \| Select-String "UUID\|PASSWORD\|KEY"` | .env 里的全部凭据 |
| 远程服务器 SSH | `python scripts/config.py` → `get_ssh_credentials()` | 从 .env 读取 SSH 主机/密码 |

> **如果在 scripts/config.py 中找不到**：直接 `Get-Content .env` 全文 grep。
> **远程服务器有自己的 .env** 在 `/root/singbox-eps-node/.env`，内容不同。

## 根目录六件套

| 文件 | 作用 | 更新时机 | 禁止内容 |
|------|------|----------|----------|
| AGENTS.md | 项目规则唯一入口 | 长期规则/协作方式/文档规范变化时 | 长篇技术细节、流水账、过时计划、重复内容 |
| README.md | 项目入口文档:是什么、怎么用、当前架构 | 使用/启动/部署方式变化时 | 排错流水账、版本历史、凭据 |
| AI_DEBUG_HISTORY.md | 踩坑病历:现象→根因→修复→教训 | 排查 bug/修复反复问题/发现高风险坑后 | 普通功能介绍、凭据明文、无结论猜测 |
| CHANGELOG.md | 用户可感知变更记录 | 完成用户可感知改动后 | 排错过程、长篇技术解释、未完成计划 |
| VERSION.md | 版本号锚点 | CHANGELOG 出现新版本级变更时同步 | 多版本历史、技术细节、计划列表 |
| project_snapshot.md | 项目当前真实状态快照 | 目录/服务/依赖/模块/部署状态变化时 | 过时历史、愿景、详细 bug 复盘 |

**文档真相源**：
- `docs/technical/`：已实现功能、模块说明、关键修复
- **禁止**新建 `AI/`、`ai-docs/`、`rules/`、`specs/`、`plans/`、`vision/` 等散落目录

## 行为规范

1. **先验证真实环境**,少猜测,少重构
2. **局部修改**,改后验证,不改不相关代码
3. **改代码前先看** project_snapshot.md + AI_DEBUG_HISTORY.md
4. **修改配置相关逻辑时**,优先统一到 scripts/config.py
5. **服务端和订阅端同类逻辑**必须一起改,不能只改一边
6. **推 GitHub 前**必须确认没有 .env、密码、Token、私钥等敏感信息
7. **修改后必须同步文档**,不要只改代码

## 重点禁忌

### 一、部署与配置

1. **本地代码修改未部署 = 线上不生效**：改完必须走 `deploy.py`（根目录部署入口，调用 `scripts/deploy_verify.py` 验证）全流程部署 → 重跑 config_generator → 重启服务。仅 SFTP 同步文件不算完成。
2. **协议增删必须三层同步**：① 订阅层 `subscription_service.py`（Base64 URI + sing-box JSON + Clash YAML 三处生成 + CLIENT_CAPABILITIES + CDN_PROTOCOL_KEYS + cdn_status_api）；② 服务端层 `config_generator.py`（入站块完全删除不能条件保留 `if enable_xxx`）；③ 辅助脚本 `install.sh` + `health_check.sh` + `diagnose.sh` + `cdn_monitor.py` + `cloudflare_proxy_rules.py` + `diagnose_disconnect.py`（端口/防火墙/iptables/CDN IP/诊断字典）。
   - 用户订阅只有两套固定模板：direct=VLESS-Reality/Trojan-TCP/anyTLS/TUIC-v5 共 4 节点；CDN=上述 4 节点 + VLESS-WS-CDN/Trojan-WS-CDN 共 6 节点。`AI_SOCKS5_*` 只允许作为服务器侧 AI 出口，禁止生成客户端 SOCKS5 节点；只有老板单独明确要求时，才能同时设置 `ENABLE_SOCKS5=true` 与 `PUBLISH_SOCKS5_NODE=true` 额外发布。
   - 加回协议时用 `grep -rn "ENABLE_xxx\|enable_xxx"` 扫描所有变量引用点，确认每处都有条件包裹，推荐 `*([{...}] if enable_xxx else [])` 解包语法
   - 每次协议增删强制 `grep` 检查 `node_name("...")` 参数不能含空格（如 `"TUIC-v5"` 不是 `"TUIC v5"`）
   - CDN WS 节点命名必须带 `-CDN` 后缀：`{CC}-VLESS-WS-CDN` / `{CC}-Trojan-WS-CDN`。Base64 fragment、Clash `name`、sing-box `tag`、proxy-groups 和 `cdn_status_api` 必须一致；所有 direct 模式不输出 CDN 节点。
3. **CRLF 换行污染**：Windows → Linux 的 `.env` 文件行尾 `\r` 会导致 hex 校验失败。所有 `.env` 读取命令加 `tr -d "\r"`。工具链：`deploy.py` pre-flight check + `scripts/deploy_verify.py` + `health_check.sh` 均已处理。
4. **凭据一致性**：服务端生成随机凭据时必须写入 `.env` 并被订阅端读取。订阅端实现凭据降级——`ENABLE_xxx=true` 且凭据为空时自动 `ENABLE_xxx=False`。
5. **Debian 12 PEP 668**：`pip3 install` 被阻止 → 用 `apt install python3-xxx` 或 `--break-system-packages`。一键安装脚本必须处理。
6. **证书信任边界**：自签证书必须含 SAN（`openssl -addext "subjectAltName=DNS:域名"`），否则 CF 回源 520；但用户直接访问的灰云订阅域名必须使用 Let's Encrypt 等公网可信证书，禁止用 `curl -k` 掩盖验证失败。一键安装必须从最终落盘 `.env` 读取域名，先同步/验证 DNS，再通过系统 CA 实际下载并校验三类订阅；任一步失败必须非零退出。
7. **小内存 VPS 必须配 MemoryMin + GOMEMLIMIT 双保险**，414MB 机器还需配 2GB Swap。
8. **pkill 自杀陷阱**：ExecStartPre 中禁止 `pkill -f "服务名.py"`，改用 `fuser -k 端口/tcp`。

### 二、Cloudflare 与 CDN

9. **CF SSL 模式必须为 full**（非 strict/full_strict），自签证书场景下 strict 导致 526。
10. **DNS proxied 按用途区分**：CDN 代理节点（VLESS-WS/Trojan-WS 入站）用主域名 `cf_domain`（橙云 `proxied=true`）；订阅端点（/clash /sub /singbox）用 sub-* 子域名（灰云 `proxied=false` 直连源站）。**两类严格分离，CDN 节点不得用 sub-***。
    - `sub-*` 只允许作为订阅入口，不得作为 CDN 节点 fallback；项目已有直连节点，CDN 节点要保持真正 CDN 路径。
11. **CF API Token 长度与认证方式**：40 字 hex(Global Key)、`cfat_` 开头 48 字(scoped token)、37 字短格式均合法。不要因长度判定"截断"。Global API Key 必须同时提供并持久化 `CF_API_EMAIL`，请求使用 `X-Auth-Key + X-Auth-Email`；`cfat_` scoped token 使用 Bearer 认证。安装日志不得输出任何 Token 前缀。
12. **CF 全局设置会漂移**：免费版 Managed Rules 自动启用拦截设置。`health_check.sh` 每 15 分钟巡检 `security_level/browser_check/bot_fight_mode/ssl/min_tls_version`，不符合自动修复。
    - 全域 CDN skip/origin 规则只有 `DEPLOY_MODE=cdn` 的服务器可以执行 `cloudflare_proxy_rules.py apply`；所有 direct 服务器健康检查必须跳过，禁止用各自 `CF_DOMAIN` 覆盖 JP 的全域规则。模式缺失或不是精确的 `cdn/direct` 时必须阻塞安装、健康检查和部署验证，禁止默认成 CDN。
13. **L7 DDoS eoff 不作为 health_check 修复目标**：`cloudflare_proxy_rules.py apply` 只维护 custom skip 规则和 TLS 1.2，确保删除 ddos_l7 override。CF 免费版 DDoS L7 无法通过 skip 规则绕过，WS 路径已改为非代理特征路径（`/api/v1/stream` `/api/v1/data`）以降低 ML 误报率。CDN 节点始终使用主域名橙云代理，不降级到 sub-*。
14. **CDN WS 验证标准 SOP**（防假阳性）：
    ```powershell
    curl.exe -s -4 --http1.1 --max-time 10 -k --noproxy "*" -o NUL -w "%{http_code}" `
      -H "Upgrade: websocket" -H "Connection: Upgrade" `
      -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Sec-WebSocket-Version: 13" `
      "https://{domain}:443/api/v1/stream"
    ```
    - **期望值**：`101`（∉403/520）
    - **铁律**：❌ 禁止漏掉 `--http1.1`（HTTP/2 不支持 Upgrade，可能假 400）；❌ 禁止 `-o /dev/null`（Windows 不识别，假 403）；❌ 禁止服务器自测（CF 拦服务器 IP，假 403）；❌ 禁止单次 403 就判 CDN 损坏（CF 瞬断重试即可）
    - **真实标准**：`tests/full_audit.py` 全 101 ✅；客户端实际能通 ✅
### 三、服务器识别

15. **直连模式与服务器标识必须分开，禁止用地理 COUNTRY_CODE 推模式**：
    - HK1（`hk1.290372913.xyz`）= 直接模式（固定 4 个订阅节点，无 CDN）
    - HK2（`hk2.290372913.xyz`）= 直接模式（固定 4 个订阅节点，无 CDN）
    - HKBEIYONG（`hkbeiyong.290372913.xyz`）= 直接模式（固定 4 个订阅节点，无 CDN）
    - `DEPLOY_MODE` 显式设置最高优先，fallback 用 `CF_DOMAIN.startswith(('hk1.', 'hk2.', 'hkbeiyong.'))`
    - `COUNTRY_CODE` 是节点/订阅服务器标识，安装器从 `CF_DOMAIN` 首标签安全转为大写（如 `hkbeiyong.* → HKBEIYONG`），不得用 ipinfo 地理码覆盖

### 四、协议与数据

16. **sing-box 字段必须查文档**：禁止凭直觉猜测（如 `idle_timeout` 不存在）。sing-box 1.13.11 默认含 gRPC transport。
17. **数据格式变更必须同步所有读取端**：如 cdn_ips_list JSON 格式变更。
18. **长驻进程必须有数据变更感知机制**：信号文件是最轻量的跨进程通知方式。

## 记录规范

| 事件 | 更新文件 | 不动 |
|------|----------|------|
| 修 bug(用户不可感知) | AI_DEBUG_HISTORY | CHANGELOG、VERSION、README、snapshot |
| 修 bug(用户可感知) | AI_DEBUG_HISTORY + CHANGELOG + VERSION | README、snapshot |
| 新增/删除功能 | CHANGELOG + VERSION + README | AI_DEBUG_HISTORY、snapshot |
| 改配置/目录结构 | snapshot + CHANGELOG + VERSION + README | AI_DEBUG_HISTORY |
| 使用方式变化 | README + CHANGELOG + VERSION | AI_DEBUG_HISTORY、snapshot |
| 纯排查未修 | AI_DEBUG_HISTORY | 其余不动 |

## 文档质量铁律

1. **禁止在根目录创建临时测试脚本**(`_*.py`/`_test*.py`/`_check*.py`/`_fix*.py`),测试脚本统一放 `tests/` 目录
2. **病历本写入前必须验证**:AI_DEBUG_HISTORY 的结论必须有命令输出/API返回/日志作为证据,禁止写无证据的猜测
3. **文档与代码同步**:改代码后必须同步更新对应的文档(六件套+docs/technical/),禁止只改代码不更新文档
4. **禁止假信息**:文档中禁止出现未经验证的"可能"/"也许"/"猜测"类结论,不确定的内容不写
