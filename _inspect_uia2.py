"""
uiautomation 补充检查 - Trae Solo 窗口内部细节
尝试获取所有可访问的属性和内容。
"""
import uiautomation as uia
from uiautomation import ControlType


def inspect_control(ctrl, indent=0, label=""):
    """Dump all accessible properties of a control."""
    prefix = "  " * indent
    try:
        # Get all common properties
        props = {}
        for attr in ['Name', 'ClassName', 'AutomationId', 'ControlType', 'LocalizedControlType',
                      'IsEnabled', 'IsOffscreen', 'IsKeyboardFocusable', 'HasKeyboardFocus',
                      'ProcessId', 'RuntimeId', 'BoundingRectangle', 'HelpText',
                      'AccessKey', 'AcceleratorKey', 'IsPassword', 'ItemStatus',
                      'ItemType', 'FrameworkId', 'ProviderDescription', 'NativeWindowHandle']:
            try:
                val = getattr(ctrl, attr)
                if val is not None and val != '' and val != 0:
                    props[attr] = val
            except:
                pass
        
        if props:
            name = props.pop('Name', '')
            print(f"{prefix}[{label or props.get('ControlType', '?')}] Name='{name}'")
            for k, v in props.items():
                print(f"{prefix}  {k} = {v}")
            return True
    except Exception as e:
        print(f"{prefix}[Error: {e}]")
    return False


def get_all_props(element, depth=0, max_depth=15, visited=None):
    """Get all properties of element and all descendants."""
    if visited is None:
        visited = set()
    if depth > max_depth:
        return
    
    try:
        ctrl_type = element.ControlType
        class_name = element.ClassName
        rect = element.BoundingRectangle
        
        # Create key
        key = (ctrl_type, class_name, element.Name, rect.left, rect.top, rect.right, rect.bottom)
        if key in visited:
            return
        visited.add(key)
        
        # Print detailed info
        inspect_control(element, depth)
        
        # Get children
        children = element.GetChildren()
        for child in children:
            get_all_props(child, depth+1, max_depth, visited)
    except Exception as e:
        print(f"{'  ' * (depth+1)}[Error: {e}]")


def main():
    window = uia.ControlFromHandle(590396)
    
    print("=" * 80)
    print("DETAILED CONTROL PROPERTIES - TRAE Work CN")
    print("=" * 80)
    
    # Print root window properties
    print("\n--- Root Control Properties ---")
    inspect_control(window, 0, "ROOT")
    
    # Get all children with full properties
    print("\n--- Full property tree ---")
    get_all_props(window, max_depth=15)
    
    # Try to find any text content via TextPattern
    print("\n--- Trying TextPattern ---")
    try:
        text_pattern = window.GetPattern(uia.PatternID.TextPattern)
        if text_pattern:
            print(f"  TextPattern available: {text_pattern}")
            try:
                text_range = text_pattern.DocumentRange
                if text_range:
                    print(f"  Document text: {text_range.GetText(-1)[:500]}")
            except:
                pass
        else:
            print("  No TextPattern on root")
    except Exception as e:
        print(f"  TextPattern error: {e}")
    
    # Try to find any ValuePattern
    print("\n--- Trying ValuePattern on all controls ---")
    def find_value_patterns(element, depth=0, max_d=10, visited=None):
        if visited is None:
            visited = set()
        if depth > max_d:
            return
        try:
            key = id(element)
            if key in visited:
                return
            visited.add(key)
            
            try:
                value_pattern = element.GetPattern(uia.PatternID.ValuePattern)
                if value_pattern:
                    val = value_pattern.Value
                    if val:
                        print(f"{'  ' * depth}Value: '{val[:200]}' on '{element.Name}' [{element.ClassName}]")
            except:
                pass
            
            try:
                text_pattern = element.GetPattern(uia.PatternID.TextPattern)
                if text_pattern:
                    try:
                        doc_range = text_pattern.DocumentRange
                        if doc_range:
                            txt = doc_range.GetText(-1)
                            if txt and txt.strip():
                                print(f"{'  ' * depth}Text: '{txt[:200]}' on '{element.Name}' [{element.ClassName}]")
                    except:
                        pass
            except:
                pass
            
            for child in element.GetChildren():
                find_value_patterns(child, depth+1, max_d, visited)
        except:
            pass
    
    find_value_patterns(window, max_d=10)
    
    # Try to enumerate all top-level windows to find related windows
    print("\n--- All Top-Level Windows (related to Trae) ---")
    root = uia.GetRootControl()
    child_count = 0
    for child in root.GetChildren():
        try:
            name = child.Name
            class_name = child.ClassName
            pid = child.ProcessId
            rect = child.BoundingRectangle
            if 'trae' in (name or '').lower() or 'solo' in (name or '').lower() or 'work' in (name or '').lower():
                print(f"  Window: '{name}' | Cls={class_name} | PID={pid} | Rect=({rect.left},{rect.top})-({rect.right},{rect.bottom})")
                child_count += 1
        except:
            pass
    if child_count == 0:
        # Print all visible windows
        print("  (No Trae-specific windows found, listing all visible windows)")
        for child in root.GetChildren():
            try:
                name = child.Name
                class_name = child.ClassName
                pid = child.ProcessId
                if name and name.strip():
                    rect = child.BoundingRectangle
                    print(f"  '{name}' | Cls={class_name} | PID={pid} | ({rect.left},{rect.top})-({rect.right},{rect.bottom})")
            except:
                pass
    
    print("\n=" * 80)
    print("DONE")
    print("=" * 80)


if __name__ == '__main__':
    main()