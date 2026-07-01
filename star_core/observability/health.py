"""
health.py - 健康检查

提供系统健康状态检查功能，包括：
- 数据库连通性
- 核心服务状态
- 资源使用情况
"""

import time
import os
import threading
from typing import Dict, Any, Optional
from enum import Enum
from loguru import logger


class HealthStatus(str, Enum):
    """健康状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthChecker:
    """健康检查器"""
    
    def __init__(self):
        self._checks = {}
        self._lock = threading.Lock()
    
    def register(self, name: str, check_func):
        """注册健康检查"""
        with self._lock:
            self._checks[name] = check_func
    
    def check_all(self) -> Dict[str, Any]:
        """执行所有健康检查"""
        results = []
        overall_status = HealthStatus.HEALTHY
        total_start = time.time()
        
        with self._lock:
            checks = dict(self._checks)
        
        for name, check_func in checks.items():
            start = time.time()
            try:
                result = check_func()
                if isinstance(result, tuple):
                    status, details = result
                else:
                    status = result
                    details = {}
                
                if status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                    
            except Exception as e:
                logger.exception(f"Health check {name} failed")
                status = HealthStatus.UNHEALTHY
                details = {'error': str(e)}
                overall_status = HealthStatus.UNHEALTHY
            
            duration = (time.time() - start) * 1000
            results.append({
                'name': name,
                'status': status.value,
                'details': details or {},
                'duration_ms': round(duration, 2),
            })
        
        total_duration = (time.time() - total_start) * 1000
        
        return {
            'status': overall_status.value,
            'total_duration_ms': round(total_duration, 2),
            'checks': results,
            'timestamp': time.time(),
        }
    
    def check(self, name: str) -> Optional[Dict[str, Any]]:
        """执行单个健康检查"""
        with self._lock:
            check_func = self._checks.get(name)
        if check_func is None:
            return None
        
        start = time.time()
        try:
            result = check_func()
            if isinstance(result, tuple):
                status, details = result
            else:
                status = result
                details = {}
        except Exception as e:
            logger.exception(f"Health check {name} failed")
            status = HealthStatus.UNHEALTHY
            details = {'error': str(e)}
        
        duration = (time.time() - start) * 1000
        return {
            'name': name,
            'status': status.value,
            'details': details or {},
            'duration_ms': round(duration, 2),
        }
    
    def list_checks(self) -> list:
        """列出所有健康检查项"""
        with self._lock:
            return list(self._checks.keys())


def _check_database():
    """数据库健康检查"""
    try:
        from star_core.database import get_db_service
        db = get_db_service()
        if db.health_check():
            return HealthStatus.HEALTHY, {'database': 'ok'}
        else:
            return HealthStatus.UNHEALTHY, {'database': 'failed'}
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")
        return HealthStatus.UNHEALTHY, {'error': str(e)}


def _check_system_resources():
    """系统资源健康检查"""
    try:
        import psutil
        
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        
        disk_path = os.getcwd()
        try:
            disk = psutil.disk_usage(disk_path)
            disk_percent = disk.percent
        except Exception:
            disk_percent = None
        
        status = HealthStatus.HEALTHY
        details = {
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
        }
        
        if disk_percent is not None:
            details['disk_percent'] = disk_percent
        
        if cpu_percent > 90 or memory.percent > 90:
            status = HealthStatus.DEGRADED
        if disk_percent is not None and disk_percent > 95:
            status = HealthStatus.DEGRADED
        
        return status, details
    except ImportError:
        return HealthStatus.DEGRADED, {'error': 'psutil not available'}
    except Exception as e:
        logger.warning(f"System resources health check failed: {e}")
        return HealthStatus.DEGRADED, {'error': str(e)}


_global_health_checker: Optional[HealthChecker] = None
_init_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """获取全局健康检查器"""
    global _global_health_checker
    if _global_health_checker is None:
        with _init_lock:
            if _global_health_checker is None:
                _global_health_checker = HealthChecker()
                _global_health_checker.register('database', _check_database)
                _global_health_checker.register('system_resources', _check_system_resources)
    return _global_health_checker
