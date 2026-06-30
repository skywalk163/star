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
