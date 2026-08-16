"""
星语者（LogReader）- 日志读取策略

直接从 AI Agent 的日志文件中读取通信信息，
比 OCR 快多个数量级（毫秒 vs 数秒）。
当日志不可用时自动回退到 OCR。
"""

import os
import re
import time
import threading
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from loguru import logger


# ==================== 预设日志路径模式 ====================

LOG_PATTERNS = {
    "trae": {
        "name": "Trae Solo",
        "paths": [
            os.path.expandvars(r"%APPDATA%\TRAE SOLO CN\logs\**\*.log"),
            os.path.expandvars(r"%APPDATA%\Trae CN\logs\**\*.log"),
            os.path.expandvars(r"%APPDATA%\Trae\logs\**\*.log"),
        ],
        "install_patterns": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Trae*\debug.log"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Trae*\logs\*.log"),
            os.path.expandvars(r"G:\Programs\TRAE SOLO CN\**\*.log"),
        ],
        "ai_response_patterns": [
            r'\[lite\]\[send_message\].*query.*content.*?([^\n]{20,})',
            r'"content"\s*:\s*"((?:[^"\\]|\\.){20,})"',
        ],
        "content_keywords": [
            r"AI.*response",
            r"assistant.*:",
            r"model.*output",
            r"chat.*completion",
            r"message.*content",
            r"lite.*send_message",
        ],
    },
    "cursor": {
        "name": "Cursor",
        "paths": [
            os.path.expandvars(r"%APPDATA%\Cursor\logs\*.log"),
            os.path.expandvars(r"%APPDATA%\Trae\logs\*.log"),
        ],
        "content_keywords": [
            r"AI.*response",
            r"completion",
            r"assistant.*message",
            r"chat.*reply",
            r"model.*response",
            r"result.*text",
        ],
    },
    "claude": {
        "name": "Claude Desktop",
        "paths": [
            os.path.expandvars(r"%APPDATA%\Claude\logs\*"),
        ],
        "content_keywords": [
            r"response",
            r"completion",
            r"assistant",
        ],
    },
    "windsurf": {
        "name": "Windsurf",
        "paths": [
            os.path.expandvars(r"%APPDATA%\Windsurf\logs\*.log"),
        ],
        "content_keywords": [
            r"AI.*response",
            r"completion",
            r"chat.*message",
            r"model.*output",
        ],
    },
}

# 通用 AI 日志关键词（跨所有类型）
_GENERIC_AI_PATTERNS = [
    re.compile(r'"content"\s*:\s*"([^"]{20,})"', re.DOTALL),
    re.compile(r'"text"\s*:\s*"([^"]{20,})"', re.DOTALL),
    re.compile(r'"message"\s*:\s*"([^"]{20,})"', re.DOTALL),
    re.compile(r'\]\s*:\s*"([^"]{50,})"', re.DOTALL),
    re.compile(r'助理[：:]\s*(.+?)(?:\n|$)', re.DOTALL),
    re.compile(r'助手[：:]\s*(.+?)(?:\n|$)', re.DOTALL),
    re.compile(r'AI[：:]\s*(.+?)(?:\n|$)', re.DOTALL),
    re.compile(r'(?:模型|model)\s*(?:回复|回答|响应)[：:]\s*(.+?)(?:\n\n|\Z)', re.DOTALL),
]


@dataclass
class LogEntry:
    """一条日志记录"""
    file_path: str
    line_number: int
    content: str
    timestamp: Optional[float] = None
    is_ai_response: bool = False
    response_text: Optional[str] = None


@dataclass
class LogReadResult:
    """日志读取结果"""
    entries: list[LogEntry] = field(default_factory=list)
    ai_responses: list[str] = field(default_factory=list)
    latest_text: Optional[str] = None
    source_files: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class LogReader:
    """
    星语者 - 日志读取器
    
    功能：
    - 根据星体类型自动发现日志文件
    - 增量读取（跟踪文件位置）
    - 解析 AI 响应内容
    - 实时监听日志变化
    """
    
    def __init__(self):
        self._file_positions: dict[str, int] = {}  # 文件路径 -> 已读位置
        self._watchers: dict[str, threading.Thread] = {}
        self._watcher_callbacks: dict[str, Callable] = {}
        self._stop_events: dict[str, threading.Event] = {}
    
    # ==================== 文件发现 ====================
    
    def find_logs(self, star_type: str = None, process_name: str = None, pid: int = None) -> list[str]:
        """
        查找 AI Agent 的日志文件
        
        Args:
            star_type: 星体类型（trae, cursor, claude, windsurf 等）
            process_name: 进程名（如 TRAE SOLO CN）
            pid: 进程 ID
            
        Returns:
            日志文件路径列表（按最后修改时间排序）
        """
        found = set()
        
        # 1. 按星体类型搜索
        if star_type and star_type.lower() in LOG_PATTERNS:
            patterns = LOG_PATTERNS[star_type.lower()]
            for path_pattern in patterns.get("paths", []):
                self._expand_and_add(path_pattern, found)
            for path_pattern in patterns.get("install_patterns", []):
                self._expand_and_add(path_pattern, found)
        
        # 2. 按进程名推测（如果进程名包含 Trae/Cursor/Claude/Windsurf）
        if process_name:
            for app_key, app_cfg in LOG_PATTERNS.items():
                if app_key in process_name.lower() or app_cfg["name"].lower().replace(" ", "") in process_name.lower().replace(" ", ""):
                    for path_pattern in app_cfg.get("paths", []):
                        self._expand_and_add(path_pattern, found)
                    for path_pattern in app_cfg.get("install_patterns", []):
                        self._expand_and_add(path_pattern, found)
        
        # 3. 按 PID 获取进程路径
        if pid:
            try:
                import psutil
                proc = psutil.Process(pid)
                proc_exe = proc.exe()
                proc_name = proc.name()
                # 从进程路径找日志
                proc_dir = os.path.dirname(proc_exe)
                self._expand_and_add(os.path.join(proc_dir, "*.log"), found)
                self._expand_and_add(os.path.join(proc_dir, "logs", "*.log"), found)
                self._expand_and_add(os.path.join(proc_dir, "..", "logs", "*.log"), found)
                
                # 也尝试从进程名推测
                for app_key, app_cfg in LOG_PATTERNS.items():
                    if app_key in proc_name.lower() or app_cfg["name"].lower().replace(" ", "") in proc_name.lower().replace(" ", ""):
                        for path_pattern in app_cfg.get("paths", []):
                            self._expand_and_add(path_pattern, found)
                        for path_pattern in app_cfg.get("install_patterns", []):
                            self._expand_and_add(path_pattern, found)
            except ImportError:
                pass
            except Exception:
                pass
        
        # 排序：按修改时间倒序
        result = sorted(found, key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0, reverse=True)
        return result
    
    def find_logs_for_star(self, star_body) -> list[str]:
        """
        为星体查找日志文件
        
        Args:
            star_body: StarBody 对象（包含 pid, star_type, title 等）
            
        Returns:
            日志文件路径列表
        """
        return self.find_logs(
            star_type=getattr(star_body, 'star_type', None),
            process_name=getattr(star_body, 'title', None),
            pid=getattr(star_body, 'pid', None),
        )
    
    def _expand_and_add(self, pattern: str, found_set: set):
        """展开文件通配符模式并加入到集合中（支持递归搜索目录）"""
        expanded = os.path.expandvars(pattern)
        
        if "*" in expanded:
            if "**" in expanded:
                # 递归 glob：找到 base 路径，用 rglob 匹配
                idx = expanded.index("**")
                base_path = expanded[:idx]
                glob_part = expanded[idx + 2:].lstrip("\\/")
                for p in Path(base_path).rglob(glob_part):
                    if p.is_file():
                        found_set.add(str(p))
            else:
                matches = [str(p) for p in Path(expanded).parent.glob(Path(expanded).name) if p.is_file()]
                for m in matches:
                    found_set.add(m)
            return
        
        if os.path.isfile(expanded):
            found_set.add(expanded)
        elif os.path.isdir(expanded):
            # 递归搜索目录下的所有日志文件
            for root, _, files in os.walk(expanded):
                for f in files:
                    if f.endswith((".log", ".txt", ".json", ".out")):
                        found_set.add(os.path.join(root, f))
    
    # ==================== 读取 ====================
    
    def read_recent(self, 
                    file_paths: list[str], 
                    max_lines: int = 100,
                    max_files: int = 3) -> LogReadResult:
        """
        读取最近的日志内容
        
        Args:
            file_paths: 日志文件路径列表
            max_lines: 每个文件最多读取的行数
            max_files: 最多读取的文件数
            
        Returns:
            LogReadResult 包含解析后的日志内容
        """
        start = time.perf_counter()
        result = LogReadResult()
        
        if not file_paths:
            result.error = "未找到日志文件"
            result.elapsed_ms = (time.perf_counter() - start) * 1000
            return result
        
        # 只读前 N 个文件
        for file_path in file_paths[:max_files]:
            if not os.path.exists(file_path):
                continue
            
            result.source_files.append(file_path)
            
            try:
                file_size = os.path.getsize(file_path)
                if file_size == 0:
                    continue
                
                # 大文件只读末尾 50KB：文本模式不支持 end-relative seek，
                # 故以二进制定位后再解码。
                if file_size > 1024 * 1024:  # > 1MB
                    with open(file_path, "rb") as fb:
                        fb.seek(-min(file_size, 50 * 1024), os.SEEK_END)
                        raw = fb.read()
                    text = raw.decode("utf-8", errors="replace")
                    raw_lines = text.splitlines(keepends=True)
                    if raw_lines:
                        raw_lines.pop(0)  # 丢弃可能被截断的首行
                else:
                    with open(file_path, encoding="utf-8", errors="replace") as f:
                        raw_lines = f.readlines()

                lines = raw_lines[-max_lines:] if max_lines else raw_lines

                # 解析每一行
                for i, line in enumerate(lines):
                    entry = LogEntry(
                        file_path=file_path,
                        line_number=i + 1,
                        content=line.rstrip("\n\r"),
                    )
                    result.entries.append(entry)
                    
                    # 检测是否包含 AI 响应
                    ai_text = self._extract_ai_response(line)
                    if ai_text:
                        entry.is_ai_response = True
                        entry.response_text = ai_text
                        result.ai_responses.append(ai_text)
                        result.latest_text = ai_text
                
            except Exception as e:
                logger.warning(f"读取日志文件失败 {file_path}: {e}")
        
        # 如果没有从单行找到，尝试跨行解析
        if not result.ai_responses and result.entries:
            full_text = "\n".join(e.content for e in result.entries)
            extracted = self._extract_ai_response_block(full_text)
            if extracted:
                result.ai_responses.append(extracted)
                result.latest_text = extracted
        
        result.elapsed_ms = (time.perf_counter() - start) * 1000
        return result
    
    def read_recent_for_star(self, star_body, max_lines: int = 100) -> LogReadResult:
        """为星体读取最近的日志"""
        files = self.find_logs_for_star(star_body)
        return self.read_recent(files, max_lines=max_lines)
    
    # ==================== 增量读取（类似 tail -f） ====================
    
    def read_new(self, file_path: str) -> list[str]:
        """
        增量读取 - 只读上次调用后新增的内容
        
        Args:
            file_path: 日志文件路径
            
        Returns:
            新增的行列表
        """
        if not os.path.exists(file_path):
            return []
        
        last_pos = self._file_positions.get(file_path, 0)
        file_size = os.path.getsize(file_path)
        
        if file_size < last_pos:
            # 文件被截断/轮转了，从头开始
            last_pos = 0
        
        if file_size == last_pos:
            return []  # 没有新内容
        
        new_lines = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(last_pos)
                for line in f:
                    new_lines.append(line.rstrip("\n\r"))
                self._file_positions[file_path] = f.tell()
        except Exception as e:
            logger.warning(f"增量读取日志失败 {file_path}: {e}")
        
        return new_lines
    
    # ==================== 实时监听 ====================
    
    def start_watching(self, file_path: str, callback: Callable[[str], None], interval: float = 0.5):
        """
        实时监听日志文件变化
        
        Args:
            file_path: 要监听的日志文件路径
            callback: 新内容回调函数（接收新文本行）
            interval: 轮询间隔（秒）
        """
        if file_path in self._watchers and self._watchers[file_path].is_alive():
            logger.warning(f"已在监听 {file_path}")
            return
        
        stop_event = threading.Event()
        self._stop_events[file_path] = stop_event
        
        def _watch():
            # 先定位到文件末尾
            if os.path.exists(file_path):
                self._file_positions[file_path] = os.path.getsize(file_path)
            
            while not stop_event.is_set():
                try:
                    new_lines = self.read_new(file_path)
                    for line in new_lines:
                        ai_text = self._extract_ai_response(line)
                        if ai_text:
                            callback(ai_text)
                        else:
                            callback(line)
                except Exception as e:
                    logger.debug(f"日志监听异常 {file_path}: {e}")
                stop_event.wait(interval)
        
        thread = threading.Thread(target=_watch, name=f"log-watcher-{Path(file_path).name}", daemon=True)
        thread.start()
        self._watchers[file_path] = thread
        logger.info(f"📡 开始监听日志: {file_path}")
    
    def stop_watching(self, file_path: str):
        """停止监听日志文件"""
        if file_path in self._stop_events:
            self._stop_events[file_path].set()
        if file_path in self._watchers:
            self._watchers[file_path].join(timeout=2)
            del self._watchers[file_path]
        if file_path in self._stop_events:
            del self._stop_events[file_path]
        logger.info(f"📡 停止监听日志: {file_path}")
    
    def stop_all_watching(self):
        """停止所有监听"""
        for file_path in list(self._stop_events.keys()):
            self.stop_watching(file_path)
    
    # ==================== AI 响应解析 ====================
    
    @staticmethod
    def _extract_ai_response(line: str) -> Optional[str]:
        """从单行日志中提取 AI 响应内容"""
        if not line or len(line) < 10:
            return None
        
        for pattern in _GENERIC_AI_PATTERNS:
            m = pattern.search(line)
            if m:
                text = m.group(1).strip()
                if len(text) > 10:
                    return text
        
        return None
    
    @staticmethod
    def _extract_ai_response_block(text: str) -> Optional[str]:
        """从多行文本中提取 AI 响应内容"""
        # 尝试匹配 JSON 格式的 content 字段
        m = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
        if m:
            content = m.group(1)
            if len(content) > 20:
                return content
        
        # 尝试匹配最后的助手回复
        for pattern in [r'(?:助理|助手|AI|模型)[：:]\s*(.+?)(?:\n\n|\Z)', 
                        r'```[\s\S]*?```']:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                content = m.group(0) if pattern.startswith('```') else m.group(1)
                if len(content) > 10:
                    return content
        
        return None
    
    @staticmethod
    def has_ai_keywords(text: str) -> bool:
        """检查文本是否包含 AI 相关关键词"""
        keywords = [
            "response", "completion", "assistant", "message",
            "content", "output", "result", "reply",
            "chat", "model", "ai", "llm",
        ]
        text_lower = text.lower()
        return any(k in text_lower for k in keywords)
    
    # ==================== 元信息 ====================
    
    @staticmethod
    def get_supported_types() -> list[dict]:
        """获取支持的星体类型和日志路径列表"""
        result = []
        for key, cfg in LOG_PATTERNS.items():
            paths = []
            for pattern in cfg.get("paths", []):
                expanded = os.path.expandvars(pattern)
                if "**" in expanded:
                    idx = expanded.index("**")
                    base_path = expanded[:idx]
                    glob_part = expanded[idx + 2:].lstrip("\\/")
                    matches = [str(p) for p in Path(base_path).rglob(glob_part)]
                elif "*" in expanded:
                    matches = [str(p) for p in Path(expanded).parent.glob(Path(expanded).name)]
                elif os.path.exists(expanded):
                    matches = [expanded]
                else:
                    matches = []
                paths.extend(matches)
            
            result.append({
                "type": key,
                "name": cfg["name"],
                "log_paths": cfg["paths"],
                "found_files": paths[:5],
                "has_logs": len(paths) > 0,
            })
        return result


# ==================== 单例 ====================

_default_reader = None


def get_reader() -> LogReader:
    """获取全局 LogReader 实例"""
    global _default_reader
    if _default_reader is None:
        _default_reader = LogReader()
    return _default_reader