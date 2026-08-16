from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from star_api import state
from star_api.auth import require_read, require_admin
import yaml
import os

router = APIRouter(prefix="/api/config", tags=["配置"])

# 可通过本接口读写的配置节。auth 不在其中：API Key 绝不下发给前端，
# 也不接受前端改写（改 Key 请直接编辑 config.yaml 并重启）。
_EDITABLE_SECTIONS = ["server", "directories", "logging", "ocr", "emissary", "websocket"]
_SECRET_SECTIONS = ("auth",)


class ConfigUpdate(BaseModel):
    server: Optional[dict] = None
    directories: Optional[dict] = None
    logging: Optional[dict] = None
    ocr: Optional[dict] = None
    emissary: Optional[dict] = None
    websocket: Optional[dict] = None


def _redacted_config() -> dict:
    """返回去掉敏感节的配置副本（用于下发给前端）"""
    import copy
    safe = copy.deepcopy(state.config or {})
    for section in _SECRET_SECTIONS:
        if section in safe:
            # 只保留「是否启用」这类无害元信息，明文 Key 一律不出网
            original = safe[section] or {}
            safe[section] = {
                "enabled": original.get("enabled", False),
                "header_name": original.get("header_name", "X-API-Key"),
                "key_count": len(original.get("api_keys") or []),
            }
    return safe


@router.get("", dependencies=[Depends(require_read)])
async def get_config():
    """获取当前配置（auth 节已脱敏，不含 API Key 明文）"""
    return {"config": _redacted_config()}


@router.get("/{section}", dependencies=[Depends(require_read)])
async def get_config_section(section: str):
    """获取配置的某个小节"""
    if section not in _EDITABLE_SECTIONS:
        return {"error": "未知配置节: " + section, "available": _EDITABLE_SECTIONS}
    return {"section": section, "value": state.config.get(section, {})}


@router.put("", dependencies=[Depends(require_admin)])
async def update_config(update: ConfigUpdate):
    """更新配置（只更新提供的小节，未提供的保持不变）"""
    updates = update.dict(exclude_unset=True)
    changed = []

    for section, value in updates.items():
        if value is None:
            continue
        if section not in state.config:
            state.config[section] = {}
        if isinstance(value, dict):
            state.config[section].update(value)
        else:
            state.config[section] = value
        changed.append(section)

    # 保存到文件（写入的是完整 state.config，auth 节原样保留）
    config_path = os.path.join(state.project_root, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(state.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return {"status": "ok", "updated_sections": changed, "config": _redacted_config()}

