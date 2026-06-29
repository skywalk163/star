"""
历史记录路由（History Routes）

提供历史记录查询和统计分析接口
"""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query

from star_api import state


router = APIRouter()


@router.get("/novas")
async def list_history(
    status: Optional[str] = None,
    star_type: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    查询新星历史记录
    
    Args:
        status: 状态过滤
        star_type: 星体类型过滤
        days: 最近 N 天
        limit: 数量限制
        offset: 偏移量
        
    Returns:
        历史记录列表
    """
    if state.history_store is None:
        raise HTTPException(status_code=503, detail="历史系统未初始化")
    
    start_date = None
    end_date = None
    
    if days:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
    
    records = state.history_store.query_novas(
        status=status,
        star_type=star_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset
    )
    
    total = state.history_store.get_nova_count(
        status=status,
        star_type=star_type,
        start_date=start_date,
        end_date=end_date
    )
    
    return {
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/novas/{nova_id}")
async def get_nova_history(nova_id: str):
    """
    获取新星历史详情
    
    Args:
        nova_id: 新星 ID
        
    Returns:
        历史详情
    """
    if state.history_store is None:
        raise HTTPException(status_code=503, detail="历史系统未初始化")
    
    detail = state.history_store.get_nova_detail(nova_id)
    
    if not detail:
        raise HTTPException(status_code=404, detail=f"历史记录 {nova_id} 未发现")
    
    return detail


@router.get("/overview")
async def get_history_overview():
    """
    获取历史概览统计
    
    Returns:
        概览统计
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return state.analytics.get_overview_stats()


@router.get("/by-star-type")
async def get_stats_by_star_type():
    """
    按星体类型统计
    
    Returns:
        各星体类型统计
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return state.analytics.get_star_type_stats()


@router.get("/daily")
async def get_daily_stats(days: int = Query(30, ge=1, le=365)):
    """
    按日统计
    
    Args:
        days: 统计天数（默认30天）
        
    Returns:
        每日统计
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return {
        "days": days,
        "data": state.analytics.get_daily_stats(days)
    }


@router.get("/hourly")
async def get_hourly_stats():
    """
    按小时统计（24小时分布）
    
    Returns:
        每小时统计
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return {
        "data": state.analytics.get_hourly_stats()
    }


@router.get("/by-priority")
async def get_priority_stats():
    """
    按优先级统计
    
    Returns:
        各优先级统计
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return state.analytics.get_priority_stats()


@router.get("/top")
async def get_top_novas(
    by: str = Query("duration", pattern="^(duration|output_length)$"),
    limit: int = Query(10, ge=1, le=100)
):
    """
    获取 TOP 新星排行
    
    Args:
        by: 排序方式 - duration（耗时最长）/ output_length（输出最长）
        limit: 数量限制
        
    Returns:
        TOP 排行
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return {
        "by": by,
        "limit": limit,
        "data": state.analytics.get_top_novas(by=by, limit=limit)
    }


@router.get("/report")
async def get_full_report():
    """
    获取完整统计报告
    
    Returns:
        完整报告
    """
    if state.analytics is None:
        raise HTTPException(status_code=503, detail="统计系统未初始化")
    
    return state.analytics.generate_report()
