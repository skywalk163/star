"""
示例钩子插件 - Demo Hook Plugin

展示如何创建任务钩子插件，在任务生命周期各节点插入自定义逻辑
"""

from star_core.plugin_system import HookPlugin


class DemoHookPlugin(HookPlugin):
    """
    示例钩子插件
    
    演示如何在任务生命周期的各个节点插入自定义逻辑。
    可以用于：日志记录、通知推送、数据收集等。
    """
    
    PLUGIN_NAME = "demo_hook"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Star Team"
    PLUGIN_DESCRIPTION = "示例钩子插件 - 演示任务生命周期钩子"
    
    def __init__(self):
        self._event_log = []
    
    def on_nova_create(self, nova) -> None:
        """新星创建时"""
        event = f"[创建] 新星诞生: {nova.id} - {nova.title}"
        self._event_log.append(event)
        print(event)
    
    def on_nova_launch(self, nova, star_body) -> bool:
        """
        新星发射前
        
        返回 False 可阻止发射
        """
        event = f"[发射] 任务 {nova.id} 分配给 {star_body.star_type}"
        self._event_log.append(event)
        print(event)
        return True  # 允许发射
    
    def on_nova_shine(self, nova, star_body) -> None:
        """新星开始闪耀时"""
        event = f"[闪耀] 任务 {nova.id} 开始执行"
        self._event_log.append(event)
        print(event)
    
    def on_starlight_received(self, nova, content: str) -> None:
        """收到星辉时"""
        # 只记录前 50 个字符
        preview = content[:50] + "..." if len(content) > 50 else content
        event = f"[输出] 任务 {nova.id}: {preview}"
        self._event_log.append(event)
        # 注意：这里不打印，避免输出太多
    
    def on_nova_complete(self, nova) -> None:
        """新星完成时"""
        event = f"[完成] 任务 {nova.id} 已成星"
        self._event_log.append(event)
        print(event)
    
    def on_nova_fade(self, nova, reason: str) -> None:
        """新星失败时"""
        event = f"[失败] 任务 {nova.id} 暗淡: {reason}"
        self._event_log.append(event)
        print(event)
