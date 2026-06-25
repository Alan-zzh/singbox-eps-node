v4.13.0 - [Trae CN+多智能体QA] 新增Cloudflare WARP DNS解锁功能:零成本原生解锁AI+流媒体(OpenAI/ChatGPT/Gemini/Claude/TikTok/Netflix);sing-box内置WireGuard直连无额外进程;X/Twitter/Google/YouTube保持服务器直连不影响速度;bash install.sh warp-unlock一键安装/关闭;默认关闭不影响现有功能;修复路由冲突(AI-SOCKS5启用时WARP仅处理流媒体);增加IPv4校验+二进制验证+trap临时文件清理;warp_unlock.sh改为薄封装避免代码重复

v4.12.22 - [Trae CN] 订阅名称修复:三端点(/clash /sub /singbox)的profile-title和Content-Disposition去掉流量数据,名称只显示国家名(如"日本 Clash");流量通过subscription-userinfo响应头实时同步(Clash更新订阅时自动读取);profile-title用URL编码兼容HTTP头;新增profile-web-page-url指向/info页面

v4.12.21 - [Trae CN] CDN优选评分修复:assign_and_save_ips漏传user_path_result和cross_isp_score参数导致评分走fallback分支(83分→应96分),修复后三台服务器CDN IP评分从83提升到95-96;修复HK服务器USER_DDNS_DOMAIN为空导致用户路径评分失效;清理病历本v4.12.12错误结论+AGENTS.md错误禁忌;清理5个临时脚本;优化文档质量铁律

v4.12.20 - [Trae CN LOOP+多智能体] 彻底修复Cloudflare 403拦截:纠正SKIP_PHASES(ddos_l7不属于可skip阶段,免费计划API返回not authorized),正确方案是skip其他3个安全阶段+ddos_l7 phase创建sensitivity_level=eoff override(非删除);修正v4.12.12病历本中"删除eoff override"的错误结论;CDN直连IP+正确Host/SNI验证VLESS-WS(8443)和Trojan-WS(2083) 101握手成功;3轮72项多UA多端点稳定性测试全部PASS

> 注:当前服务端为单独 sing-box,JP/SG/HK 统一运行官方 latest 1.13.13;Xray/v2rayN 仅是客户端兼容口径。
