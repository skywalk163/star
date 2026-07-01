"""
可观测性路由

提供指标查询、健康检查等 API。
"""

from fastapi import APIRouter, HTTPException
from star_core.observability import get_metrics_registry, get_health_checker

router = APIRouter(tags=["可观测性"])


@router.get("/metrics")
async def get_metrics():
    """获取所有指标"""
    registry = get_metrics_registry()
    return registry.get_all()


@router.get("/health")
async def health_check():
    """健康检查"""
    checker = get_health_checker()
    result = checker.check_all()
    return result


@router.get("/health/list")
async def list_health_checks():
    """列出所有健康检查项"""
    checker = get_health_checker()
    return {"checks": checker.list_checks()}


@router.get("/health/{check_name}")
async def health_check_single(check_name: str):
    """单个健康检查"""
    checker = get_health_checker()
    result = checker.check(check_name)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Health check '{check_name}' not found")
    return result
