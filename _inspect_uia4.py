"""
检查 Trae Solo 进程信息及尝试启用 Chrome 无障碍/可访问性
"""
import uiautomation as uia
import psutil
import subprocess
import ctypes


def check_process_info():
    """Check process details for Trae Solo."""
    print("=" * 80)
    print("Process Information")
    print("=" * 80)
    
    try:
        proc = psutil.Process(18424)
        print(f"\nMain Process (PID 18424):")
        print(f"  Name: {proc.name()}")
        print(f"  Exe: {proc.exe()}")
        print(f"  Cmdline: {' '.join(proc.cmdline())[:300]}")
        print(f"  Cwd: {proc.cwd()}")
        
        # Check for accessibility flags
        cmdline = ' '.join(proc.cmdline()).lower()
        if 'force-renderer-accessibility' in cmdline:
            print(f"  [OK] Chrome accessibility IS enabled via --force-renderer-accessibility")
        else:
            print(f"  [WARN] Chrome accessibility NOT enabled in command line")
        
        if 'disable-gpu' in cmdline or '--disable-gpu' in cmdline:
            print(f"  [OK] GPU is disabled")
        else:
            print(f"  [INFO] GPU acceleration is enabled (D3D surface used)")
        
        # Children
        children = proc.children()
        print(f"\nChild Processes ({len(children)}):")
        for child in children:
            print(f"  PID={child.pid} | {child.name()}")
            try:
                cl = ' '.join(child.cmdline())[:200]
                print(f"    -> {cl}")
            except:
                pass
        
    except Exception as e:
        print(f"  Error: {e}")


def try_chrome_accessibility_workaround():
    """
    Try to access Chrome accessibility tree via UI Automation.
    Even without --force-renderer-accessibility, we can sometimes
    trigger it by manipulating the window.
    """
    print("\n" + "=" * 80)
    print("Chrome Accessibility Tree Exploration")
    print("=" * 80)
    
    window = uia.ControlFromHandle(590396)
    
    # Try to find any content-bearing controls by exploring deeper
    # The Chrome content might be behind the View pane
    print("\n--- Exploring Chrome content region ---")
    
    root_view = None
    d3d_window = None
    
    def find_chrome_nodes(element, depth=0, max_depth=10, visited=None):
        nonlocal root_view, d3d_window
        if visited is None:
            visited = set()
        if depth > max_depth:
            return
        try:
            rect = element.BoundingRectangle
            key = (id(element), element.ControlType, rect.left, rect.top)
            if key in visited:
                return
            visited.add(key)
            
            class_name = element.ClassName
            fw = element.FrameworkId
            
            if class_name == 'RootView':
                root_view = element
            if class_name == 'Intermediate D3D Window':
                d3d_window = element
            
            # Try to use FindFirst/FindAll to locate specific controls
            try:
                # Look for any controls with AutomationId or Name
                cond = uia.CreateCondition('Name', '', uia.PropertyConditionFlags.IgnoreCase)
                # Not quite right, let's just walk children
            except:
                pass
            
            children = element.GetChildren()
            for child in children:
                find_chrome_nodes(child, depth+1, max_depth, visited)
        except:
            pass
    
    find_chrome_nodes(window)
    
    if root_view:
        print(f"RootView found: {root_view.Name}")
        # Explore RootView's children deeply
        def explore_chrome_tree(element, depth=0, max_d=12, visited=None):
            if visited is None:
                visited = set()
            if depth > max_d:
                return
            try:
                rect = element.BoundingRectangle
                key = (element.ClassName, element.Name, rect.left, rect.top)
                if key in visited:
                    return
                visited.add(key)
                
                name = element.Name or ''
                cls = element.ClassName or ''
                ctrl = element.ControlType
                fw = element.FrameworkId
                loc = element.LocalizedControlType or ''
                
                # Skip very generic containers at depth > 3
                skip = (depth > 3 and not name and cls in ('', 'View', 'Pane', 'Custom'))
                
                if not skip or depth <= 2:
                    type_map = {50020: 'W', 50032: 'P', 50000: 'B', 50002: 'E',
                                50033: 'D', 50038: 'C', 50012: 'T', 50006: 'LI',
                                50005: 'L', 50010: 'Tab', 50011: 'TI', 50044: 'G'}
                    tn = type_map.get(ctrl, f'?{ctrl}')
                    parts = [f"{'  ' * depth}{tn}"]
                    if name:
                        parts.append(f'"{name[:60]}"')
                    if cls:
                        parts.append(f'[{cls}]')
                    if fw and fw != 'Win32':
                        parts.append(f'({fw})')
                    if loc not in ('', 'pane', 'region', 'window'):
                        parts.append(f'{{{loc}}}')
                    rect_str = f'({rect.left},{rect.top})-({rect.right},{rect.bottom})'
                    parts.append(rect_str)
                    print(' '.join(parts))
                
                if not skip:
                    try:
                        for child in element.GetChildren():
                            explore_chrome_tree(child, depth+1, max_d, visited)
                    except:
                        pass
            except:
                pass
        
        print("\nChrome UI Tree:")
        explore_chrome_tree(root_view)
    
    if d3d_window:
        print(f"\nD3D Window HWND: {d3d_window.NativeWindowHandle}")
        # Try to get the window text via Win32 API
        try:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(d3d_window.NativeWindowHandle, buf, 256)
            print(f"  GetWindowText: '{buf.value}'")
        except Exception as e:
            print(f"  GetWindowText error: {e}")


def enumerate_all_accessible_elements():
    """Try using raw COM accessibility interface."""
    print("\n" + "=" * 80)
    print("Raw COM Accessibility (IAccessible)")
    print("=" * 80)
    
    try:
        import comtypes
        import comtypes.client
        from comtypes.gen import Accessibility as acc
        
        # Get the accessible object from the window handle
        from ctypes import byref, POINTER
        oleacc = ctypes.windll.oleacc
        
        acc_obj = ctypes.POINTER(ctypes.c_void_p)()
        result = oleacc.AccessibleObjectFromWindow(
            590396, 0xFFFFFFFF,  # OBJID_CLIENT = 0xFFFFFFFF
            ctypes.byref(ctypes.POINTER(ctypes.c_void_p)())(),
            ctypes.byref(acc_obj)
        )
        print(f"  AccessibleObjectFromWindow result: {result}")
        
        if result == 0:  # S_OK
            print("  Got IAccessible object!")
            # Try to get child count and names
            try:
                from comtypes.automation import VARIANT
                # This is complex, let's just note it
                print("  (IAccessible obtained but complex to enumerate without proper bindings)")
            except Exception as e:
                print(f"  Enumeration error: {e}")
        else:
            print(f"  Failed to get IAccessible (code={result})")
    except ImportError:
        print("  comtypes not fully configured for Accessibility")
    except Exception as e:
        print(f"  Error: {e}")


def main():
    check_process_info()
    try_chrome_accessibility_workaround()
    enumerate_all_accessible_elements()
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("""
TRAE Work CN (TRAE Solo) 窗口分析结果:
--------------------------------------
1. 主窗口: Chrome_WidgetWin_1 (Chromium Embedded Framework 窗口)
2. 内容渲染: Intermediate D3D Window (Direct3D 硬件加速表面)
3. UI Automation 可见的控件: 仅窗口标题栏按钮 (最小化/最大化/关闭)
4. 实际内容 (聊天/任务/代码): 通过 Chrome/CEF 在 D3D 表面渲染

关键限制:
- Trae Solo 没有启用 --force-renderer-accessibility 标志
- 因此 Chrome 的无障碍树 (accessibility tree) 没有暴露给 UI Automation
- 无法通过标准 UI Automation API 获取聊天内容、任务列表、输入框等元素

可能的解决方案:
1. 使用图像识别 (OpenCV + 模板匹配)
2. 使用 OCR (Tesseract / PaddleOCR)
3. 通过 Trae Solo 自身的 API 或日志获取数据
4. 启用 Chrome 无障碍模式后重新连接 (需要修改启动参数)
""")


if __name__ == '__main__':
    main()