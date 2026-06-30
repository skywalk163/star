"""
寻星者（StarSeeker）- Agent 发现与注册

自动扫描系统，发现正在运行的 AI Agent 进程
"""

import time
import re
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

import psutil

from star_core.observatory import Observatory


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
            # Trae Work CN 模式
            if "TRAE Work" in title or "Trae Work" in title:
                ctx.is_work_mode = True
                ctx.window_type = "work_mode"
                ctx.project_name = "Trae Work"
                return ctx
            
            # Trae CN 编辑器模式: 格式 "文件名 - 项目名 - Trae CN"
            # 如: "hanoi.duan - duan - Trae CN"
            # 如: "setup-redis.sh - sound - Trae CN"
            # 如: "2026-06-19-ai-finder-design.md (Preview) - search - Trae CN"
            parts = [p.strip() for p in title.rsplit(" - ", 2)]
            
            if len(parts) >= 2 and ("Trae" in parts[-1] or "trae" in parts[-1]):
                # 末尾是 Trae CN，去掉
                parts = parts[:-1]
            
            if len(parts) >= 2:
                # 最后一段是项目名
                ctx.project_name = parts[-1]
                # 前面的都是文件名
                ctx.file_name = " - ".join(parts[:-1])
                
                # 判断窗口类型
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
            # CodeArts Agent 格式: "项目名 - 文件名 - CodeArts Agent"
            # 如: "yanpub - adapter.py - CodeArts Agent"
            # 如: "zhixing - _test_friendly.py - CodeArts Agent"
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
            # 搭子 DuMate 格式: "搭子DuMate"
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
    process: psutil.Process
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

    def refresh_windows(self, observatory: Observatory, title_patterns: Optional[list] = None):
        """刷新所有窗口信息"""
        import win32gui
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


class StarSeeker:
    """
    寻星者 - 发现并管理 AI Agent 进程
    
    通过进程名、窗口类名、窗口标题等特征扫描系统，
    发现正在运行的 AI Agent 实例
    """

    # 已知星体特征签名
    STAR_SIGNATURES = {
        'trae': {
            'process_names': ['Trae.exe', 'trae.exe', 'TRAE SOLO CN.exe', 'TRAE SOLO CN', 'Trae CN.exe', 'Trae CN', 'trae', 'trae cn.exe', 'trae cn'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['Trae', 'trae', 'TRAE Work CN', 'TRAE SOLO', 'Trae CN'],
            'description': '字节跳动 AI 编程助手（Trae Solo / Trae CN）'
        },
        'codearts_atomcode': {
            'process_names': ['CodeArts.exe', 'AtomCode.exe', 'HuaweiCodeArts.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'CEF窗外壳窗口'],
            'window_title_patterns': ['CodeArts', 'AtomCode', '华为云CodeArts'],
            'description': '华为云 CodeArts IDE'
        },
        'codearts_agent': {
            'process_names': ['codearts-agent.exe', 'CodeArts Agent.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['CodeArts Agent', 'codearts agent'],
            'description': '华为云 CodeArts Agent AI 编程助手'
        },
        'dumate': {
            'process_names': ['DuMate.exe', 'dumate.exe', '搭子.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['搭子DuMate', 'DuMate', 'dumate', '搭子'],
            'description': '百度 搭子 DuMate AI 编程助手'
        },
        'cursor': {
            'process_names': ['Cursor.exe', 'cursor.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['Cursor'],
            'description': 'Cursor AI IDE'
        },
        'copilot': {
            'process_names': ['Cursor.exe', 'VSCodium.exe', 'Code.exe'],  # Copilot 集成在 VS Code 中
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['GitHub Copilot'],
            'description': 'GitHub Copilot'
        },
        'copilot_studio': {
            'process_names': ['msedgedev.exe', 'msedge.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'WorkerW'],
            'window_title_patterns': ['Copilot'],
            'description': 'GitHub Copilot Studio'
        },
        'windsurf': {
            'process_names': ['windsurf.exe', 'Windsurf.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['Windsurf', 'Codeium'],
            'description': 'Windsurf AI IDE'
        },
        'claude': {
            'process_names': ['claude.exe', 'ClaudeDesktop.exe'],
            'window_class': ['Chrome_WidgetWin_1'],
            'window_title_patterns': ['Claude'],
            'description': 'Anthropic Claude'
        },
        # ===== 国产 AI Agent =====
        'ernie': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['文心一言', 'ERNIE Bot', 'ernie', 'yiyan', '文心'],
            'description': '百度文心一言'
        },
        'yiyan': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['文心一言', 'ERNIE Bot', 'ernie', 'yiyan', '文心'],
            'description': '百度文心一言'
        },
        'spark': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['讯飞星火', 'Spark', 'xinghuo'],
            'description': '科大讯飞星火大模型'
        },
        'glm': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['智谱清言', 'GLM', 'chatglm', 'zhipu'],
            'description': '智谱 AI 清言'
        },
        'step': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['跃问', 'Step', 'stepfun', 'StepFun'],
            'description': '阶跃星辰跃问'
        },
        'wanzhi': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['万知', 'WanZhi', 'wps', '金山'],
            'description': '金山万知 AI'
        },
        'shangliang': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['商量', 'ShangLiang', 'SenseChat', 'SenseTime'],
            'description': '商汤商量大模型'
        },
        'hailuo': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['海螺', 'Hailuo', 'hailuoai', 'MiniMax'],
            'description': '海螺问问 MiniMax AI'
        },
        'baichuan': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['百川', 'BaiChuan', 'baichuan', '百川智能'],
            'description': '百川智能大模型'
        },
        'qwen': {
            'process_names': ['msedge.exe', 'chrome.exe', 'brave.exe', 'firefox.exe'],
            'window_class': ['Chrome_WidgetWin_1', 'MozillaWindowClass'],
            'window_title_patterns': ['通义千问', 'Qwen', 'qwen', '阿里云'],
            'description': '阿里通义千问'
        },
        'generic': {
            'process_names': [],  # 通用 AI Agent，待扩展
            'window_class': [],
            'window_title_patterns': [],
            'description': '通用 AI Agent'
        }
    }

    def __init__(self, observatory: Optional[Observatory] = None, plugin_manager=None):
        self.observatory = observatory or Observatory()
        self._discovered_stars: dict[int, StarBody] = {}  # pid -> StarBody
        self._plugin_manager = plugin_manager
        self._plugin_signatures: dict = {}

    def load_plugin_signatures(self):
        """加载插件中的星体签名"""
        if not self._plugin_manager:
            return
        
        star_plugins = self._plugin_manager.get_star_plugins()
        for star_type, plugin in star_plugins.items():
            try:
                sig = plugin.get_star_signature()
                self._plugin_signatures[star_type] = sig
            except Exception:
                pass
    
    def get_all_signatures(self) -> dict:
        """获取所有星体签名（内置 + 配置文件 + 插件）"""
        signatures = dict(self.STAR_SIGNATURES)
        
        try:
            from star_core.config_service import get_config_service
            config_svc = get_config_service()
            config_svc.reload_if_changed()
            yaml_signatures = config_svc.get_star_signatures()
            for key, val in yaml_signatures.items():
                if key not in signatures:
                    signatures[key] = val
        except Exception:
            pass
        
        signatures.update(self._plugin_signatures)
        return signatures

    def scan_skies(self, force: bool = False) -> list[StarBody]:
        """
        扫描天际，发现所有闪耀的星
        
        Args:
            force: 是否强制重新扫描
            
        Returns:
            发现的星体列表
        """
        if not force and self._discovered_stars:
            # 返回缓存，验证进程仍然有效
            return self._validate_stars()
        
        # 刷新插件签名
        self.load_plugin_signatures()
        
        stars = []
        all_signatures = self.get_all_signatures()
        
        # 遍历所有星体类型（内置 + 插件）
        for star_type, sig in all_signatures.items():
            if not sig.get('process_names'):
                continue
                
            # 通过进程名查找
            processes = self.observatory.get_process_by_executable(sig['process_names'])
            
            for proc in processes:
                try:
                    if not proc.is_running():
                        continue
                        
                    # 查找所有匹配窗口
                    hwnds = self.observatory.find_all_windows_by_pid(proc.info['pid'])
                    
                    # 过滤匹配标题模式的窗口
                    import win32gui
                    matched_hwnds = []
                    matched_titles = []
                    for hwnd in hwnds:
                        try:
                            title = win32gui.GetWindowText(hwnd) or ""
                            if not sig.get('window_title_patterns') or any(
                                p.lower() in title.lower() for p in sig['window_title_patterns']
                            ):
                                matched_hwnds.append(hwnd)
                                matched_titles.append(title)
                        except Exception:
                            continue
                    
                    if not matched_hwnds:
                        continue
                    
                    # 构建 StarWindow 列表
                    star_windows = []
                    for hwnd in matched_hwnds:
                        try:
                            title = win32gui.GetWindowText(hwnd) or ""
                            class_name = win32gui.GetClassName(hwnd) or ""
                            rect = win32gui.GetWindowRect(hwnd)
                            is_visible = win32gui.IsWindowVisible(hwnd)
                            star_windows.append(StarWindow(
                                hwnd=hwnd,
                                title=title,
                                class_name=class_name,
                                rect=rect,
                                is_visible=bool(is_visible),
                            ))
                        except Exception:
                            continue
                    
                    main_hwnd = matched_hwnds[0]
                    main_title = matched_titles[0] if matched_titles else ""
                    
                    star = StarBody(
                        star_type=star_type,
                        pid=proc.info['pid'],
                        hwnd=main_hwnd,
                        title=main_title,
                        process=proc,
                        windows=star_windows,
                    )
                    stars.append(star)
                    self._discovered_stars[proc.info['pid']] = star
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        return stars

    def _validate_stars(self) -> list[StarBody]:
        """验证已发现星体的有效性"""
        valid_stars = []
        removed_pids = []
        
        for pid, star in self._discovered_stars.items():
            if self.observatory.is_process_running(pid):
                valid_stars.append(star)
            else:
                removed_pids.append(pid)
        
        # 清理无效星体
        for pid in removed_pids:
            del self._discovered_stars[pid]
        
        return valid_stars

    def get_star(self, pid: int) -> Optional[StarBody]:
        """通过 PID 获取星体"""
        return self._discovered_stars.get(pid)

    def get_star_by_type(self, star_type: str) -> list[StarBody]:
        """获取指定类型的所有星体"""
        return [
            star for star in self._discovered_stars.values()
            if star.star_type == star_type
        ]

    def get_idle_stars(self, star_type: Optional[str] = None) -> list[StarBody]:
        """
        获取空闲星体（未在处理任务的星）
        
        Args:
            star_type: 星体类型过滤，None 表示所有类型
            
        Returns:
            空闲星体列表
        """
        stars = self._discovered_stars.values()
        if star_type:
            stars = [s for s in stars if s.star_type == star_type]
        
        return [s for s in stars if not s.is_shining]

    def get_any_idle_star(self) -> Optional[StarBody]:
        """获取任意一个空闲星体"""
        idle_stars = self.get_idle_stars()
        return idle_stars[0] if idle_stars else None

    def get_shining_stars(self) -> list[StarBody]:
        """获取所有正在闪耀的星体"""
        return [s for s in self._discovered_stars.values() if s.is_shining]

    def register_callback(self, star: StarBody, callback: callable):
        """
        注册星体状态变化回调
        
        当星体开始闪耀或结束闪耀时通知
        """
        # TODO: 实现状态监控回调
        pass

    def refresh_star(self, pid: int) -> Optional[StarBody]:
        """
        刷新单个星体的信息（包括所有窗口）
        
        Args:
            pid: 进程 ID
            
        Returns:
            更新后的星体，未找到返回 None
        """
        if pid not in self._discovered_stars:
            return None
        
        star = self._discovered_stars[pid]
        
        try:
            if not self.observatory.is_process_running(pid):
                del self._discovered_stars[pid]
                return None
            
            # 获取签名中的标题模式
            sig = self.get_all_signatures().get(star.star_type, {})
            title_patterns = sig.get('window_title_patterns', [])
            
            # 刷新所有窗口
            star.refresh_windows(self.observatory, title_patterns)
            star.refresh_activity()
            return star
            
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            del self._discovered_stars[pid]
            return None

    def list_star_types(self) -> dict[str, dict]:
        """列出所有已知星体类型及其描述"""
        all_sigs = self.get_all_signatures()
        return {
            star_type: {
                'description': sig.get('description', ''),
                'process_names': sig.get('process_names', [])
            }
            for star_type, sig in all_sigs.items()
            if sig.get('process_names')
        }
