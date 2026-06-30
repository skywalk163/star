# AI Agent 特征规范表

> **版本：** v1.0  
> **日期：** 2026-06-30  
> **用途：** 快速适配新 AI Agent，标准化群星对 AI Agent 的识别和交互

---

## 规范说明

### 字段定义

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 唯一标识，如 `trae`, `dumate` |
| `name` | string | ✅ | 显示名称 |
| `vendor` | string | ✅ | 厂商 |
| `description` | string | ❌ | 描述 |
| `category` | enum | ✅ | `ide`(IDE类) / `chat`(对话类) / `browser`(浏览器类) |
| `process_names` | string[] | ✅ | 进程名列表（大小写敏感） |
| `window_class` | string[] | ❌ | 窗口类名 |
| `title_patterns` | string[] | ✅ | 窗口标题关键词 |
| `title_format` | object | ❌ | 标题格式解析规则 |
| `input_config` | object | ❌ | 输入框配置 |
| `send_config` | object | ❌ | 发送指令配置 |
| `status_config` | object | ❌ | 状态检测配置 |
| `ocr_config` | object | ❌ | OCR 配置 |
| `capabilities` | string[] | ❌ | 支持的能力列表 |

---

## IDE 类 AI Agent

### 1. Trae CN / Trae Solo

| 字段 | 值 |
|------|-----|
| **id** | `trae` |
| **name** | Trae AI |
| **vendor** | 字节跳动 |
| **category** | `ide` |
| **process_names** | `Trae.exe`, `trae.exe`, `Trae CN.exe`, `Trae CN`, `TRAE SOLO CN.exe`, `TRAE SOLO CN` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `Trae`, `trae`, `TRAE Work CN`, `TRAE SOLO`, `Trae CN` |

**标题格式：**
```
{文件名} - {项目名} - Trae CN
```

**标题示例：**
```
hanoi.duan - duan - Trae CN
setup-redis.sh - sound - Trae CN
2026-06-19-ai-finder-design.md (Preview) - search - Trae CN
TRAE Work CN.0.1.23.no_sid.no_ppe.T(2026/6/29 00:05:54)
```

**窗口类型解析：**
| 文件类型 | window_type |
|---------|-------------|
| .md, .txt, .docx | `document` |
| .py, .js, .ts, .java | `editor` |
| 含 (Preview) | `preview` |
| 含 TRAE Work | `work_mode` |

---

### 2. CodeArts Agent

| 字段 | 值 |
|------|-----|
| **id** | `codearts_agent` |
| **name** | CodeArts Agent |
| **vendor** | 华为云 |
| **category** | `ide` |
| **process_names** | `codearts-agent.exe`, `CodeArts Agent.exe` |
| **window_class** | `Chrome_WidgetWin_1` |
| **title_patterns** | `CodeArts Agent`, `codearts agent` |

**标题格式：**
```
{项目名} - {文件名} - CodeArts Agent
```

**标题示例：**
```
yanpub - adapter.py - CodeArts Agent
zhixing - _test_friendly.py - CodeArts Agent
```

---

### 3. CodeArts IDE

| 字段 | 值 |
|------|-----|
| **id** | `codearts_atomcode` |
| **name** | CodeArts IDE |
| **vendor** | 华为云 |
| **category** | `ide` |
| **process_names** | `CodeArts.exe`, `AtomCode.exe`, `HuaweiCodeArts.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `CEF窗外壳窗口` |
| **title_patterns** | `CodeArts`, `AtomCode`, `华为云CodeArts` |

---

### 4. Cursor

| 字段 | 值 |
|------|-----|
| **id** | `cursor` |
| **name** | Cursor |
| **vendor** | Anysphere |
| **category** | `ide` |
| **process_names** | `Cursor.exe`, `cursor.exe` |
| **window_class** | `Chrome_WidgetWin_1` |
| **title_patterns** | `Cursor` |

---

### 5. Windsurf

| 字段 | 值 |
|------|-----|
| **id** | `windsurf` |
| **name** | Windsurf |
| **vendor** | Codeium |
| **category** | `ide` |
| **process_names** | `windsurf.exe`, `Windsurf.exe` |
| **window_class** | `Chrome_WidgetWin_1` |
| **title_patterns** | `Windsurf`, `Codeium` |

---

### 6. Claude Desktop

| 字段 | 值 |
|------|-----|
| **id** | `claude` |
| **name** | Claude Desktop |
| **vendor** | Anthropic |
| **category** | `ide` |
| **process_names** | `claude.exe`, `ClaudeDesktop.exe` |
| **window_class** | `Chrome_WidgetWin_1` |
| **title_patterns** | `Claude` |

---

### 7. 搭子 DuMate

| 字段 | 值 |
|------|-----|
| **id** | `dumate` |
| **name** | 搭子 DuMate |
| **vendor** | 百度 |
| **category** | `ide` |
| **process_names** | `DuMate.exe`, `dumate.exe`, `搭子.exe` |
| **window_class** | `Chrome_WidgetWin_1` |
| **title_patterns** | `搭子DuMate`, `DuMate`, `dumate`, `搭子` |

**标题示例：**
```
搭子DuMate
```

**窗口类型：** `chat`

---

## 浏览器类 AI Agent

> 此类 AI Agent 通常以浏览器标签页形式运行

### 8. 文心一言 (ERNIE)

| 字段 | 值 |
|------|-----|
| **id** | `ernie` / `yiyan` |
| **name** | 文心一言 |
| **vendor** | 百度 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `文心一言`, `ERNIE Bot`, `ernie`, `yiyan`, `文心` |

---

### 9. 讯飞星火 (Spark)

| 字段 | 值 |
|------|-----|
| **id** | `spark` |
| **name** | 讯飞星火 |
| **vendor** | 科大讯飞 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `讯飞星火`, `Spark`, `xinghuo` |

---

### 10. 智谱清言 (GLM)

| 字段 | 值 |
|------|-----|
| **id** | `glm` |
| **name** | 智谱清言 |
| **vendor** | 智谱 AI |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `智谱清言`, `GLM`, `chatglm`, `zhipu` |

---

### 11. 通义千问 (Qwen)

| 字段 | 值 |
|------|-----|
| **id** | `qwen` |
| **name** | 通义千问 |
| **vendor** | 阿里云 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `通义千问`, `Qwen`, `qwen`, `阿里云` |

---

### 12. 跃问 (StepFun)

| 字段 | 值 |
|------|-----|
| **id** | `step` |
| **name** | 跃问 |
| **vendor** | 阶跃星辰 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `跃问`, `Step`, `stepfun`, `StepFun` |

---

### 13. 万知 AI

| 字段 | 值 |
|------|-----|
| **id** | `wanzhi` |
| **name** | 万知 AI |
| **vendor** | 金山办公 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `万知`, `WanZhi`, `wps`, `金山` |

---

### 14. 海螺问问 (Hailuo)

| 字段 | 值 |
|------|-----|
| **id** | `hailuo` |
| **name** | 海螺问问 |
| **vendor** | MiniMax |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `海螺`, `Hailuo`, `hailuoai`, `MiniMax` |

---

### 15. 百川智能 (BaiChuan)

| 字段 | 值 |
|------|-----|
| **id** | `baichuan` |
| **name** | 百川智能 |
| **vendor** | 百川智能 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `百川`, `BaiChuan`, `baichuan`, `百川智能` |

---

### 16. 商汤商量 (ShangLiang)

| 字段 | 值 |
|------|-----|
| **id** | `shangliang` |
| **name** | 商汤商量 |
| **vendor** | 商汤科技 |
| **category** | `browser` |
| **process_names** | `msedge.exe`, `chrome.exe`, `brave.exe`, `firefox.exe` |
| **window_class** | `Chrome_WidgetWin_1`, `MozillaWindowClass` |
| **title_patterns** | `商量`, `ShangLiang`, `SenseChat`, `SenseTime` |

---

## 适配器配置模板

当新增 AI Agent 时，可参考以下配置模板：

```yaml
# 在 star_emissary.py 的 PRESET_ADAPTERS 中添加

"{agent_id}": StarAdapterConfig(
    name="{agent_id}",
    # 输入框位置（相对屏幕百分比）
    input_click_x_ratio=0.5,      # 水平位置 0.0-1.0
    input_click_y_ratio=0.93,      # 垂直位置 0.0-1.0
    
    # 输出区域类型
    output_region="center_chat",   # center_chat | right_panel | custom
    
    # 完成检测策略
    completion_strategy=CompletionStrategy.STATUS_KEYWORD,
    # 或 COMPLETION_KEYWORD / STABLE_CONTENT / TIMEOUT
    
    # 完成关键词（状态检测用）
    completion_keywords=[
        "重新生成", "复制", "清空", "发送", "已收到",
        "Regenerate", "Copy", "Send"
    ],
    
    # 运行中关键词
    running_keywords=[
        "思考中", "生成中", "处理中", "正在思考",
        "Thinking...", "Generating...", "Processing..."
    ],
    
    # 检测参数
    stable_count=2,      # 连续 N 次检测结果一致视为完成
    check_interval=2.5,   # 检测间隔（秒）
    timeout=300.0,        # 超时时间（秒）
    
    # OCR 配置
    ocr_lang="ch",        # ch / en / chs
),
```

---

## 窗口标题解析模板

```python
# 在 StarWindow.parse_context() 中添加

elif star_type == "{agent_id}":
    # {agent_name} 格式: "{项目} - {文件} - {agent_name}"
    
    # 1. 去掉末尾的 Agent 标识
    parts = [p.strip() for p in title.rsplit(" - ", 2)]
    if len(parts) >= 2 and "{agent_name}" in parts[-1]:
        parts = parts[:-1]
    
    # 2. 解析项目和文件
    if len(parts) >= 2:
        ctx.project_name = parts[0]
        ctx.file_name = parts[1]
        
        # 3. 判断窗口类型
        fn_lower = ctx.file_name.lower()
        if "(preview)" in fn_lower:
            ctx.window_type = "preview"
        elif any(ext in fn_lower for ext in ['.md', '.txt', '.docx']):
            ctx.window_type = "document"
        elif any(ext in fn_lower for ext in ['.py', '.js', '.java', '.cpp']):
            ctx.window_type = "editor"
        else:
            ctx.window_type = "unknown"
    elif len(parts) == 1:
        ctx.project_name = parts[0]
        ctx.window_type = "chat"  # 或 "unknown"
```

---

## 新增 Agent 快速流程

1. **收集信息**
   - 运行 Agent，记录进程名
   - 截图并查看窗口标题格式
   - 记录窗口类名（可用 Spy++ 或工具获取）

2. **添加签名**
   ```python
   # 在 STAR_SIGNATURES 中添加
   '{new_id}': {
       'process_names': ['进程名.exe'],
       'window_class': ['窗口类名'],
       'window_title_patterns': ['标题关键词'],
       'description': '描述'
   }
   ```

3. **添加适配器配置**
   ```python
   # 在 PRESET_ADAPTERS 中添加
   "{new_id}": StarAdapterConfig(
       name="{new_id}",
       input_click_x_ratio=0.5,
       input_click_y_ratio=0.93,
       # ...
   )
   ```

4. **添加解析规则**
   ```python
   # 在 StarWindow.parse_context() 中添加
   elif star_type == "{new_id}":
       # 解析逻辑
   ```

5. **测试验证**
   - 启动 API 服务
   - 访问星图面板
   - 验证 Agent 被正确识别

---

## 附录：常见窗口类名

| 窗口类名 | 应用 |
|---------|------|
| `Chrome_WidgetWin_1` | Chrome/Edge/Electron 应用 |
| `MozillaWindowClass` | Firefox |
| `CEF窗外壳窗口` | 华为 CodeArts |
| `Notepad++` | Notepad++ |
| `SciteWindow` | SciTE |
| `Vim` | GVim/MacVim |
| `XLMAIN` | Excel |
| `OpusApp` | Word |

---

## 更新日志

| 日期 | 版本 | 更新内容 |
|------|------|---------|
| 2026-06-30 | v1.0 | 初始版本，支持 16 个 AI Agent |
