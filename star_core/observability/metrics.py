"""
metrics.py - 指标收集与管理

提供统一的指标收集接口，支持：
- Counter（计数器）
- Gauge（仪表盘）
- Histogram（直方图，简化版）
"""

import time
import threading
from typing import Dict, Any, Optional, List
from collections import defaultdict


class Counter:
    """计数器 - 只增不减"""
    
    def __init__(self, name: str, description: str = "", label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None):
        if amount < 0:
            raise ValueError("Counter amount must be non-negative")
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] += amount
    
    def get(self, labels: Dict[str, str] = None) -> float:
        key = self._labels_to_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            values = dict(self._values)
        return {
            'name': self.name,
            'type': 'counter',
            'description': self.description,
            'values': values,
            'label_names': self.label_names,
        }


class Gauge:
    """仪表盘 - 可增可减"""
    
    def __init__(self, name: str, description: str = "", label_names: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = label_names or []
        self._values: Dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def set(self, value: float, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] = value
    
    def inc(self, amount: float = 1.0, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] += amount
    
    def dec(self, amount: float = 1.0, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._values[key] -= amount
    
    def get(self, labels: Dict[str, str] = None) -> float:
        key = self._labels_to_key(labels)
        with self._lock:
            return self._values.get(key, 0.0)
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            values = dict(self._values)
        return {
            'name': self.name,
            'type': 'gauge',
            'description': self.description,
            'values': values,
            'label_names': self.label_names,
        }


class Histogram:
    """直方图 - 统计分布（简化版）"""
    
    def __init__(self, name: str, description: str = "", 
                 buckets: List[float] = None, label_names: List[str] = None):
        self.name = name
        self.description = description
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self.label_names = label_names or []
        self._sum: Dict[str, float] = defaultdict(float)
        self._count: Dict[str, int] = defaultdict(int)
        self._bucket_counts: Dict[str, List[int]] = defaultdict(lambda: [0] * len(self.buckets))
        self._lock = threading.Lock()
    
    def observe(self, value: float, labels: Dict[str, str] = None):
        key = self._labels_to_key(labels)
        with self._lock:
            self._sum[key] += value
            self._count[key] += 1
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._bucket_counts[key][i] += 1
    
    def _labels_to_key(self, labels: Dict[str, str] = None) -> str:
        if not labels:
            return ''
        return ','.join(f'{k}={v}' for k, v in sorted(labels.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'name': self.name,
                'type': 'histogram',
                'description': self.description,
                'buckets': self.buckets,
                'sum': dict(self._sum),
                'count': dict(self._count),
                'bucket_counts': {k: list(v) for k, v in self._bucket_counts.items()},
                'label_names': self.label_names,
            }


class MetricsRegistry:
    """指标注册表"""
    
    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._lock = threading.Lock()
    
    def counter(self, name: str, description: str = "", label_names: List[str] = None) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, label_names)
            return self._counters[name]
    
    def gauge(self, name: str, description: str = "", label_names: List[str] = None) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, label_names)
            return self._gauges[name]
    
    def histogram(self, name: str, description: str = "", 
                  buckets: List[float] = None, label_names: List[str] = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets, label_names)
            return self._histograms[name]
    
    def get_all(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'counters': {name: c.to_dict() for name, c in self._counters.items()},
                'gauges': {name: g.to_dict() for name, g in self._gauges.items()},
                'histograms': {name: h.to_dict() for name, h in self._histograms.items()},
            }


_global_registry: Optional[MetricsRegistry] = None
_init_lock = threading.Lock()


def get_metrics_registry() -> MetricsRegistry:
    """获取全局指标注册表"""
    global _global_registry
    if _global_registry is None:
        with _init_lock:
            if _global_registry is None:
                _global_registry = MetricsRegistry()
    return _global_registry
