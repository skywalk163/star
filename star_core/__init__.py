"""
星核（Star Core）- 群星调度核心引擎

采用容错导入策略：各子模块独立导入，单个模块失败不阻断其他模块。
这样 CDP 桥等轻量模块可在缺少 win32gui/cv2 等可选依赖时正常使用。
"""

import importlib
import logging

logger = logging.getLogger(__name__)

__all__ = []

#: 各子模块及其要导出的符号
_MODULE_EXPORTS: list[tuple[str, list[str]]] = [
    ("star_core.star_seeker", ["StarSeeker"]),
    ("star_core.models", ["StarBody", "StarWindow", "StarWindowContext", "AuditLogEntry"]),
    ("star_core.star_assigner", ["StarAssigner"]),
    ("star_core.star_gazer", ["StarGazer"]),
    ("star_core.ocr_gazer", ["OCRGazer", "OCRResult", "check_ocr_dependencies"]),
    (
        "star_core.orbit_engine",
        [
            "OrbitEngine", "Nova", "Constellation", "ConstellationStatus",
            "StarStatus", "StarPriority", "ConstellationStorage", "ResultComparator",
        ],
    ),
    (
        "star_core.star_emissary",
        [
            "StarEmissary", "StarAdapter", "StarAdapterConfig",
            "InteractionTurn", "InteractionStatus", "CompletionStrategy",
            "MultiEmissary", "PRESET_ADAPTERS",
        ],
    ),
    ("star_core.log_reader", ["LogReader", "LogReadResult", "LogEntry", "get_reader"]),
]

for _module_name, _symbols in _MODULE_EXPORTS:
    try:
        _mod = importlib.import_module(_module_name)
        for _sym in _symbols:
            if hasattr(_mod, _sym):
                globals()[_sym] = getattr(_mod, _sym)
                __all__.append(_sym)
            else:
                logger.warning("star_core: %s 中未找到符号 %s", _module_name, _sym)
    except ImportError as _e:
        logger.warning("star_core: 跳过 %s（可选依赖缺失: %s）", _module_name, _e)
