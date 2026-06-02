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
