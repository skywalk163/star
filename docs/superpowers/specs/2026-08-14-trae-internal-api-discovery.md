# Trae 内部 API 逆向发现报告

> 日期：2026-08-14
> 来源：Trae Solo CN v0.1.48 (build 20260806) 日志逆向
> 日志路径：`%APPDATA%/TRAE SOLO CN/logs/20260813T223332/Modular/ai-agent_*.log`

## 1. 背景

用户观察到 Trae 有手机端 App 可控制桌面端 Trae Work，推断存在内部 API。通过对 Trae 的 ai-agent 模块日志（27MB Rust stdout 日志）进行逆向分析，完整还原了其内部通信架构。

## 2. 三层通信架构

```
┌─────────────┐     ┌──────────────────────────────┐     ┌─────────────┐
│  Trae 手机端  │────▶│  云端 Hub API + WebSocket     │◀────│  Trae 桌面端  │
│  (Mobile)   │     │  trae-api-cn.mchost.guru     │     │  (Electron)  │
└─────────────┘     │  frontier.zijieapi.com/ws/v2 │     └──────┬──────┘
                    └──────────────────────────────┘            │
                                                          ┌─────▼─────┐
                                                          │  本地 IPC   │
                                                          │  命名管道    │
                                                          │  AhaIPC    │
                                                          └─────┬─────┘
                                                          ┌─────▼─────┐
                                                          │ ai-agent   │
                                                          │ (Rust DLL) │
                                                          └───────────┘
```

### 2.1 本地 IPC 层

| 组件 | 协议 | 地址 |
|------|------|------|
| AhaIPC Server | 字节跳动 BP_IPC_SERVER/CLIENT | 命名管道（动态名称） |
| Toolhost IPC | Windows Named Pipe | `\\.\pipe\agent-code-toolhost-{pid}-{hash}` |
| Toolhost TCP | TCP | `127.0.0.1:8999` |
| CKG Server | 本地服务 | 端口 51000 |

- Electron 前端通过 AhaIPC 与 Rust ai-agent 模块通信
- IPC 请求格式：`{service: "xxx", method: "yyy", data: {...}, channel_id: "uuid", trace_id: "uuid"}`
- IPC 响应格式：`{code: 0, message: "ok", data: {...}}`

### 2.2 云端 Hub API 层

**Base URL**: `https://trae-api-cn.mchost.guru/api/solo_hub/v1/`

| 端点 | 方法 | 功能 |
|------|------|------|
| `/clis/register` | POST | 注册桌面端实例（CLI） |
| `/clis/status` | GET | 获取 CLI 状态 |
| `/clis/requests/respond` | POST | 响应远程请求（手机端控制） |
| `/apps/online` | GET | 列出在线 App |
| `/conversations` | GET | 列出会话 |
| `/conversations/clis/messages/list` | POST | 列出消息 |
| `/conversations/messages/batchInsert` | POST | 批量插入消息 |
| `/wsmessages/poll` | GET | 轮询 WebSocket 消息 |

**其他云端 API**:
- `https://trae-api-cn.mchost.guru/api/ide/v1/get_skill_detail` - 技能详情
- `https://trae-api-cn.mchost.guru/api/ide/v1/batch_get_detail_param` - 模型配置
- `https://trae-api-cn.mchost.guru/api/agent/v3/query_history_state` - 历史状态
- `https://api.trae.cn/cloudide/api/v3/trae/GetThirdPartyToken` - 第三方 Token
- `https://api.trae.cn/trae/api/v2/pay/ide_user_pay_status` - 付费状态
- `https://api.trae.cn/trae/api/v2/pay/ide_user_ent_usage` - 用量

### 2.3 实时 WebSocket 层

**URL**: `wss://frontier.zijieapi.com/ws/v2`

参数：`frontier_id`, `app_runtime_type`, `process_id`, `client_timestamp`, `name`, `device_model`

这是字节跳动 Frontier 实时推送服务，用于：
- 手机端 → 云端 → 桌面端的实时命令转发
- 事件流推送（AI 生成进度、状态变更等）

## 3. IPC 方法清单

从日志中提取到的所有 service/method 组合：

### 3.1 核心 AI 交互

| service | method | 功能 | 关键参数 |
|---------|--------|------|----------|
| **lite** | **send_message** | **发送消息** | `chat_session_id`, `query`, `model_name`, `agent_type` |
| chat | start_chat | 启动 AI 生成 | `session_id`, `message_id`, `query`, `model_name` |
| chat | get_messages | 获取消息历史 | `session_id` |
| chat | subscribe_events | 订阅事件流 | `session_id` |
| chat | get_lite_sessions | 列出会话 | `work_mode`, `limit`, `page_token` |

### 3.2 会话管理

| service | method | 功能 |
|---------|--------|------|
| lite | list_chat_sessions | 列出聊天会话 |
| lite | get_chat_session | 获取会话详情 |
| lite | get_messages | 获取消息 |
| lite | get_pinned_sessions | 获取置顶会话 |
| lite | get_session_products | 获取会话产品 |

### 3.3 项目和工作区

| service | method | 功能 |
|---------|--------|------|
| lite | list_projects | 列出项目 |
| lite | create_project | 创建项目 |
| lite | project_change_event | 项目变更事件 |
| lite | check_cli_status | 检查 CLI 状态 |
| lite | wakeup_sandbox | 唤醒沙箱 |
| lite | vm_operate | VM 操作 |
| lite | super_completion_query | 超级补全查询 |

### 3.4 Hub 和远程控制

| service | method | 功能 |
|---------|--------|------|
| lite | login_for_hub | Hub 登录（手机控制） |
| lite | state_notification | 状态通知 |
| lite | subscribe_events | 订阅事件 |

### 3.5 其他

| service | method | 功能 |
|---------|--------|------|
| healthcheck | ping | 健康检查 |
| configuration | get_user_configuration | 用户配置 |
| ckg | setup | CKG 初始化 |
| ckg | refresh_token | 刷新 Token |
| ckg | get_build_status | 构建状态 |
| model | model_list_by_function | 模型列表 |
| plugin | install_marketplace_plugin | 安装插件 |
| plugin | batch_update_plugin_config | 更新插件配置 |
| browser | check_browser_tools_enabled | 浏览器工具检查 |
| toolcall | list_workflows | 列出工作流 |

## 4. send_message 完整请求结构

```json
{
  "service": "lite",
  "method": "send_message",
  "data": {
    "chat_session_id": "6a766f5288a66e597806ad55",
    "content": [],
    "model_name": "DeepSeek-V4-Flash",
    "agent_type": "solo_agent_lite",
    "agent_id": "solo_agent_lite",
    "query": "[{\"type\":\"text\",\"data\":{\"content\":\"hello\"}}]",
    "model_selection_strategy": "manual",
    "custom_model": {
      "is_preset": true,
      "config_name": "DeepSeek-V4-Flash",
      "use_remote_service": true,
      "max_turn": 500,
      "max_tokens": 64000,
      "prompt_max_tokens": 936000
    }
  },
  "user_info": {
    "name": "skywalk",
    "token": "<JWT REDACTED>",
    "region": "cn",
    "user_id": "1053797751201322",
    "scope": "marscode"
  },
  "client_info": {
    "workspace_folder": "c:\\dumatework\\duan",
    "chat_session_id": "6a766f5288a66e597806ad55",
    "connect_session_id": "66e40edd-53b2-41ae-af6d-70b3fe42c1f1",
    "device_id": "357778168484124",
    "client_type": "Lite"
  }
}
```

## 5. Hub 注册流程

```
1. POST /clis/register
   Body: {
     "name": "skywalk",
     "device_model": "VirtualBox",
     "cli_type": "local",
     "frontier_id": "1412888296469275275",
     "app_id": 787976,
     "product_id": 420,
     "status": "online"
   }
   
2. Response: {
     "cli": {
       "id": "592055285fdb9184dcfd410bcac789d8",
       "user_id": "1053797751201322",
       "status": "offline"
     }
   }

3. WebSocket 连接:
   wss://frontier.zijieapi.com/ws/v2?frontier_id=1412888296469275275
   
4. 进入 WebSocket 模式，等待远程命令
```

## 6. 认证架构

### 6.1 认证层级

| 层级 | 认证方式 | 存储位置 |
|------|----------|----------|
| Hub API | AhaNet SDK 内部管理 | 加密存储在 `iCubeAuthInfo` |
| WebSocket | frontier_id + device_id | 运行时生成 |
| 本地 IPC | 无需认证（本地管道） | N/A |

### 6.2 HTTP 请求头

```
x-app-id: 6eefa01c-1036-4c7e-9ca5-d891f63bfcd8
x-app-version: 0.1.48
x-app-version-code: 20260806
x-device-id: 357778168484124
x-device-type: windows
x-machine-id: 8aceb5bc7a7bcf34ca47c0bdd2f53f16d6e71ea4d25ef5e39f937c074e77bb3d
x-ide-version: 0.1.48
x-ide-version-code: 20260806
x-ide-version-type: stable
x-os-version: Windows 10 Pro
x-trae-authorized-services: feishu
request-traffic-type: prod
```

JWT Token 由 AhaNet SDK (`aha_net.dll`) 内部管理，日志中始终脱敏为 `eyJh***_T6E`。
Token 存储在 `storage.json` 的 `iCubeAuthInfo` 字段中，但为加密二进制格式。

### 6.3 关键身份信息

| 字段 | 值 |
|------|-----|
| user_id | `1053797751201322` |
| device_id | `357778168484124` |
| machine_id | `8aceb5bc7a7bcf34ca47c0bdd2f53f16d6e71ea4d25ef5e39f937c074e77bb3d` |
| cli_id | `592055285fdb9184dcfd410bcac789d8` |
| frontier_id | `1412888296469275275` |
| connect_session_id | `66e40edd-53b2-41ae-af6d-70b3fe42c1f1` |

## 7. 无法直接调用 Hub API 的原因

1. **JWT Token 不可提取**：由 ByteDance AhaNet SDK (`aha_net.dll`) 加密管理，存储在 `iCubeAuthInfo` 加密字段中
2. **AhaIPC 协议未公开**：本地命名管道使用字节跳动 proprietary IPC 协议
3. **Token 会过期**：日志显示有 `refresh_token` 调用，说明 Token 有有效期
4. **API 未文档化**：所有端点均为内部 API，随时可能变更

## 8. 推荐集成方案：Electron DevTools Protocol (CDP)

### 8.1 原理

Trae 是基于 VS Code 的 Electron 应用。通过 `--remote-debugging-port=9223` 启动参数开启 CDP 端口后，可以：

1. **枚举渲染器目标**：找到 Trae 的聊天 UI 渲染器进程
2. **执行 JavaScript**：在渲染器上下文中执行代码
3. **DOM 操作**：直接操作聊天输入框、发送按钮、消息区域
4. **访问内部 API**：通过渲染器的全局对象访问 AhaIPC 层

### 8.2 优势对比

| 方案 | 可靠性 | 延迟 | 前台要求 | 实现复杂度 |
|------|--------|------|----------|-----------|
| GUI 自动化 (pyautogui) | 中 | 慢 | 必须前台 | 低（已实现） |
| **CDP (DevTools Protocol)** | **高** | **快** | **不需要** | **中** |
| Hub API 直调 | 最高 | 最快 | 不需要 | 高（Token 不可得） |
| 本地 IPC 直连 | 最高 | 最快 | 不需要 | 高（协议未公开） |

### 8.3 实现方案

1. 启动 Trae 时添加 `--remote-debugging-port=9223`
2. 通过 CDP 连接 `http://127.0.0.1:9223`
3. 枚举 targets，找到聊天 UI 的渲染器
4. 使用 `Runtime.evaluate` 执行 JavaScript：
   - 找到聊天输入框（textarea/monaco editor）
   - 设置文本内容
   - 触发发送
   - 读取响应区域内容
5. 使用 `Input.dispatchKeyEvent` 发送 Enter/Escape

### 8.4 启动方式

```bash
# 方式1：命令行启动
"C:\Users\skywalk\AppData\Local\Programs\TRAE SOLO CN\TRAE SOLO CN.exe" --remote-debugging-port=9223

# 方式2：修改快捷方式（永久生效）
# 在 Trae 快捷方式的"目标"末尾添加 --remote-debugging-port=9223
```

## 9. 工作模式

日志中发现 Trae 支持三种工作模式：

| work_mode | 说明 |
|-----------|------|
| `code` | 代码模式（默认） |
| `design` | 设计模式 |
| `work` | 工作模式 |

## 10. Agent 类型

| agent_type | 说明 |
|------------|------|
| `solo_agent_lite` | 本地轻量 Agent（默认） |
| `solo_agent_remote` | 远程 Agent |
| `solo_coder` | 纯代码 Agent |
| `solo_work_lite` | 工作模式本地 |
| `solo_work_remote` | 工作模式远程 |
| `solo_design_lite` | 设计模式本地 |
| `solo_design_remote` | 设计模式远程 |
| `builder` | 构建器 |
| `assistant` | 助手 |

## 11. 后续方向

1. **短期**：实现 CDP-based Trae adapter，替代 GUI 自动化
2. **中期**：研究 AhaNet SDK 的 token 刷新机制，尝试通过 Hook 获取 token
3. **长期**：如果 Trae 开放官方 API，直接迁移到官方 API

## 12. CDP 从 code CLI 被移除的调查（v0.1.50）

> 追加于 2026-08-14 第二轮深挖：目标——确认 Trae 何时、为何把 `--remote-debugging-port`
> 从命令行拿掉，并判断 argv.json 是否仍是 0.1.50 唯一可行通道。

### 12.1 结论

- **何时**：介于 `v0.1.48`（build `20260806`，本文档 §8 当时仍把 CLI 标志列为"推荐方案"）与当前安装版本 `v0.1.50` 之间。大概率落在 **v0.1.49 或 v0.1.50** 的静默安全加固，**未写入公开更新日志**（trae.cn/changelog 在该区间无任何 CDP/命令行安全条目；0.1.49 甚至未单列）。
- **为何**：安全收敛。开放 `--remote-debugging-port` 等价于在渲染器暴露完整 `Runtime.evaluate`，经内部 `AhaIPC`/`browser`/`Hub` 服务即可控制整个 AI Agent、文件系统与云端 API——是"任意本地进程都能拉起一个带调试端口的 Trae"的本地 RCE/自动化劫持面。与 ByteDance 同期加固一致：AhaNet JWT 加密存储（§6）、Hub token 不可提取、2025-12-23「命令行运行更安全」沙箱化。
- **机制（挖的一层）**：他们**没有**把 `remote-debugging-port` 从选项 schema 删掉（CLI 全局选项 `global` 仍含该项，且 `onUnknownOption` 为空操作→未知全局选项静默忽略、不报 "bad option"）；他们移除的是 **CLI 标志 → Chromium 的转发**。唯一仍被 honor 的通道是 `argv.json`（`%APPDATA%/.trae-cn/argv.json`）。

### 12.2 源码证据（resources/app/out/main.js）

- argv.json 路径：`argvResource` getter → `userHome/.trae-cn/argv.json`（dataFolderName=`.trae-cn`）。
- argv.json 维护：`ib()` 仅自动补全 `enable-crash-reporter`/`crash-reporter-id`；`jb()` 做 JSONC 修复。
- **关键 `GBe()`（@~2643000）** 即 readArgvJson 允许列表应用器：
  ```js
  const e=["disable-hardware-acceleration","force-color-profile",
           "disable-lcd-text","proxy-bypass-list","remote-debugging-port"];
  const r=JBe();              // 读 argv.json
  Object.keys(r).forEach(c=>{
    if(e.indexOf(c)!==-1) cr.commandLine.appendSwitch(c,l);  // 转发给 Chromium
  });
  ```
  即：`argv.json` 里的 `remote-debugging-port` **仍被 `appendSwitch` 转发到 Chromium** → 0.1.50 仍开 CDP。
- 全部 `appendSwitch` 调用（14 处）中，唯有 `GBe()` 经 argv.json 处理 `remote-debugging-port`；**没有任何代码从 `process.argv` 转发该标志** → CLI 传参被吞、CDP 不开。
- 历史 `%APPDATA%/TRAE SOLO CN/DevToolsActivePort` 内容 `9223|...` 印证该端口曾由 argv.json 路径开启。

### 12.3 product.json / 内部 API 是否还有别的通道

- **product.json**（resources/app/product.json，appVersion=0.1.50）：**无**任何 CDP/远程调试开关键；`bootConfig` 全是云端端点，不含 devtools 端口。
- **环境变量**：无 `VSCODE_*` / `ELECTRON_*` 捷径可开 CDP。
- **内部 AhaIPC `browser` 服务**（`check_browser_tools_enabled` 等）：是「Browser Use」浏览器工具能力，**非** CDP 端口开启器。
- `cloudide.icube-devtool-ports` 扩展（product.json 列出 workspacePath=extensions/icube-devtool-ports）在本机安装 resources 中**未落地**（按需从市场拉取），不构成稳定通道。
- **结论：argv.json 是 0.1.50 唯一被官方保留的 escape hatch**——它需要写入用户 profile 目录（与「启用崩溃上报」同级的显式、需用户授权的高权限动作），而 CLI 标志是「任意自动化可随意触发」的低门槛路径，故被关闭。

### 12.4 对 Star 集成的影响

- Star 当前方案（写 `argv.json` 的 `remote-debugging-port=9223` + 清 `code.lock` + 零参数重启 Trae）**正是 0.1.50 的预期正确路径**，方向无误。
- 无需、也不可依赖 CLI 标志。沙箱非交互会话无法实测 9223，但机制已由 `GBe()` 源码 + 历史 `DevToolsActivePort` 双重证实；用户在桌面会话重启一次 Trae 即可被 Star 以 9223 连上。
