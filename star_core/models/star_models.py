"""
star_models.py - 星体相关数据模型

核心数据类：
- StarWindowContext: 窗口上下文（项目/文件/状态）
- StarWindow: 星体窗口
- StarBody: 星体（AI Agent 实例）
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field


@dataclass
class StarWindowContext:
    """
    星窗上下文 - 从窗口标题等信息解析出的项目/文件/状态

    Attributes:
        project_name: 项目名称
        file_name: 当前打开的文件名
        window_type: 窗口类型 (editor, chat, preview, work_mode, unknown)
        is_work_mode: 是否为 Trae Work 任务模式
    """
    project_name: str = ""
    file_name: str = ""
    window_type: str = "unknown"
    is_work_mode: bool = False

    def to_dict(self) -> dict:
        return {
            'project_name': self.project_name,
            'file_name': self.file_name,
            'window_type': self.window_type,
            'is_work_mode': self.is_work_mode,
        }


@dataclass
class StarWindow:
    """
    星窗 - 代表星体进程中的一个窗口/标签页

    Attributes:
        hwnd: 窗口句柄
        title: 窗口标题
        class_name: 窗口类名
        rect: 窗口矩形 (left, top, right, bottom)
        is_visible: 是否可见
    """
    hwnd: int
    title: str = ""
    class_name: str = ""
    rect: tuple = ()
    is_visible: bool = True

    def parse_context(self, star_type: str = "trae") -> StarWindowContext:
        """
        从窗口标题解析项目上下文

        Args:
            star_type: 星体类型，决定解析规则

        Returns:
            StarWindowContext 上下文对象
        """
        ctx = StarWindowContext()

        if not self.title:
            return ctx

        title = self.title.strip()

        if star_type == "trae":
            if "TRAE Work" in title or "Trae Work" in title:
                ctx.is_work_mode = True
                ctx.window_type = "work_mode"
                ctx.project_name = "Trae Work"
                return ctx

            parts = [p.strip() for p in title.rsplit(" - ", 2)]

            if len(parts) >= 2 and ("Trae" in parts[-1] or "trae" in parts[-1]):
                parts = parts[:-1]

            if len(parts) >= 2:
                ctx.project_name = parts[-1]
                ctx.file_name = " - ".join(parts[:-1])

                fn_lower = ctx.file_name.lower()
                if "(preview)" in fn_lower:
                    ctx.window_type = "preview"
                elif any(ext in fn_lower for ext in ['.md', '.txt', '.docx', '.pdf', '.html']):
                    ctx.window_type = "document"
                elif any(ext in fn_lower for ext in ['.py', '.js', '.ts', '.rkt', '.duan', '.sh', '.json', '.yaml', '.yml']):
                    ctx.window_type = "editor"
                else:
                    ctx.window_type = "editor"
            elif len(parts) == 1:
                ctx.project_name = parts[0]
                ctx.window_type = "unknown"
        elif star_type == "codearts_agent":
            parts = [p.strip() for p in title.rsplit(" - ", 2)]

            if len(parts) >= 2 and ("CodeArts" in parts[-1] or "codearts" in parts[-1]):
                parts = parts[:-1]

            if len(parts) >= 2:
                ctx.project_name = parts[0]
                ctx.file_name = parts[1]

                fn_lower = ctx.file_name.lower()
                if "(preview)" in fn_lower:
                    ctx.window_type = "preview"
                elif any(ext in fn_lower for ext in ['.md', '.txt', '.docx', '.pdf', '.html']):
                    ctx.window_type = "document"
                elif any(ext in fn_lower for ext in ['.py', '.js', '.ts', '.rkt', '.java', '.cpp', '.c', '.cs', '.go', '.rs', '.sh', '.json', '.yaml', '.yml']):
                    ctx.window_type = "editor"
                else:
                    ctx.window_type = "editor"
            elif len(parts) == 1:
                ctx.project_name = parts[0]
                ctx.window_type = "unknown"

        elif star_type == "dumate":
            ctx.project_name = "搭子DuMate"
            ctx.window_type = "chat"
            ctx.is_work_mode = True

        return ctx

    def get_context(self, star_type: str = "trae") -> StarWindowContext:
        """获取窗口上下文（别名，保持代码可读性）"""
        return self.parse_context(star_type)

    def to_dict(self) -> dict:
        ctx = self.parse_context()
        return {
            'hwnd': self.hwnd,
            'title': self.title,
            'class_name': self.class_name,
            'rect': list(self.rect) if self.rect else [],
            'is_visible': self.is_visible,
            'context': ctx.to_dict(),
        }


@dataclass
class StarBody:
    """
    星体 - 代表一个运行中的 AI Agent 实例

    Attributes:
        star_type: 星体类型 ('trae', 'codearts_atomcode', 'cursor', 'copilot')
        pid: 进程 ID
        hwnd: 主窗口句柄（第一个可见窗口）
        title: 主窗口标题
        process: psutil.Process 对象
        windows: 该进程的所有窗口列表
        is_shining: 是否正在闪耀（处理任务）
        last_activity: 最后活跃时间
    """
    star_type: str
    pid: int
    hwnd: int
    title: str
    process: Any = None
    windows: List[StarWindow] = field(default_factory=list)
    is_shining: bool = False
    last_activity: float = field(default_factory=time.time)

    def refresh_activity(self):
        """刷新活跃时间"""
        self.last_activity = time.time()

    def mark_shining(self, shining: bool = True):
        """标记为闪耀状态"""
        self.is_shining = shining
        if shining:
            self.refresh_activity()

    def refresh_windows(self, observatory: Any = None, title_patterns: Optional[list] = None):
        """刷新所有窗口信息"""
        import win32gui
        if observatory is None:
            return
        hwnds = observatory.find_all_windows_by_pid(self.pid)
        new_windows = []
        for hwnd in hwnds:
            try:
                title = win32gui.GetWindowText(hwnd) or ""
                if title_patterns and not any(p.lower() in title.lower() for p in title_patterns):
                    continue
                class_name = win32gui.GetClassName(hwnd) or ""
                rect = win32gui.GetWindowRect(hwnd)
                is_visible = win32gui.IsWindowVisible(hwnd)
                new_windows.append(StarWindow(
                    hwnd=hwnd,
                    title=title,
                    class_name=class_name,
                    rect=rect,
                    is_visible=bool(is_visible),
                ))
            except Exception:
                continue
        self.windows = new_windows
        if new_windows:
            self.hwnd = new_windows[0].hwnd
            self.title = new_windows[0].title

    def get_window_count(self) -> int:
        """获取窗口数量"""
        return len(self.windows)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于 API 返回）"""
        return {
            'star_id': 'star_%d' % self.pid,
            'star_type': self.star_type,
            'pid': self.pid,
            'hwnd': self.hwnd,
            'title': self.title,
            'is_shining': self.is_shining,
            'last_activity': self.last_activity,
            'window_count': len(self.windows),
            'windows': [w.to_dict() for w in self.windows],
        }

    def __hash__(self):
        return hash(self.pid)
