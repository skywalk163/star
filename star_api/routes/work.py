from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from star_core.trae_work_parser import TraeWorkParser, TraeWorkTask
from star_core.star_emissary import StarEmissary
from star_api import state
import time

router = APIRouter(prefix="/api/work", tags=["工作模式"])


# ===== 任务相关 =====

class TaskOutput(BaseModel):
    path: str
    name: str


class TaskResponse(BaseModel):
    task_id: str
    name: str
    project_name: str
    path: str
    script_files: List[str]
    output_files: List[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    status: str


def task_to_response(task: TraeWorkTask) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        name=task.name,
        project_name=task.project_name,
        path=task.path,
        script_files=task.script_files,
        output_files=[f if isinstance(f, str) else str(f) for f in task.output_files],
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
        status=task.status,
    )


@router.get("/tasks", response_model=List[TaskResponse])
async def list_tasks():
    """获取所有 Trae Work 任务"""
    tasks = TraeWorkParser.list_tasks()
    return [task_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """获取单个任务的详细信息"""
    task = TraeWorkParser.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 未找到")
    return task_to_response(task)


@router.get("/tasks/{task_id}/script/{script_name}")
async def get_task_script(task_id: str, script_name: str):
    """获取任务的脚本内容"""
    content = TraeWorkParser.get_script_content(task_id, script_name)
    if content is None:
        raise HTTPException(status_code=404, detail=f"脚本 {script_name} 未找到")
    return {"script_name": script_name, "content": content}


# ===== AI 相关 =====

class AIStatus(BaseModel):
    ai_id: str
    name: str
    type: str
    pid: Optional[int]
    status: str  # running, idle, busy
    uptime: Optional[str]
    memory_mb: Optional[float]


class AIListResponse(BaseModel):
    ais: List[AIStatus]
    total: int


def _get_emissary_by_id(ai_id: str) -> Optional[StarEmissary]:
    for e in state.emissaries.values():
        if str(e.star.pid) == ai_id or e.star.name == ai_id:
            return e
    return None


@router.get("/ai", response_model=AIListResponse)
async def list_ais():
    """获取所有可用的 AI Agent 列表"""
    ais = []
    
    # 从星使管理器获取在线 AI
    if hasattr(state, 'emissaries') and state.emissaries:
        for emissary in state.emissaries.values():
            status = "busy" if hasattr(emissary, '_busy') and emissary._busy else "idle"
            uptime = None
            if emissary.star.started_at:
                uptime_seconds = time.time() - emissary.star.started_at
                uptime = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"
            
            ais.append(AIStatus(
                ai_id=str(emissary.star.pid),
                name=emissary.star.name or f"Star-{emissary.star.pid}",
                type=emissary.star.type,
                pid=emissary.star.pid,
                status=status,
                uptime=uptime,
                memory_mb=None,
            ))
    
    return AIListResponse(ais=ais, total=len(ais))


@router.get("/ai/{ai_id}/status", response_model=AIStatus)
async def get_ai_status(ai_id: str):
    """获取指定 AI 的运行状态"""
    # 尝试从 emissary 获取
    emissary = _get_emissary_by_id(ai_id)
    if emissary:
        status = "busy" if hasattr(emissary, '_busy') and emissary._busy else "idle"
        uptime = None
        if emissary.star.started_at:
            uptime_seconds = time.time() - emissary.star.started_at
            uptime = f"{int(uptime_seconds // 3600)}h {int((uptime_seconds % 3600) // 60)}m"
        return AIStatus(
            ai_id=str(emissary.star.pid),
            name=emissary.star.name or f"Star-{emissary.star.pid}",
            type=emissary.star.type,
            pid=emissary.star.pid,
            status=status,
            uptime=uptime,
            memory_mb=None,
        )
    
    # 尝试从进程获取状态
    try:
        import psutil
        pid = int(ai_id)
        p = psutil.Process(pid)
        return AIStatus(
            ai_id=ai_id,
            name=f"Process-{pid}",
            type="unknown",
            pid=pid,
            status="running",
            uptime=None,
            memory_mb=p.memory_info().rss / 1024 / 1024,
        )
    except (ValueError, psutil.NoSuchProcess, psutil.AccessDenied):
        raise HTTPException(status_code=404, detail=f"AI {ai_id} 未找到或未运行")


class AskRequest(BaseModel):
    prompt: str
    adapter_name: str = "trae"
    task_id: Optional[str] = None  # 可选：指定任务
    timeout: int = 60


@router.post("/ai/{ai_id}/ask")
async def ask_ai(ai_id: str, req: AskRequest):
    """向指定 AI 发送指令"""
    emissary = _get_emissary_by_id(ai_id)
    if not emissary:
        raise HTTPException(status_code=404, detail=f"AI {ai_id} 未找到")
    
    try:
        result = await emissary.ask(
            prompt=req.prompt,
            adapter_name=req.adapter_name,
            timeout=req.timeout,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
