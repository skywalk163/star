"""
星控者（WindowController）- 窗口点击与文本输入控制

预设热点配置 + 鼠标键盘模拟
"""

import os
import time
import win32gui
import win32con
from typing import Optional, Dict, Tuple
from dataclasses import dataclass


@dataclass
class Hotspot:
    name: str
    label: str
    position: str
    width_ratio: float = 0.3
    height_ratio: float = 0.1
    offset_x: int = 0
    offset_y: int = 0


HOTSPOT_CONFIG = {
    'trae': {
        'input_box': Hotspot(
            name='input_box',
            label='AI 对话输入框',
            position='right_bottom',
            width_ratio=0.35,
            height_ratio=0.08,
            offset_x=-10,
            offset_y=-60,
        ),
        'task_list': Hotspot(
            name='task_list',
            label='任务列表',
            position='left_top',
            width_ratio=0.2,
            height_ratio=0.5,
            offset_x=10,
            offset_y=80,
        ),
    },
    'default': {
        'input_box': Hotspot(
            name='input_box',
            label='输入框',
            position='center_bottom',
            width_ratio=0.5,
            height_ratio=0.1,
            offset_x=0,
            offset_y=-50,
        ),
    },
}


class WindowController:
    def __init__(self):
        pass

    def activate(self, hwnd: int) -> bool:
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            return True
        except Exception:
            return False

    def get_window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

    def calc_hotspot_center(self, hwnd: int, hotspot: Hotspot) -> Optional[Tuple[int, int]]:
        rect = self.get_window_rect(hwnd)
        if not rect:
            return None
        left, top, right, bottom = rect
        w = right - left
        h = bottom - top

        hotspot_w = int(w * hotspot.width_ratio)
        hotspot_h = int(h * hotspot.height_ratio)

        pos = hotspot.position
        if pos == 'left_top':
            anchor_x = left
            anchor_y = top
        elif pos == 'right_bottom':
            anchor_x = right
            anchor_y = bottom
        elif pos == 'center_bottom':
            anchor_x = left + w // 2
            anchor_y = bottom
        elif pos == 'left_bottom':
            anchor_x = left
            anchor_y = bottom
        elif pos == 'right_top':
            anchor_x = right
            anchor_y = top
        elif pos == 'center':
            anchor_x = left + w // 2
            anchor_y = top + h // 2
        else:
            anchor_x = left + w // 2
            anchor_y = top + h // 2

        if 'right' in pos:
            center_x = anchor_x + hotspot.offset_x - hotspot_w // 2
        elif 'left' in pos:
            center_x = anchor_x + hotspot.offset_x + hotspot_w // 2
        else:
            center_x = anchor_x + hotspot.offset_x

        if 'bottom' in pos:
            center_y = anchor_y + hotspot.offset_y - hotspot_h // 2
        elif 'top' in pos:
            center_y = anchor_y + hotspot.offset_y + hotspot_h // 2
        else:
            center_y = anchor_y + hotspot.offset_y

        return (center_x, center_y)

    def click_at(self, x: int, y: int) -> bool:
        try:
            import pyautogui
            pyautogui.click(x, y)
            time.sleep(0.1)
            return True
        except ImportError:
            try:
                import ctypes
                ctypes.windll.user32.SetCursorPos(x, y)
                ctypes.windll.user32.mouse_event(2, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(4, 0, 0, 0, 0)
                time.sleep(0.1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def type_text(self, text: str) -> bool:
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.01)
            return True
        except ImportError:
            try:
                import subprocess
                p = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
                p.communicate(input=text.encode('utf-16-le'))
                import ctypes
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
                time.sleep(0.1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def press_enter(self) -> bool:
        try:
            import pyautogui
            pyautogui.press('enter')
            return True
        except ImportError:
            try:
                import ctypes
                ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def send_to_hotspot(self, hwnd: int, hotspot: Hotspot, text: str) -> bool:
        if not self.activate(hwnd):
            return False

        pos = self.calc_hotspot_center(hwnd, hotspot)
        if not pos:
            return False

        if not self.click_at(pos[0], pos[1]):
            return False

        time.sleep(0.2)

        if not self.type_text(text):
            return False

        time.sleep(0.1)

        return True

    def get_hotspots(self, star_type: str) -> Dict[str, Hotspot]:
        if star_type in HOTSPOT_CONFIG:
            return HOTSPOT_CONFIG[star_type]
        return HOTSPOT_CONFIG['default']

    # ==================== 键盘模拟 ====================

    # 虚拟键码映射
    VK_MAP = {
        'ctrl': 0x11, 'control': 0x11,
        'alt': 0x12,
        'shift': 0x10,
        'win': 0x5B, 'lwin': 0x5B, 'rwin': 0x5C,
        'tab': 0x09,
        'enter': 0x0D, 'return': 0x0D,
        'escape': 0x1B, 'esc': 0x1B,
        'space': 0x20,
        'backspace': 0x08,
        'delete': 0x2E, 'del': 0x2E,
        'home': 0x24,
        'end': 0x23,
        'pageup': 0x21,
        'pagedown': 0x22,
        'up': 0x26,
        'down': 0x28,
        'left': 0x25,
        'right': 0x27,
        'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
        'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
        'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
        'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
        'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
        'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
        'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
        'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
        'z': 0x5A,
        '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
        '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    }

    def _get_vk(self, key: str) -> Optional[int]:
        key = key.lower().strip()
        return self.VK_MAP.get(key)

    def _keydown(self, vk: int):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        except Exception:
            pass

    def _keyup(self, vk: int):
        try:
            import ctypes
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        except Exception:
            pass

    def press_key(self, key: str) -> bool:
        vk = self._get_vk(key)
        if vk is None:
            return False
        self._keydown(vk)
        time.sleep(0.05)
        self._keyup(vk)
        time.sleep(0.05)
        return True

    def send_hotkey(self, *keys) -> bool:
        """
        按下组合键（如 Ctrl+S）
        
        Args:
            *keys: 键名列表，如 send_hotkey('ctrl', 's')
        """
        vks = []
        for k in keys:
            vk = self._get_vk(k)
            if vk is None:
                return False
            vks.append(vk)

        for vk in vks:
            self._keydown(vk)
            time.sleep(0.05)

        for vk in reversed(vks):
            self._keyup(vk)
            time.sleep(0.05)

        return True

    def send_keys(self, text: str) -> bool:
        """
        发送字符串（逐字符输入）
        
        对于非ASCII字符，使用剪贴板粘贴
        """
        try:
            import pyautogui
            pyautogui.typewrite(text, interval=0.01)
            return True
        except ImportError:
            # 混合方案：ASCII用keybd_event，非ASCII用剪贴板
            try:
                import ctypes
                for ch in text:
                    if ord(ch) < 128:
                        vk = self.VK_MAP.get(ch.lower())
                        if vk:
                            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
                            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
                        else:
                            ctypes.windll.user32.keybd_event(ord(ch), 0, 0, 0)
                            ctypes.windll.user32.keybd_event(ord(ch), 0, 2, 0)
                        time.sleep(0.02)
                    else:
                        # 非ASCII字符通过剪贴板粘贴
                        import subprocess
                        orig = subprocess.run(['clip'], capture_output=True)
                        subprocess.run(['cmd', '/c', 'echo', text], stdin=subprocess.PIPE)
                        self.send_hotkey('ctrl', 'v')
                        time.sleep(0.1)
                return True
            except Exception:
                return False
        except Exception:
            return False

    def keyboard_operation(self, hwnd: int, operation: str, params: dict = None) -> dict:
        """
        执行键盘操作

        Args:
            hwnd: 窗口句柄
            operation: 操作类型（hotkey/send_text/press_key）
            params: 操作参数

        Returns:
            执行结果
        """
        params = params or {}
        self.activate(hwnd)
        time.sleep(0.1)

        if operation == 'hotkey':
            keys = params.get('keys', [])
            success = self.send_hotkey(*keys)
            return {'success': success, 'operation': 'hotkey', 'keys': keys}

        elif operation == 'send_text':
            text = params.get('text', '')
            success = self.send_keys(text)
            return {'success': success, 'operation': 'send_text', 'length': len(text)}

        elif operation == 'press_key':
            key = params.get('key', '')
            success = self.press_key(key)
            return {'success': success, 'operation': 'press_key', 'key': key}

        elif operation == 'sequence':
            seq = params.get('sequence', [])
            results = []
            for item in seq:
                if isinstance(item, list):
                    results.append(self.send_hotkey(*item))
                elif isinstance(item, str):
                    if len(item) == 1:
                        results.append(self.send_keys(item))
                    else:
                        results.append(self.press_key(item))
                else:
                    results.append(False)
            return {'success': all(results), 'operation': 'sequence', 'steps': len(seq)}

        else:
            return {'success': False, 'error': 'unknown operation: ' + operation}

    # ==================== 标签页切换 ====================

    def switch_to_tab(self, hwnd: int, tab_index: int) -> bool:
        """
        切换到指定标签页（1-6）

        使用 Ctrl+1 到 Ctrl+6 快捷键
        """
        if tab_index < 1 or tab_index > 6:
            return False
        return self.send_hotkey('ctrl', str(tab_index))

    def switch_to_next_tab(self, hwnd: int) -> bool:
        """切换到下一个标签页 (Ctrl+Tab)"""
        return self.send_hotkey('ctrl', 'tab')

    def switch_to_prev_tab(self, hwnd: int) -> bool:
        """切换到上一个标签页 (Ctrl+Shift+Tab)"""
        return self.send_hotkey('ctrl', 'shift', 'tab')

    def get_tab_region(self) -> dict:
        """
        返回标签页区域的默认位置（相对于窗口）

        标签页区域位于窗口顶部，高度约为窗口高度的 5-8%
        """
        return {
            'top_ratio': 0.0,
            'height_ratio': 0.06,
            'left_ratio': 0.0,
            'right_ratio': 1.0,
        }

    def calc_tab_index_from_click(self, hwnd: int, x_ratio: float, y_ratio: float,
                                   total_tabs: int = 6) -> int:
        """
        根据点击位置计算标签页索引

        Args:
            hwnd: 窗口句柄
            x_ratio: 点击的 x 坐标比例（0-1）
            y_ratio: 点击的 y 坐标比例（0-1）
            total_tabs: 总标签页数量

        Returns:
            标签页索引（1-based），如果不在标签页区域返回 0
        """
        region = self.get_tab_region()
        if (y_ratio < region['top_ratio'] or
            y_ratio > region['top_ratio'] + region['height_ratio']):
            return 0
        tab_width = 1.0 / total_tabs
        index = int(x_ratio / tab_width) + 1
        return min(index, total_tabs)

    # ==================== 热点校准 ====================

    # 输入框候选关键词（OCR识别结果匹配）
    INPUT_KEYWORDS = [
        '输入', '询问', '提问', '发送', '说什么', 'ask', 'send',
        'message', 'type', '说话', '输入框', '请输入', '在这里输入',
        'messageinput', 'chatinput', 'composer',
    ]

    # 候选框宽高比阈值（输入框通常比较宽矮）
    INPUT_BOX_MIN_WIDTH_RATIO = 0.15   # 最小宽度占窗口的 15%
    INPUT_BOX_MAX_HEIGHT_RATIO = 0.15  # 最大高度占窗口的 15%

    def calibrate_hotspots(self, image_path: str, star_type: str = 'trae') -> dict:
        """
        通过 OCR 自动识别输入框位置并校准热点

        Args:
            image_path: 窗口截图路径
            star_type: 星体类型（用于匹配 HOTSPOT_CONFIG）

        Returns:
            校准结果字典，包含原始坐标和比例坐标
        """
        try:
            from star_core.ocr_gazer import OCRGazer
        except ImportError:
            return {'success': False, 'error': 'OCR 模块未安装'}

        if not os.path.exists(image_path):
            return {'success': False, 'error': '截图文件不存在'}

        try:
            gazer = OCRGazer()
            ocr_result = gazer.recognize_text(image_path, use_post_process=False)
            lines = ocr_result.lines

            if not lines:
                return {'success': False, 'error': '未识别到任何文字'}

            # 获取窗口尺寸
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                return {'success': False, 'error': '无法读取截图'}
            img_h, img_w = img.shape[:2]

            # 收集候选输入框
            candidates = []
            for line in lines:
                text_lower = line.text.lower().strip()
                # 检查是否匹配输入框关键词
                is_input_keyword = any(kw in text_lower for kw in self.INPUT_KEYWORDS)
                # 检查宽高比（输入框通常较宽）
                box_w_ratio = line.width / img_w
                box_h_ratio = line.height / img_h
                is_wide = box_w_ratio > self.INPUT_BOX_MIN_WIDTH_RATIO
                is_short = box_h_ratio < self.INPUT_BOX_MAX_HEIGHT_RATIO

                if is_input_keyword or (is_wide and is_short):
                    candidates.append({
                        'text': line.text,
                        'confidence': line.confidence,
                        'x_center': line.x_center,
                        'y_center': line.y_center,
                        'width': line.width,
                        'height': line.height,
                        'box': line.box,
                        'x_ratio': line.x_center / img_w,
                        'y_ratio': line.y_center / img_h,
                        'w_ratio': box_w_ratio,
                        'h_ratio': box_h_ratio,
                        'score': (1 if is_input_keyword else 0) + (1 if is_wide else 0) + (1 if is_short else 0),
                    })

            # 按分数排序，取最高分
            candidates.sort(key=lambda c: c['score'], reverse=True)

            if not candidates:
                # 兜底：找最宽矮的文本框（可能在底部）
                for line in lines:
                    box_w_ratio = line.width / img_w
                    box_h_ratio = line.height / img_h
                    if box_w_ratio > 0.2 and box_h_ratio < 0.1:
                        candidates.append({
                            'text': line.text,
                            'confidence': line.confidence,
                            'x_center': line.x_center,
                            'y_center': line.y_center,
                            'width': line.width,
                            'height': line.height,
                            'box': line.box,
                            'x_ratio': line.x_center / img_w,
                            'y_ratio': line.y_center / img_h,
                            'w_ratio': box_w_ratio,
                            'h_ratio': box_h_ratio,
                            'score': 0,
                        })
                if candidates:
                    candidates.sort(key=lambda c: c['y_ratio'], reverse=True)  # 取底部的

            if not candidates:
                return {'success': False, 'error': '未找到候选输入框'}

            best = candidates[0]

            # 构建校准后的热点
            # 输入框：以识别到的框为中心，但保持一定宽度
            calibrated_input = {
                'name': 'input_box',
                'label': 'AI 对话输入框 (校准)',
                'x_ratio': best['x_ratio'],
                'y_ratio': best['y_ratio'],
                'width_ratio': max(best['w_ratio'], 0.3),
                'height_ratio': max(best['h_ratio'], 0.06),
                'confidence': best['confidence'],
                'matched_text': best['text'][:50],
                'score': best['score'],
            }

            # 如果有多个候选，找任务列表区域（通常在左侧上方）
            task_list_candidates = [c for c in candidates if c['x_ratio'] < 0.4 and c['y_ratio'] < 0.6]
            calibrated_task_list = None
            if task_list_candidates and len(task_list_candidates) > 1:
                # 取最左上方的
                task_list_candidates.sort(key=lambda c: (c['x_ratio'], c['y_ratio']))
                best_task = task_list_candidates[0]
                calibrated_task_list = {
                    'name': 'task_list',
                    'label': '任务列表 (校准)',
                    'x_ratio': best_task['x_ratio'],
                    'y_ratio': best_task['y_ratio'],
                    'width_ratio': max(best_task['w_ratio'], 0.2),
                    'height_ratio': max(best_task['h_ratio'], 0.3),
                    'confidence': best_task['confidence'],
                    'matched_text': best_task['text'][:50],
                }

            return {
                'success': True,
                'image_width': img_w,
                'image_height': img_h,
                'input_box': calibrated_input,
                'task_list': calibrated_task_list,
                'all_candidates': [
                    {
                        'text': c['text'][:30],
                        'x_ratio': round(c['x_ratio'], 3),
                        'y_ratio': round(c['y_ratio'], 3),
                        'score': c['score'],
                    }
                    for c in candidates[:5]
                ],
            }

        except ImportError:
            return {'success': False, 'error': 'OCR 依赖未安装'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
