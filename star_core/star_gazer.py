"""
观星者（StarGazer）- 捕获星体的输出

监控 Agent 的输出变化，提取对话内容
"""

import time
import asyncio
import threading
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

from star_core.star_seeker import StarBody
from star_core.observatory import Observatory


@dataclass
class StarlightSnapshot:
    """
    星光快照 - 某一时刻的输出状态
    
    Attributes:
        timestamp: 时间戳
        content: 输出内容
        delta: 与上次的差异增量
    """
    timestamp: datetime
    content: str
    delta: str = ""


class StarGazer:
    """
    观星者 - 捕获星体的输出
    
    通过 UI Automation 或窗口文本监控获取 Agent 的回复内容
    """

    # 输出控件的常见类名
    OUTPUT_CLASS_NAMES = [
        'TextBlock',
        'TextArea',
        'RichTextControl',
        'ContentElement',
        'TextControl',
        'MonacoEditor',
        'CodeEditor'
    ]

    def __init__(self, observatory: Optional[Observatory] = None, use_ocr: bool = False):
        self.observatory = observatory or Observatory()
        self._gaze_sessions: dict[int, 'GazeSession'] = {}
        self._use_ocr = use_ocr
        self._ocr_gazer = None
    
    def _get_ocr_gazer(self):
        """懒加载 OCR 观星者"""
        if self._ocr_gazer is None and self._use_ocr:
            from star_core.ocr_gazer import OCRGazer
            self._ocr_gazer = OCRGazer()
        return self._ocr_gazer

    def gaze(self, star: StarBody) -> str:
        """
        凝视星辉 - 获取星体当前输出
        
        Args:
            star: 目标星体
            
        Returns:
            当前的输出文本
        """
        # 策略1: UIA 文本控件
        text = self._gaze_by_uia(star.hwnd)
        if text:
            return text
        
        # 策略2: 窗口标题（某些 Agent 在标题显示状态）
        text = self._gaze_by_title(star.hwnd)
        if text:
            return text
        
        # 策略3: OCR 截图识别（可选，作为最后的手段）
        if self._use_ocr:
            text = self._gaze_by_ocr(star)
            if text:
                return text
        
        return ""
    
    def _gaze_by_ocr(self, star: StarBody) -> str:
        """通过 OCR 截图识别获取输出"""
        ocr = self._get_ocr_gazer()
        if not ocr:
            return ""
        return ocr.gaze(star)

    def _gaze_by_uia(self, hwnd: int) -> str:
        """通过 UI Automation 获取输出"""
        try:
            uia = self.observatory.uia
            window = uia.ControlFromHandle(hwnd)
            
            if not window:
                return ""
            
            # 尝试多种输出控件
            for class_name in self.OUTPUT_CLASS_NAMES:
                try:
                    # 查找文本文档控件（通常是最后一个大文本区）
                    text_controls = window.TextControls(
                        searchDepth=10,
                        ClassName=class_name
                    )
                    
                    texts = []
                    for ctrl in text_controls:
                        try:
                            name = ctrl.Name
                            if name and len(name) > 10:  # 过滤掉短标签
                                texts.append(name)
                        except Exception:
                            continue
                    
                    if texts:
                        # 返回最长的文本（通常是主输出区）
                        return max(texts, key=len)
                        
                except Exception:
                    continue
            
            # 尝试查找 Monaco Editor 的内容
            try:
                edit = window.EditControl(searchDepth=10, ClassName='MonacoEditor')
                if edit:
                    return edit.GetValue() or ""
            except Exception:
                pass
                
            return ""
            
        except Exception:
            return ""

    def _gaze_by_title(self, hwnd: int) -> str:
        """通过窗口标题获取状态信息"""
        try:
            import win32gui
            title = win32gui.GetWindowText(hwnd)
            
            # 某些 Agent 在标题显示处理状态
            if any(kw in title.lower() for kw in ['thinking', 'processing', 'working', '闪耀']):
                return f"[状态] {title}"
            
            return ""
        except Exception:
            return ""
    
    def gaze_by_ocr(self, star: StarBody) -> str:
        """
        强制使用 OCR 观星（绕过 UIA，直接截图识别）
        
        Args:
            star: 目标星体
            
        Returns:
            识别到的文本
        """
        if not self._use_ocr:
            self._use_ocr = True
        ocr = self._get_ocr_gazer()
        if not ocr:
            return ""
        return ocr.gaze(star)
    
    def get_current_status(self, star: StarBody) -> dict:
        """
        获取 Agent 当前工作状态（OCR 分析）
        
        Args:
            star: 目标星体
            
        Returns:
            状态信息
        """
        if not self._use_ocr:
            self._use_ocr = True
        ocr = self._get_ocr_gazer()
        if not ocr:
            return {"status": "unknown", "is_active": False}
        return ocr.get_current_status(star)
    
    def extract_task_list(self, star: StarBody) -> list[dict]:
        """
        提取界面中的任务列表（OCR 分析）
        
        Args:
            star: 目标星体
            
        Returns:
            任务列表
        """
        if not self._use_ocr:
            self._use_ocr = True
        ocr = self._get_ocr_gazer()
        if not ocr:
            return []
        return ocr.extract_task_list(star)

    def get_output_delta(self, star: StarBody) -> str:
        """
        获取输出增量 - 与上次相比的变化部分
        
        Args:
            star: 目标星体
            
        Returns:
            新增的输出内容
        """
        session = self._gaze_sessions.get(star.pid)
        if not session:
            current = self.gaze(star)
            self._gaze_sessions[star.pid] = deque(maxlen=100)
            self._gaze_sessions[star.pid].append(StarlightSnapshot(
                timestamp=datetime.now(),
                content=current
            ))
            return current
        
        last = session[-1] if session else None
        current = self.gaze(star)
        
        if last is None:
            return current
        
        if current == last.content:
            return ""
        
        # 提取增量
        if current.startswith(last.content):
            delta = current[len(last.content):]
        else:
            # 内容被替换，使用全部新内容
            delta = current
        
        session.append(StarlightSnapshot(
            timestamp=datetime.now(),
            content=current,
            delta=delta
        ))
        
        return delta

    def continuous_gaze(
        self,
        star: StarBody,
        on_starlight_change: Callable[[StarBody, str], None],
        poll_interval: float = 1.0
    ) -> threading.Event:
        """
        持续观星 - 监控输出变化
        
        Args:
            star: 目标星体
            on_starlight_change: 输出变化时的回调 (star, new_content)
            poll_interval: 轮询间隔（秒）
            
        Returns:
            停止事件，用于取消监控
        """
        stop_event = threading.Event()
        
        def gaze_thread():
            last_content = ""
            while not stop_event.is_set():
                current = self.gaze(star)
                if current != last_content:
                    if current:  # 忽略空内容
                        on_starlight_change(star, current)
                    last_content = current
                time.sleep(poll_interval)
        
        thread = threading.Thread(target=gaze_thread, daemon=True)
        thread.start()
        
        return stop_event

    async def async_continuous_gaze(
        self,
        star: StarBody,
        on_starlight_change: Callable[[StarBody, str], Awaitable[None]],
        poll_interval: float = 1.0
    ) -> asyncio.Event:
        """
        异步持续观星
        
        Args:
            star: 目标星体
            on_starlight_change: 异步回调函数
            poll_interval: 轮询间隔（秒）
            
        Returns:
            停止事件
        """
        import asyncio
        
        stop_event = asyncio.Event()
        
        async def gaze_loop():
            last_content = ""
            while not stop_event.is_set():
                current = self.gaze(star)
                if current != last_content and current:
                    await on_starlight_change(star, current)
                    last_content = current
                await asyncio.sleep(poll_interval)
        
        asyncio.create_task(gaze_loop())
        return stop_event

    def stop_gazing(self, star: StarBody):
        """停止观星"""
        if star.pid in self._gaze_sessions:
            del self._gaze_sessions[star.pid]

    def get_gaze_history(self, star: StarBody) -> list[StarlightSnapshot]:
        """获取观星历史"""
        return list(self._gaze_sessions.get(star.pid, []))

    def extract_response(self, starlight: str) -> str:
        """
        从星光中提取纯文本回复
        
        去除状态信息、标记等，只保留实际内容
        """
        lines = starlight.split('\n')
        content_lines = []
        
        skip_prefixes = [
            '[状态]', '[系统]', '[星核]', '[星语]',
            'thinking', 'processing', 'working...'
        ]
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            
            # 跳过状态行
            if any(stripped.lower().startswith(p.lower()) for p in skip_prefixes):
                continue
            
            content_lines.append(stripped)
        
        return '\n'.join(content_lines)

    def detect_completion(self, star: StarBody) -> bool:
        """
        检测星体是否完成当前任务
        
        通过观察输出模式判断是否完成
        """
        current = self.gaze(star)
        
        # 完成标志
        completion_patterns = [
            '✨', '完成', 'done', 'finished', 'success',
            '✅', '已生成', '已创建', '已修复', '已优化'
        ]
        
        if any(pattern in current for pattern in completion_patterns):
            return True
        
        # 检查是否还在思考（通过标题或内容）
        thinking_patterns = ['thinking', '思考中', 'processing', '处理中']
        if any(p in current.lower() for p in thinking_patterns):
            return False
        
        # 多次采样确认稳定
        samples = [current]
        for _ in range(3):
            time.sleep(0.5)
            sample = self.gaze(star)
            samples.append(sample)
            if sample != samples[0]:
                return False  # 还在变化
        
        return True
