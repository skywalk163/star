"""
星核（Star Core）- 群星调度核心引擎
"""

from star_core.star_seeker import StarSeeker, StarBody
from star_core.star_assigner import StarAssigner
from star_core.star_gazer import StarGazer
from star_core.ocr_gazer import OCRGazer, OCRResult, check_ocr_dependencies
from star_core.orbit_engine import (
    OrbitEngine, Nova, Constellation, ConstellationStatus,
    StarStatus, StarPriority, ConstellationStorage, ResultComparator
)
from star_core.star_emissary import (
    StarEmissary, StarAdapter, StarAdapterConfig,
    InteractionTurn, InteractionStatus, CompletionStrategy,
    MultiEmissary, PRESET_ADAPTERS,
)

from star_core.log_reader import LogReader, LogReadResult, LogEntry, get_reader

__all__ = [
    "StarSeeker",
    "StarBody",
    "StarAssigner",
    "StarGazer",
    "OCRGazer",
    "OCRResult",
    "check_ocr_dependencies",
    "OrbitEngine",
    "Nova",
    "Constellation",
    "ConstellationStatus",
    "StarStatus",
    "StarPriority",
    "ConstellationStorage",
    "ResultComparator",
    "StarEmissary",
    "StarAdapter",
    "StarAdapterConfig",
    "InteractionTurn",
    "InteractionStatus",
    "CompletionStrategy",
    "MultiEmissary",
    "PRESET_ADAPTERS",
    "LogReader",
    "LogReadResult",
    "LogEntry",
    "get_reader",
]
