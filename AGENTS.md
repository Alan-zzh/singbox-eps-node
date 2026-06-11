# Singbox EPS Node 项目规则

## 接手流程

新AI接手本项目时，按以下顺序阅读：

1. **AGENTS.md**（本文件）— 项目规则唯一入口
2. **project_snapshot.md** — 当前项目真实状态
3. **AI_DEBUG_HISTORY.md** — 历史踩坑记录，禁止重复犯错
4. **CHANGELOG.md** — 最近变更
5. **VERSION.md** — 当前版本号
6. **docs/technical/** — 功能模块技术细节

## 根目录六件套

| 文件 | 作用 | 更新时机 | 禁止内容 |
|------|------|----------|----------|
| AGENTS.md | 项目规则唯一入口 | 长期规则/协作方式/文档规范变化时 | 长篇技术细节、流水账、过时计划、重复内容 |
| README.md | 项目入口文档：是什么、怎么用、当前架构 | 使用/启动/部署方式变化时 | 排错流水账、版本历史、凭据 |
| AI_DEBUG_HISTORY.md | 踩坑病历：现象→根因→修复→教训 | 排查bug/修复反复问题/发现高风险坑后 | 普通功能介绍、凭据明文、无结论猜测 |
| CHANGELOG.md | 用户可感知变更记录 | 完成用户可感知改动后 | 排错过程、长篇技术解释、未完成计划 |
| VERSION.md | 版本号锚点 | CHANGELOG出现新版本级变更时同步 | 多版本历史、技术细节、计划列表 |
| project_snapshot.md | 项目当前真实状态快照 | 目录/服务/依赖/模块/部署状态变化时 | 过时历史、愿景、详细bug复盘 |

## 文档真相源

- **根目录六件套**：项目级核心文档，各管各的，不重复
- **docs/technical/**：已实现功能、模块说明、关键修复、重要约束
- **docs/plans/**：计划、方案、任务拆解（必须标明状态）
- **docs/vision/**：愿景、路线图、产品方向
- **docs/reference/**：外部资料、接口说明、调研记录
- **docs/archive/**：过时但需保留的旧文档

禁止新建 AI/ai-docs/rules/specs/plans 等散落目录。

## 行为规范

1. **先验证真实环境**，少猜测，少重构
2. **局部修改**，改后验证，不改不相关代码
3. **改代码前先看** project_snapshot.md + AI_DEBUG_HISTORY.md
4. **修改配置相关逻辑时**，优先统一到 scripts/config.py
5. **服务端和订阅端同类逻辑**必须一起改，不能只改一边
6. **推GitHub前**必须确认没有 .env、密码、Token、私钥等敏感信息
7. **修改后必须同步文档**，不要只改代码

## Clash 订阅生成铁律

### 1. url-test 策略组三件套与测速方案
修改 `subscription_service.py` 中 Clash url-test 生成时，必须使用：
- `lazy: false` — 后台持续测速（严禁设为 `true` 导致锁死坏节点）
- `tolerance: 150` — 电信网络波动容忍值（禁止低于 100）
- `interval: 60` — 60 秒测速一轮（严禁设为 600s 导致卡顿 10 分钟）
- `url: http://cp.cloudflare.com/generate_204` — HTTP 协议避免 TLS 握手损耗
- `timeout: 5000` — 测速超时 5 秒

违反后果：Clash 自动切换过于迟钝导致发消息卡顿，或过于频繁导致连接抖动（Bug #88）。

### 2. 规则 MATCH 必须指向 select 组（节点选择）
- MATCH 规则必须指向 `节点选择`（select 组），绝对不能直接指向 `自动选择`（url-test 组）
- `节点选择` 的首个 proxy 必须是 `自动选择`，用户可在 UI 自由切换（Bug #89）

### 3. 高风险参数禁止恢复
以下参数在丢包环境下会放大问题，禁止恢复到自动选择组：
- `keep-alive-interval` — 丢包隧道上适得其反
- `tcp-concurrent` — 频繁触发连接 RST
- `unified-delay` — 干扰判断

## 重点禁忌

1. **本地代码修改未部署 = 线上不生效**：修改后必须同步部署到所有服务器
2. **SQLite 迁移假成功**：迁移后必须核验表结构
3. **pkill 自杀陷阱**：ExecStartPre 中禁止 `pkill -f "服务名.py"`，改用 `fuser -k 端口/tcp`
4. **sing-box 字段必须查文档**：禁止凭直觉猜测字段名（如 idle_timeout 不存在）
5. **CDN 443 端口不提供 HTTP 服务**：测速只能用 TCP+TLS 握手，不能发 HTTP 请求
6. **"推特私信发不出"先判平台限流**：不要只凭单一应用体感就改服务器
7. **数据格式变更必须同步所有读取端**：如 cdn_ips_list JSON 格式变更
8. **长驻进程必须有数据变更感知机制**：信号文件是最轻量的跨进程通知方式
9. **小内存 VPS 必须配 MemoryMin + GOMEMLIMIT 双保险**
10. **评分维度必须全部有效**：无效维度等于白算且拉低区分度
11. **CDN 520是假象**：curl测试CDN端口返回520不等于CDN不通，需用正确WebSocket头（含Sec-WebSocket-Key）测试，sing-box只响应合法WebSocket握手
12. **DNS proxied=false致命**：proxied=false会导致CDN完全失效（TLS握手失败），绝对不能改。CDN节点需要proxied=true才能通过Cloudflare代理回源
13. **Debian 12 PEP 668**：pip3 install被阻止，需用apt install python3-xxx或--break-system-packages，一键安装脚本必须处理此兼容性
14. **psmisc是必需依赖**：fuser命令来自psmisc包，缺失会导致singbox ExecStartPre失败，一键安装必须包含psmisc
15. **自签证书必须含SAN**：openssl生成自签名证书时必须添加-addext "subjectAltName=DNS:域名"，否则Cloudflare回源520错误
16. **CF API Token 长度校验**（v4.10.21 新增）：.env 中 `CF_API_TOKEN` 必须是 40 字符 hex（Global API Key）或 `cfat_` 开头 48 字符（scoped token），37 字符是截断的病态值，会导致所有 CF API 调用静默失败
17. **CF 全局设置巡检**（v4.10.21 新增）：每周或每次新部署必须确认 `security_level=essentially_off` + `browser_check=off` + `bot_fight_mode=off`，CF 免费版 Managed Rules 会自动启用并拦截代理流量
18. **诊断必须分 IPv4/IPv6**（v4.10.21 新增）：CF 对数据中心 IPv6 段会误判为爬虫，curl 测试必须加 `-4` 强制 IPv4 才不会误判"CDN 全断"
19. **Global API Key 用完立刻 Roll**（v4.10.21 新增）：Global API Key 是账户最高权限，用完必须在 https://dash.cloudflare.com/profile/api-tokens 页面底部点 "Roll" 吊销旧 key 拿新 key
20. **sing-box 400/520 ≠ 协议不通**（v4.10.21 新增）：curl 测试 CDN 协议没做完整 WS 握手被 sing-box 拒，返回 4xx 是正常的。**真实用户客户端会做完整握手**。要验证是否真通，必须看 sing-box.log 中有无 inbound 真实连接记录
21. **协议代码层新增必须配套配置重生成**（v4.11.1 新增）：修改 `scripts/config_generator.py` 新增/删除入站协议时，必须确保 install.sh 启动流程会重跑 `config_generator.py`，否则服务器 config.json 仍合法存在 → 触发器不生效 → 入站缺失但订阅伪造"已生效"。教训：v4.11.0 新增 vless-grpc/trojan-tcp 后，install.sh 只在 config.json 缺失/损坏时才重跑，服务器 config.json 没更新 → 用户"协议连不上"实际是入站缺失
22. **deploy.py 同步 .py 后必须重跑 config_generator.py + 重启 singbox**（v4.11.1 新增）：仅 SFTP 同步文件不算完成部署，必须 `cd && python3 scripts/config_generator.py` + `systemctl restart singbox`，否则 singbox 仍跑旧 config.json
23. **verify_installation 验证脚本必须覆盖所有入站端口**（v4.11.1 新增）：包括 .env 随机端口（VLESS_GRPC_PORT/TROJAN_TCP_PORT），不能只验证老端口
24. **订阅伪造"已生效"陷阱**（v4.11.1 新增）：subscription_service.py 是订阅层（生成 7 节点 URL），config_generator.py 是服务端层（生成 7 入站配置），两者**必须同时部署**。仅升级订阅层导致"订阅看到节点但服务端没监听"——用户感知"协议连不上"
25. **singbox 1.13.11 默认编译已含 gRPC transport**（v4.11.1 新增）：不需要升级到 1.15.0 也能用 grpc（strings 验证含 grpc/grpcu/GRPCOptions）
26. **CF SSL 模式必须为 full**（v4.11.2 新增）：自签证书场景下 strict/full_strict 会导致 526 回源失败，必须设为 full（允许自签证书，只加密不验证 CA 身份）。每次部署或 CF 设置变更后必须确认 SSL 模式为 full
27. **v2rayN/Xray-core 客户端协议兼容**（v4.12.1 新增）：VLESS-HTTPUpgrade（`type=httpupgrade`）和 TUIC v5（`tuic://`）Xray-core 完全不支持。生成订阅时必须按 UA 自动分流：Clash/sing-box/NekoBox → 7 节点；v2rayN/v2rayNG/Shadowrocket/Quantumult X → 5 节点（剔除这 2 个）。**禁止把任何 Xray-core 不识别的 URI 塞进 /sub 端点**
28. **订阅流量统计必须 INPUT+OUTPUT 双向**（v4.12.1 新增）：原版 `setup_iptables_traffic_counters()` 只在 INPUT 链建规则，下载流量被低估 50%。修复：INPUT + OUTPUT 双链都建规则，UDP 端口（TUIC v5 QUIC 协议）独立建规则。`get_iptables_traffic_bytes()` 也必须 INPUT+OUTPUT 求和
29. **v2rayN 不解析 subscription-userinfo header**（v4.12.1 新增）：v2rayN 订阅更新只显示"成功: N 个节点"，永远不显示流量。新增 `/info` 端点（v2rayN 浏览器能看）+ Base64 头部插入流量注释行（部分客户端可见）作为补充，**禁止期望 v2rayN 通过 subscription 显示流量**
30. **HTTP header 不能含非 ASCII 字符**（v4.12.1 新增）：Flask `Response.headers` 只能设置 latin-1 编码的值，`Content-Disposition: attachment; filename=香港订阅.txt` 会触发 UnicodeEncodeError 导致 500。修复：RFC 5987 `filename*=UTF-8''URL编码`，或 profile-title 改为纯 ASCII。**任何通过 header 传递中文字符必须 URL-encode**

## 记录规范

| 事件 | 更新文件 | 不动 |
|------|----------|------|
| 修 bug（用户不可感知） | AI_DEBUG_HISTORY | CHANGELOG、VERSION、README、snapshot |
| 修 bug（用户可感知） | AI_DEBUG_HISTORY + CHANGELOG + VERSION | README、snapshot |
| 新增/删除功能 | CHANGELOG + VERSION + README | AI_DEBUG_HISTORY、snapshot |
| 改配置/目录结构 | snapshot + CHANGELOG + VERSION + README | AI_DEBUG_HISTORY |
| 使用方式变化 | README + CHANGELOG + VERSION | AI_DEBUG_HISTORY、snapshot |
| 纯排查未修 | AI_DEBUG_HISTORY | 其余不动 |

## 技术细节引用

长技术说明不要写进本文件，指向 docs/technical/：
- 全量技术文档：[docs/technical/technical-doc.md](docs/technical/technical-doc.md)
- 闪断排查手册：[docs/technical/troubleshooting-silent-disconnect.md](docs/technical/troubleshooting-silent-disconnect.md)
- CDN 质量集成指南：[docs/reference/cdn-quality-integration-guide.md](docs/reference/cdn-quality-integration-guide.md)

## 计划引用

所有计划写入 docs/plans/，必须标明状态（已完成/部分完成/未执行/已废弃）。

## 愿景引用

愿景和路线图写入 docs/vision/，README 和 snapshot 只写当前真实状态。
