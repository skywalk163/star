import os
import re
import json
from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class TraeWorkTask:
    def __init__(self, task_id: str, path: str):
        self.task_id = task_id
        self.path = path
        self.name = ""
        self.project_name = ""
        self.script_files: List[str] = []
        self.output_files: List[str] = []
        self.created_at: Optional[datetime] = None
        self.updated_at: Optional[datetime] = None
        self.status = "unknown"
        self.parse()

    def parse(self):
        p = Path(self.path)
        if not p.exists():
            return

        self.created_at = datetime.fromtimestamp(p.stat().st_ctime)
        self.updated_at = datetime.fromtimestamp(p.stat().st_mtime)

        for item in p.iterdir():
            if item.is_file():
                if item.suffix in ('.js', '.json', '.py'):
                    self.script_files.append(item.name)
                    self._parse_script(item)
                elif item.suffix in ('.docx', '.md', '.txt', '.pdf', '.html'):
                    self.output_files.append(item.name)
            elif item.is_dir() and item.name != '.uploads':
                self._parse_subdir(item)

        if not self.name:
            self.name = f"任务 {self.task_id[:8]}"
            self._try_extract_from_outputs()

    def _parse_subdir(self, subdir: Path):
        for item in subdir.rglob('*'):
            if item.is_file():
                if item.suffix in ('.docx', '.md', '.txt', '.pdf', '.html'):
                    rel = item.relative_to(subdir.parent)
                    self.output_files.append(str(rel))
                    self._extract_name_from_output_path(item)

    def _parse_script(self, script_path: Path):
        try:
            content = script_path.read_text(encoding='utf-8', errors='ignore')
            self._extract_name_from_content(content)
            self._extract_output_files(content)
            self._extract_project_name(content)
        except Exception:
            pass

    def _extract_name_from_content(self, content: str):
        output_match = re.search(r'writeFileSync\(["\']([^"\']+?)["\']', content)
        if output_match:
            output_path = output_match.group(1)
            output_name = os.path.basename(output_path)
            output_name = output_name.replace('.docx', '').replace('.md', '').replace('.txt', '').replace('.json', '')
            if len(output_name) > 5 and len(output_name) < 100:
                self.name = output_name.strip()
                return

        patterns = [
            r'["\']title["\']\s*[:=]\s*["\']([^"\']+)["\']',
            r'["\']name["\']\s*[:=]\s*["\']([^"\']+)["\']',
            r'["\']taskName["\']\s*[:=]\s*["\']([^"\']+)["\']',
            r'title\s*[:=]\s*["\']([^"\']+)["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                name = match.group(1)
                if len(name) > 5 and len(name) < 150:
                    self.name = name.strip()
                    break

    def _extract_output_files(self, content: str):
        matches = re.findall(r'writeFileSync\(["\']([^"\']+?)["\']', content)
        for path in matches:
            if path not in self.output_files:
                self.output_files.append(os.path.basename(path))

    def _extract_project_name(self, content: str):
        patterns = [
            r'trae-work-projects[\\/]([^\\/]+?)[\\/]',
            r'work-mode-projects[\\/]([^\\/]+?)[\\/]',
        ]
        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                self.project_name = match.group(1)
                break

    def _extract_name_from_output_path(self, path: Path):
        name = path.stem
        if len(name) > 5 and len(name) < 100 and not self.name:
            self.name = name.strip()

    def _try_extract_from_outputs(self):
        for f in self.output_files:
            if isinstance(f, str) and f:
                name = os.path.basename(f).rsplit('.', 1)[0]
                if len(name) > 5 and len(name) < 100:
                    self.name = name.strip()
                    return

    def merge_from_work_dir(self, work_path: str):
        """合并 work 目录中的脚本文件"""
        for item in Path(work_path).iterdir():
            if item.is_file():
                if item.suffix in ('.js', '.json', '.py'):
                    if item.name not in self.script_files:
                        self.script_files.append(item.name)
                    self._parse_script(item)
        self.updated_at = datetime.fromtimestamp(Path(work_path).stat().st_mtime)

    def merge_from_project_subdir(self, project_subdir: str):
        """合并 project 子目录中的输出文件"""
        for item in Path(project_subdir).rglob('*'):
            if item.is_file():
                if item.suffix in ('.docx', '.md', '.txt', '.pdf', '.html'):
                    rel = item.relative_to(Path(project_subdir).parent)
                    rel_str = str(rel)
                    if rel_str not in self.output_files:
                        self.output_files.append(rel_str)
                    if not self.name:
                        self._extract_name_from_output_path(item)
        self.updated_at = datetime.fromtimestamp(Path(project_subdir).stat().st_mtime)

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "project_name": self.project_name,
            "path": self.path,
            "script_files": self.script_files,
            "output_files": self.output_files,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "status": self.status,
        }


class TraeWorkParser:
    WORK_DIRS = [
        os.path.join(os.path.expanduser('~'), '.trae-cn', 'work'),
        os.path.join(os.path.expanduser('~'), '.trae', 'work'),
    ]

    PROJECT_DATA_DIRS = [
        os.path.join(os.path.expanduser('~'), '.trae-cn', 'ModularData', 'ai-agent', 'work-mode-projects'),
        os.path.expandvars(r"%APPDATA%\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects"),
        os.path.expandvars(r"%APPDATA%\Trae\ModularData\ai-agent\work-mode-projects"),
    ]

    @classmethod
    def find_work_dir(cls) -> Optional[str]:
        for dir_path in cls.WORK_DIRS:
            if os.path.isdir(dir_path):
                return dir_path
        return None

    @classmethod
    def find_project_data_dir(cls) -> Optional[str]:
        for dir_path in cls.PROJECT_DATA_DIRS:
            if os.path.isdir(dir_path):
                return dir_path
        return None

    @classmethod
    def _normalize_task_id(cls, task_id: str) -> str:
        """标准化任务ID，用于匹配相似任务"""
        # 尝试用前20字符匹配（忽略末尾的差异）
        if len(task_id) >= 20:
            return task_id[:20]
        return task_id

    @classmethod
    def list_tasks(cls) -> List[TraeWorkTask]:
        tasks_map: Dict[str, TraeWorkTask] = {}
        proj_dir = cls.find_project_data_dir()

        # 1. 先扫描 project-data 目录（包含输出文件）
        if proj_dir:
            for entry in os.listdir(proj_dir):
                entry_path = os.path.join(proj_dir, entry)
                if os.path.isdir(entry_path):
                    key = cls._normalize_task_id(entry)
                    if key not in tasks_map:
                        tasks_map[key] = TraeWorkTask(entry, entry_path)
                    else:
                        tasks_map[key].merge_from_project_subdir(entry_path)

        # 2. 再扫描 work 目录（包含脚本），合并输出
        work_dir = cls.find_work_dir()
        if work_dir:
            for entry in os.listdir(work_dir):
                entry_path = os.path.join(work_dir, entry)
                if os.path.isdir(entry_path):
                    key = cls._normalize_task_id(entry)
                    if key in tasks_map:
                        # 合并：保留 project-data 的名称，合并 work 的脚本
                        tasks_map[key].merge_from_work_dir(entry_path)
                    else:
                        tasks_map[key] = TraeWorkTask(entry, entry_path)

        tasks = list(tasks_map.values())
        tasks.sort(key=lambda t: t.updated_at or datetime.min, reverse=True)
        return tasks

    @classmethod
    def get_task(cls, task_id: str) -> Optional[TraeWorkTask]:
        # 先从 work 目录找
        work_dir = cls.find_work_dir()
        if work_dir:
            task_path = os.path.join(work_dir, task_id)
            if os.path.isdir(task_path):
                return TraeWorkTask(task_id, task_path)

        # 再从 project-data 目录找
        project_dir = cls.find_project_data_dir()
        if project_dir:
            task_path = os.path.join(project_dir, task_id)
            if os.path.isdir(task_path):
                return TraeWorkTask(task_id, task_path)
        return None

    @classmethod
    def get_script_content(cls, task_id: str, script_name: str) -> Optional[str]:
        task = cls.get_task(task_id)
        if not task:
            return None

        script_path = os.path.join(task.path, script_name)
        if os.path.isfile(script_path):
            try:
                return open(script_path, 'r', encoding='utf-8').read()
            except Exception:
                return None
        return None

    @classmethod
    def get_project_tasks(cls, project_name: str) -> List[TraeWorkTask]:
        all_tasks = cls.list_tasks()
        return [t for t in all_tasks if t.project_name == project_name]
