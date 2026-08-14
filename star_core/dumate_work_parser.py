"""
DuMate 工作解析器（DuMateWorkParser）- 读取 DuMate 的项目和任务数据

DuMate（百度文心快码 Comate）将任务数据存储在以下位置：
  - ~/.comate/plan/ - 项目计划文件
  - ~/.comate-engine/store/ - 引擎存储（agents、blobs 等）
  - ~/.comate-engine/log/ - 内核日志

本解析器模仿 TraeWorkParser 的设计，提供统一的 DuMate 任务发现接口。
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DuMateTask:
    """DuMate 任务 - 对应一次 AI Agent 交互/任务"""

    def __init__(self, task_id: str, source: str = "unknown"):
        self.task_id = task_id
        self.source = source  # agent_output / kernel_log / plan_file
        self.name = ""
        self.project_name = ""
        self.agent_name = "Comate"
        self.content = ""
        self.status = "unknown"  # active / completed / error
        self.created_at: Optional[datetime] = None
        self.updated_at: Optional[datetime] = None
        self.file_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name or f"任务 {self.task_id[:8]}",
            "project_name": self.project_name,
            "agent_name": self.agent_name,
            "source": self.source,
            "status": self.status,
            "content_preview": self.content[:500] if self.content else "",
            "content_length": len(self.content),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DuMateWorkParser:
    """DuMate 工作解析器

    从 DuMate 的引擎存储和日志中提取任务信息。
    """

    #: DuMate 引擎数据目录
    ENGINE_DIR = os.path.expanduser("~/.comate-engine")
    #: DuMate 配置目录
    CONFIG_DIR = os.path.expanduser("~/.comate")

    #: Agent 输出目录
    AGENT_OUTPUT_DIR = os.path.join(ENGINE_DIR, "store", "agents")
    #: 内核日志目录
    KERNEL_LOG_DIR = os.path.join(ENGINE_DIR, "log")
    #: 计划文件目录
    PLANS_DIR = os.path.join(CONFIG_DIR, "plans")

    @classmethod
    def find_engine_dir(cls) -> Optional[str]:
        """查找 DuMate 引擎目录"""
        if os.path.isdir(cls.ENGINE_DIR):
            return cls.ENGINE_DIR
        return None

    @classmethod
    def list_tasks(cls) -> list[DuMateTask]:
        """列出所有 DuMate 任务

        从多个来源合并任务数据：
        1. Agent 输出文件（store/agents/*.output）
        2. 计划文件（plans/*.plan.md）

        Returns:
            任务列表，按更新时间降序排列。
        """
        tasks_map: dict[str, DuMateTask] = {}

        # 1. 从 Agent 输出文件获取任务
        agent_dir = Path(cls.AGENT_OUTPUT_DIR)
        if agent_dir.is_dir():
            for f in sorted(agent_dir.glob("*.output"),
                            key=os.path.getmtime, reverse=True):
                m = re.match(r"(\w+)_(\d+)\.output", f.name)
                if m:
                    agent_name = m.group(1)
                    task_id = m.group(2)
                    key = f"agent_{task_id}"

                    if key not in tasks_map:
                        task = DuMateTask(task_id, source="agent_output")
                        task.agent_name = agent_name
                        task.file_path = str(f)
                        task.updated_at = datetime.fromtimestamp(os.path.getmtime(f))
                        task.created_at = datetime.fromtimestamp(os.path.getctime(f))

                        # 读取内容
                        try:
                            content = f.read_text(encoding="utf-8", errors="ignore")
                            task.content = content
                            task.name = cls._extract_name(content, f.name)
                        except Exception:
                            pass

                        # 判断状态
                        age = (datetime.now() - task.updated_at).total_seconds()
                        task.status = "active" if age < 300 else "completed"

                        tasks_map[key] = task

        # 2. 从计划文件获取任务
        plans_dir = Path(cls.PLANS_DIR)
        if plans_dir.is_dir():
            for f in sorted(plans_dir.glob("*.plan.md"),
                            key=os.path.getmtime, reverse=True):
                task_id = f.stem.replace(".plan", "")
                key = f"plan_{task_id}"

                if key not in tasks_map:
                    task = DuMateTask(task_id, source="plan_file")
                    task.file_path = str(f)
                    task.updated_at = datetime.fromtimestamp(os.path.getmtime(f))
                    task.created_at = datetime.fromtimestamp(os.path.getctime(f))

                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        task.content = content
                        task.name = cls._extract_name_from_plan(content, f.stem)
                    except Exception:
                        pass

                    tasks_map[key] = task

        # 3. 从内核日志提取任务
        log_dir = Path(cls.KERNEL_LOG_DIR)
        if log_dir.is_dir():
            log_files = sorted(log_dir.glob("kernel-*.log"),
                               key=os.path.getmtime, reverse=True)
            if log_files:
                latest_log = log_files[0]
                try:
                    with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            m = re.search(r'taskId=(\d+)', line)
                            if m:
                                task_id = m.group(1)
                                key = f"log_{task_id}"
                                if key not in tasks_map:
                                    task = DuMateTask(task_id, source="kernel_log")
                                    task.updated_at = datetime.fromtimestamp(
                                        os.path.getmtime(latest_log))
                                    task.status = "active"
                                    tasks_map[key] = task
                except Exception:
                    pass

        tasks = list(tasks_map.values())
        tasks.sort(key=lambda t: t.updated_at or datetime.min, reverse=True)
        return tasks

    @classmethod
    def get_task(cls, task_id: str) -> Optional[DuMateTask]:
        """获取指定任务的详细信息"""
        for task in cls.list_tasks():
            if task.task_id == task_id:
                return task
        return None

    @classmethod
    def get_active_tasks(cls) -> list[DuMateTask]:
        """获取活跃任务（最近 5 分钟内有更新）"""
        tasks = cls.list_tasks()
        now = datetime.now()
        return [t for t in tasks if t.status == "active"
                and t.updated_at and (now - t.updated_at).total_seconds() < 300]

    @staticmethod
    def _extract_name(content: str, filename: str) -> str:
        """从 Agent 输出内容中提取名称"""
        # 尝试提取任务名称
        patterns = [
            r'"taskName"\s*:\s*"([^"]+)"',
            r'"name"\s*:\s*"([^"]+)"',
            r'"title"\s*:\s*"([^"]+)"',
            r'任务名称[：:]\s*(.+?)[\n\r]',
            r'项目名称[：:]\s*(.+?)[\n\r]',
        ]
        for pattern in patterns:
            m = re.search(pattern, content)
            if m and len(m.group(1)) > 2:
                return m.group(1).strip()

        # 从文件名提取
        m = re.match(r"\w+_(\d+)\.output", filename)
        if m:
            return f"Agent 任务 {m.group(1)[:8]}"

        return filename

    @staticmethod
    def _extract_name_from_plan(content: str, stem: str) -> str:
        """从计划文件内容中提取名称"""
        # 尝试从 Markdown 标题提取
        m = re.search(r'^#\s+(.+?)$', content, re.MULTILINE)
        if m and len(m.group(1)) > 2:
            return m.group(1).strip()

        # 尝试从文件名提取
        # 格式: M23_远程发布实现_d7031ffc.plan.md
        parts = stem.split("_")
        if len(parts) >= 2:
            # 去掉第一个部分（如 M23）和最后一个部分（hash）
            name_parts = parts[1:-1] if len(parts) > 2 else parts[1:]
            if name_parts:
                return "_".join(name_parts)

        return stem

    @classmethod
    def get_project_tasks(cls, project_name: str) -> list[DuMateTask]:
        """获取指定项目的所有任务"""
        all_tasks = cls.list_tasks()
        return [t for t in all_tasks if t.project_name == project_name]


def discover_dumate_workspaces() -> dict:
    """发现 DuMate 工作区信息

    Returns:
        工作区信息字典
    """
    info = {
        "engine_dir": DuMateWorkParser.find_engine_dir(),
        "agent_output_dir": DuMateWorkParser.AGENT_OUTPUT_DIR,
        "plans_dir": DuMateWorkParser.PLANS_DIR,
        "has_agent_outputs": os.path.isdir(DuMateWorkParser.AGENT_OUTPUT_DIR),
        "has_plans": os.path.isdir(DuMateWorkParser.PLANS_DIR),
        "has_kernel_logs": os.path.isdir(DuMateWorkParser.KERNEL_LOG_DIR),
    }

    # 统计任务数
    if info["has_agent_outputs"]:
        agent_dir = Path(DuMateWorkParser.AGENT_OUTPUT_DIR)
        info["agent_output_count"] = len(list(agent_dir.glob("*.output")))
    else:
        info["agent_output_count"] = 0

    if info["has_plans"]:
        plans_dir = Path(DuMateWorkParser.PLANS_DIR)
        info["plan_count"] = len(list(plans_dir.glob("*.plan.md")))
    else:
        info["plan_count"] = 0

    return info