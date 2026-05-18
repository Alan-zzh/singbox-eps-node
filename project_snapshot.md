# Singbox EPS Node 项目快照

**版本**: v4.3.6 | **更新**: 2026-05-18

---

## 当前状态

### 服务状态
| 服务 | 状态 | 说明 |
|------|------|------|
| singbox | ✅ | 代理内核，5个入站协议 |
| singbox-sub | ✅ | HTTPS订阅服务，端口2087 |
| singbox-cdn | ✅ | CDN优选IP学习系统（v4.1 存活优先模式） |

### 核心功能
- ✅ 5个代理协议：VLESS-Reality, VLESS-WS, VLESS-HTTPUpgrade, Trojan-WS, Hysteria2
- ✅ CDN优选IP：v4.1 存活优先模式（现有IP存活则不换，死亡才替换 + 用户投喂+外部API收集 + 存活率评分）
- ✅ CDN每小时自动更新：cdn_monitor.py while循环 + 进程锁防重复
- ✅ CDN IP自动同步：cdn_monitor写数据库 → subscription_service实时读取 → 用户更新订阅即可
- ✅ CDN纠错机制：subscription_service.py启动时检测CDN IP连通性，连不上自动回退到域名兜底
- ✅ 用户投喂IP池：config.py的CDN_PREFERRED_IPS为真理来源，优先级最高
- ✅ 存活检测：TCP端口连通性测试（3秒超时），不代替用户判断延迟质量
- ✅ 外部API持续收集：vvhan/090227/001315/WeTest/IPDB作为候选池补充
- ✅ 黑名单机制：CDN_IP_BLACKLIST永久跳过不需要的IP
- ✅ IP性能数据库：记录IP存活历史，连续死亡IP建议加入黑名单
- ✅ SOCKS5 AI路由：可选项（默认关闭），开启时13个AI域名走住宅代理，X/推特/groK排除
- ✅ AI路由开关：install.sh安装时可配置，tg_bot.py一键切换，立即重启生效
- ✅ 故障转移：AI-SOCKS5不可用时自动fallback到direct
- ✅ HY2端口跳跃：21000-21200→443，UDP+TCP双协议
- ✅ SSL证书：fullchain.pem优先，降级cert.pem
- ✅ `.env` 兼容读取：优先 `python-dotenv`，降级时兼容历史行内注释格式
- ✅ DNS配置已迁移到 sing-box 新格式，不再依赖 `ENABLE_DEPRECATED_*` 兼容开关
- ✅ sing-box JSON 默认关闭 FakeIP，避免 TUN 模式下 `ping <1ms` 这类假延迟误导判断
- ✅ 按月流量统计：iptables内核级计数器，持久化、重启不丢失
- ✅ BBR+FQ+CAKE三合一加速
- ✅ 旧面板彻底卸载：x-ui/marzban/3x-ui
- ✅ 一键诊断脚本：diagnose.sh 18项检查
- ✅ sing-box 1.13.9 完全兼容

### CDN优选IP学习系统（v4.1 存活优先模式）
**核心理念：现有IP存活则不换，死亡才替换 + 用户反馈驱动**

**工作流：**
```
每小时自动执行
          ↓
  检查数据库现有CDN IP → TCP存活检测
          ↓
  存活的IP保留 | 死亡的IP标记待替换
          ↓
  收集候选IP（用户投喂+外部API）
          ↓
  从候选池挑存活IP补上死亡空缺
          ↓
  只对新增候选IP做HTTP测试记录评分
          ↓
  写入数据库，更新订阅
```

**更新逻辑：**
- ✅ 现有IP存活 → 不替换，继续用
- ❌ 现有IP死亡 → 从候选池挑新的补上
- 🆕 用户投喂IP → 存活就加入候选池，按评分排序备选
- 🌐 外部API → 持续收集（vvhan/090227/001315/WeTest/IPDB）

**优先级排序：**
1. 现有存活IP - 优先保留
2. 用户投喂IP池（CDN_PREFERRED_IPS）- 填补空缺首选
3. 外部API候选 - 按存活率评分排序

**淘汰机制：**
- TCP连通失败 → 标记死亡，下次替换
- 用户反馈不好 → 加入CDN_IP_BLACKLIST，永久跳过
- 用户发现新好IP → 加入CDN_PREFERRED_IPS

**数据来源：**
- 用户投喂候选池（config.py的CDN_PREFERRED_IPS）- 优先级最高
- 外部API持续收集（vvhan/090227/001315/WeTest/IPDB）- 候选池补充

**v4.1 vs v4.0 区别：**
| 维度 | v4.0（旧） | v4.1（新） |
|------|-----------|-----------|
| 更新逻辑 | 每小时重新评分选TOP5 | 只替换死亡IP，存活不换 |
| 外部API | 仅当用户IP不足时使用 | 持续收集，作为候选池补充 |
| 稳定性 | 可能频繁切换IP | 更稳定，存活就不换 |
| 评分算法 | 存活率评分 | 存活率评分（保留历史评分机制） |

**为什么v4.1要改：**
- v4.0每小时重新选TOP5，即使现有IP都存活也会换
- 频繁切换IP可能导致用户连接不稳定
- v4.1改为"存活不换，死亡才换"，更稳定

### 定时任务
| 任务 | 频率 | 说明 |
|------|------|------|
| health_check.sh | 每5分钟 | config.json自愈+端口/服务/订阅/防火墙/证书/磁盘/Swap/iptables流量/CDN连通性检查 |
| cert_manager.py --renew | 每月1号凌晨3点 | SSL证书自动续签 |

### 三层自愈机制
| 层级 | 机制 | 触发条件 | 恢复动作 |
|------|------|----------|----------|
| 第1层 | systemd ExecStartPre | singbox启动时config.json不存在 | 自动运行config_generator.py |
| 第2层 | health_check.sh | 每5分钟crontab检查 | config.json缺失→自动生成+重启singbox |
| 第3层 | StartLimitBurst=10 | singbox连续崩溃 | 60秒内最多重启10次 |

### 路由规则顺序（客户端）
1. DNS规则
2. 私有地址直连
3. 国内直连（rule_set）
4. X/推特/groK排除（走ePS-Auto，不走SOCKS5）
5. AI网站（走ai-residential→AI-SOCKS5，故障转移direct）
6. final: ePS-Auto

### 路由规则顺序（服务端）
1. X/推特/groK排除（走direct）
2. AI网站（走ai-residential→AI-SOCKS5，故障转移direct）
3. final: direct

---

## 近期Bug修复

| Bug# | 版本 | 问题 | 修复 |
|------|------|------|------|
| #75 | v4.1.0 | CDN监控每小时重新选TOP5，即使现有IP都存活也会换，导致频繁切换 | 改为v4.1存活优先模式：现有IP存活则不换，死亡才替换 + 外部API持续收集 |
| #76 | v4.3.0 | AWS云服务器MTU 9001导致数据包分片，Hysteria2 UDP和所有协议卡顿 | MTU改为1500 + UDP缓冲区优化到25MB + 永久生效配置（日本+新加坡） |
| #77 | v4.3.0 | 新加坡CF_DOMAIN配置为us.290372913.xyz，CDN节点SNI错误导致连不上 | 改为sg.290372913.xyz，订阅路径大小写不敏感支持 |
| #78 | v4.3.1 | REALITY协议100%握手失败，客户端疯狂重试导致卡顿 | 重新生成REALITY密钥对（日本+新加坡），重启订阅服务 |
| #79 | v4.3.1 | sing-box 1.12.0+ DNS配置格式过时导致启动失败 | systemd服务添加ENABLE_DEPRECATED_LEGACY_DNS_SERVERS和ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER环境变量 |
| #80 | v4.3.1 | singbox-cdn服务未运行（日本），CDN数据库不存在 | 启动singbox-cdn，创建CDN数据库 |
| #81 | v4.3.2 | subscription_service.py的COUNTRY_CODE/SUB_TOKEN/AI_SOCKS5_POOL自己读.env不从config.py导入，违反唯一真相源 | 改为从config.py统一导入，删掉覆盖行 |
| #82 | v4.3.2 | REALITY_SHORT_ID/DEST/SNI从config.py导入后被os.getenv覆盖，等于白导入 | 删掉覆盖行，直接用config.py导入值 |
| #83 | v4.3.2 | config.py缺少AI_SOCKS5_POOL变量定义 | 补充AI_SOCKS5_POOL = os.getenv('AI_SOCKS5_POOL', '') |
| #84 | v4.3.2 | install.sh硬编码CF API Token，推GitHub会泄露 | 改为环境变量传入+交互式输入 |
| #85 | v4.3.3 | singbox-cdn死循环重启1492次：crontab每小时restart + systemd Restart=always + 进程锁冲突 | 删crontab重启条目 + Restart=always→on-failure + 清理锁文件重启 |
| #87 | v4.3.5 | singbox当前虽然能跑，但仍依赖 `ENABLE_DEPRECATED_*` 才能吃旧式DNS配置，未来升到1.14会再次启动失败 | `config_generator.py/subscription_service.py` 全量改成新DNS格式 + `route.default_domain_resolver`，并移除install.sh兼容开关 |
| #89 | v4.3.5 | 新格式DNS迁移时把 `detour: direct` 误带进新版 DNS server，导致日本机 singbox 起不来 | 删掉新版 DNS server 上错误的 `detour`，保留 `default_domain_resolver/domain_resolver` |
| #88 | v4.3.5 | install.sh和diagnose.sh仍有隐藏误差：21000-21200尾端口被写成21199，诊断脚本还会把正常CDN和正常流量计数器误判成故障 | 统一修正端口范围 + 改正iptables匹配逻辑 + CDN连通性改成带域名SNI测试 |
| #86 | v4.3.4 | `.env.example` 残留行内注释，手动复制后可能再次触发 `.env` 解析错值 | 清理示例文件行内注释 + `config.py/config_generator.py` 统一兼容解析旧格式 |
| #74 | v4.0.0 | CDN监控测试逻辑不合理：服务器在新加坡测延迟不代表国内体验，全量测试浪费资源 | 重构为v4.0用户反馈驱动版：只测存活、用户IP优先、外部API仅补充 |
| #73 | v3.1.3 | diagnose.sh crontab检查仍要求singbox-cdn重启(Bug#51已废弃) | 改为检测到则提示移除 |
| #72 | v3.1.3 | diagnose.sh 缺少4项关键检查 | 新增Swap/iptables流量/旧面板残留/CDN连通性/孤儿进程检查，14项→18项 |
| #71 | v3.1.3 | health_check.sh config.json自愈不校验JSON语法 | 增加JSON语法校验，损坏时自动重新生成 |
| #70 | v3.1.3 | health_check.sh 订阅检查硬编码端口2087 | 改为从config.py读取SUB_PORT |
| #69 | v3.1.3 | health_check.sh 缺少Swap和iptables流量计数器检查 | 新增check_swap()和check_iptables_traffic() |
| #68 | v3.1.3 | tg_bot.py 启动日志泄露Bot Token前缀 | 移除Token打印，仅记录启动事件 |
| #67 | v3.1.3 | tg_bot.py 异常信息暴露给用户(stderr/exception) | 异常写日志，返回通用错误信息 |
| #66 | v3.1.3 | tg_bot.py 设置住宅触发12次服务重启(4次×3服务) | 新增batch_update_env()批量更新后只重启1次 |
| #65 | v3.1.3 | tg_bot.py /重启命令漏重启singbox-sub和singbox-cdn | restart_singbox()改为重启全部3个服务 |

---

## 关键避坑记录

1. DNS服务器detour必须为direct，不能走代理（Bug #23）
2. AI规则禁止包含通用域名如google.com（Bug #28）
3. 排除规则必须在AI规则之前（Bug #25）
4. 104.x.x.x段必须严格过滤，不能"全部保留"（Bug #29）
5. ~~CDN服务必须crontab兜底重启~~ 已废弃：cdn_monitor.py加进程锁后不再需要crontab重启（Bug #31→#51）
6. 修改subscription_service.py必须同步修改config_generator.py（Bug #30）
7. 修复服务器问题必须同步更新install.sh（Bug #34）
8. 卸载旧面板必须彻底：stop+disable+删服务文件+删目录+杀进程+daemon-reload（Bug #33）
9. CDN本地IP池也必须过滤104.x.x.x段，不能因为"本地池"就放松过滤标准（Bug #35）
10. 服务重启必须覆盖所有相关服务：singbox + singbox-sub + singbox-cdn，包括cert_manager续签场景（Bug #36）
11. 健康检查必须覆盖UDP端口，HY2/QUIC使用UDP 443（Bug #37）
12. 数据库连接必须在finally中关闭，即使init_db()这种简单函数也不能例外（Bug #38）
13. 414MB小内存VPS必须配Swap（2GB），否则OOM killer会杀掉singbox进程导致掉线（Bug #39）
14. fwupd服务在小内存VPS上必须mask，它占用144MB会触发OOM（Bug #39）
15. singbox日志必须配logrotate，否则日志膨胀占满磁盘（运维#1）
16. HUNAN_CT_OPTIMAL_PREFIXES只包含实测确认的优质段：162.159/172.64/108.162/198.41/173.245，001315 API返回的非优质段IP也必须过滤（Bug #40修正）
17. ~~CDN优选IP必须以真实HTTP延迟测试为准~~ v4.0已废弃：服务器测的延迟≠用户体验，改为只测存活、以用户反馈为准
18. ~~CDN优选IP不能依赖IP段前缀打分，必须基于历史表现数据~~ v4.0已废弃：改为用户投喂=真理来源
19. CDN学习系统必须记录每个IP的性能历史，否则无法做存活检测（v4.0简化为存活记录）
20. 安装脚本添加crontab前必须先chmod +x，Git上传的脚本文件默认无执行权限（Bug #45）
21. 禁用服务时必须同时禁用其timer，否则timer会重新拉起service。systemctl mask要覆盖service+timer（Bug #46）
22. 外部API随时可能失效（如vvhan），必须有降级方案。多数据源+本地池冗余设计是正确的（Bug #47）
23. config.json被删时health_check应能自动重新生成，部署操作后必须验证config.json存在（Bug #48）
24. 从Windows上传shell脚本到Linux后必须转换换行符：sed -i 's/\r$//' （Bug #49）
25. systemd服务文件中所有路径必须使用绝对路径，禁止cd+相对路径组合（Bug #50）
26. 守护进程必须加进程锁（fcntl.flock），防止多实例运行导致内存泄漏（Bug #51）
27. VPS部署后必须禁用无用系统服务：multipathd/ModemManager/udisks2/caddy/unattended-upgrades（Bug #52）
28. sing-box 1.13.9 要求DNS配置必须有final字段，否则启动失败。历史上曾靠 systemd 的 deprecated DNS 兼容环境变量兜底，但这只是临时止血，不是长期方案（Bug #54）
29. sing-box 升级到 1.14 前，必须先把旧式 DNS server 写法迁移到新版 `type/server/path/rcode` 结构，并显式补 `route.default_domain_resolver`。不要再用 `ENABLE_DEPRECATED_*` 顶着跑（Bug #87）
29. HY2端口跳跃必须配置iptables UDP+TCP双协议规则，否则QUIC协议无法通过端口跳跃连接（Bug #55）
30. 新服务器一键安装必须完整验证，不能假设脚本能直接跑通，每个版本升级后必须实测（Bug #56）
31. 部署脚本执行完成后必须删除所有含密码/凭据的临时文件，禁止在本地或远程留存
32. Clash API /proxies 端点不返回 download/upload 字段，sing-box 1.10.0 无持久流量统计能力。流量统计必须用 iptables 内核级计数器（sing-box 1.13.9 编译标签只有 with_clash_api，没有 with_v2ray_api，所以 gRPC StatsService 也不可用）
33. CDN监控保存的数据库key必须与订阅服务读取的key一致：vless_ws_cdn_ip/vless_upgrade_cdn_ip/trojan_ws_cdn_ip（Bug #74）
34. CDN优选IP必须以用户反馈为准，服务器在新加坡/日本测的延迟不代表中国用户体验（v4.0重构依据）
35. 部署时不能用自定义脚本替代install.sh，install.sh是唯一安装入口，所有功能变更必须先改install.sh（Bug #65教训）
36. AWS云服务器默认MTU 9001（Jumbo Frames），但客户端MTU 1500，数据包分片导致UDP丢包和TCP重传，所有协议卡顿。必须改为MTU 1500 + 优化UDP缓冲区（Bug #76）
37. 新加坡服务器CF_DOMAIN必须用sg.290372913.xyz，不能用us域名，否则CDN节点SNI错误导致连不上（Bug #77）
38. subscription_service.py从config.py导入的变量禁止被os.getenv覆盖，否则等于白导入，config.py的值会被丢弃（Bug #82）
39. config.py必须定义所有被其他文件引用的变量，缺少定义会导致ImportError或NameError（Bug #83）
40. install.sh禁止硬编码API Token/密码/密钥，必须从环境变量传入或交互式输入，否则推GitHub会泄露（Bug #84）
41. singbox-cdn的systemd服务必须用Restart=on-failure而非Restart=always，因为cdn_monitor检测到已有实例运行时会正常退出(exit 0)，Restart=always会导致死循环重启。同时crontab中禁止加systemctl restart singbox-cdn（Bug #85）

---

## 部署记录

### 新加坡服务器（13.212.37.11）
- 域名：sg.290372913.xyz
- 部署时间：2026-05-04
- 版本：v4.3.1
- 状态：正常运行
- 修复记录：2026-05-07 修复CF_DOMAIN错误(us→sg)、MTU 9001→1500、UDP缓冲区优化、REALITY密钥更新、DNS兼容性修复

### 日本服务器（52.195.179.240）
- 域名：jp.290372913.xyz
- 部署时间：2026-05-03
- 版本：v4.3.1
- 状态：正常运行
- 修复记录：2026-05-07 修复.env注释导致ValueError、空密码导致singbox无法启动、MTU 9001→1500、UDP缓冲区优化、REALITY密钥更新、DNS兼容性修复、启动singbox-cdn
