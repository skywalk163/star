"""
config_service.py - 统一配置中心

功能：
- 从 YAML 文件加载 Agent 配置（签名 + 适配器）
- 配置缓存和热加载
- 提供统一的配置访问接口
- 合并默认配置和用户配置
"""

import os
import yaml
import threading
from typing import Dict, Any, Optional
from datetime import datetime


class ConfigService:
    """统一配置服务"""
    
    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config')
        self.config_dir = config_dir
        self._agents_config: Dict[str, Any] = {}
        self._default_adapter_config: Dict[str, Any] = {}
        self._interaction_configs: Dict[str, Any] = {}
        self._last_mtime = 0
        self._lock = threading.RLock()
        self.load()
    
    def load(self) -> bool:
        """加载所有配置"""
        try:
            with self._lock:
                self._load_agents_config()
                return True
        except Exception as e:
            print(f"[ConfigService] Failed to load config: {e}")
            return False
    
    def _load_agents_config(self):
        """加载 Agent 配置"""
        yaml_path = os.path.join(self.config_dir, 'ai-agents.yaml')
        if not os.path.exists(yaml_path):
            print(f"[ConfigService] Config file not found: {yaml_path}")
            return
        
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if not data or 'agents' not in data:
            return
        
        agents_dict = {}
        for agent in data.get('agents', []):
            agent_id = agent.get('id')
            if agent_id:
                agents_dict[agent_id] = agent
        
        self._agents_config = agents_dict
        self._default_adapter_config = data.get('default_adapter_config', {})
        self._last_mtime = os.path.getmtime(yaml_path)
        
        # Parse interaction configs
        self._interaction_configs = {}
        for agent_id, agent in agents_dict.items():
            interaction_data = agent.get('interaction')
            if interaction_data:
                try:
                    ic = _parse_interaction_config(interaction_data)
                    if ic is not None:
                        self._interaction_configs[agent_id] = ic
                except Exception as e:
                    print(f"[ConfigService] Failed to parse interaction for {agent_id}: {e}")
    
    def reload_if_changed(self) -> bool:
        """如果配置文件变更则重新加载"""
        yaml_path = os.path.join(self.config_dir, 'ai-agents.yaml')
        if not os.path.exists(yaml_path):
            return False
        
        try:
            current_mtime = os.path.getmtime(yaml_path)
            if current_mtime > self._last_mtime:
                print(f"[ConfigService] Config changed, reloading...")
                return self.load()
        except Exception:
            pass
        return False
    
    # ========== Agent 配置访问 ==========
    
    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Agent 的完整配置"""
        with self._lock:
            agent = self._agents_config.get(agent_id)
            if not agent:
                return None
            
            result = dict(agent)
            if self._default_adapter_config:
                default_adapter = dict(self._default_adapter_config)
                agent_adapter = agent.get('adapter_config', {})
                default_adapter.update(agent_adapter)
                result['adapter_config'] = default_adapter
            
            return result
    
    def get_all_agents(self) -> Dict[str, Any]:
        """获取所有 Agent 配置"""
        with self._lock:
            return dict(self._agents_config)
    
    def get_star_signatures(self) -> Dict[str, Any]:
        """获取星体签名（兼容 StarSeeker 的格式）"""
        with self._lock:
            signatures = {}
            for agent_id, agent in self._agents_config.items():
                signatures[agent_id] = {
                    'process_names': agent.get('process_names', []),
                    'window_class': agent.get('window_class', []),
                    'window_title_patterns': agent.get('title_patterns', []),
                    'description': agent.get('description', ''),
                }
            return signatures
    
    def get_adapter_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取指定 Agent 的适配器配置"""
        agent = self.get_agent(agent_id)
        if not agent:
            return None
        return agent.get('adapter_config', dict(self._default_adapter_config))
    
    def get_all_adapter_configs(self) -> Dict[str, Any]:
        """获取所有 Agent 的适配器配置"""
        result = {}
        for agent_id in self._agents_config:
            adapter = self.get_adapter_config(agent_id)
            if adapter:
                result[agent_id] = adapter
        return result
    
    def get_default_adapter_config(self) -> Dict[str, Any]:
        """获取默认适配器配置"""
        return dict(self._default_adapter_config)
    
    def get_interaction_config(self, agent_id: str) -> Optional[Any]:
        """
        Get InteractionConfig for the specified agent.
        
        Args:
            agent_id: Agent ID (e.g. "trae", "browser_yiyan").
            
        Returns:
            InteractionConfig instance or None if not configured.
        """
        with self._lock:
            return self._interaction_configs.get(agent_id)
    
    # ========== 配置校验 ==========
    
    def validate_agent_config(self, agent_id: str) -> tuple:
        """校验 Agent 配置完整性"""
        errors = []
        agent = self._agents_config.get(agent_id)
        
        if not agent:
            return False, [f"Agent '{agent_id}' not found"]
        
        required_fields = ['id', 'name', 'category', 'process_names', 'title_patterns']
        for field in required_fields:
            if not agent.get(field):
                errors.append(f"Missing required field: {field}")
        
        return len(errors) == 0, errors


_config_service: Optional[ConfigService] = None


def get_config_service() -> ConfigService:
    """获取配置服务单例"""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service


# ========== Interaction Config Parsing ==========

def _parse_interaction_config(data: dict) -> Optional[Any]:
    """
    Parse interaction section from yaml dict into InteractionConfig.
    
    Uses lazy import of star_core.interaction to avoid circular dependency.
    """
    try:
        from star_core.interaction import (
            InteractionConfig,
            LocatorTarget,
            UIAQuery,
            VisualQuery,
            RatioQuery,
            CDPQuery,
        )
    except ImportError:
        return None

    input_data = data.get("input", {})

    # Build input LocatorTarget
    input_target = _build_locator_target("input", input_data)

    # Build send_button LocatorTarget
    send_button = None
    send_button_data = input_data.get("send_button")
    if send_button_data:
        send_button = _build_locator_target("send_button", send_button_data)

    # Build stop LocatorTarget from stop.cancel_button
    stop = None
    stop_data = data.get("stop", {})
    cancel_button_data = stop_data.get("cancel_button")
    if cancel_button_data:
        stop = _build_locator_target("stop_button", cancel_button_data)

    # stop_fallback_keys
    fallback_keys = stop_data.get("fallback_keys", [])

    # output
    output = data.get("output", [])

    # locators order
    locators = input_data.get("locators", [])

    # send_on
    send_on = input_data.get("send_on", "Enter")

    return InteractionConfig(
        locators=locators,
        input=input_target,
        send_on=send_on,
        send_button=send_button,
        stop=stop,
        stop_fallback_keys=fallback_keys,
        output=output,
    )


def _build_locator_target(kind: str, data: dict) -> Any:
    """Build LocatorTarget from yaml dict."""
    from star_core.interaction import (
        LocatorTarget,
        UIAQuery,
        VisualQuery,
        RatioQuery,
        CDPQuery,
    )

    target = LocatorTarget(kind=kind)

    if "uia" in data:
        uia_data = data["uia"]
        target.uia = UIAQuery(
            control_type=uia_data.get("control_type"),
            automation_id=uia_data.get("automation_id"),
            name_regex=uia_data.get("name_pattern") or uia_data.get("name_regex"),
            depth_limit=uia_data.get("depth_limit", 8),
        )

    if "visual" in data:
        vis_data = data["visual"]
        target.visual = VisualQuery(
            hint_text=vis_data.get("hint_text"),
            template=vis_data.get("template"),
            region=vis_data.get("region", "full_window"),
            ocr_min_confidence=vis_data.get("ocr_min_confidence", 0.5),
        )

    if "ratio" in data:
        ratio_data = data["ratio"]
        target.ratio = RatioQuery(
            x_ratio=ratio_data.get("x", ratio_data.get("x_ratio", 0.5)),
            y_ratio=ratio_data.get("y", ratio_data.get("y_ratio", 0.92)),
        )

    if "cdp" in data:
        cdp_data = data["cdp"]
        target.cdp = CDPQuery(
            selector=cdp_data.get("selector"),
            text_contains=cdp_data.get("text_contains"),
            role=cdp_data.get("role"),
        )

    return target
