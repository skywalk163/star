"""
uiautomation 深度检查脚本 - Trae Solo (TRAE Work CN) 窗口结构
PID: 18424, HWND: 590396

使用多种方法探索 Chromium embedded 应用的 UI 结构。
"""
import uiautomation as uia
import sys


def safe_get(ctrl, attr, default=''):
    """Safely get an attribute from a control."""
    try:
        val = getattr(ctrl, attr, default)
        if callable(val):
            val = val()
        return val if val is not None else default
    except Exception:
        return default


def print_element(element, indent=0, label=''):
    """Print detailed element info."""
    prefix = "  " * indent
    try:
        name = safe_get(element, 'Name')
        ctrl_type = safe_get(element, 'ControlType')
        class_name = safe_get(element, 'ClassName')
        auto_id = safe_get(element, 'AutomationId')
        rect = safe_get(element, 'BoundingRectangle')
        
        # Map control type numbers to names
        type_name = {
            50020: 'Window', 50032: 'Pane', 50000: 'Button', 50002: 'Edit',
            50005: 'List', 50006: 'ListItem', 50007: 'Menu', 50008: 'MenuItem',
            50010: 'Tab', 50011: 'TabItem', 50012: 'Text', 50014: 'ScrollBar',
            50015: 'ComboBox', 50022: 'ToolBar', 50030: 'Hyperlink',
            50033: 'Document', 50034: 'ToolTip', 50036: 'Tree',
            50037: 'TreeItem', 50038: 'Custom', 50039: 'Slider',
            50041: 'ProgressBar', 50044: 'Group', 50047: 'RadioButton',
            50053: 'CheckBox', 50054: 'Thumb',
        }.get(ctrl_type, f'T{ctrl_type}')
        
        parts = [f'{type_name}']
        
        if name:
            n = name.strip()
            if len(n) > 100:
                n = n[:97] + '...'
            parts.append(f'"{n}"')
        if auto_id:
            parts.append(f'[id:{auto_id}]')
        if class_name and class_name not in ('', 'Window', 'Pane', 'Custom', 'View'):
            parts.append(f'{{{class_name}}}')
        if rect:
            r = rect
            parts.append(f'({r.left},{r.top})-({r.right},{r.bottom})')
        
        is_off = safe_get(element, 'IsOffscreen', False)
        is_enabled = safe_get(element, 'IsEnabled', True)
        if is_off:
            parts.append('OFFSCREEN')
        if not is_enabled:
            parts.append('DISABLED')
        
        print(f"{prefix}{' | '.join(parts)}")
        return True
    except Exception as e:
        print(f"{prefix}[Error: {e}]")
        return False


def explore_all(element, max_depth=10, current_depth=0, visited=None):
    """Explore all children including custom patterns."""
    if visited is None:
        visited = set()
    if current_depth > max_depth:
        return
    
    try:
        # Create unique key
        try:
            rect = safe_get(element, 'BoundingRectangle')
            key = (safe_get(element, 'ControlType'), safe_get(element, 'Name'),
                   safe_get(element, 'ClassName'), safe_get(element, 'AutomationId'),
                   str(rect))
        except:
            key = id(element)
        
        if key in visited:
            return
        visited.add(key)
        
        printed = print_element(element, current_depth)
        if not printed:
            return
        
        # Try getting children via different methods
        children = []
        
        # Method 1: GetChildren
        try:
            children.extend(element.GetChildren())
        except:
            pass
        
        # Method 2: Find all with depth-first
        if not children:
            try:
                found = element.FindAll(uia.TreeScope.Subtree, 
                                        uia.ControlCondition(uia.ControlType.PaneControl))
                if found:
                    children.extend(found[:50])  # limit
            except:
                pass
        
        child_count = len(children)
        if child_count > 0:
            if child_count > 100:
                print(f"{'  ' * (current_depth+1)}... ({child_count} children, showing first 100)")
                children = children[:100]
            
            for child in children:
                explore_all(child, max_depth, current_depth + 1, visited)
        else:
            # Try to get text/value patterns
            try:
                name = safe_get(element, 'Name', '')
                value = safe_get(element, 'Value')
                if value and isinstance(value, str) and value.strip() and value != name:
                    print(f"{'  ' * (current_depth+1)}Value: \"{value[:100]}\"")
            except:
                pass
    except Exception as e:
        print(f"{'  ' * current_depth}[Explore error: {e}]")


def search_deep(element, keyword, max_depth=10, current_depth=0, results=None):
    """Deep search for text patterns across all controls."""
    if results is None:
        results = []
    if current_depth > max_depth:
        return results
    
    try:
        name = safe_get(element, 'Name', '')
        auto_id = safe_get(element, 'AutomationId', '')
        class_name = safe_get(element, 'ClassName', '')
        value = ''
        try:
            val = safe_get(element, 'Value')
            if val and isinstance(val, str):
                value = val
        except:
            pass
        
        combined = f"{name} {auto_id} {class_name} {value}".lower()
        if keyword.lower() in combined:
            label = print_element(element, current_depth)
            if value and value != name:
                print(f"{'  ' * (current_depth+1)}→ Value: \"{value[:200]}\"")
            # Don't add to results, already printed
        
        children = element.GetChildren()
        for child in children:
            search_deep(child, keyword, max_depth, current_depth + 1, results)
    except:
        pass
    
    return results


def main():
    print("=" * 90)
    print("UI Automation DEEP Inspection: TRAE Work CN (PID: 18424, HWND: 590396)")
    print("=" * 90)
    
    # --- Method 1: Get window by HWND ---
    try:
        window = uia.ControlFromHandle(590396)
        print(f"\n[+] Window by HWND: '{window.Name}' (type={window.ControlType})")
    except Exception as e:
        print(f"[-] Error: {e}")
        sys.exit(1)
    
    # --- Method 2: Search by PID ---
    print("\n[*] Searching for window by PID via uiautomation...")
    found_windows = []
    def find_by_pid(ctrl, depth=0):
        if depth > 4:
            return
        try:
            pid = ctrl.GetPattern(uia.PatternID.WindowPattern) if hasattr(ctrl, 'GetPattern') else None
            if pid:
                print(f"  Found window: {ctrl.Name}")
        except:
            pass
        try:
            for child in ctrl.GetChildren():
                find_by_pid(child, depth+1)
        except:
            pass
    
    try:
        root = uia.GetRootControl()
        find_by_pid(root)
    except Exception as e:
        print(f"  PID search: {e}")
    
    # --- Method 3: Full deep tree walk ---
    print("\n" + "=" * 90)
    print("FULL DEEP TREE WALK")
    print("=" * 90)
    explore_all(window, max_depth=12)
    
    # --- Method 4: Search for specific keywords ---
    print("\n" + "=" * 90)
    print("KEYWORD SEARCH")
    print("=" * 90)
    
    keywords = [
        # English
        'task', 'agent', 'chat', 'conversation', 'message', 'input', 'output',
        'send', 'prompt', 'status', 'think', 'reply', 'result', 'code',
        'terminal', 'edit', 'file', 'session', 'history', 'assistant',
        'ai', 'model', 'generate', 'response', 'suggest', 'commit',
        # Chinese
        '任务', '对话', '输入', '输出', '发送', '状态', '消息',
        '思考', '回答', '代码', '文件', '终端', '编辑',
        '助手', '智能', '模型', '生成', '回复', '建议',
        '提交', '预览', '运行',
        # UI-specific
        'explorer', 'sidebar', 'panel', 'tab', 'content', 'main',
        '聊天', '侧边栏', '面板', '主区域', '内容区',
    ]
    
    for kw in keywords:
        results = search_deep(window, kw, max_depth=8)
        if results:
            print()  # spacing
    
    # --- Method 5: Find all text/documents/edits ---
    print("\n" + "=" * 90)
    print("ALL TEXT AND EDIT CONTROLS")
    print("=" * 90)
    
    def find_text_controls(element, depth=0, max_d=8, visited=None):
        if visited is None:
            visited = set()
        if depth > max_d:
            return
        try:
            key = id(element)
            if key in visited:
                return
            visited.add(key)
            
            ctrl_type = safe_get(element, 'ControlType')
            if ctrl_type in (50012, 50002, 50033, 50038):  # Text, Edit, Document, Custom
                name = safe_get(element, 'Name', '')
                value = ''
                try:
                    v = safe_get(element, 'Value')
                    if v and isinstance(v, str):
                        value = v
                except:
                    pass
                
                if name or value:
                    print_element(element, depth)
                    if value and value != name and len(value) > 0:
                        print(f"{'  ' * (depth+1)}→ Text: \"{value[:200]}\"")
            
            children = element.GetChildren()
            for child in children:
                find_text_controls(child, depth+1, max_d, visited)
        except:
            pass
    
    find_text_controls(window, max_d=8)
    
    # --- Method 6: Try to find elements via walker ---
    print("\n" + "=" * 90)
    print("UI Automation Walker (alternative traversal)")
    print("=" * 90)
    
    try:
        walker = uia.TreeWalker(uia.ControlViewCondition)
        node = walker.GetFirstChildElement(window)
        depth = 0
        while node and depth < 20:
            print_element(node, depth)
            # Try to go deeper into this branch
            child = walker.GetFirstChildElement(node)
            child_depth = depth + 1
            while child and child_depth < 8:
                print_element(child, child_depth)
                grandchild = walker.GetFirstChildElement(child)
                if grandchild:
                    child = grandchild
                    child_depth += 1
                else:
                    child = walker.GetNextSiblingElement(child)
            node = walker.GetNextSiblingElement(node)
            depth += 1
    except Exception as e:
        print(f"  Walker error: {e}")
    
    print("\n" + "=" * 90)
    print("INSPECTION COMPLETE")
    print("=" * 90)


if __name__ == '__main__':
    main()