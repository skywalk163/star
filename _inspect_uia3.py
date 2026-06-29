"""
进一步探索 Trae Solo - 子进程、子窗口、Chrome 无障碍树
"""
import uiautomation as uia
import subprocess
import json


def get_element_full(element, indent=0):
    """Get comprehensive element data."""
    prefix = "  " * indent
    try:
        name = element.Name
        ctrl_type = element.ControlType
        class_name = element.ClassName
        auto_id = element.AutomationId
        rect = element.BoundingRectangle
        pid = element.ProcessId
        fw = element.FrameworkId
        native_hwnd = element.NativeWindowHandle
        is_off = element.IsOffscreen
        is_enabled = element.IsEnabled
        localized = element.LocalizedControlType
        
        type_map = {50020: 'Window', 50032: 'Pane', 50000: 'Button', 50002: 'Edit',
                    50033: 'Document', 50038: 'Custom', 50012: 'Text', 50006: 'ListItem',
                    50005: 'List', 50010: 'Tab', 50011: 'TabItem', 50044: 'Group'}
        type_name = type_map.get(ctrl_type, f'T{ctrl_type}')
        
        info = {
            'type': type_name,
            'name': name or '',
            'class': class_name or '',
            'aid': auto_id or '',
            'rect': f'({rect.left},{rect.top})-({rect.right},{rect.bottom})' if rect else '',
            'pid': pid,
            'fw': fw or '',
            'hwnd': native_hwnd,
            'enabled': is_enabled,
            'offscreen': is_off,
            'loc': localized or ''
        }
        
        # Only print if has meaningful content
        has_content = any([
            name and name.strip(),
            class_name not in ('', 'Pane', 'Custom', 'View', 'Window'),
            auto_id and auto_id.strip(),
            localized and localized not in ('window', 'pane', 'region'),
            ctrl_type in (50000, 50002, 50012)  # Button, Edit, Text
        ])
        
        if has_content or indent <= 2:
            parts = []
            if info['name']:
                n = info['name'][:80]
                parts.append(f'[{type_name}] "{n}"')
            else:
                parts.append(f'[{type_name}]')
            
            extras = []
            if info['class'] and info['class'] not in ('Pane', 'Custom', 'View', 'Window', 'Chrome_WidgetWin_1'):
                extras.append(f'cls={info["class"]}')
            if info['aid']:
                extras.append(f'id={info["aid"]}')
            if info['loc'] and info['loc'] not in ('window', 'pane', 'region', 'pane'):
                extras.append(f'type={info["loc"]}')
            if info['fw'] and info['fw'] not in ('Win32',):
                extras.append(f'fw={info["fw"]}')
            if info['pid']:
                extras.append(f'pid={info["pid"]}')
            if info['rect']:
                extras.append(f'at={info["rect"]}')
            if info['offscreen']:
                extras.append('OFFSCREEN')
            if not info['enabled']:
                extras.append('DISABLED')
            
            if extras:
                parts.append(' | '.join(extras))
            
            print(f"{prefix}{'  '.join(parts)}")
            return True
    except Exception as e:
        if indent <= 1:
            print(f"{prefix}[Error: {e}]")
    return False


def explore_all_two_pass(element, max_depth=10):
    """Two-pass exploration: first surface-level, then deep."""
    # Pass 1: Tree exploration with filtering
    print("\n--- Pass 1: Filtered Tree ---")
    
    def walk(element, depth=0, visited=None):
        if visited is None:
            visited = set()
        if depth > max_depth:
            return
        
        try:
            rect = element.BoundingRectangle
            key = (element.ControlType, element.ClassName, element.Name,
                   rect.left, rect.top, rect.right, rect.bottom)
            if key in visited:
                return
            visited.add(key)
            
            should_print = depth <= 2
            if not should_print:
                name = element.Name or ''
                cls = element.ClassName or ''
                aid = element.AutomationId or ''
                ctrl = element.ControlType
                should_print = any([
                    name.strip() and aid.strip(),
                    ctrl in (50000, 50002, 50012),
                    cls not in ('', 'Pane', 'Custom', 'View', 'Window', 'NonClientView', 
                                'WinFrameView', 'ClientView', 'RootView', 'Chrome_WidgetWin_1')
                ])
            
            if should_print:
                get_element_full(element, depth)
            
            try:
                children = element.GetChildren()
            except:
                children = []
            
            # If depth <= 3, continue unconditionally; deeper only if we found something
            if depth <= 3:
                for child in children:
                    walk(child, depth+1, visited)
            elif should_print:
                for child in children:
                    walk(child, depth+1, visited)
        except Exception as e:
            if depth <= 2:
                print(f"{'  ' * depth}[Walk error: {e}]")
    
    walk(element)
    
    # Pass 2: Try to get text content from D3D window
    print("\n--- Pass 2: D3D Window Content ---")
    try:
        def find_d3d(element, depth=0):
            if depth > 5:
                return None
            try:
                if 'Intermediate D3D' in (element.ClassName or ''):
                    return element
                for child in element.GetChildren():
                    result = find_d3d(child, depth+1)
                    if result:
                        return result
            except:
                pass
            return None
        
        d3d = find_d3d(element)
        if d3d:
            print(f"  Found D3D Window: PID={d3d.ProcessId}, HWND={d3d.NativeWindowHandle}")
            
            # Try to get higher-level content from its parent/ancestors
            try:
                parent = d3d.GetParent()
                if parent:
                    print(f"  D3D Parent: '{parent.Name}' cls={parent.ClassName}")
            except:
                pass
            
            # Try exploring D3D window's own children
            try:
                d3d_children = d3d.GetChildren()
                print(f"  D3D has {len(d3d_children)} children")
                for i, child in enumerate(d3d_children[:20]):
                    get_element_full(child, 2)
            except Exception as e:
                print(f"  D3D children: {e}")
    except Exception as e:
        print(f"  D3D search: {e}")


def main():
    print("=" * 90)
    print("TRAE Solo Deep UI Exploration")
    print("=" * 90)
    
    window = uia.ControlFromHandle(590396)
    print(f"\nRoot: '{window.Name}' | Class={window.ClassName} | PID={window.ProcessId}")
    print(f"Framework: {window.FrameworkId}")
    print(f"Provider: {window.ProviderDescription[:100]}...")
    
    # Full exploration
    explore_all_two_pass(window, max_depth=12)
    
    # Another approach: iterate all windows and find child windows of our process
    print("\n--- All Windows of PID 18424 & child processes ---")
    
    root = uia.GetRootControl()
    for child in root.GetChildren():
        try:
            pid = child.ProcessId
            name = child.Name
            cls = child.ClassName
            hwnd = child.NativeWindowHandle
            rect = child.BoundingRectangle
            fw = child.FrameworkId
            
            if pid in (18424, 12876) or (pid and (pid == 18424 or pid == 12876)):
                print(f"  PID={pid} | '{name}' | cls={cls} | hwnd={hwnd} | fw={fw} | {rect}")
        except:
            pass
    
    # Let's also try to find by process name
    print("\n--- Looking for 'TRAE SOLO CN' process windows ---")
    for child in root.GetChildren():
        try:
            name = child.Name or ''
            cls = child.ClassName or ''
            pid = child.ProcessId
            if 'TRAE' in name.upper() or 'SOLO' in name.upper() or 'solo' in (child.ProcessId and str(child.ProcessId) or ''):
                rect = child.BoundingRectangle
                print(f"  '{name}' | PID={pid} | cls={cls} | hwnd={child.NativeWindowHandle} | {rect}")
                # Show this child's children too
                try:
                    for c2 in child.GetChildren()[:5]:
                        get_element_full(c2, 1)
                except:
                    pass
        except:
            pass
    
    # Print all visible windows on the desktop for context
    print("\n--- All visible desktop windows (with name) ---")
    count = 0
    for child in root.GetChildren():
        try:
            name = child.Name or ''
            cls = child.ClassName or ''
            if name.strip() and ('TRAE' in name.upper() or 'trae' in name.lower()):
                rect = child.BoundingRectangle
                print(f"  '{name}' | cls={cls} | PID={child.ProcessId}")
                count += 1
        except:
            pass
    if count == 0:
        print("  (No Trae-related windows found by name)")
        # Show first 10 non-empty windows
        for child in root.GetChildren():
            try:
                name = child.Name or ''
                if name.strip():
                    print(f"  '{name[:60]}' | PID={child.ProcessId} | cls={child.ClassName}")
            except:
                pass


if __name__ == '__main__':
    main()