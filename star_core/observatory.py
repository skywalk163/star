"""
观星台（Observatory）- Windows API 封装

提供 Windows 系统级 API 能力：
- 句柄与窗口管理
- 进程与线程操作
- UI Automation 封装
- 键盘/鼠标模拟
- 剪贴板操作
"""

import time
from typing import Optional, Callable, Any
from dataclasses import dataclass

import win32gui
import win32process
import win32con
import win32api
import win32ui
from ctypes import windll, Structure, c_long, byref
from ctypes.wintypes import POINT

import psutil


@dataclass
class WindowInfo:
    """窗口信息"""
    hwnd: int
    title: str
    class_name: str
    rect: tuple[int, int, int, int]  # left, top, right, bottom
    process_id: int
    process_name: str


class Observatory:
    """
    观星台 - Windows API 统一封装
    
    提供窗口发现、进程管理、输入模拟等系统级能力
    """

    def __init__(self):
        self._uia = None  # Lazy load uiautomation

    @property
    def uia(self):
        """懒加载 UI Automation"""
        if self._uia is None:
            import uiautomation as uia
            self._uia = uia
        return self._uia

    def find_window_by_pid(self, pid: int, title_patterns: Optional[list[str]] = None) -> Optional[int]:
        """
        通过进程 ID 查找窗口句柄
        
        Args:
            pid: 进程 ID
            title_patterns: 窗口标题匹配模式（可选）
            
        Returns:
            匹配的窗口句柄，未找到返回 None
        """
        hwnds = []
        
        def callback(hwnd, hwnds_list):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            
            try:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            
            if found_pid == pid:
                title = win32gui.GetWindowText(hwnd)
                if title_patterns is None or any(p.lower() in title.lower() for p in title_patterns):
                    hwnds_list.append(hwnd)
            return True
        
        win32gui.EnumWindows(callback, hwnds)
        return hwnds[0] if hwnds else None

    def find_all_windows_by_pid(self, pid: int) -> list[int]:
        """获取进程所有窗口句柄"""
        hwnds = []
        
        def callback(hwnd, hwnds_list):
            if not win32gui.IsWindowVisible(hwnd):
                return True
            try:
                _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            except Exception:
                return True
            if found_pid == pid:
                hwnds_list.append(hwnd)
            return True
        
        win32gui.EnumWindows(callback, hwnds)
        return hwnds

    def get_window_info(self, hwnd: int) -> Optional[WindowInfo]:
        """获取窗口详细信息"""
        try:
            if not win32gui.IsWindow(hwnd):
                return None
            
            title = win32gui.GetWindowText(hwnd)
            class_name = win32gui.GetClassName(hwnd)
            rect = win32gui.GetWindowRect(hwnd)
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            
            try:
                process = psutil.Process(pid)
                process_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                process_name = "unknown"
            
            return WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name=class_name,
                rect=rect,
                process_id=pid,
                process_name=process_name
            )
        except Exception:
            return None

    def get_foreground_window(self) -> Optional[int]:
        """获取当前前台窗口"""
        return win32gui.GetForegroundWindow()

    def set_foreground_window(self, hwnd: int) -> bool:
        """将窗口置前"""
        try:
            # 尝试使用 ShowWindow
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            
            # 使用 SetForegroundWindow
            return win32gui.SetForegroundWindow(hwnd) != 0
        except Exception:
            return False

    def find_control_by_uia(
        self,
        hwnd: int,
        control_type: str,
        search_depth: int = 5,
        **kwargs
    ) -> Any:
        """
        通过 UI Automation 查找控件
        
        Args:
            hwnd: 窗口句柄
            control_type: 控件类型（如 'EditControl', 'TextControl'）
            search_depth: 搜索深度
            **kwargs: uiautomation 的搜索参数（如 ClassName, Name 等）
        """
        window = self.uia.ControlFromHandle(hwnd)
        if not window:
            return None
        
        control_class = getattr(self.uia, control_type, None)
        if not control_class:
            return None
        
        try:
            return control_class(searchDepth=search_depth, **kwargs)
        except Exception:
            return None

    def get_control_text(self, hwnd: int, control_class_name: str = "TextArea") -> str:
        """获取文本控件内容"""
        control = self.find_control_by_uia(
            hwnd, "TextControl",
            search_depth=10,
            ClassName=control_class_name
        )
        if control:
            try:
                return control.Name or ""
            except Exception:
                pass
        return ""

    def set_control_text(self, hwnd: int, text: str, control_class_name: str = "TextArea") -> bool:
        """设置文本控件内容"""
        control = self.find_control_by_uia(
            hwnd, "EditControl",
            search_depth=5,
            ClassName=control_class_name
        )
        if control:
            try:
                control.SetValue(text)
                return True
            except Exception:
                pass
        return False

    def send_keys_to_window(self, hwnd: int, keys: str) -> bool:
        """发送按键到窗口"""
        try:
            self.set_foreground_window(hwnd)
            time.sleep(0.05)
            
            for key in keys:
                win32api.keybd_event(ord(key.upper()), 0, 0, 0)
                win32api.keybd_event(ord(key.upper()), 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception:
            return False

    def send_ctrl_v(self, hwnd: int) -> bool:
        """发送 Ctrl+V 粘贴"""
        try:
            self.set_foreground_window(hwnd)
            time.sleep(0.05)
            
            win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, 0, 0)
            win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
            win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception:
            return False

    def send_enter(self, hwnd: int) -> bool:
        """发送 Enter 键"""
        try:
            self.set_foreground_window(hwnd)
            time.sleep(0.05)
            
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            return True
        except Exception:
            return False

    def get_clipboard_text(self) -> str:
        """获取剪贴板文本"""
        try:
            win32gui.OpenClipboard(None)
            data = win32gui.GetClipboardData(win32con.CF_UNICODETEXT)
            win32gui.CloseClipboard()
            return data
        except Exception:
            return ""

    def set_clipboard_text(self, text: str) -> bool:
        """设置剪贴板文本"""
        try:
            win32gui.OpenClipboard(None)
            win32gui.EmptyClipboard()
            win32gui.SetClipboardData(win32con.CF_UNICODETEXT, text)
            win32gui.CloseClipboard()
            return True
        except Exception:
            return False

    def get_process_by_name(self, name: str) -> list[psutil.Process]:
        """通过进程名查找进程"""
        matching = []
        name_lower = name.lower()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if name_lower in proc.info['name'].lower():
                    matching.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return matching

    def get_process_by_executable(self, names: list[str]) -> list[psutil.Process]:
        """通过可执行文件名查找进程"""
        matching = []
        names_lower = [n.lower() for n in names]
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() in names_lower:
                    matching.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return matching

    def is_process_running(self, pid: int) -> bool:
        """检查进程是否在运行"""
        try:
            proc = psutil.Process(pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def get_window_rect(self, hwnd: int) -> Optional[tuple[int, int, int, int]]:
        """获取窗口矩形区域"""
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    def get_client_rect(self, hwnd: int) -> Optional[tuple[int, int, int, int]]:
        """获取窗口客户区矩形"""
        try:
            return win32gui.GetClientRect(hwnd)
        except Exception:
            return None

    def screen_to_client(self, hwnd: int, point: tuple[int, int]) -> tuple[int, int]:
        """屏幕坐标转客户区坐标"""
        try:
            return win32gui.ScreenToClient(hwnd, point)
        except Exception:
            return point

    def client_to_screen(self, hwnd: int, point: tuple[int, int]) -> tuple[int, int]:
        """客户区坐标转屏幕坐标"""
        try:
            return win32gui.ClientToScreen(hwnd, point)
        except Exception:
            return point
