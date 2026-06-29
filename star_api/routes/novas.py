"""
新星路由（Novas Routes）- 任务接口

提供任务的创建、查询、调整等接口
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from star_core import Nova, StarStatus, StarPriority
from star_api import state


router = APIRouter()


# ==================== 请求/响应模型 ====================

class NovaCreate(BaseModel):
    """创建新星请求"""
    title: str
    description: str
    starlight: str
    context_files: list[str] = []
    assigned_star: Optional[str] = None
    priority: int = 1  # 0=DIM, 1=NORMAL, 2=BRIGHT, 3=SUPERNOVA


class NovaAdjust(BaseModel):
    """调整星轨请求"""
    new_starlight: str


class NovaEcho(BaseModel):
    """添加回响请求"""
    echo: str


# ==================== 接口实现 ====================

@router.post("/")
async def create_nova(request: NovaCreate):
    """
    诞生新星 - 创建新任务
    
    Args:
        request: 创建请求
        
    Returns:
        新星的 ID 和信息
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    # 构建 Nova
    nova = Nova(
        id="",  # 将由引擎生成
        title=request.title,
        description=request.description,
        starlight=request.starlight,
        context_files=request.context_files,
        assigned_star=request.assigned_star,
        priority=StarPriority(request.priority)
    )
    
    # 提交任务
    nova_id = await state.orbit_engine.birth_nova(nova)
    
    return {
        "id": nova_id,
        "title": nova.title,
        "status": nova.status.value,
        "assigned_star": nova.assigned_star,
        "message": "新星已诞生，等待入轨"
    }


@router.get("/")
async def list_novas(
    status: Optional[str] = None,
    star_type: Optional[str] = None
):
    """
    列出所有新星
    
    Args:
        status: 状态过滤
        star_type: 目标星类型过滤
        
    Returns:
        新星列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    if status:
        try:
            status_enum = StarStatus(status)
            novas = state.orbit_engine.get_novas_by_status(status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效状态: {status}")
    elif star_type:
        novas = state.orbit_engine.get_novas_by_star(star_type)
    else:
        novas = list(state.orbit_engine._active_novas.values())
    
    return {
        "novas": [
            {
                "id": n.id,
                "title": n.title,
                "description": n.description,
                "status": n.status.value,
                "priority": n.priority.value,
                "assigned_star": n.assigned_star,
                "created_at": n.created_at.isoformat(),
                "updated_at": n.updated_at.isoformat(),
                "result_starlight": n.result_starlight,
                "error": n.error
            }
            for n in sorted(novas, key=lambda x: (-x.priority.value, x.created_at))
        ],
        "total": len(novas)
    }


@router.get("/{nova_id}")
async def get_nova(nova_id: str):
    """
    获取新星详情
    
    Args:
        nova_id: 新星 ID
        
    Returns:
        新星详情
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    nova = state.orbit_engine.get_nova(nova_id)
    
    if not nova:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    return {
        "id": nova.id,
        "title": nova.title,
        "description": nova.description,
        "starlight": nova.starlight,
        "status": nova.status.value,
        "priority": nova.priority.value,
        "assigned_star": nova.assigned_star,
        "created_at": nova.created_at.isoformat(),
        "updated_at": nova.updated_at.isoformat(),
        "result_starlight": nova.result_starlight,
        "starlight_log": nova.starlight_log,
        "echo": nova.echo,
        "error": nova.error
    }


@router.post("/{nova_id}/launch")
async def launch_nova(nova_id: str):
    """
    发射新星 - 将任务分配给星体执行
    
    Args:
        nova_id: 新星 ID
        
    Returns:
        发射结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.launch_nova(nova_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="发射失败：无可用星体或发送指令失败"
        )
    
    nova = state.orbit_engine.get_nova(nova_id)
    return {
        "id": nova_id,
        "status": nova.status.value,
        "message": "新星已发射，正在闪耀"
    }


@router.post("/{nova_id}/adjust")
async def adjust_orbit(nova_id: str, request: NovaAdjust):
    """
    调整星轨 - 修改运行中的任务
    
    Args:
        nova_id: 新星 ID
        request: 调整请求
        
    Returns:
        调整结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.adjust_orbit(nova_id, request.new_starlight)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="调整失败：任务未在运行或无可用星体"
        )
    
    nova = state.orbit_engine.get_nova(nova_id)
    return {
        "id": nova_id,
        "starlight": nova.starlight,
        "message": "星轨已调整"
    }


@router.post("/{nova_id}/echo")
async def add_echo(nova_id: str, request: NovaEcho):
    """
    添加回响 - 用户对结果的反馈
    
    Args:
        nova_id: 新星 ID
        request: 回响内容
        
    Returns:
        处理结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.add_echo(nova_id, request.echo)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    nova = state.orbit_engine.get_nova(nova_id)
    return {
        "id": nova_id,
        "status": nova.status.value,
        "message": "回响已添加"
    }


@router.post("/{nova_id}/fade")
async def fade_nova(nova_id: str, reason: str = "未知原因"):
    """
    使新星暗淡 - 标记任务失败
    
    Args:
        nova_id: 新星 ID
        reason: 失败原因
        
    Returns:
        结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.fade_nova(nova_id, reason)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    return {
        "id": nova_id,
        "status": StarStatus.FADED.value,
        "message": f"新星已暗淡: {reason}"
    }


@router.post("/{nova_id}/darken")
async def darken_nova(nova_id: str):
    """
    熄灭新星 - 取消任务
    
    Args:
        nova_id: 新星 ID
        
    Returns:
        结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.darken_nova(nova_id)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    return {
        "id": nova_id,
        "status": StarStatus.DARKENED.value,
        "message": "新星已熄灭"
    }


@router.get("/{nova_id}/gaze")
async def get_gaze_history(nova_id: str):
    """
    获取观星历史
    
    Args:
        nova_id: 新星 ID
        
    Returns:
        观星历史
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    nova = state.orbit_engine.get_nova(nova_id)
    
    if not nova:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    return {
        "nova_id": nova_id,
        "history": nova.starlight_log
    }
