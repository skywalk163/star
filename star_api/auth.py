"""
星鉴者（StarAuth）- 认证与权限控制

API Key 认证 + 角色权限（admin/viewer）
"""

from typing import Optional, List
from fastapi import HTTPException, Header, Depends
from star_api import state


# 角色权限定义
ROLE_PERMISSIONS = {
    'admin': ['read', 'write', 'control', 'admin'],
    'viewer': ['read'],
}


def _get_auth_config() -> dict:
    """获取认证配置"""
    if not hasattr(state, 'config') or not state.config:
        return {}
    return state.config.get('auth', {})


def is_auth_enabled() -> bool:
    """检查认证是否启用"""
    cfg = _get_auth_config()
    return cfg.get('enabled', False)


def _get_api_keys() -> List[dict]:
    """获取所有 API Key 配置"""
    cfg = _get_auth_config()
    keys = cfg.get('api_keys', [])
    if not keys:
        return []
    # 兼容字典和列表两种格式
    if isinstance(keys, dict):
        return [{'key': k, 'role': v.get('role', 'viewer'), 'name': v.get('name', k)}
                for k, v in keys.items()]
    return keys


def _find_key_info(api_key: str) -> Optional[dict]:
    """根据 key 查找配置信息"""
    for key_info in _get_api_keys():
        if key_info.get('key') == api_key:
            return key_info
    return None


def has_permission(role: str, permission: str) -> bool:
    """检查角色是否拥有指定权限"""
    perms = ROLE_PERMISSIONS.get(role, [])
    return permission in perms


async def get_current_user(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> dict:
    """
    获取当前用户（认证依赖）

    如果认证未启用，返回默认 admin 角色
    如果认证启用，验证 API Key 并返回用户信息
    """
    if not is_auth_enabled():
        return {'role': 'admin', 'name': 'default', 'authenticated': False}

    if not x_api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")

    key_info = _find_key_info(x_api_key)
    if not key_info:
        raise HTTPException(status_code=401, detail="无效的 API Key")

    return {
        'role': key_info.get('role', 'viewer'),
        'name': key_info.get('name', 'unknown'),
        'authenticated': True,
    }


def require_permission(permission: str):
    """
    创建权限检查依赖

    用法: @router.get(..., dependencies=[Depends(require_permission('write'))])
    """
    async def checker(current_user: dict = Depends(get_current_user)):
        if not is_auth_enabled():
            return
        if not has_permission(current_user['role'], permission):
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：需要 {permission} 权限"
            )
    return checker


# 预定义的权限依赖（直接作为 callable 传入 dependencies=[]）
require_read = require_permission('read')
require_write = require_permission('write')
require_control = require_permission('control')
require_admin = require_permission('admin')
