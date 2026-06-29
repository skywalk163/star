"""
插件管理路由（Plugins Routes）

提供插件的发现、加载、启用、禁用等管理接口
"""

from typing import Optional
from fastapi import APIRouter, HTTPException

from star_core.plugin_system import PluginType, PluginStatus
from star_api import state


router = APIRouter()


@router.get("/")
async def list_plugins(plugin_type: Optional[str] = None):
    """
    列出所有插件
    
    Args:
        plugin_type: 按类型过滤（star, injector, gazer, hook, extension）
        
    Returns:
        插件列表
    """
    if state.plugin_manager is None:
        raise HTTPException(status_code=503, detail="插件系统未初始化")
    
    ptype = None
    if plugin_type:
        try:
            ptype = PluginType(plugin_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效的插件类型: {plugin_type}")
    
    plugins = state.plugin_manager.list_plugins(ptype)
    
    return {
        "plugins": [p.to_dict() for p in plugins],
        "total": len(plugins)
    }


@router.get("/{plugin_name}")
async def get_plugin(plugin_name: str):
    """
    获取插件详情
    
    Args:
        plugin_name: 插件名称
        
    Returns:
        插件详情
    """
    if state.plugin_manager is None:
        raise HTTPException(status_code=503, detail="插件系统未初始化")
    
    info = state.plugin_manager.get_plugin_info(plugin_name)
    
    if not info:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 未发现")
    
    return info.to_dict()


@router.post("/{plugin_name}/load")
async def load_plugin(plugin_name: str):
    """
    加载插件
    
    Args:
        plugin_name: 插件名称
        
    Returns:
        加载结果
    """
    if state.plugin_manager is None:
        raise HTTPException(status_code=503, detail="插件系统未初始化")
    
    success = state.plugin_manager.load_plugin(plugin_name)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 加载失败")
    
    info = state.plugin_manager.get_plugin_info(plugin_name)
    return {
        "name": plugin_name,
        "status": info.status.value if info else "unknown",
        "message": "插件已加载"
    }


@router.post("/{plugin_name}/enable")
async def enable_plugin(plugin_name: str):
    """
    启用插件
    
    Args:
        plugin_name: 插件名称
        
    Returns:
        启用结果
    """
    if state.plugin_manager is None:
        raise HTTPException(status_code=503, detail="插件系统未初始化")
    
    success = state.plugin_manager.enable_plugin(plugin_name)
    
    if not success:
        raise HTTPException(status_code=400, detail=f"插件 {plugin_name} 启用失败")
    
    info = state.plugin_manager.get_plugin_info(plugin_name)
    return {
        "name": plugin_name,
        "status": info.status.value if info else "unknown",
        "message": "插件已启用"
    }


@router.post("/{plugin_name}/disable")
async def disable_plugin(plugin_name: str):
    """
    禁用插件
    
    Args:
        plugin_name: 插件名称
        
    Returns:
        禁用结果
    """
    if state.plugin_manager is None:
        raise HTTPException(status_code=503, detail="插件系统未初始化")
    
    success = state.plugin_manager.disable_plugin(plugin_name)
    
    if not success:
        raise HTTPException(status_code=404, detail=f"插件 {plugin_name} 未发现")
    
    return {
        "name": plugin_name,
        "status": "disabled",
        "message": "插件已禁用"
    }


@router.get("/types/available")
async def get_plugin_types():
    """获取所有插件类型"""
    return {
        "types": [
            {"value": t.value, "name": t.name}
            for t in PluginType
        ]
    }
