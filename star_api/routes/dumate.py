"""
搭子路由（DuMate Routes）- 连接群星与 DuMate 任务管理

提供 RESTful API 接口，让群星系统可以像在 PC 机前一样
操控 DuMate。支持任务类型、工作目录、实时流式输出。

使用逆向分析得到的 COMATE_AGENT_* 协议通过命名管道通讯。
"""

import asyncio
import json
import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from star_core.dumate_bridge import (
    DuMateBridge,
    TASK_TYPE_AGENTS,
    TASK_TYPE_STRATEGIES,
    discover_dumate,
)
from star_core.dumate_work_parser import DuMateWorkParser, DuMateTask
from star_core.ai_adapter import get_adapter_registry, get_adapter

#: 各适配器连接/重启失败时的排障指引（按 ai_id）。没有条目的适配器用通用文案。
_CONNECT_HINTS = {
    "trae_work": (
        "Star 已自动把 remote-debugging-port 写入 ~/.trae-cn/argv.json 并以零参数"
        "启动 Trae，但 CDP 端口仍不可用。常见原因：① Trae 未安装；② 已有 Trae 实例"
        "占用单实例锁，请先彻底关闭 Trae 再点“连接”；③ Trae 启动较慢，可稍后重试"
        "或用“重启并连接”按钮强制重启。"
    ),
    "dumate_app": (
        "DuMate 是单实例应用且不读 argv.json，只能命令行直传调试端口。"
        "若 DuMate 已在运行但没带调试端口，“连接”不会去打断它——请点“重启并连接”，"
        "Star 会关闭现有 DuMate 再以调试端口重启。其它可能原因：① DuMate 未安装；"
        "② 启动较慢，可稍后重试。"
    ),
}

#: 重启失败时的排障指引（按 ai_id）
_RESTART_HINTS = {
    "trae_work": (
        "Star 已关闭现有 Trae、把 remote-debugging-port 写入 argv.json 并以零参数"
        "重启，但 CDP 端口仍不可用。常见原因：① Trae 未正确安装；② 重启后窗口/端口"
        "尚未就绪（Trae 启动较慢，可稍后重试连接）；③ 本机有其它机制阻止 CDP 端口绑定。"
    ),
    "dumate_app": (
        "Star 已关闭现有 DuMate 并带调试端口重启，但 CDP 端口仍不可用。常见原因："
        "① 未找到 DuMate.exe；② 重启后窗口/端口尚未就绪，可稍后重试连接；"
        "③ 本机有其它机制阻止 CDP 端口绑定。"
    ),
}


def _adapter_port(adapter) -> Optional[int]:
    """取适配器的调试端口（CDP 型适配器有 ``port`` 属性）。"""
    port = getattr(adapter, "port", None)
    return port if isinstance(port, int) else None


def _can_restart(adapter) -> bool:
    """该适配器是否支持"带调试端口重启"（会终止并重新拉起目标进程）。"""
    return callable(getattr(adapter, "restart_with_cdp", None))

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dumate", tags=["搭子桥"])


def _get_bridge() -> Optional[DuMateBridge]:
    """获取 DuMate 适配器（通过注册表）

    优先从 AIAdapterRegistry 获取已注册的 DuMateAdapter，
    如果没有则创建新的实例并注册。
    """
    # 先从注册表获取
    adapter = get_adapter("dumate")
    if adapter and isinstance(adapter, DuMateBridge) and adapter.connected:
        return adapter

    # 注册表无可用实例，创建新的
    b = DuMateBridge()
    if b.port:
        b.connect()
    return b if b.connected else None


# ==================== 数据模型 ====================


class DuMateTaskResponse(BaseModel):
    task_id: str
    name: str
    project_name: str
    agent_name: str
    source: str
    status: str
    content_preview: str
    content_length: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DuMateConversationResponse(BaseModel):
    conversation_id: str
    title: str
    status: str
    workspace_id: str
    workspace_name: str


class DuMateDiscoverResponse(BaseModel):
    found: bool
    kernel_online: bool
    port: Optional[int] = None
    pipe_path: Optional[str] = None
    agent_output_dir: Optional[str] = None
    kernel_log_dir: Optional[str] = None
    agent_output_count: int = 0
    plan_count: int = 0
    workspaces: list = []


class DuMateStatusResponse(BaseModel):
    status: str  # idle / generating / unknown / offline
    kernel_online: bool
    port: Optional[int] = None


class CreateTaskRequest(BaseModel):
    prompt: str
    agent_name: str = "Comate"
    workspace_id: str = ""
    task_type: str = "work"  # work / code / design


class CreateTaskResponse(BaseModel):
    success: bool
    message: str
    task_id: Optional[str] = None
    conversation_id: Optional[str] = None


class StopTaskResponse(BaseModel):
    success: bool
    message: str


class TaskTypeInfo(BaseModel):
    type: str
    name: str
    description: str
    agent_name: str
    strategy: str


# ==================== 辅助函数 ====================


def _task_to_response(task: DuMateTask) -> DuMateTaskResponse:
    return DuMateTaskResponse(
        task_id=task.task_id,
        name=task.name or f"任务 {task.task_id[:8]}",
        project_name=task.project_name,
        agent_name=task.agent_name,
        source=task.source,
        status=task.status,
        content_preview=task.content[:500] if task.content else "",
        content_length=len(task.content),
        created_at=task.created_at.isoformat() if task.created_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


# ==================== 路由：发现与状态 ====================


@router.get("/discover", response_model=DuMateDiscoverResponse)
async def discover():
    """发现系统上的 DuMate 安装信息"""
    info = discover_dumate()

    from star_core.dumate_work_parser import discover_dumate_workspaces
    ws_info = discover_dumate_workspaces()

    return DuMateDiscoverResponse(
        found=info["found"],
        kernel_online=info["kernel_online"],
        port=info["port"],
        pipe_path=info["pipe_path"],
        agent_output_dir=info["agent_output_dir"],
        kernel_log_dir=info["kernel_log_dir"],
        agent_output_count=ws_info.get("agent_output_count", 0),
        plan_count=ws_info.get("plan_count", 0),
        workspaces=info.get("workspaces", []),
    )


@router.get("/adapters")
async def list_adapters():
    """列出所有已注册的 AI 适配器

    通过 AIAdapterRegistry 获取所有已注册的 AI 适配器信息。
    每个适配器报告其 AI_ID、名称、连接状态、能力列表，并附加 UI 需要的
    ``alive``（端口可达）/ ``can_restart``（支持带调试端口重启）/ ``port``。
    """
    registry = get_adapter_registry()

    def _snapshot() -> list[dict]:
        out = []
        for info in registry.list_adapters():
            d = info.to_dict()
            a = registry.get(info.ai_id)
            if a is not None:
                try:
                    d["alive"] = bool(a.is_alive())
                except Exception:
                    d["alive"] = False
                d["can_restart"] = _can_restart(a)
                d["port"] = _adapter_port(a)
            out.append(d)
        return out

    adapters = await run_in_threadpool(_snapshot)
    default = registry.get_default()
    return {
        "adapters": adapters,
        "default": default.AI_ID if default else None,
        "count": len(adapters),
    }


@router.post("/adapters/{ai_id}/connect")
async def connect_adapter(ai_id: str):
    """连接指定 AI 适配器

    Args:
        ai_id: 适配器 ID（如 "dumate"、"trae_work"）

    Returns:
        {"success": bool, "ai_id": str, "ai_name": str, "message": str}
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    # 连接可能自动拉起目标 AI（如 Trae），耗时较长，放到线程避免阻塞事件循环
    ok = await asyncio.to_thread(adapter.connect)
    if not ok:
        port = _adapter_port(adapter)
        detail = f"连接 {adapter.AI_NAME} 失败"
        if port:
            detail += f"（CDP 端口 {port} 不可用）"
        hint = _CONNECT_HINTS.get(ai_id)
        if hint:
            detail += "：" + hint
        return {
            "success": False,
            "ai_id": ai_id,
            "ai_name": adapter.AI_NAME,
            "message": detail,
        }

    # 设为默认
    registry.set_default(ai_id)

    # 连接成功后附带能力自检结果（若有），便于 UI 直接展示
    sc = None
    if hasattr(adapter, "get_self_check"):
        try:
            sc = adapter.get_self_check()
        except Exception:
            sc = None

    return {
        "success": True,
        "ai_id": ai_id,
        "ai_name": adapter.AI_NAME,
        "message": f"已连接 {adapter.AI_NAME}",
        "self_check": sc,
    }


@router.post("/adapters/{ai_id}/restart")
async def restart_adapter(ai_id: str):
    """关闭正在运行的实例并以调试端口重启指定 AI 适配器

    仅对实现了 ``restart_with_cdp`` 的适配器生效（当前为 Trae Work 与
    DuMate 桌面端）。**这会终止用户正在使用的目标 AI 进程**，是"目标 AI
    已开但没带调试端口"这一困境的唯一解法（两者都是单实例应用）。
    普通的 ``connect`` 不会打断已运行实例。

    Returns:
        {"success": bool, "ai_id": str, "ai_name": str, "message": str}
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    if not _can_restart(adapter):
        return {
            "success": False,
            "ai_id": ai_id,
            "ai_name": adapter.AI_NAME,
            "message": f"{adapter.AI_NAME} 不支持带调试端口重启",
        }

    port = _adapter_port(adapter)
    logger.warning(
        "restart_adapter: 即将终止并重启 %s（ai_id=%s, 调试端口 %s）",
        adapter.AI_NAME, ai_id, port,
    )

    # 重启会终止并重新拉起目标 AI 进程，耗时较长，放到线程避免阻塞事件循环
    ok = await asyncio.to_thread(adapter.restart_with_cdp)
    if not ok:
        detail = f"重启 {adapter.AI_NAME} 失败"
        if port:
            detail += f"（CDP 端口 {port} 不可用）"
        hint = _RESTART_HINTS.get(ai_id)
        if hint:
            detail += "：" + hint
        return {
            "success": False,
            "ai_id": ai_id,
            "ai_name": adapter.AI_NAME,
            "message": detail,
        }

    registry.set_default(ai_id)
    suffix = f"（调试端口 {port}）" if port else ""

    # 重启并连接成功后附带能力自检结果（若有），便于 UI 直接展示
    sc = None
    if hasattr(adapter, "get_self_check"):
        try:
            sc = adapter.get_self_check()
        except Exception:
            sc = None

    return {
        "success": True,
        "ai_id": ai_id,
        "ai_name": adapter.AI_NAME,
        "message": f"已重启并连接 {adapter.AI_NAME}{suffix}",
        "self_check": sc,
    }


@router.post("/adapters/{ai_id}/disconnect")
async def disconnect_adapter(ai_id: str):
    """断开指定 AI 适配器"""
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    adapter.disconnect()
    return {
        "success": True,
        "ai_id": ai_id,
        "ai_name": adapter.AI_NAME,
        "message": f"已断开 {adapter.AI_NAME}",
    }


@router.post("/adapters/{ai_id}/default")
async def set_default_adapter(ai_id: str):
    """设置默认 AI 适配器

    所有未指定适配器的操作将使用默认适配器。
    """
    registry = get_adapter_registry()
    ok = registry.set_default(ai_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")
    return {"success": True, "default": ai_id, "message": f"默认适配器已设为 {ai_id}"}


@router.post("/adapters/{ai_id}/tasks")
async def create_task_via_adapter(ai_id: str, req: CreateTaskRequest):
    """通过指定 AI 适配器创建任务

    通用接口：不限于 DuMate，任何注册的 AI 适配器都可使用。
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    if not adapter.connected:
        raise HTTPException(status_code=503, detail=f"AI 适配器 {ai_id} 未连接")

    result = await run_in_threadpool(
        adapter.create_task,
        prompt=req.prompt,
        workspace_id=req.workspace_id,
        task_type=req.task_type,
        agent_name=req.agent_name,
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])

    return {
        "success": True,
        "ai_id": ai_id,
        "conversation_id": result.get("conversation_id", ""),
        "message": result["message"],
    }


@router.post("/adapters/{ai_id}/tasks/{task_id}/stop")
async def stop_task_via_adapter(ai_id: str, task_id: str):
    """通过指定 AI 适配器停止任务"""
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    ok = adapter.stop_task(task_id)
    return {"success": ok, "ai_id": ai_id, "task_id": task_id, "message": "已停止" if ok else "停止失败"}


@router.get("/adapters/{ai_id}/status")
async def get_adapter_status(ai_id: str):
    """获取指定 AI 适配器的状态"""
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    def _snapshot() -> dict:
        out = {"alive": adapter.is_alive(), "status": adapter.get_status()}
        # 已连接且支持自检时顺带跑一次能力自检，供 UI 持续展示
        if adapter.connected and hasattr(adapter, "self_check"):
            try:
                out["self_check"] = adapter.self_check()
            except Exception:
                out["self_check"] = None
        return out

    snap = await run_in_threadpool(_snapshot)
    return {
        "ai_id": ai_id,
        "ai_name": adapter.AI_NAME,
        "connected": adapter.connected,
        "alive": snap["alive"],
        "status": snap["status"],
        "self_check": snap.get("self_check"),
    }


@router.get("/adapters/{ai_id}/selfcheck")
async def selfcheck_adapter(ai_id: str):
    """对指定 AI 适配器触发一次能力自检（连接成功后也可手动复检）。

    仅对实现了 ``self_check`` 的适配器（当前为 Trae Work）生效；未连接或
    不支持时返回 ``ok=False`` 并说明原因。
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    if not hasattr(adapter, "self_check"):
        return {
            "ai_id": ai_id,
            "ai_name": adapter.AI_NAME,
            "ok": False,
            "detail": f"{adapter.AI_NAME} 不支持能力自检",
        }

    def _run() -> dict:
        return adapter.self_check() or {
            "ok": False, "detail": "适配器未连接，无法自检",
        }

    sc = await run_in_threadpool(_run)
    return {
        "ai_id": ai_id,
        "ai_name": adapter.AI_NAME,
        "connected": adapter.connected,
        **(sc if isinstance(sc, dict) else {"ok": False, "detail": "自检返回非预期结构"}),
    }


@router.get("/adapters/{ai_id}/tasks/{task_id}/output")
async def get_adapter_task_output(ai_id: str, task_id: str, max_lines: int = 200):
    """获取指定适配器下某任务的实时输出（通用，适配 DuMate / Trae Work）

    - DuMate: 按 conversation_id → taskId 精确映射读取 .output 文件
    - Trae Work: 读取渲染器中可见的最新 AI 响应

    未连接或读不到内容时返回 found=False，绝不返回他人任务内容。
    """
    registry = get_adapter_registry()
    adapter = registry.get(ai_id)
    if not adapter:
        raise HTTPException(status_code=404, detail=f"AI 适配器 {ai_id} 未注册")

    base = {
        "ai_id": ai_id,
        "task_id": task_id,
        "content": "",
        "line_count": 0,
        "found": False,
    }
    if not adapter.connected:
        return base

    content = await run_in_threadpool(adapter.get_task_output, task_id, max_lines=max_lines)
    if content is None:
        return base

    lines = content.split("\n")
    return {
        "ai_id": ai_id,
        "task_id": task_id,
        "content": content,
        "line_count": len(lines),
        "found": True,
    }


@router.get("/status", response_model=DuMateStatusResponse)
async def get_status():
    """获取 DuMate 内核当前状态"""
    bridge = _get_bridge()
    if not bridge:
        return DuMateStatusResponse(
            status="offline", kernel_online=False, port=None,
        )

    status = bridge.get_status()
    return DuMateStatusResponse(
        status=status, kernel_online=bridge.is_alive(), port=bridge.port,
    )


@router.get("/task-types", response_model=List[TaskTypeInfo])
async def list_task_types():
    """列出可用的任务类型"""
    return [
        TaskTypeInfo(
            type="work",
            name="工作模式",
            description="具备读取、编写、执行命令与联网能力，可灵活适配多种任务与场景。",
            agent_name="Comate",
            strategy="TODOS",
        ),
        TaskTypeInfo(
            type="code",
            name="代码模式",
            description="专注于代码生成、重构和调试。",
            agent_name="Comate",
            strategy="CODE",
        ),
        TaskTypeInfo(
            type="design",
            name="设计模式",
            description="专注于架构设计、方案评审和文档编写。",
            agent_name="Comate",
            strategy="DESIGN",
        ),
    ]


# ==================== 路由：任务管理 ====================


@router.get("/tasks", response_model=List[DuMateTaskResponse])
async def list_tasks():
    """列出所有 DuMate 任务"""
    tasks = DuMateWorkParser.list_tasks()
    return [_task_to_response(t) for t in tasks]


@router.get("/tasks/active", response_model=List[DuMateTaskResponse])
async def list_active_tasks():
    """列出活跃的 DuMate 任务"""
    tasks = DuMateWorkParser.get_active_tasks()
    return [_task_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=DuMateTaskResponse)
async def get_task(task_id: str):
    """获取指定任务的详细信息"""
    task = DuMateWorkParser.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 未找到")
    return _task_to_response(task)


@router.post("/tasks/create", response_model=CreateTaskResponse)
async def create_task(req: CreateTaskRequest):
    """新建 DuMate 任务

    通过命名管道向 DuMate 内核发送命令，使用与 PC 端一致的
    消息格式，支持工作目录、任务类型选择。

    支持:
    - workspace_id: 指定工作目录
    - task_type: 任务类型（work/code/design）
    - agent_name: Agent 名称
    - prompt: 任务提示词
    """
    bridge = _get_bridge()
    if not bridge:
        raise HTTPException(
            status_code=503,
            detail="DuMate 内核未运行，请先启动 DuMate (Comate)"
        )

    # 使用 PC 端真实协议格式创建任务
    result = bridge.create_task(
        prompt=req.prompt,
        workspace_id=req.workspace_id,
        task_type=req.task_type,
        agent_name=req.agent_name,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=500,
            detail=result["message"],
        )

    return CreateTaskResponse(
        success=True,
        message=result["message"],
        task_id=result["conversation_id"][:8] if result["conversation_id"] else None,
        conversation_id=result["conversation_id"],
    )


@router.post("/tasks/{task_id}/stop", response_model=StopTaskResponse)
async def stop_task(task_id: str):
    """结束指定的 DuMate 任务

    发送 COMATE_AGENT_STOP 到内核。
    """
    bridge = _get_bridge()
    if not bridge:
        raise HTTPException(
            status_code=503,
            detail="DuMate 内核未运行，请先启动 DuMate (Comate)"
        )

    stopped = bridge.stop_generation()
    if stopped:
        return StopTaskResponse(
            success=True,
            message=f"已发送停止命令，任务 {task_id} 正在终止"
        )

    task = DuMateWorkParser.get_task(task_id)
    if task:
        return StopTaskResponse(
            success=True,
            message=f"任务 {task_id} 已标记为完成"
        )

    raise HTTPException(
        status_code=404,
        detail=f"任务 {task_id} 未找到，或无法停止"
    )


@router.get("/tasks/{task_id}/content")
async def get_task_content(task_id: str):
    """获取指定任务的完整内容"""
    task = DuMateWorkParser.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 未找到")

    return {
        "task_id": task.task_id,
        "name": task.name,
        "content": task.content,
        "content_length": len(task.content),
        "file_path": task.file_path,
        "source": task.source,
        "status": task.status,
    }


@router.get("/tasks/{task_id}/log")
async def get_task_log(task_id: str):
    """获取指定任务的内核日志片段"""
    log_dir = os.path.expanduser("~/.comate-engine/log")
    log_lines = []

    if os.path.isdir(log_dir):
        log_files = sorted(
            [f for f in os.listdir(log_dir) if f.startswith("kernel-") and f.endswith(".log")],
            reverse=True,
        )
        for log_file in log_files[:2]:
            path = os.path.join(log_dir, log_file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if f"taskId={task_id}" in line or task_id in line:
                            log_lines.append({
                                "file": log_file,
                                "line": line.strip(),
                            })
            except Exception:
                pass

    return {"task_id": task_id, "log_lines": log_lines, "count": len(log_lines)}


# ==================== 路由：SSE 流式响应 ====================
#
# 这两个端点的鉴权不在此处：它们是 GET，走 router 级的 require_by_method，
# 那里已经支持「没带 X-API-Key 时用 ticket query 参数」作为回退——
# 浏览器原生 EventSource 设不了请求头，只能这么过。
# 不要在函数体内再补一层校验：router 级依赖先执行，写在这里的检查永远轮不到。


@router.get("/stream")
async def stream_events(request: Request):
    """SSE 事件流 - 实时推送内核响应

    建立持久连接，将 DuMate 内核的 ENGINE SEND 和
    KERNEL_SPEC_STATE_CHANGED 等事件实时推送到前端。
    """
    bridge = _get_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="DuMate 内核未运行")

    async def event_generator():
        last_event_id = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                # 非阻塞读取队列
                event = bridge.response_queue.get_nowait()
                last_event_id += 1
                data = json.dumps(event, ensure_ascii=False)
                yield f"id: {last_event_id}\ndata: {data}\n\n"
            except Exception:
                # 队列为空，发送心跳
                yield f": heartbeat {time.time()}\n\n"
                await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/stream/session/{conversation_id}")
async def stream_session_events(conversation_id: str, request: Request):
    """SSE 事件流 - 监听指定会话的实时状态

    过滤出指定会话的 SESSION_STATUS_UPDATED 事件。
    """
    bridge = _get_bridge()
    if not bridge:
        raise HTTPException(status_code=503, detail="DuMate 内核未运行")

    async def event_generator():
        last_status = None
        while True:
            if await request.is_disconnected():
                break
            # 检查会话状态缓存
            status = bridge.get_session_status(conversation_id)
            if status and status != last_status:
                last_status = status
                data = json.dumps({
                    "type": "session_status",
                    "conversation_id": conversation_id,
                    "data": status,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

                # 如果任务已完成，发送结束信号后退出
                if status.get("status") in ("completed", "failed", "error"):
                    yield f"data: {json.dumps({'type': 'stream_end', 'conversation_id': conversation_id})}\n\n"
                    break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ==================== 路由：会话与工作目录 ====================


@router.get("/conversations", response_model=List[DuMateConversationResponse])
async def list_conversations():
    """列出所有 DuMate 会话（从内核日志解析）"""
    bridge = _get_bridge()
    if not bridge:
        return []

    conversations = bridge.list_conversations()
    return [
        DuMateConversationResponse(
            conversation_id=c["conversation_id"],
            title=c.get("title", ""),
            status=c.get("status", "unknown"),
            workspace_id=c.get("workspace_id", ""),
            workspace_name=c.get("workspace_name", ""),
        )
        for c in conversations
    ]


@router.get("/workspaces")
async def list_workspaces():
    """列出可用的工作目录"""
    info = discover_dumate()
    return {"workspaces": info.get("workspaces", [])}


@router.get("/conversations/{conversation_id}/output")
async def get_conversation_output(conversation_id: str, max_lines: int = 200):
    """获取指定会话的 AI 输出内容（实时轮询用）

    当 DuMate 正在生成时，Agent 输出文件会持续写入。
    该端点用于前端轮询获取最新生成内容。

    Args:
        conversation_id: 会话 UUID
        max_lines: 最大读取行数

    Returns:
        {"conversation_id": str, "content": str, "line_count": int, "found": bool}
    """
    bridge = _get_bridge()
    if not bridge:
        return {"conversation_id": conversation_id, "content": "", "line_count": 0, "found": False}

    content = bridge.get_conversation_output(conversation_id, max_lines=max_lines)
    if content is None:
        return {"conversation_id": conversation_id, "content": "", "line_count": 0, "found": False}

    lines = content.split("\n")
    return {
        "conversation_id": conversation_id,
        "content": content,
        "line_count": len(lines),
        "found": True,
    }


@router.get("/bridge/status")
async def bridge_status():
    """获取 DuMate 桥接状态详情"""
    bridge = _get_bridge()
    if not bridge:
        return {
            "connected": False, "port": None,
            "pipe_path": None, "is_alive": False,
        }

    return {
        "connected": bridge.connected,
        "port": bridge.port,
        "pipe_path": bridge.pipe_path,
        "is_alive": bridge.is_alive(),
        "session_count": len(bridge.session_status),
    }


import os  # noqa: E402 (used by get_task_log)