"""
可观测性模块测试

测试 star_core.observability 中的：
- Counter / Gauge / Histogram 指标类型
- MetricsRegistry 指标注册表
- HealthChecker / HealthStatus 健康检查
- 全局单例 get_metrics_registry / get_health_checker
"""

import threading
import pytest

from star_core.observability.metrics import (
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    get_metrics_registry,
)
from star_core.observability.health import (
    HealthChecker,
    HealthStatus,
    get_health_checker,
)


# ========== Counter 测试 ==========

class TestCounter:
    """测试 Counter 计数器"""

    def test_create_counter(self):
        c = Counter("requests", "total requests")
        assert c.name == "requests"
        assert c.description == "total requests"
        assert c.label_names == []

    def test_create_counter_with_labels(self):
        c = Counter("requests", "total", label_names=["method", "status"])
        assert c.label_names == ["method", "status"]

    def test_inc_default(self):
        c = Counter("req")
        c.inc()
        assert c.get() == 1.0

    def test_inc_with_amount(self):
        c = Counter("req")
        c.inc(5)
        assert c.get() == 5.0

    def test_inc_multiple_times(self):
        c = Counter("req")
        c.inc()
        c.inc()
        c.inc(3)
        assert c.get() == 5.0

    def test_inc_float_amount(self):
        c = Counter("req")
        c.inc(0.5)
        c.inc(1.5)
        assert c.get() == 2.0

    def test_inc_negative_raises(self):
        c = Counter("req")
        with pytest.raises(ValueError):
            c.inc(-1)

    def test_inc_zero_allowed(self):
        c = Counter("req")
        c.inc(0)
        assert c.get() == 0.0

    def test_get_default_zero(self):
        c = Counter("req")
        assert c.get() == 0.0

    def test_inc_with_labels(self):
        c = Counter("requests", label_names=["method"])
        c.inc(labels={"method": "GET"})
        c.inc(labels={"method": "GET"})
        c.inc(labels={"method": "POST"})
        assert c.get(labels={"method": "GET"}) == 2.0
        assert c.get(labels={"method": "POST"}) == 1.0

    def test_get_with_unseen_labels(self):
        c = Counter("req")
        assert c.get(labels={"unknown": "x"}) == 0.0

    def test_to_dict(self):
        c = Counter("requests", "total", label_names=["method"])
        c.inc(labels={"method": "GET"})
        d = c.to_dict()
        assert d['name'] == "requests"
        assert d['type'] == "counter"
        assert d['description'] == "total"
        assert d['label_names'] == ["method"]
        assert '' not in d['values'] or d['values'].get('method=GET') == 1.0
        assert d['values']['method=GET'] == 1.0

    def test_to_dict_empty(self):
        c = Counter("empty")
        d = c.to_dict()
        assert d['name'] == "empty"
        assert d['type'] == "counter"
        assert d['values'] == {}


# ========== Gauge 测试 ==========

class TestGauge:
    """测试 Gauge 仪表盘"""

    def test_create_gauge(self):
        g = Gauge("memory", "memory usage")
        assert g.name == "memory"
        assert g.description == "memory usage"

    def test_set_value(self):
        g = Gauge("mem")
        g.set(42.5)
        assert g.get() == 42.5

    def test_set_overwrites(self):
        g = Gauge("mem")
        g.set(10)
        g.set(20)
        assert g.get() == 20.0

    def test_inc(self):
        g = Gauge("mem")
        g.set(10)
        g.inc(5)
        assert g.get() == 15.0

    def test_inc_default(self):
        g = Gauge("mem")
        g.set(10)
        g.inc()
        assert g.get() == 11.0

    def test_dec(self):
        g = Gauge("mem")
        g.set(10)
        g.dec(3)
        assert g.get() == 7.0

    def test_dec_default(self):
        g = Gauge("mem")
        g.set(10)
        g.dec()
        assert g.get() == 9.0

    def test_get_default_zero(self):
        g = Gauge("mem")
        assert g.get() == 0.0

    def test_set_with_labels(self):
        g = Gauge("cpu", label_names=["host"])
        g.set(50, labels={"host": "a"})
        g.set(80, labels={"host": "b"})
        assert g.get(labels={"host": "a"}) == 50.0
        assert g.get(labels={"host": "b"}) == 80.0

    def test_inc_dec_with_labels(self):
        g = Gauge("conn", label_names=["service"])
        g.inc(labels={"service": "db"})
        g.inc(labels={"service": "db"})
        g.dec(labels={"service": "db"})
        assert g.get(labels={"service": "db"}) == 1.0

    def test_to_dict(self):
        g = Gauge("memory", "mem usage")
        g.set(100)
        d = g.to_dict()
        assert d['name'] == "memory"
        assert d['type'] == "gauge"
        assert d['description'] == "mem usage"
        assert d['values'][''] == 100.0


# ========== Histogram 测试 ==========

class TestHistogram:
    """测试 Histogram 直方图"""

    def test_create_histogram(self):
        h = Histogram("latency", "request latency")
        assert h.name == "latency"
        assert h.description == "request latency"

    def test_default_buckets(self):
        h = Histogram("lat")
        assert len(h.buckets) == 11
        assert 0.005 in h.buckets
        assert 10.0 in h.buckets

    def test_custom_buckets(self):
        custom = [0.1, 0.5, 1.0, 5.0]
        h = Histogram("lat", buckets=custom)
        assert h.buckets == custom

    def test_observe_increases_count(self):
        h = Histogram("lat")
        h.observe(0.05)
        h.observe(0.1)
        d = h.to_dict()
        assert d['count'][''] == 2

    def test_observe_accumulates_sum(self):
        h = Histogram("lat")
        h.observe(0.5)
        h.observe(1.5)
        d = h.to_dict()
        assert d['sum'][''] == 2.0

    def test_observe_bucket_counts(self):
        h = Histogram("lat", buckets=[0.1, 0.5, 1.0])
        h.observe(0.05)   # 落入 0.1
        h.observe(0.3)    # 落入 0.5
        h.observe(0.7)    # 落入 1.0
        d = h.to_dict()
        # bucket_counts[i] 表示 <= buckets[i] 的样本数
        assert d['bucket_counts'][''][0] == 1   # <=0.1
        assert d['bucket_counts'][''][1] == 2   # <=0.5
        assert d['bucket_counts'][''][2] == 3   # <=1.0

    def test_observe_with_labels(self):
        h = Histogram("lat", label_names=["method"])
        h.observe(0.1, labels={"method": "GET"})
        h.observe(0.2, labels={"method": "GET"})
        h.observe(0.3, labels={"method": "POST"})
        d = h.to_dict()
        assert d['count']['method=GET'] == 2
        assert d['count']['method=POST'] == 1

    def test_to_dict_structure(self):
        h = Histogram("lat", "desc", buckets=[0.1, 1.0])
        h.observe(0.05)
        d = h.to_dict()
        assert d['name'] == "lat"
        assert d['type'] == "histogram"
        assert d['description'] == "desc"
        assert d['buckets'] == [0.1, 1.0]
        assert 'sum' in d
        assert 'count' in d
        assert 'bucket_counts' in d

    def test_observe_zero(self):
        h = Histogram("lat", buckets=[0.1])
        h.observe(0)
        d = h.to_dict()
        assert d['count'][''] == 1
        assert d['bucket_counts'][''][0] == 1


# ========== MetricsRegistry 测试 ==========

class TestMetricsRegistry:
    """测试 MetricsRegistry 指标注册表"""

    def test_create_registry(self):
        r = MetricsRegistry()
        assert r is not None

    def test_counter_create(self):
        r = MetricsRegistry()
        c = r.counter("requests", "total")
        assert isinstance(c, Counter)
        assert c.name == "requests"

    def test_counter_returns_same_instance(self):
        r = MetricsRegistry()
        c1 = r.counter("requests")
        c2 = r.counter("requests")
        assert c1 is c2

    def test_gauge_create(self):
        r = MetricsRegistry()
        g = r.gauge("memory", "mem")
        assert isinstance(g, Gauge)
        assert g.name == "memory"

    def test_gauge_returns_same_instance(self):
        r = MetricsRegistry()
        g1 = r.gauge("memory")
        g2 = r.gauge("memory")
        assert g1 is g2

    def test_histogram_create(self):
        r = MetricsRegistry()
        h = r.histogram("latency", "lat")
        assert isinstance(h, Histogram)
        assert h.name == "latency"

    def test_histogram_returns_same_instance(self):
        r = MetricsRegistry()
        h1 = r.histogram("latency")
        h2 = r.histogram("latency")
        assert h1 is h2

    def test_get_all_empty(self):
        r = MetricsRegistry()
        all_metrics = r.get_all()
        assert all_metrics == {'counters': {}, 'gauges': {}, 'histograms': {}}

    def test_get_all_with_data(self):
        r = MetricsRegistry()
        r.counter("req").inc()
        r.gauge("mem").set(50)
        r.histogram("lat").observe(0.1)
        all_metrics = r.get_all()
        assert 'req' in all_metrics['counters']
        assert 'mem' in all_metrics['gauges']
        assert 'lat' in all_metrics['histograms']
        assert all_metrics['counters']['req']['type'] == 'counter'
        assert all_metrics['gauges']['mem']['type'] == 'gauge'
        assert all_metrics['histograms']['lat']['type'] == 'histogram'

    def test_counter_and_gauge_independent(self):
        r = MetricsRegistry()
        c = r.counter("metric_name")
        g = r.gauge("metric_name")
        # 同名但不同类型应独立
        assert c is not g
        assert isinstance(c, Counter)
        assert isinstance(g, Gauge)

    def test_get_all_returns_serialized(self):
        r = MetricsRegistry()
        c = r.counter("req", "total")
        c.inc(5)
        all_metrics = r.get_all()
        # 应返回字典形式，而不是对象
        assert isinstance(all_metrics['counters']['req'], dict)
        assert all_metrics['counters']['req']['values'][''] == 5.0


# ========== HealthStatus 枚举测试 ==========

class TestHealthStatus:
    """测试 HealthStatus 枚举"""

    def test_enum_values(self):
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"

    def test_is_string_enum(self):
        assert HealthStatus.HEALTHY == "healthy"
        assert isinstance(HealthStatus.HEALTHY, str)

    def test_enum_members_count(self):
        assert len(HealthStatus) == 3


# ========== HealthChecker 测试 ==========

class TestHealthChecker:
    """测试 HealthChecker 健康检查器"""

    def test_create_checker(self):
        h = HealthChecker()
        assert h is not None

    def test_register_and_list(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("cache", lambda: HealthStatus.HEALTHY)
        checks = h.list_checks()
        assert "db" in checks
        assert "cache" in checks
        assert len(checks) == 2

    def test_list_checks_empty(self):
        h = HealthChecker()
        assert h.list_checks() == []

    def test_register_overwrites(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("db", lambda: HealthStatus.UNHEALTHY)
        assert h.list_checks() == ["db"]
        result = h.check("db")
        assert result['status'] == "unhealthy"

    def test_check_returns_dict(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        result = h.check("db")
        assert isinstance(result, dict)
        assert result['name'] == "db"
        assert result['status'] == "healthy"
        assert 'duration_ms' in result
        assert 'details' in result

    def test_check_with_details_tuple(self):
        h = HealthChecker()
        h.register("db", lambda: (HealthStatus.HEALTHY, {"latency": 5}))
        result = h.check("db")
        assert result['status'] == "healthy"
        assert result['details'] == {"latency": 5}

    def test_check_status_only_no_details(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.DEGRADED)
        result = h.check("db")
        assert result['status'] == "degraded"
        assert result['details'] == {}

    def test_check_nonexistent_returns_none(self):
        h = HealthChecker()
        result = h.check("nonexistent")
        assert result is None

    def test_check_exception_marks_unhealthy(self):
        h = HealthChecker()

        def bad_check():
            raise RuntimeError("boom")

        h.register("bad", bad_check)
        result = h.check("bad")
        assert result['status'] == "unhealthy"
        assert 'error' in result['details']

    def test_check_all_empty(self):
        h = HealthChecker()
        result = h.check_all()
        assert result['status'] == "healthy"
        assert result['checks'] == []
        assert 'total_duration_ms' in result
        assert 'timestamp' in result

    def test_check_all_healthy(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("cache", lambda: HealthStatus.HEALTHY)
        result = h.check_all()
        assert result['status'] == "healthy"
        assert len(result['checks']) == 2

    def test_check_all_with_degraded(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("cache", lambda: HealthStatus.DEGRADED)
        result = h.check_all()
        assert result['status'] == "degraded"

    def test_check_all_with_unhealthy(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("cache", lambda: HealthStatus.UNHEALTHY)
        result = h.check_all()
        assert result['status'] == "unhealthy"

    def test_check_all_unhealthy_overrides_degraded(self):
        h = HealthChecker()
        h.register("a", lambda: HealthStatus.UNHEALTHY)
        h.register("b", lambda: HealthStatus.DEGRADED)
        result = h.check_all()
        # UNHEALTHY 应覆盖 DEGRADED
        assert result['status'] == "unhealthy"

    def test_check_all_exception_marks_unhealthy(self):
        h = HealthChecker()

        def bad_check():
            raise ValueError("fail")

        h.register("db", bad_check)
        h.register("cache", lambda: HealthStatus.HEALTHY)
        result = h.check_all()
        assert result['status'] == "unhealthy"
        # 应该都执行了，坏的 + 好的
        assert len(result['checks']) == 2

    def test_check_all_includes_details(self):
        h = HealthChecker()
        h.register("db", lambda: (HealthStatus.HEALTHY, {"latency": 5}))
        result = h.check_all()
        assert result['checks'][0]['details'] == {"latency": 5}

    def test_check_all_includes_duration(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        result = h.check_all()
        assert 'duration_ms' in result['checks'][0]
        assert 'total_duration_ms' in result

    def test_check_all_each_has_name_status(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        h.register("cache", lambda: HealthStatus.DEGRADED)
        result = h.check_all()
        names = [c['name'] for c in result['checks']]
        assert "db" in names
        assert "cache" in names
        statuses = [c['status'] for c in result['checks']]
        assert "healthy" in statuses
        assert "degraded" in statuses


# ========== 全局单例测试 ==========

class TestGlobalSingletons:
    """测试全局单例"""

    def test_get_metrics_registry(self):
        r = get_metrics_registry()
        assert r is not None
        assert isinstance(r, MetricsRegistry)

    def test_metrics_registry_singleton(self):
        r1 = get_metrics_registry()
        r2 = get_metrics_registry()
        assert r1 is r2

    def test_get_health_checker(self):
        h = get_health_checker()
        assert h is not None
        assert isinstance(h, HealthChecker)

    def test_health_checker_singleton(self):
        h1 = get_health_checker()
        h2 = get_health_checker()
        assert h1 is h2

    def test_health_checker_has_default_checks(self):
        # get_health_checker 首次调用应注册 database / system_resources 检查
        h = get_health_checker()
        checks = h.list_checks()
        assert "database" in checks
        assert "system_resources" in checks


# ========== 线程安全测试 ==========

class TestThreadSafety:
    """测试指标与健康检查的线程安全"""

    def test_counter_concurrent_inc(self):
        c = Counter("req")
        N = 20
        EACH = 50

        def inc_many():
            for _ in range(EACH):
                c.inc()

        threads = [threading.Thread(target=inc_many) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert c.get() == N * EACH

    def test_gauge_concurrent_set(self):
        g = Gauge("mem")
        threads = []

        def set_val(v):
            g.set(v)

        for i in range(50):
            t = threading.Thread(target=set_val, args=(i,))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 不报错、不死锁即可；最终值是某个线程设置过的值
        assert g.get() in [float(i) for i in range(50)]

    def test_histogram_concurrent_observe(self):
        h = Histogram("lat")
        N = 20
        EACH = 50

        def observe_many():
            for _ in range(EACH):
                h.observe(0.1)

        threads = [threading.Thread(target=observe_many) for _ in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        d = h.to_dict()
        assert d['count'][''] == N * EACH

    def test_registry_concurrent_create(self):
        r = MetricsRegistry()
        results = []
        lock = threading.Lock()

        def get_counter():
            c = r.counter("shared")
            with lock:
                results.append(c)

        threads = [threading.Thread(target=get_counter) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有线程应该拿到同一个实例
        for c in results:
            assert c is results[0]

    def test_health_checker_concurrent_register(self):
        h = HealthChecker()
        N = 20

        def register_check(i):
            h.register(f"check_{i}", lambda: HealthStatus.HEALTHY)

        threads = [threading.Thread(target=register_check, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(h.list_checks()) == N

    def test_health_checker_concurrent_check_all(self):
        h = HealthChecker()
        h.register("db", lambda: HealthStatus.HEALTHY)
        results = []
        lock = threading.Lock()

        def check_all():
            r = h.check_all()
            with lock:
                results.append(r)

        threads = [threading.Thread(target=check_all) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        for r in results:
            assert r['status'] == "healthy"
