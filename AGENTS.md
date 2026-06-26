# Singbox EPS Node 项目规则

## 接手流程

新 AI 接手本项目时,按以下顺序阅读:

1. **AGENTS.md**(本文件)— 项目规则唯一入口
2. **project_snapshot.md** — 当前项目真实状态
3. **AI_DEBUG_HISTORY.md** — 历史踩坑记录,禁止重复犯错
4. **CHANGELOG.md** — 最近变更
5. **VERSION.md** — 当前版本号
6. **docs/technical/** — 功能模块技术细节

## 根目录六件套

| 文件 | 作用 | 更新时机 | 禁止内容 |
|------|------|----------|----------|
| AGENTS.md | 项目规则唯一入口 | 长期规则/协作方式/文档规范变化时 | 长篇技术细节、流水账、过时计划、重复内容 |
| README.md | 项目入口文档:是什么、怎么用、当前架构 | 使用/启动/部署方式变化时 | 排错流水账、版本历史、凭据 |
| AI_DEBUG_HISTORY.md | 踩坑病历:现象→根因→修复→教训 | 排查 bug/修复反复问题/发现高风险坑后 | 普通功能介绍、凭据明文、无结论猜测 |
| CHANGELOG.md | 用户可感知变更记录 | 完成用户可感知改动后 | 排错过程、长篇技术解释、未完成计划 |
| VERSION.md | 版本号锚点 | CHANGELOG 出现新版本级变更时同步 | 多版本历史、技术细节、计划列表 |
| project_snapshot.md | 项目当前真实状态快照 | 目录/服务/依赖/模块/部署状态变化时 | 过时历史、愿景、详细 bug 复盘 |

## 文档真相源

- **根目录六件套**:项目级核心文档,各管各的,不重复
- **docs/technical/**:已实现功能、模块说明、关键修复、重要约束
- **docs/reference/**:外部资料、接口说明、调研记录
- **docs/archive/**:过时但需保留的旧文档

禁止新建 AI/ai-docs/rules/specs/plans/vision 等散落目录。计划类内容直接写进 CHANGELOG 或 project_snapshot.md。

## 行为规范

1. **先验证真实环境**,少猜测,少重构
2. **局部修改**,改后验证,不改不相关代码
3. **改代码前先看** project_snapshot.md + AI_DEBUG_HISTORY.md
4. **修改配置相关逻辑时**,优先统一到 scripts/config.py
5. **服务端和订阅端同类逻辑**必须一起改,不能只改一边
6. **推 GitHub 前**必须确认没有 .env、密码、Token、私钥等敏感信息
7. **修改后必须同步文档**,不要只改代码

## 重点禁忌

### 部署与配置

1. **本地代码修改未部署 = 线上不生效**:修改后必须同步部署到所有服务器,仅 SFTP 同步文件不算完成,必须 `cd && python3 scripts/config_generator.py` + `systemctl restart singbox`
2. **协议代码层新增必须配套配置重生成**:修改 `config_generator.py` 新增/删除入站协议时,必须确保 install.sh 启动流程会重跑 `config_generator.py`,否则服务器 config.json 仍合法存在 → 入站缺失但订阅伪造"已生效"
3. **协议增删必须订阅层 + 服务端层 + 辅助脚本三处同步**(v4.14.0 扩展):新增/删除协议时,必须同步修改三类文件——① 订阅层 `subscription_service.py`(Base64 URI + sing-box JSON + Clash YAML 三处生成函数 + `CLIENT_CAPABILITIES` + `CDN_PROTOCOL_KEYS` + `cdn_status_api`);② 服务端层 `config_generator.py`(入站块完全删除,不能条件性保留 `if enable_xxx`,否则 `ENABLE_xxx=true` 时服务端有入站但客户端无节点);③ 辅助脚本 `install.sh` + `health_check.sh` + `diagnose.sh` + `cdn_monitor.py` + `cloudflare_proxy_rules.py` + `diagnose_disconnect.py`(端口列表 + 防火墙规则 + iptables 计数器 + CDN IP 分配 + 诊断协议字典)。**v4.13.3 教训**:修改订阅层 CDN 节点的 server/Host 字段时,必须同步修改 config_generator.py 中 CDN 入站的 `headers.Host`/`host` 字段,否则 sing-box Host 校验失败报 "bad host"。**v4.14.0 教训**:废弃协议必须完全删除入站块,不能条件性保留(`if enable_tuic`),否则配置不一致;辅助脚本的残留代码不会立即报错但会污染数据库和诊断输出
4. **verify_installation 必须覆盖所有入站端口**:包括 .env 随机端口(VLESS_GRPC_PORT/TROJAN_TCP_PORT),不能只验证老端口
5. **SQLite 迁移假成功**:迁移后必须核验表结构;多进程并发场景必须用 WAL 模式(`PRAGMA journal_mode = WAL`)
6. **pkill 自杀陷阱**:ExecStartPre 中禁止 `pkill -f "服务名.py"`,改用 `fuser -k 端口/tcp`(fuser 来自 psmisc 包,一键安装必须包含)
7. **Debian 12 PEP 668**:pip3 install 被阻止,需用 `apt install python3-xxx` 或 `--break-system-packages`,一键安装脚本必须处理此兼容性
8. **自签证书必须含 SAN**:openssl 生成自签名证书时必须添加 `-addext "subjectAltName=DNS:域名"`,否则 Cloudflare 回源 520 错误
9. **小内存 VPS 必须配 MemoryMin + GOMEMLIMIT 双保险**,414MB 机器还需配 2GB Swap

### Cloudflare 与 CDN

10. **CF SSL 模式必须为 full**:自签证书场景下 strict/full_strict 会导致 526 回源失败,必须设为 full(允许自签证书,只加密不验证 CA 身份)
11. **DNS proxied 按用途区分（v4.13.2 修正）**:CDN 节点子域名（如 `jp/sg/hk.290372913.xyz`）必须 `proxied=true`（橙云），否则 CDN 完全失效（TLS 握手失败），绝对不能改；但**订阅端点 sub-* 子域名**（如 `sub-jp/sub-sg/sub-hk.290372913.xyz`）必须 `proxied=false`（灰云直连源站），绕过 CF DDoS L7 ML 系统（详见第16条）。两类子域名用途不同，proxied 设置相反，不能混淆
12. **CF API Token 长度校验**:`CF_API_TOKEN` 必须是 40 字符 hex(Global API Key)或 `cfat_` 开头 48 字符(scoped token),37 字符是截断的病态值,会导致所有 CF API 调用静默失败。Global API Key 用完立刻在 https://dash.cloudflare.com/profile/api-tokens 页面底部点 "Roll" 吊销旧 key
13. **CF 全局设置巡检**:每周或每次新部署必须确认 `security_level=essentially_off` + `browser_check=off` + `bot_fight_mode=off`,CF 免费版 Managed Rules 会自动启用并拦截代理流量
14. **诊断必须分 IPv4/IPv6**:CF 对数据中心 IPv6 段会误判为爬虫,curl 测试必须加 `-4` 强制 IPv4 才不会误判"CDN 全断"
15. **CDN 520/400/403 是假象**:curl 测试 CDN 端口返回 4xx/520 不等于协议不通,需用正确 WebSocket 头(含 Sec-WebSocket-Key)测试,sing-box 只响应合法 WebSocket 握手。要验证是否真通,必须看 sing-box.log 中有无 inbound 真实连接记录
16. **订阅端点必须走 sub-* gray cloud 直连子域名绕过 CF DDoS L7**(v4.13.1 推翻 v4.12.20 的 eoff 方案):CF 免费计划 DDoS L7 是基于 ML 的动态保护系统,**无法通过任何 API 配置完全关闭**。`sensitivity_level=eoff` 只降低灵敏度,ML 仍会动态拦截(`off`/`skip ddos_l7 phase`/`skip ddosL7 product` 全部被 API 拒绝)。v4.12.20 的 eoff 方案是假阳性——3轮72项测试在 CF 规则传播延迟窗口(~1-2小时)内通过,传播完成后 ML 重新激活 403 复发。**正确方案**:订阅端点走 `sub-jp/sub-sg/sub-hk.290372913.xyz` 三个 gray cloud(`proxied=false`)子域名直连源站,完全绕过 CF 代理层。`cert_manager.py` 的 `_build_sub_domain()` + `generate_self_signed_cert()` + `request_cf_ssl_certificate()` 已将 sub-* 子域名加入 SAN。CF API 配置(skip 规则 + eoff override)仍需保留作为代理路径的兜底降级,但不能作为订阅端点的唯一路径。CDN 全部 403 诊断顺序:① 确认订阅走 sub-* 直连(主路径) → ② 源站直连确认服务正常 → ③ GraphQL 查 `firewallEventsAdaptive.source` 字段确认拦截源 → ④ 检查 skip 规则是否正确(不能含 ddos_l7) → ⑤ 检查 ddos_l7 override 是否为 eoff

### sing-box 与协议

17. **sing-box 字段必须查文档**:禁止凭直觉猜测字段名(如 idle_timeout 不存在);sing-box 1.13.11 默认编译已含 gRPC transport,不需要升级到 1.15.0 也能用 grpc
18. **CDN 443 端口不提供 HTTP 服务**:测速只能用 TCP+TLS 握手,不能发 HTTP 请求
19. **评分维度必须全部有效**:无效维度等于白算且拉低区分度;CDN→Google 测速不影响用户体验,不应纳入评分

### 跨进程与数据

20. **数据格式变更必须同步所有读取端**:如 cdn_ips_list JSON 格式变更
21. **长驻进程必须有数据变更感知机制**:信号文件是最轻量的跨进程通知方式
22. **"推特私信发不出"先判平台限流**:不要只凭单一应用体感就改服务器

## 记录规范

| 事件 | 更新文件 | 不动 |
|------|----------|------|
| 修 bug(用户不可感知) | AI_DEBUG_HISTORY | CHANGELOG、VERSION、README、snapshot |
| 修 bug(用户可感知) | AI_DEBUG_HISTORY + CHANGELOG + VERSION | README、snapshot |
| 新增/删除功能 | CHANGELOG + VERSION + README | AI_DEBUG_HISTORY、snapshot |
| 改配置/目录结构 | snapshot + CHANGELOG + VERSION + README | AI_DEBUG_HISTORY |
| 使用方式变化 | README + CHANGELOG + VERSION | AI_DEBUG_HISTORY、snapshot |
| 纯排查未修 | AI_DEBUG_HISTORY | 其余不动 |

## 技术细节引用

长技术说明不要写进本文件,指向 docs/technical/:

- Clash 订阅生成铁律:[docs/technical/clash-subscription-rules.md](docs/technical/clash-subscription-rules.md)
- 全量技术文档:[docs/technical/technical-doc.md](docs/technical/technical-doc.md)
- 闪断排查手册:[docs/technical/troubleshooting-silent-disconnect.md](docs/technical/troubleshooting-silent-disconnect.md)
- CDN 质量集成指南:[docs/reference/cdn-quality-integration-guide.md](docs/reference/cdn-quality-integration-guide.md)

## 文档质量铁律

1. **禁止在根目录创建临时测试脚本**(`_*.py`/`_test*.py`/`_check*.py`/`_fix*.py`),测试脚本统一放 `tests/` 目录
2. **病历本写入前必须验证**:AI_DEBUG_HISTORY 的结论必须有命令输出/API返回/日志作为证据,禁止写无证据的猜测
3. **病历本错误结论必须标注推翻**:如果后续发现某条目结论错误,必须在原条目标注 `⚠️ 已被 vXXX 推翻`,并写明正确结论,不能直接删除(保留排查过程供参考)
4. **文档与代码同步**:改代码后必须同步更新对应的文档(六件套+docs/technical/),禁止只改代码不更新文档
5. **禁止假信息**:文档中禁止出现未经验证的"可能"/"也许"/"猜测"类结论,不确定的内容不写
