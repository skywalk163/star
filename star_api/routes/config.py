from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from star_api import state
import yaml
import os

router = APIRouter(prefix="/api/config", tags=["配置"])


class ConfigUpdate(BaseModel):
    server: Optional[dict] = None
    directories: Optional[dict] = None
    logging: Optional[dict] = None
    ocr: Optional[dict] = None
    emissary: Optional[dict] = None
    websocket: Optional[dict] = None


@router.get("")
async def get_config():
    """获取当前配置"""
    import copy
    safe_config = copy.deepcopy(state.config)
    return {"config": safe_config}


@router.get("/{section}")
async def get_config_section(section: str):
    """获取配置的某个小节"""
    sections = ["server", "directories", "logging", "ocr", "emissary", "websocket"]
    if section not in sections:
        return {"error": "未知配置节: " + section, "available": sections}
    return {"section": section, "value": state.config.get(section, {})}


@router.put("")
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
    
    # 保存到文件
    config_path = os.path.join(state.project_root, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(state.config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    
    return {"status": "ok", "updated_sections": changed, "config": state.config}
