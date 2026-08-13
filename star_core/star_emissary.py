"""
星使（StarEmissary）- 星体交互闭环

普适化的 Agent 交互框架：
- 文本注入（剪贴板+键盘输入）
- 输出捕获（OCR+状态检测）
- 对话轮次管理
- 可扩展的星体适配器系统

适用于任何有输入框和输出区域的 GUI 应用
"""

import time
import re
import uuid
from typing import Optional, Callable, Any, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from loguru import logger

from star_core.star_seeker import StarBody
from star_core.star_assigner import StarAssigner, AssignStrategy
from star_core.ocr_gazer import OCRGazer, OCRResult, TaskItem, PRESET_REGIONS
from star_core.observatory import Observatory
from star_core.log_reader import LogReader, get_reader

if TYPE_CHECKING:
    from star_core.interaction import InteractionSession


class InteractionStatus(Enum):
    """交互状态"""
    IDLE = "idle"           # 空闲
    SENDING = "sending"     # 正在发送指令
    WAITING = "waiting"     # 等待响应
    READING = "reading"     # 正在读取结果
    COMPLETED = "completed" # 完成
    TIMEOUT = "timeout"     # 超时
    ERROR = "error"         # 错误


class CompletionStrategy(Enum):
    """完成检测策略"""
    STATUS_KEYWORD = "status_keyword"   # 基于状态关键词
    STABLE_CONTENT = "stable_content"   # 基于内容稳定（连续多次相同）
    NO_CHANGE = "no_change"             # 基于无变化（图像差异）
    KEYWORD_APPEAR = "keyword_appear"   # 基于指定关键词出现
    MANUAL = "manual"                   # 手动触发


@dataclass
class InteractionTurn:
    """
    一次对话轮次
    
    Attributes:
        turn_id: 轮次 ID
        prompt: 发送的指令
        response: 收到的响应
        response_source: 响应来源（log/ocr）
        status: 状态
        start_time: 开始时间
        end_time: 结束时间
        metadata: 附加信息
    """
    turn_id: str
    prompt: str
    response: str = ""
    response_source: str = "unknown"  # log / ocr / unknown
    status: InteractionStatus = InteractionStatus.IDLE
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    metadata: dict = field(default_factory=dict)
    
    @property
    def duration(self) -> float:
        """持续时间（秒）"""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return (datetime.now() - self.start_time).total_seconds()


@dataclass
class StarAdapterConfig:
    """
    星体适配器配置
    
    定义不同 Agent 应用的交互特征，使交互闭环能够自适应
    """
    name: str = "generic"
    
    # 输入区域配置
    input_click_x_ratio: float = 0.5    # 输入框点击位置 x 比例
    input_click_y_ratio: float = 0.92   # 输入框点击位置 y 比例
    use_clipboard: bool = True          # 是否使用剪贴板粘贴
    press_enter: bool = True            # 是否按回车发送
    send_delay: float = 0.2             # 发送后等待时间
    
    # 输出区域配置
    output_region: str = "center_chat"  # 输出区域（预设区域名）
    
    # 完成检测配置
    completion_strategy: CompletionStrategy = CompletionStrategy.STABLE_CONTENT
    completion_keywords: list[str] = field(default_factory=lambda: [
        "完成", "已完成", "任务完成", "成功", "就绪",
        "Done", "Complete", "Success", "Ready"
    ])
    running_keywords: list[str] = field(default_factory=lambda: [
        "运行中", "执行中", "进行中", "处理中", "生成中",
        "思考中", "编写中", "搜索中", "分析中", "正在",
        "thinking", "generating", "processing", "running"
    ])
    stable_count: int = 3               # 内容稳定次数（连续相同次数）
    check_interval: float = 2.0         # 检查间隔（秒）
    timeout: float = 300.0              # 超时时间（秒）
    no_change_threshold: float = 0.005  # 无变化阈值
    
    # OCR 配置
    ocr_lang: str = "ch"
    ocr_det_limit: int = 960
    ocr_min_confidence: float = 0.5
    use_incremental_ocr: bool = True
    
    # 注入策略
    inject_strategies: list[AssignStrategy] = field(default_factory=lambda: [
        AssignStrategy.CLIPBOARD,
        AssignStrategy.WIN32,
    ])


# 预设的星体适配器配置
PRESET_ADAPTERS: dict[str, StarAdapterConfig] = {
    "generic": StarAdapterConfig(
        name="generic",
        output_region="center_content",
    ),
    "trae": StarAdapterConfig(
        name="trae",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "任务完成", "已完成", "完成", "成功", "就绪",
            "passed", "✅"
        ],
        running_keywords=[
            "运行中", "执行中", "进行中", "处理中", "生成中",
            "思考中", "编写中", "搜索中", "分析中", "正在",
            "思考", "生成", "处理"
        ],
        stable_count=2,
        check_interval=3.0,
        timeout=300.0,
        ocr_lang="ch",
        ocr_det_limit=960,
    ),
    "chatgpt": StarAdapterConfig(
        name="chatgpt",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.95,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=["Regenerate", "Copy", "重新生成", "复制"],
        running_keywords=[],
        stable_count=3,
        check_interval=2.0,
        timeout=600.0,
        ocr_lang="en",
    ),
    "cursor": StarAdapterConfig(
        name="cursor",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.9,
        output_region="center_content",
        completion_strategy=CompletionStrategy.NO_CHANGE,
        stable_count=2,
        check_interval=2.0,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "claude": StarAdapterConfig(
        name="claude",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.94,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "Regenerate", "Copy", "Edit", "重新生成", "复制",
            "Use model", "切换模型", "New chat", "新对话"
        ],
        running_keywords=[
            "Claude is thinking", "Thinking...", "思考中",
            "Generating", "生成中", "Processing", "处理中"
        ],
        stable_count=3,
        check_interval=2.5,
        timeout=600.0,
        ocr_lang="en",
    ),
    "gemini": StarAdapterConfig(
        name="gemini",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "Regenerate", "Copy", "Edit", "重新生成", "复制",
            "Share", "分享", "New chat", "新对话"
        ],
        running_keywords=[
            "Gemini is thinking", "Thinking...", "思考中",
            "Generating", "生成中", "Processing", "处理中"
        ],
        stable_count=3,
        check_interval=2.5,
        timeout=600.0,
        ocr_lang="en",
    ),
    "windsurf": StarAdapterConfig(
        name="windsurf",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.92,
        output_region="center_content",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "Regenerate", "Copy", "重新生成", "复制",
            "Apply", "应用", "Accept", "接受"
        ],
        running_keywords=[
            "Thinking", "思考", "Generating", "生成中",
            "Planning", "规划中", "Editing", "编辑中"
        ],
        stable_count=2,
        check_interval=2.0,
        timeout=300.0,
        ocr_lang="en",
    ),
    "windsurf-cn": StarAdapterConfig(
        name="windsurf-cn",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.92,
        output_region="center_content",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "重新生成", "复制", "应用", "接受", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考", "生成中", "规划中", "编辑中", "Thinking", "Generating"
        ],
        stable_count=2,
        check_interval=2.0,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "doubao": StarAdapterConfig(
        name="doubao",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "已完成", "完成", "结束", "发送", "重新生成", "复制"
        ],
        running_keywords=[
            "豆包思考中", "生成中", "思考中", "处理中", "正在"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "kimi": StarAdapterConfig(
        name="kimi",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "已完成", "完成", "重新生成", "复制", "新对话"
        ],
        running_keywords=[
            "Kimi 思考中", "思考中", "生成中", "处理中", "正在", "写作中"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "tongyi": StarAdapterConfig(
        name="tongyi",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "已完成", "完成", "重新生成", "复制", "新对话", "通义千问"
        ],
        running_keywords=[
            "思考中", "生成中", "处理中", "正在", "写作中"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "github-copilot": StarAdapterConfig(
        name="github-copilot",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.9,
        output_region="center_content",
        completion_strategy=CompletionStrategy.NO_CHANGE,
        completion_keywords=[
            "Accept", "接受", "Reject", "拒绝", "Discard", "放弃"
        ],
        running_keywords=[
            "Generating", "生成中", "Thinking", "思考中"
        ],
        stable_count=2,
        check_interval=1.5,
        timeout=120.0,
        ocr_lang="en",
    ),
    "codegeex": StarAdapterConfig(
        name="codegeex",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.9,
        output_region="center_content",
        completion_strategy=CompletionStrategy.NO_CHANGE,
        completion_keywords=[
            "接受", "重新生成", "复制", "Accept", "Regenerate", "Copy"
        ],
        running_keywords=[
            "生成中", "思考中", "处理中", "Generating", "Thinking"
        ],
        stable_count=2,
        check_interval=2.0,
        timeout=180.0,
        ocr_lang="ch",
    ),
    "codearts_agent": StarAdapterConfig(
        name="codearts_agent",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.92,
        output_region="center_content",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "接受", "重新生成", "复制", "应用", "发送", "Accept", "Regenerate", "Copy", "Apply"
        ],
        running_keywords=[
            "生成中", "思考中", "处理中", "代码生成中", "编写中", "Generating", "Thinking"
        ],
        stable_count=3,
        check_interval=2.0,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "dumate": StarAdapterConfig(
        name="dumate",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "发送", "继续", "插入", "Regenerate", "Copy", "Insert"
        ],
        running_keywords=[
            "思考中", "生成中", "处理中", "代码生成中", "搭子思考中", "Thinking", "Generating"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "deepseek": StarAdapterConfig(
        name="deepseek",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "重新生成", "复制", "新对话", "Regenerate", "Copy", "New chat"
        ],
        running_keywords=[
            "思考中", "生成中", "DeepSeek 思考中", "Thinking", "Generating"
        ],
        stable_count=3,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    # ===== 国产 AI Agent =====
    "ernie": StarAdapterConfig(
        name="ernie",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "清空", "发送", "已收到", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "处理中", "正在思考", "正在生成", "思考中..."
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "spark": StarAdapterConfig(
        name="spark",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新回答", "复制", "继续", "发送", "追问", "重新提问"
        ],
        running_keywords=[
            "思考中", "生成中", "处理中", "星火正在", "正在为您", "加载中"
        ],
        stable_count=2,
        check_interval=2.0,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "glm": StarAdapterConfig(
        name="glm",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "重新生成", "复制", "清空", "新对话", "继续", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "GLM 思考中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=3,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "step": StarAdapterConfig(
        name="step",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "继续", "继续追问", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "分析中", "Step 思考中", "正在思考", "正在分析"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "wanzhi": StarAdapterConfig(
        name="wanzhi",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "继续", "创建", "编辑", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "万知思考中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "shangliang": StarAdapterConfig(
        name="shangliang",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "继续", "继续追问", "清空", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "商量中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "hailuo": StarAdapterConfig(
        name="hailuo",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "发送", "继续", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "海螺思考中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "baichuan": StarAdapterConfig(
        name="baichuan",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STABLE_CONTENT,
        completion_keywords=[
            "重新生成", "复制", "清空", "新对话", "继续", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "百川思考中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=3,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
    "qwen": StarAdapterConfig(
        name="qwen",
        input_click_x_ratio=0.5,
        input_click_y_ratio=0.93,
        output_region="center_chat",
        completion_strategy=CompletionStrategy.STATUS_KEYWORD,
        completion_keywords=[
            "重新生成", "复制", "清空", "新对话", "继续", "发送", "Regenerate", "Copy"
        ],
        running_keywords=[
            "思考中", "生成中", "通义思考中", "处理中", "正在思考", "正在生成"
        ],
        stable_count=2,
        check_interval=2.5,
        timeout=300.0,
        ocr_lang="ch",
    ),
}


class StarAdapter:
    """
    星体适配器
    
    封装特定 Agent 应用的交互特征，
    为 StarEmissary 提供统一的适配接口。
    """
    
    def __init__(self, config: Optional[StarAdapterConfig] = None):
        self.config = config or StarAdapterConfig()
    
    @classmethod
    def from_name(cls, name: str) -> 'StarAdapter':
        """从预设名称创建适配器"""
        config = PRESET_ADAPTERS.get(name.lower())
        if config:
            return cls(config)
        return cls(StarAdapterConfig(name=name))
    
    @classmethod
    def from_star_type(cls, star_type: str) -> 'StarAdapter':
        """根据星体类型自动选择适配器"""
        mapping = {
            "trae": "trae",
            "chatgpt": "chatgpt",
            "cursor": "cursor",
            "claude": "claude",
            "gemini": "gemini",
            "windsurf": "windsurf",
            "doubao": "doubao",
            "kimi": "kimi",
            "tongyi": "tongyi",
            "deepseek": "deepseek",
            "codegeex": "codegeex",
            "copilot": "github-copilot",
            "codearts_agent": "codearts_agent",
            "codearts": "codearts_agent",
            "华为云": "codearts_agent",
            "dumate": "dumate",
            "搭子": "dumate",
            # 国产 AI Agent
            "ernie": "ernie",
            "yiyan": "ernie",
            "文心": "ernie",
            "baidu": "ernie",
            "spark": "spark",
            "星火": "spark",
            "xunfei": "spark",
            "glm": "glm",
            "zhipu": "glm",
            "智谱": "glm",
            "step": "step",
            "跃问": "step",
            "stepfun": "step",
            "wanzhi": "wanzhi",
            "万知": "wanzhi",
            "shangliang": "shangliang",
            "商量": "shangliang",
            "sensetime": "shangliang",
            "hailuo": "hailuo",
            "海螺": "hailuo",
            "minimax": "hailuo",
            "baichuan": "baichuan",
            "百川": "baichuan",
            "qwen": "qwen",
            "通义": "qwen",
            "tongyiqianwen": "qwen",
        }
        adapter_name = mapping.get(star_type.lower(), "generic")
        return cls.from_name(adapter_name)
    
    def get_input_click_position(self, window_width: int, window_height: int) -> tuple[int, int]:
        """获取输入框点击位置（屏幕坐标）"""
        x = int(window_width * self.config.input_click_x_ratio)
        y = int(window_height * self.config.input_click_y_ratio)
        return (x, y)
    
    def get_output_region_name(self) -> str:
        """获取输出区域名称"""
        return self.config.output_region
    
    def is_complete(self, text: str, stable_rounds: int = 0) -> bool:
        """
        检测任务是否完成
        
        Args:
            text: 当前识别到的文本
            stable_rounds: 内容稳定次数
            
        Returns:
            是否完成
        """
        strategy = self.config.completion_strategy
        
        if strategy == CompletionStrategy.STATUS_KEYWORD:
            return self._check_completion_keywords(text)
        elif strategy == CompletionStrategy.STABLE_CONTENT:
            return stable_rounds >= self.config.stable_count
        elif strategy == CompletionStrategy.KEYWORD_APPEAR:
            return self._check_completion_keywords(text)
        else:
            return stable_rounds >= self.config.stable_count
    
    def is_running(self, text: str) -> bool:
        """检测是否正在运行"""
        text_lower = text.lower()
        for kw in self.config.running_keywords:
            if kw.lower() in text_lower:
                return True
        return False
    
    def _check_completion_keywords(self, text: str) -> bool:
        """检查完成关键词"""
        text_lower = text.lower()
        for kw in self.config.completion_keywords:
            if kw.lower() in text_lower:
                return True
        return False


class StarEmissary:
    """
    星使 - 星体交互闭环管理器
    
    实现文本注入 → 等待响应 → 捕获输出 → 上下文管理
    的完整交互闭环，支持任意有 GUI 的 Agent 应用。
    
    使用方式：
    ```python
    emissary = StarEmissary(star, adapter_name="trae")
    
    # 单次问答
    response = emissary.ask("解释一下什么是星核")
    
    # 多轮对话
    for turn in emissary.history:
        print(f"{turn.prompt} -> {turn.response[:50]}")
    ```
    """
    
    def __init__(
        self,
        star: StarBody,
        adapter: Optional[StarAdapter] = None,
        adapter_name: Optional[str] = None,
        assigner: Optional[StarAssigner] = None,
        ocr_gazer: Optional[OCRGazer] = None,
        observatory: Optional[Observatory] = None,
        interaction: Optional[Any] = None,
    ):
        """
        Initialize the emissary.
        
        Args:
            star: Target star body.
            adapter: Star adapter (takes priority).
            adapter_name: Adapter preset name.
            assigner: Star assigner for text injection.
            ocr_gazer: OCR gazer for output capture.
            observatory: Observatory for window management.
            interaction: InteractionSession for locator-based interaction.
                If None, attempts to load from config_service.
        """
        self.star = star
        self.observatory = observatory or Observatory()
        self.assigner = assigner or StarAssigner(self.observatory)
        
        # Adapter
        if adapter:
            self.adapter = adapter
        elif adapter_name:
            self.adapter = StarAdapter.from_name(adapter_name)
        else:
            self.adapter = StarAdapter.from_star_type(star.star_type)
        
        # OCR
        if ocr_gazer:
            self.ocr = ocr_gazer
        else:
            cfg = self.adapter.config
            self.ocr = OCRGazer(
                lang=cfg.ocr_lang,
                det_limit_side_len=cfg.ocr_det_limit,
                min_confidence=cfg.ocr_min_confidence,
                use_incremental=cfg.use_incremental_ocr,
            )
        
        # Interaction session
        self.interaction = interaction
        self._cdp_bridge: Optional[Any] = None
        self._cdp_url_pattern: Optional[str] = None
        if self.interaction is None:
            try:
                from star_core.config_service import get_config_service
                from star_core.interaction import InteractionSession
                cfg_service = get_config_service()
                # 浏览器 agent（category==browser 或带 cdp 段）自动注入 CDP bridge
                agent_cfg = cfg_service.get_agent(star.star_type) or {}
                cdp_cfg = agent_cfg.get("cdp") or {}
                bridge = None
                if cdp_cfg.get("url_pattern"):
                    from star_core.cdp_bridge import CDPBridge
                    port = int(cdp_cfg.get("port", 9222) or 9222)
                    bridge = CDPBridge(port=port)
                    self._cdp_bridge = bridge
                    self._cdp_url_pattern = cdp_cfg.get("url_pattern")
                ic = cfg_service.get_interaction_config(star.star_type)
                if ic is not None:
                    self.interaction = InteractionSession(
                        config=ic, bridge=bridge, ocr=self.ocr
                    )
            except Exception:
                pass
        
        # 对话历史
        self.history: list[InteractionTurn] = []
        self._current_turn: Optional[InteractionTurn] = None
        
        # 状态
        self.status = InteractionStatus.IDLE
        self._last_text: str = ""
        self._stable_count: int = 0
        
        # 回调
        self.on_status_change: Optional[Callable[[InteractionStatus], None]] = None
        self.on_progress: Optional[Callable[[str], None]] = None
    
    def _build_interaction_ctx(self):
        """构造交互上下文：桌面 agent 带 hwnd，浏览器 agent 自动装配 cdptab。"""
        try:
            from star_core.interaction import WindowContext
        except ImportError:
            return None
        cdptab = None
        if self._cdp_bridge is not None and self._cdp_url_pattern:
            try:
                cdptab = self._cdp_bridge.find_tab(self._cdp_url_pattern)
            except Exception:
                cdptab = None
        return WindowContext(
            hwnd=self.star.hwnd,
            star=self.star,
            cdptab=cdptab,
            min_confidence=0.3,
        )

    def _set_status(self, status: InteractionStatus):
        """设置状态并触发回调"""
        self.status = status
        if self.on_status_change:
            try:
                self.on_status_change(status)
            except Exception:
                pass
    
    def _get_window_size(self) -> tuple[int, int]:
        """获取窗口大小"""
        rect = self.observatory.get_window_rect(self.star.hwnd)
        if rect:
            left, top, right, bottom = rect
            return (right - left, bottom - top)
        return (1440, 900)
    
    def _get_window_rect(self) -> Optional[tuple[int, int, int, int]]:
        """Get window rect (left, top, right, bottom)."""
        return self.observatory.get_window_rect(self.star.hwnd)
    
    def _click_input_area(self, box: Any = None) -> bool:
        """
        Click the input area to focus it.
        
        Args:
            box: ElementBox from locator. If provided, click at box center.
                 If None, use legacy ratio-based position.
        
        Returns:
            True if click succeeded.
        """
        try:
            import win32gui
            import win32api
            import win32con
            
            rect = self._get_window_rect()
            if not rect:
                return False
            
            left, top, right, bottom = rect
            w, h = right - left, bottom - top
            
            if box is not None:
                # Use locator box center (absolute screen coords)
                abs_x = box.x + box.width // 2
                abs_y = box.y + box.height // 2
            else:
                # Legacy ratio-based position
                rel_x, rel_y = self.adapter.get_input_click_position(w, h)
                abs_x = left + rel_x
                abs_y = top + rel_y
            
            # Activate window
            self.observatory.set_foreground_window(self.star.hwnd)
            time.sleep(0.15)
            
            # Move mouse and click
            win32api.SetCursorPos((abs_x, abs_y))
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, abs_x, abs_y, 0, 0)
            time.sleep(0.05)
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, abs_x, abs_y, 0, 0)
            time.sleep(0.1)
            
            return True
        except Exception:
            return False
    
    def _paste_text(self, text: str) -> bool:
        """
        使用剪贴板粘贴文本到当前焦点
        
        Args:
            text: 要粘贴的文本
            
        Returns:
            是否成功
        """
        try:
            import win32api
            import win32con
            import pyperclip
            
            # 备份剪贴板
            backup = pyperclip.paste()
            
            try:
                # 复制到剪贴板
                pyperclip.copy(text)
                time.sleep(0.05)
                
                # Ctrl+V 粘贴
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                time.sleep(0.02)
                win32api.keybd_event(ord('V'), 0, 0, 0)
                time.sleep(0.05)
                win32api.keybd_event(ord('V'), 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.02)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.1)
                
                return True
            finally:
                # 恢复剪贴板
                pyperclip.copy(backup)
                
        except Exception:
            return False
    
    def _press_enter(self) -> bool:
        """Press the Enter key."""
        try:
            import win32api
            import win32con
            
            win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            time.sleep(0.1)
            return True
        except Exception:
            return False
    
    def stop_current(self):
        """
        Stop current generation.
        
        When interaction session is available, delegates to
        interaction.stop_current() (button priority, key fallback).
        Otherwise, uses keyboard Esc as fallback.
        
        Returns:
            StopResult with ok, via, and reason.
        """
        if self.interaction is not None:
            try:
                from star_core.interaction import WindowContext, StopResult
                ctx = self._build_interaction_ctx()
                result = self.interaction.stop_current(ctx)
                if result.ok:
                    self._set_status(InteractionStatus.IDLE)
                    return result
                # If interaction failed, fall through to keyboard fallback
            except Exception:
                pass
        
        # Fallback: keyboard Esc
        try:
            import win32api
            import win32con
            self.observatory.set_foreground_window(self.star.hwnd)
            time.sleep(0.1)
            win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
            time.sleep(0.05)
            win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
            self._set_status(InteractionStatus.IDLE)
            from star_core.interaction import StopResult
            return StopResult(ok=True, via="keys")
        except Exception:
            from star_core.interaction import StopResult
            return StopResult(ok=False, reason="esc_failed")
    
    def send_prompt(self, prompt: str) -> bool:
        """
        Send a prompt without waiting for response.
        
        When interaction session is available, uses locator chain to find
        the input box. Falls back to legacy ratio-based click otherwise.
        
        Args:
            prompt: Text to send.
            
        Returns:
            True if send succeeded.
        """
        self._set_status(InteractionStatus.SENDING)
        
        # Create turn
        turn = InteractionTurn(
            turn_id=str(uuid.uuid4())[:8],
            prompt=prompt,
            status=InteractionStatus.SENDING,
        )
        self._current_turn = turn
        self.history.append(turn)
        
        # Try to locate input via interaction session
        interaction_box = None
        if self.interaction is not None:
            try:
                from star_core.interaction import WindowContext
                ctx = self._build_interaction_ctx()
                interaction_box = self.interaction.locate("input", ctx)
            except Exception:
                interaction_box = None
        
        # 1. Click input area (with box if located, legacy ratio otherwise)
        clicked = self._click_input_area(box=interaction_box)
        if not clicked:
            self.observatory.set_foreground_window(self.star.hwnd)
            time.sleep(0.2)
        
        # 2. Paste text
        pasted = self._paste_text(prompt)
        if not pasted:
            # Fallback: use StarAssigner
            pasted = self.assigner.send_starlight(
                self.star,
                prompt,
                strategy_priority=self.adapter.config.inject_strategies,
            )
        
        # 3. Press enter
        if pasted and self.adapter.config.press_enter:
            self._press_enter()
        
        if pasted:
            turn.status = InteractionStatus.WAITING
            self._set_status(InteractionStatus.WAITING)
            self._last_text = ""
            self._stable_count = 0
            time.sleep(self.adapter.config.send_delay)
        else:
            turn.status = InteractionStatus.ERROR
            self._set_status(InteractionStatus.ERROR)
        
        return pasted
    
    def _capture_output(self) -> str:
        """
        捕获当前输出（双引擎策略）
        
        策略：
        1. ⚡ 日志读取（毫秒级）- 直接读取日志文件
        2. 📷 OCR 识别（秒级）- 截图 + OCR 兜底
        """
        # 策略 1: 日志读取（快）
        try:
            reader = get_reader()
            log_files = reader.find_logs_for_star(self.star)
            if log_files:
                log_result = reader.read_recent(log_files, max_lines=50)
                if log_result.latest_text:
                    logger.debug(f"[星使] 日志读取捕获到响应 ({log_result.elapsed_ms:.1f}ms)")
                    # 记录来源
                    self._current_turn.response = log_result.latest_text
                    self._current_turn.response_source = "log"
                    return log_result.latest_text
        except Exception as e:
            logger.debug(f"[星使] 日志读取失败: {e}")
        
        # 策略 2: OCR 识别（慢）
        region = self.adapter.get_output_region_name()
        try:
            result = self.ocr.gaze_region(self.star, region)
            if result.text:
                self._current_turn.response_source = "ocr"
            return result.text
        except Exception:
            return ""
    
    def _check_completion(self, text: str) -> bool:
        """检查是否完成"""
        # 检查内容是否稳定
        if text and text == self._last_text:
            self._stable_count += 1
        else:
            self._stable_count = 0
            self._last_text = text
            # 触发进度回调
            if self.on_progress:
                try:
                    self.on_progress(text)
                except Exception:
                    pass
        
        # 使用适配器判断
        return self.adapter.is_complete(text, self._stable_count)
    
    def wait_for_response(self, timeout: Optional[float] = None) -> str:
        """
        等待响应并返回结果
        
        Args:
            timeout: 超时时间（秒），默认使用配置中的值
            
        Returns:
            响应文本
        """
        if self.status != InteractionStatus.WAITING:
            return ""
        
        timeout = timeout or self.adapter.config.timeout
        interval = self.adapter.config.check_interval
        start_time = time.time()
        
        self._set_status(InteractionStatus.WAITING)
        
        while time.time() - start_time < timeout:
            text = self._capture_output()
            
            if self._check_completion(text):
                # 再等一下确认稳定
                time.sleep(interval * 0.5)
                text = self._capture_output()
                
                if self._check_completion(text):
                    break
            
            time.sleep(interval)
        
        # 最终读取
        final_text = self._capture_output()
        
        # 更新轮次
        if self._current_turn:
            self._current_turn.response = final_text
            self._current_turn.end_time = datetime.now()
            
            if time.time() - start_time >= timeout:
                self._current_turn.status = InteractionStatus.TIMEOUT
                self._set_status(InteractionStatus.TIMEOUT)
            else:
                self._current_turn.status = InteractionStatus.COMPLETED
                self._set_status(InteractionStatus.COMPLETED)
        else:
            self._set_status(InteractionStatus.IDLE)
        
        return final_text
    
    def ask(self, prompt: str, timeout: Optional[float] = None) -> str:
        """
        一次完整的问答：发送指令 → 等待响应 → 返回结果
        
        Args:
            prompt: 要发送的指令
            timeout: 超时时间（秒）
            
        Returns:
            响应文本
        """
        success = self.send_prompt(prompt)
        if not success:
            return ""
        
        return self.wait_for_response(timeout)
    
    def ask_stream(
        self,
        prompt: str,
        on_chunk: Callable[[str], None],
        timeout: Optional[float] = None
    ) -> str:
        """
        流式问答：边生成边回调
        
        Args:
            prompt: 要发送的指令
            on_chunk: 每次获取到新内容时的回调函数
            timeout: 超时时间
            
        Returns:
            最终响应文本
        """
        old_progress = self.on_progress
        self.on_progress = on_chunk
        
        try:
            return self.ask(prompt, timeout)
        finally:
            self.on_progress = old_progress
    
    def get_task_list(self) -> list[TaskItem]:
        """获取任务列表"""
        try:
            return self.ocr.get_task_list(self.star)
        except Exception:
            return []
    
    def get_todo_list(self) -> list[TaskItem]:
        """获取待办列表"""
        try:
            return self.ocr.get_todo_list(self.star)
        except Exception:
            return []
    
    def get_current_status(self) -> dict:
        """获取当前状态"""
        try:
            return self.ocr.get_current_status(self.star)
        except Exception:
            return {"status": "unknown", "is_active": False}
    
    def clear_history(self):
        """清空对话历史"""
        self.history.clear()
        self._current_turn = None
        self.status = InteractionStatus.IDLE
    
    @property
    def last_turn(self) -> Optional[InteractionTurn]:
        """获取最后一轮对话"""
        return self.history[-1] if self.history else None
    
    def __repr__(self) -> str:
        return (
            f"StarEmissary(star={self.star.star_type}, "
            f"adapter={self.adapter.config.name}, "
            f"history={len(self.history)} turns, "
            f"status={self.status.value})"
        )


class MultiEmissary:
    """
    众星使 - 多星体协同交互
    
    管理多个 StarEmissary，支持多 Agent 并行/串行任务
    """
    
    def __init__(self):
        self.emissaries: dict[str, StarEmissary] = {}
    
    def add(self, star: StarBody, adapter_name: Optional[str] = None) -> str:
        """
        添加星体
        
        Returns:
            星体 ID
        """
        emissary = StarEmissary(star, adapter_name=adapter_name)
        self.emissaries[star.star_id] = emissary
        return star.star_id
    
    def remove(self, star_id: str):
        """移除星体"""
        self.emissaries.pop(star_id, None)
    
    def ask_all(self, prompt: str, parallel: bool = True) -> dict[str, str]:
        """
        向所有星体发送同一指令
        
        Args:
            prompt: 指令
            parallel: 是否并行执行
            
        Returns:
            {star_id: response}
        """
        results = {}
        
        if parallel:
            # 先全部发送
            for sid, em in self.emissaries.items():
                em.send_prompt(prompt)
            
            # 再分别等待
            for sid, em in self.emissaries.items():
                results[sid] = em.wait_for_response()
        else:
            for sid, em in self.emissaries.items():
                results[sid] = em.ask(prompt)
        
        return results
    
    def get(self, star_id: str) -> Optional[StarEmissary]:
        """获取指定星体的星使"""
        return self.emissaries.get(star_id)
    
    @property
    def count(self) -> int:
        return len(self.emissaries)
