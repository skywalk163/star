"""
星座路由（Constellations Routes）- 多星协同任务接口

提供星座（多任务协同）的创建和管理接口
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from star_core import (
    Nova, Constellation, ConstellationStatus,
    ResultComparator, StarStatus
)
from star_api import state


router = APIRouter()


# ==================== 请求模型 ====================

class NovaSpec(BaseModel):
    """新星规格"""
    title: str
    description: str
    starlight: str
    assigned_star: Optional[str] = None


class ConstellationCreate(BaseModel):
    """创建星座请求"""
    name: str
    description: str
    nova_specs: list[NovaSpec]
    execution_mode: str = "parallel"  # "parallel" 或 "sequential"


# ==================== 接口实现 ====================

@router.post("/")
async def create_constellation(request: ConstellationCreate):
    """
    创建星座 - 多星协同任务
    
    Args:
        request: 创建请求
        
    Returns:
        星座信息
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    constellation = await state.orbit_engine.create_constellation(
        name=request.name,
        description=request.description,
        nova_specs=[s.model_dump() for s in request.nova_specs],
        execution_mode=request.execution_mode
    )
    
    return {
        "id": constellation.id,
        "name": constellation.name,
        "description": constellation.description,
        "status": constellation.status.value,
        "execution_mode": constellation.execution_mode,
        "nova_count": len(constellation.novas),
        "nova_ids": [n.id for n in constellation.novas],
        "message": "星座已形成，等待群星闪耀"
    }


@router.get("/")
async def list_constellations(status: Optional[str] = None):
    """
    列出所有星座
    
    Args:
        status: 状态过滤（可选）
        
    Returns:
        星座列表
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    if status:
        try:
            status_enum = ConstellationStatus(status)
            constellations = state.orbit_engine.get_constellations_by_status(status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效状态: {status}")
    else:
        constellations = state.orbit_engine.get_all_constellations()
    
    return {
        "constellations": [
            {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "status": c.status.value,
                "execution_mode": c.execution_mode,
                "nova_count": len(c.novas),
                "completed_count": len(c.completed_novas),
                "shining_count": len(c.get_shining_novas()),
                "created_at": c.created_at.isoformat(),
                "updated_at": c.updated_at.isoformat()
            }
            for c in constellations
        ],
        "total": len(constellations)
    }


@router.get("/{constellation_id}")
async def get_constellation(constellation_id: str):
    """
    获取星座详情
    
    Args:
        constellation_id: 星座 ID
        
    Returns:
        星座详情
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    constellation = state.orbit_engine.get_constellation(constellation_id)
    
    if not constellation:
        raise HTTPException(status_code=404, detail=f"星座 {constellation_id} 未发现")
    
    return {
        "id": constellation.id,
        "name": constellation.name,
        "description": constellation.description,
        "status": constellation.status.value,
        "execution_mode": constellation.execution_mode,
        "created_at": constellation.created_at.isoformat(),
        "updated_at": constellation.updated_at.isoformat(),
        "novas": [
            {
                "id": n.id,
                "title": n.title,
                "description": n.description,
                "assigned_star": n.assigned_star,
                "status": n.status.value,
                "priority": n.priority.value,
                "result_starlight": n.result_starlight,
                "created_at": n.created_at.isoformat(),
                "updated_at": n.updated_at.isoformat()
            }
            for n in constellation.novas
        ]
    }


@router.post("/{constellation_id}/launch")
async def launch_constellation(constellation_id: str):
    """
    发射星座 - 启动所有组成新星
    
    Args:
        constellation_id: 星座 ID
        
    Returns:
        发射结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    success = await state.orbit_engine.launch_constellation(constellation_id)
    
    if not success:
        raise HTTPException(
            status_code=400,
            detail="发射失败：星座不存在或已发射/已完成"
        )
    
    constellation = state.orbit_engine.get_constellation(constellation_id)
    return {
        "id": constellation_id,
        "status": constellation.status.value,
        "shining_novas": [n.id for n in constellation.get_shining_novas()],
        "message": "星座已发射，群星开始闪耀"
    }


@router.post("/{constellation_id}/compare")
async def compare_constellation(constellation_id: str):
    """
    对比星座中各新星的结果
    
    Args:
        constellation_id: 星座 ID
        
    Returns:
        对比结果
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    constellation = state.orbit_engine.get_constellation(constellation_id)
    
    if not constellation:
        raise HTTPException(status_code=404, detail=f"星座 {constellation_id} 未发现")
    
    comparison = ResultComparator.compare_novas(constellation.novas)
    return comparison


@router.get("/{constellation_id}/novas/{nova_id}")
async def get_constellation_nova(constellation_id: str, nova_id: str):
    """
    获取星座中指定新星的详情
    
    Args:
        constellation_id: 星座 ID
        nova_id: 新星 ID
        
    Returns:
        新星详情
    """
    if state.orbit_engine is None:
        raise HTTPException(status_code=503, detail="星核未初始化")
    
    constellation = state.orbit_engine.get_constellation(constellation_id)
    
    if not constellation:
        raise HTTPException(status_code=404, detail=f"星座 {constellation_id} 未发现")
    
    nova = next((n for n in constellation.novas if n.id == nova_id), None)
    
    if not nova:
        raise HTTPException(status_code=404, detail=f"新星 {nova_id} 未发现")
    
    return {
        "id": nova.id,
        "title": nova.title,
        "description": nova.description,
        "starlight": nova.starlight,
        "assigned_star": nova.assigned_star,
        "status": nova.status.value,
        "priority": nova.priority.value,
        "created_at": nova.created_at.isoformat(),
        "updated_at": nova.updated_at.isoformat(),
        "result_starlight": nova.result_starlight,
        "starlight_log": nova.starlight_log,
        "echo": nova.echo,
        "error": nova.error
    }
