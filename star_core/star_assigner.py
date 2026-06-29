"""
授星者（StarAssigner）- 向星体注入星令

通过多种策略向运行中的 Agent 发送指令或文本
"""

import time
from typing import Optional
from enum import Enum

import pyperclip

from star_core.star_seeker import StarBody
from star_core.observatory import Observatory


class AssignStrategy(Enum):
    """注入策略优先级"""
    UIA = "uia"              # UI Automation - 最精准
    CLIPBOARD = "clipboard"   # 剪贴板 - 通用可靠
    MESSAGE = "message"       # 窗口消息 - 适用于原生控件
    WIN32 = "win32"           # Win32 API - 底层控制


class StarAssigner:
    """
    授星者 - 向星体发送星辉指令
    
    提供多种文本注入策略，按优先级尝试直到成功
    """

    def __init__(self, observatory: Optional[Observatory] = None):
        self.observatory = observatory or Observatory()
        self._clipboard_backup: Optional[str] = None

    def send_starlight(
        self,
        star: StarBody,
        starlight: str,
        strategy_priority: Optional[list[AssignStrategy]] = None
    ) -> bool:
        """
        向星体发送星辉指令
        
        Args:
            star: 目标星体
            starlight: 要发送的指令内容
            strategy_priority: 策略优先级列表
            
        Returns:
            是否发送成功
        """
        if strategy_priority is None:
            strategy_priority = [
                AssignStrategy.UIA,
                AssignStrategy.CLIPBOARD,
                AssignStrategy.MESSAGE,
                AssignStrategy.WIN32
            ]
        
        for strategy in strategy_priority:
            success = self._try_strategy(star, starlight, strategy)
            if success:
                return True
        
        return False

    def _try_strategy(
        self,
        star: StarBody,
        starlight: str,
        strategy: AssignStrategy
    ) -> bool:
        """尝试单个注入策略"""
        method_name = f"_try_{strategy.value}"
        method = getattr(self, method_name, None)
        if method:
            try:
                return method(star, starlight)
            except Exception as e:
                pass
        return False

    def _try_uia(self, star: StarBody, starlight: str) -> bool:
        """
        观星术 - 通过 UI Automation 精确定位输入框
        
        适用于基于 Chromium/ Electron 的应用
        """
        try:
            uia = self.observatory.uia
            window = uia.ControlFromHandle(star.hwnd)
            
            if not window:
                return False
            
            # 尝试查找常见的输入框类
            input_class_names = ['TextArea', 'textarea', 'MonacoEditor', 'CodeEditor']
            
            for class_name in input_class_names:
                try:
                    edit = window.EditControl(
                        searchDepth=5,
                        ClassName=class_name
                    )
                    if edit:
                        # 清空并设置新值
                        edit.SetValue(starlight)
                        edit.SendKeys('{Enter}')
                        star.mark_shining(True)
                        return True
                except Exception:
                    continue
            
            # 尝试 ComboBox（某些 IDE 的输入框）
            try:
                combo = window.ComboBoxControl(searchDepth=5)
                if combo:
                    combo.SetValue(starlight)
                    combo.SendKeys('{Enter}')
                    star.mark_shining(True)
                    return True
            except Exception:
                pass
                
            return False
            
        except Exception:
            return False

    def _try_clipboard(self, star: StarBody, starlight: str) -> bool:
        """
        星光传递 - 剪贴板注入
        
        步骤：
        1. 保存原剪贴板内容
        2. 复制新内容到剪贴板
        3. 激活目标窗口
        4. Ctrl+V 粘贴
        5. Enter 确认
        6. 恢复原剪贴板
        """
        self._clipboard_backup = self.observatory.get_clipboard_text()
        
        try:
            # 复制到剪贴板
            if not self.observatory.set_clipboard_text(starlight):
                return False
            
            # 激活目标窗口
            if not self.observatory.set_foreground_window(star.hwnd):
                return False
            
            time.sleep(0.1)
            
            # 粘贴
            if not self.observatory.send_ctrl_v(star.hwnd):
                return False
            
            time.sleep(0.1)
            
            # 回车确认
            self.observatory.send_enter(star.hwnd)
            
            star.mark_shining(True)
            return True
            
        except Exception:
            return False
        finally:
            # 恢复原剪贴板
            if self._clipboard_backup is not None:
                self.observatory.set_clipboard_text(self._clipboard_backup)
                self._clipboard_backup = None

    def _try_message(self, star: StarBody, starlight: str) -> bool:
        """
        星波 - 通过窗口消息发送文本
        
        适用于原生 Windows 控件
        """
        import win32gui
        import win32con
        import win32api
        
        try:
            # 查找输入框
            input_hwnd = self._find_input_window(star.hwnd)
            if not input_hwnd:
                return False
            
            # 设置前景窗口
            win32gui.SetForegroundWindow(input_hwnd)
            time.sleep(0.05)
            
            # 发送文本消息
            for char in starlight:
                # WM_CHAR 消息
                win32api.PostMessage(
                    input_hwnd,
                    win32con.WM_CHAR,
                    ord(char),
                    0
                )
                time.sleep(0.01)
            
            # 发送回车
            win32api.PostMessage(input_hwnd, win32con.WM_KEYDOWN, win32con.VK_RETURN, 0)
            win32api.PostMessage(input_hwnd, win32con.WM_KEYUP, win32con.VK_RETURN, 0)
            
            star.mark_shining(True)
            return True
            
        except Exception:
            return False

    def _try_win32(self, star: StarBody, starlight: str) -> bool:
        """
        Win32 底层注入 - 使用 SendInput
        
        最底层方案，直接模拟键盘输入
        """
        import pyautogui
        
        try:
            # 激活窗口
            if not self.observatory.set_foreground_window(star.hwnd):
                return False
            
            time.sleep(0.1)
            
            # 使用 pyautogui 粘贴
            pyautogui.hotkey('ctrl', 'v')
            time.sleep(0.1)
            pyautogui.press('enter')
            
            star.mark_shining(True)
            return True
            
        except Exception:
            return False

    def _find_input_window(self, hwnd: int) -> Optional[int]:
        """查找输入框窗口"""
        import win32gui
        
        # 尝试在子窗口中找 Edit 或 TextArea
        def enum_child(hwnd, result):
            class_name = win32gui.GetClassName(hwnd)
            if 'Edit' in class_name or 'TextArea' in class_name:
                result.append(hwnd)
        
        children = []
        try:
            win32gui.EnumChildWindows(hwnd, enum_child, children)
        except Exception:
            pass
        
        return children[0] if children else None

    def send_starlight_to_input(
        self,
        star: StarBody,
        starlight: str,
        input_class_name: str = "TextArea"
    ) -> bool:
        """
        向星体的指定输入框发送指令
        
        Args:
            star: 目标星体
            starlight: 要发送的指令
            input_class_name: 输入框的类名
        """
        return self.observatory.set_control_text(star.hwnd, starlight, input_class_name)

    def inject_correction(
        self,
        star: StarBody,
        original_starlight: str,
        correction: str
    ) -> bool:
        """
        注入修正指令 - 覆盖之前的指令
        
        向正在运行的星体发送修正指令，忽略之前的中间结果
        """
        correction_starlight = f"""
[星核指令] 对当前星轨进行调整：
原始星图：{original_starlight}
调轨指令：{correction}
请忽略之前的中间星光，基于调轨指令重新闪耀。
"""
        return self.send_starlight(star, correction_starlight)

    def send_partial_starlight(
        self,
        star: StarBody,
        starlight: str,
        position: Optional[tuple[int, int]] = None
    ) -> bool:
        """
        发送部分星辉 - 仅在光标位置插入文本
        
        适用于追加内容而非覆盖
        """
        # 先获取当前剪贴板内容
        original_clipboard = self.observatory.get_clipboard_text()
        
        try:
            # 如果指定了位置，先点击
            if position:
                import pyautogui
                if not self.observatory.set_foreground_window(star.hwnd):
                    return False
                pyautogui.click(*position)
                time.sleep(0.05)
            
            # 使用 Ctrl+V 粘贴
            self.observatory.set_clipboard_text(starlight)
            return self.observatory.send_ctrl_v(star.hwnd)
            
        finally:
            # 恢复剪贴板
            self.observatory.set_clipboard_text(original_clipboard)
