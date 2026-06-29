"""
示例星体插件 - Demo Star Plugin

展示如何创建自定义星体插件
"""

from star_core.plugin_system import StarPlugin


class DemoStarPlugin(StarPlugin):
    """
    示例星体插件 - 演示自定义星体类型
    
    这个插件展示了如何添加一个新的星体类型支持。
    在实际使用中，请根据你的 Agent 修改签名信息。
    """
    
    # 插件元信息
    PLUGIN_NAME = "demo_star"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Star Team"
    PLUGIN_DESCRIPTION = "示例星体插件 - 演示如何添加自定义 Agent 支持"
    
    # 星体签名（用于识别进程）
    STAR_TYPE = "demo_agent"
    PROCESS_NAMES = ["DemoAgent.exe", "demo-agent.exe"]
    WINDOW_CLASS = ["Chrome_WidgetWin_1"]
    WINDOW_TITLE_PATTERNS = ["Demo Agent", "DemoAgent"]
    DESCRIPTION = "示例 Agent - 用于演示插件系统"
    
    # 亲缘性关键词（影响智能路由）
    AFFINITY_KEYWORDS = ["示例", "demo", "测试", "test"]
    AFFINITY_WEIGHT = 0.5  # 权重较低，作为示例
    
    def get_star_signature(self) -> dict:
        """返回星体签名"""
        return {
            "process_names": self.PROCESS_NAMES,
            "window_class": self.WINDOW_CLASS,
            "window_title_patterns": self.WINDOW_TITLE_PATTERNS,
            "description": self.DESCRIPTION
        }
    
    def on_launch(self, star_body, nova) -> bool:
        """
        发射前钩子 - 可以在这里做自定义预处理
        
        返回 False 可以阻止发射
        """
        # 示例：打印一条日志
        print(f"[DemoStar] 即将发射任务 {nova.id} 到 {star_body.star_type}")
        return True
    
    def on_complete(self, star_body, nova) -> None:
        """完成后钩子"""
        print(f"[DemoStar] 任务 {nova.id} 已完成")
