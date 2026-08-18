# 新会话交接 Prompt

用途：开新会话时把本文件内容整段粘到第一条消息，让新会话不必重新摸底。
落笔时间：2026-08-16，对应 HEAD `d6787ab`。

> 维护提醒：完成 P0 后请更新「本次要做的事」与 HEAD，避免交接信息过期。

---

```
# 项目：群星 Star —— 一个 web 管所有 AI agent

## 仓库
g:\traework\star（Python/FastAPI 后端 + star-ui 静态前端）
远端：github、gitcode 两个，main 分支当前 HEAD = d6787ab

## 产品目标（最重要，别偏离）
手机上只装一个浏览器、打开一个地址，就能管理所有 AI agent。
不要每个 agent 装一个 App、开一堆窗口、各存一份数据。
Star 用一套系统统一接管：目前支持 DuMate 桌面端、Trae，都通过
Chrome DevTools Protocol(CDP) 驱动。端口约定：9223=Trae、9224=Comate、9225=DuMate。

## 后端现状（已验证可用，不用重做）
- 鉴权已改成「结构上默认拒绝」：所有 /api router 经 _include_guarded 强制挂
  require_by_method 依赖。安全方法要 read，写方法按 control/admin/write 分级。
- 3 个 AI 适配器后端正常：GET /api/dumate/adapters 带 X-API-Key 返回
  dumate / trae_work / dumate_app，trae_work 和 dumate_app 均 connected。
- Trae 冷启动已修好：真凶是 Comate 集成终端注入的 ELECTRON_RUN_AS_NODE=1
  被子进程继承，导致 Trae 退化成纯 Node 秒退。已用 clean_launch_env() 剔除
  ELECTRON_*。全链路（杀进程→自动拉起→9223 就绪→发任务→取回复）实测通过。
- admin key 在 config.yaml 的 auth.api_keys 里（role=admin）。config.yaml 已
  被 gitignore，首跑自动生成随机 key。
- pytest tests：388 passed。

## 本次要做的事：前端从「能连」升级到「好用」
根因诊断：UI 打开后一片空白，不是后端问题，而是前端 localStorage 没存
API Key，所有请求 401，且 UI 把 401 当成「没有 AI」静默吞掉。

已探明的前端问题（star-ui/，11 个页面，入口 pages/starmap.html）：
- pages/dumate.html:1074-1083 loadAdapters()：catch 后置空数组，401 被伪装成
  「未发现适配器」。这是用户看到空白的直接原因。
- 全站 9 处 catch(e){} 完全静默；starmap.html:1036 用 .catch(()=>({stars:[]}))
  把 401 变空星图。
- broadcast.html:258 用裸 fetch()，根本不带 X-API-Key，鉴权上线后必然失败且无提示。
- 只有 settings.html:697 一处正确用了 err.status 判断 401；starfleet.html:507
  靠 err.message.startsWith('401') 凑，且引导指向和 settings 不一致。
- AI 列表散在 3 个互不相干的接口：/api/dumate/adapters（dumate.html）、
  /api/work/ai（dispatch.html）、/api/emissary/adapters（starmap.html）。
  「一套系统管所有」在 UI 层还没落地。
- 移动端基本不可用：零外部 CSS，全站只有 1 处 @media，starmap 侧边栏是
  w-[60px] 固定图标条。5 个页面（starfleet/remote/programming/broadcast/
  calibrator）没有任何导航，进去出不来。
- 共享脚本：star-ui/js/api-bridge.js（apiFetch 在 :35-39 抛带 err.status 的错，
  各 api 对象在此定义）、js/nav.js（导航行为）。

## 分三步做（先 P0）
P0 让手机打开不再是白板：
  - 新建 star-ui/js/auth-gate.js：全站共享 Key 网关。无 Key→顶部常驻提示条+
    一键填 Key 浮层；任意 401→统一弹同一浮层，填完自动重试。一处实现全站引用。
  - api-bridge.js apiFetch 401 时派发全局事件，页面不再各自 catch。
  - 修掉 9 处静默 catch + broadcast.html 裸 fetch。
P1 一个页面管所有 agent：统一 agent 总览（合并 3 个接口），就地发任务/看回复；
   统一导航组件，11 页项一致，补齐 5 个孤岛页面入口。
P2 移动端：补 viewport + 响应式断点，窄屏侧边栏折叠为底部 tab bar。

## 工作约定
- Windows + PowerShell 5.1；写 .ps1 必须带 UTF-8 BOM，否则中文乱码解析失败。
  PowerShell 5.1 不支持 && 串联命令，用 ; 或分开执行。
- 临时探测脚本用 .probe_*.ps1 / .probe_*.py，用完立即删，保持工作区干净。
- 提交中文 message 用 git commit -F .git/STAR_COMMIT_MSG.txt（PowerShell -m 会
  搞坏中文/尖括号）。只在用户明确要求时提交。
- 别杀用户正在用的 AI 应用，动之前先问。
- 改完跑 pytest tests 验证。

## 现在请先做
读 star-ui/js/api-bridge.js 和 pages/dumate.html，然后实现 P0，最后自测：
无 Key 打开任意页面应看到明确的「请填 API Key」引导而非空白；填入 admin key
后 AI 列表正常出现。
```
