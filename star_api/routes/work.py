from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import List, Optional, Dict
from star_core.trae_work_parser import TraeWorkParser, TraeWorkTask
from star_core.ai_adapter import get_adapter_registry

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


def _runtime_status(adapter) -> str:
    """把适配器的运行态收敛成 AIStatus.status 的取值。

    注册表可能仍记着 connected，但适配器实际已掉线（进程被关、调试端口失效）。
    这种情况按 offline 记——否则会让调用方对着一个死适配器发任务。
    """
    if adapter is None or not adapter.connected:
        return "offline"
    try:
        runtime = adapter.get_status()
    except Exception:
        # 单个适配器探测失败不该影响整表，按离线处理
        return "offline"
    if runtime == "offline":
        return "offline"
    if runtime == "generating":
        return "busy"
    return "idle"


def _to_ai_status(info, adapter) -> AIStatus:
    """AIAdapterInfo → AIStatus。

    pid / uptime / memory_mb 适配器层面没有对应概念，留 None；
    字段保留是为了不破坏本接口既有的响应结构。
    """
    return AIStatus(
        ai_id=info.ai_id,
        name=info.ai_name or info.ai_id,
        type=info.ai_id,
        pid=None,
        status=_runtime_status(adapter),
        uptime=None,
        memory_mb=None,
    )


@router.get("/ai", response_model=AIListResponse)
async def list_ais():
    """获取所有可用的 AI Agent 列表

    数据源是 AIAdapterRegistry —— 与 /api/dumate/adapters 同一个真相。
    历史实现读 state.emissaries，而该属性全代码库从未被赋值，导致这里恒返回空表。
    """
    registry = get_adapter_registry()

    def _snapshot() -> List[AIStatus]:
        return [
            _to_ai_status(info, registry.get(info.ai_id))
            for info in registry.list_adapters()
        ]

    ais = await run_in_threadpool(_snapshot)
    return AIListResponse(ais=ais, total=len(ais))


@router.get("/ai/{ai_id}/status", response_model=AIStatus)
async def get_ai_status(ai_id: str):
    """获取指定 AI 的运行状态"""
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    def _snapshot() -> AIStatus:
        return _to_ai_status(adapter.get_info(), adapter)

    return await run_in_threadpool(_snapshot)


class AskRequest(BaseModel):
    prompt: str
    #: 已忽略：ai_id 本身就定位到具体适配器。字段保留仅为不破坏旧调用方。
    adapter_name: str = "trae"
    task_id: Optional[str] = None  # 可选：指定任务
    timeout: int = 60


@router.post("/ai/{ai_id}/ask")
async def ask_ai(ai_id: str, req: AskRequest):
    """向指定 AI 发送指令

    走适配器的通用任务接口，与 POST /api/dumate/adapters/{ai_id}/tasks 同一条实现。
    历史实现 await 了同步的 StarEmissary.ask 并多传 adapter_name，任何调用必抛 TypeError。
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if adapter is None:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")
    if not adapter.connected:
        raise HTTPException(status_code=503, detail=f"AI 适配器 {ai_id} 未连接")

    result = await run_in_threadpool(adapter.create_task, prompt=req.prompt)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("message", "发送失败"))

    return {
        "success": True,
        "ai_id": ai_id,
        "conversation_id": result.get("conversation_id", ""),
        "message": result.get("message", ""),
    }

