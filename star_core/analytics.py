"""
星辉永驻（Star Analytics）- 历史记录与统计分析

提供任务历史记录、多维统计分析功能
"""

import sqlite3
import json
from typing import Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from star_core.orbit_engine import Nova, StarStatus, StarPriority, Constellation


@dataclass
class NovaHistory:
    """
    新星历史记录
    """
    id: str
    title: str
    description: str
    starlight: str
    assigned_star: Optional[str]
    final_status: str
    priority: int
    created_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    result_starlight: Optional[str]
    error: Optional[str]
    echo: Optional[str]
    constellation_id: Optional[str]
    total_output_length: int
    total_interactions: int


class HistoryStore:
    """
    历史记录存储
    
    负责任务历史的持久化和查询
    """
    
    def __init__(self, db_path: str = "data/history.db"):
        import os
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS nova_history (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                starlight TEXT,
                assigned_star TEXT,
                final_status TEXT NOT NULL,
                priority INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds REAL,
                result_starlight TEXT,
                error TEXT,
                echo TEXT,
                constellation_id TEXT,
                total_output_length INTEGER DEFAULT 0,
                total_interactions INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS constellation_history (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                final_status TEXT NOT NULL,
                execution_mode TEXT,
                nova_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                duration_seconds REAL
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nova_status ON nova_history(final_status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nova_star ON nova_history(assigned_star)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_nova_created ON nova_history(created_at)
        """)
        
        conn.commit()
        conn.close()
    
    def record_nova(self, nova: Nova, constellation_id: Optional[str] = None):
        """记录新星到历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        duration = None
        if nova.status in {StarStatus.CONSTELLATED, StarStatus.FADED, StarStatus.DARKENED}:
            duration = (nova.updated_at - nova.created_at).total_seconds()
        
        cursor.execute("""
            INSERT OR REPLACE INTO nova_history
            (id, title, description, starlight, assigned_star, final_status, priority,
             created_at, completed_at, duration_seconds, result_starlight, error, echo,
             constellation_id, total_output_length, total_interactions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            nova.id,
            nova.title,
            nova.description,
            nova.starlight,
            nova.assigned_star,
            nova.status.value,
            nova.priority.value,
            nova.created_at.isoformat(),
            nova.updated_at.isoformat() if duration else None,
            duration,
            nova.result_starlight,
            nova.error,
            nova.echo,
            constellation_id,
            len(nova.result_starlight) if nova.result_starlight else 0,
            len(nova.starlight_log)
        ))
        
        conn.commit()
        conn.close()
    
    def record_constellation(self, constellation: Constellation):
        """记录星座到历史"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        duration = None
        if constellation.is_all_complete():
            duration = (constellation.updated_at - constellation.created_at).total_seconds()
        
        cursor.execute("""
            INSERT OR REPLACE INTO constellation_history
            (id, name, description, final_status, execution_mode, nova_count,
             created_at, completed_at, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            constellation.id,
            constellation.name,
            constellation.description,
            constellation.status.value,
            constellation.execution_mode,
            len(constellation.novas),
            constellation.created_at.isoformat(),
            constellation.updated_at.isoformat() if duration else None,
            duration
        ))
        
        # 同时记录每个新星
        for nova in constellation.novas:
            self.record_nova(nova, constellation.id)
        
        conn.commit()
        conn.close()
    
    def query_novas(
        self,
        status: Optional[str] = None,
        star_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> list[dict]:
        """
        查询新星历史
        
        Args:
            status: 状态过滤
            star_type: 星体类型过滤
            start_date: 开始日期
            end_date: 结束日期
            limit: 数量限制
            offset: 偏移量
            
        Returns:
            历史记录列表
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM nova_history WHERE 1=1"
        params = []
        
        if status:
            query += " AND final_status = ?"
            params.append(status)
        
        if star_type:
            query += " AND assigned_star = ?"
            params.append(star_type)
        
        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_nova_count(
        self,
        status: Optional[str] = None,
        star_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """获取新星数量"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = "SELECT COUNT(*) FROM nova_history WHERE 1=1"
        params = []
        
        if status:
            query += " AND final_status = ?"
            params.append(status)
        
        if star_type:
            query += " AND assigned_star = ?"
            params.append(star_type)
        
        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())
        
        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())
        
        cursor.execute(query, params)
        count = cursor.fetchone()[0]
        conn.close()
        
        return count
    
    def get_nova_detail(self, nova_id: str) -> Optional[dict]:
        """获取新星详细历史"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM nova_history WHERE id = ?", (nova_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None


class StarAnalytics:
    """
    星图分析器
    
    提供多维统计分析功能
    """
    
    def __init__(self, history_store: HistoryStore):
        self.store = history_store
    
    def get_overview_stats(self) -> dict:
        """
        获取概览统计
        
        Returns:
            概览统计数据
        """
        total = self.store.get_nova_count()
        completed = self.store.get_nova_count(status=StarStatus.CONSTELLATED.value)
        failed = self.store.get_nova_count(status=StarStatus.FADED.value)
        cancelled = self.store.get_nova_count(status=StarStatus.DARKENED.value)
        
        success_rate = (completed / total * 100) if total > 0 else 0
        
        return {
            "total_novas": total,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "success_rate": round(success_rate, 2),
            "avg_duration": self._get_avg_duration()
        }
    
    def _get_avg_duration(self) -> Optional[float]:
        """获取平均完成时长（秒）"""
        completed = self.store.query_novas(
            status=StarStatus.CONSTELLATED.value,
            limit=1000
        )
        
        if not completed:
            return None
        
        durations = [n['duration_seconds'] for n in completed if n['duration_seconds']]
        if not durations:
            return None
        
        return round(sum(durations) / len(durations), 2)
    
    def get_star_type_stats(self) -> dict:
        """
        按星体类型统计
        
        Returns:
            各星体类型的统计数据
        """
        all_novas = self.store.query_novas(limit=10000)
        
        stats = defaultdict(lambda: {
            "total": 0,
            "completed": 0,
            "failed": 0,
            "total_duration": 0.0,
            "total_output": 0
        })
        
        for nova in all_novas:
            star = nova['assigned_star'] or 'unknown'
            stats[star]['total'] += 1
            
            if nova['final_status'] == StarStatus.CONSTELLATED.value:
                stats[star]['completed'] += 1
                if nova['duration_seconds']:
                    stats[star]['total_duration'] += nova['duration_seconds']
            
            if nova['final_status'] == StarStatus.FADED.value:
                stats[star]['failed'] += 1
            
            stats[star]['total_output'] += nova['total_output_length'] or 0
        
        result = {}
        for star_type, s in stats.items():
            avg_dur = s['total_duration'] / s['completed'] if s['completed'] > 0 else None
            success_rate = (s['completed'] / s['total'] * 100) if s['total'] > 0 else 0
            
            result[star_type] = {
                "total": s['total'],
                "completed": s['completed'],
                "failed": s['failed'],
                "success_rate": round(success_rate, 2),
                "avg_duration": round(avg_dur, 2) if avg_dur else None,
                "avg_output_length": round(s['total_output'] / s['total'], 0) if s['total'] > 0 else 0
            }
        
        return result
    
    def get_daily_stats(self, days: int = 30) -> list[dict]:
        """
        按日统计
        
        Args:
            days: 统计天数
            
        Returns:
            每日统计列表
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        all_novas = self.store.query_novas(
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )
        
        daily = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})
        
        for nova in all_novas:
            date = nova['created_at'][:10]  # YYYY-MM-DD
            daily[date]['total'] += 1
            
            if nova['final_status'] == StarStatus.CONSTELLATED.value:
                daily[date]['completed'] += 1
            elif nova['final_status'] == StarStatus.FADED.value:
                daily[date]['failed'] += 1
        
        # 填充所有日期
        result = []
        for i in range(days):
            d = end_date - timedelta(days=i)
            date_str = d.strftime('%Y-%m-%d')
            day_stats = daily.get(date_str, {"total": 0, "completed": 0, "failed": 0})
            result.append({
                "date": date_str,
                **day_stats
            })
        
        result.reverse()
        return result
    
    def get_hourly_stats(self) -> list[dict]:
        """
        按小时统计（分布）
        
        Returns:
            每小时统计列表（0-23小时）
        """
        all_novas = self.store.query_novas(limit=10000)
        
        hourly = [0] * 24
        
        for nova in all_novas:
            try:
                hour = datetime.fromisoformat(nova['created_at']).hour
                hourly[hour] += 1
            except Exception:
                pass
        
        return [{"hour": h, "count": hourly[h]} for h in range(24)]
    
    def get_priority_stats(self) -> dict:
        """
        按优先级统计
        
        Returns:
            各优先级的统计
        """
        all_novas = self.store.query_novas(limit=10000)
        
        stats = defaultdict(lambda: {"total": 0, "completed": 0, "failed": 0})
        
        for nova in all_novas:
            priority = nova['priority']
            stats[priority]['total'] += 1
            
            if nova['final_status'] == StarStatus.CONSTELLATED.value:
                stats[priority]['completed'] += 1
            elif nova['final_status'] == StarStatus.FADED.value:
                stats[priority]['failed'] += 1
        
        result = {}
        for prio, s in stats.items():
            success_rate = (s['completed'] / s['total'] * 100) if s['total'] > 0 else 0
            result[prio] = {
                "total": s['total'],
                "completed": s['completed'],
                "failed": s['failed'],
                "success_rate": round(success_rate, 2)
            }
        
        return result
    
    def get_top_novas(self, by: str = "duration", limit: int = 10) -> list[dict]:
        """
        获取 TOP 新星
        
        Args:
            by: 排序方式 - duration / output_length
            limit: 数量
            
        Returns:
            TOP 新星列表
        """
        all_novas = self.store.query_novas(limit=10000)
        
        if by == "duration":
            completed = [n for n in all_novas if n['duration_seconds']]
            completed.sort(key=lambda x: x['duration_seconds'], reverse=True)
            return completed[:limit]
        
        elif by == "output_length":
            completed = [n for n in all_novas if n['total_output_length']]
            completed.sort(key=lambda x: x['total_output_length'], reverse=True)
            return completed[:limit]
        
        return []
    
    def generate_report(self) -> dict:
        """
        生成完整统计报告
        
        Returns:
            完整报告
        """
        return {
            "overview": self.get_overview_stats(),
            "by_star_type": self.get_star_type_stats(),
            "daily": self.get_daily_stats(7),
            "hourly": self.get_hourly_stats(),
            "by_priority": self.get_priority_stats(),
            "generated_at": datetime.now().isoformat()
        }
