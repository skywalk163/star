"""
database.py - SQLite 数据库服务层

功能：
- SQLite 连接管理
- 表结构自动创建
- 审计日志持久化
- 任务历史持久化
- 配置版本管理
"""

import sqlite3
import os
import json
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager


SCHEMA_VERSION = 1


class DatabaseService:
    """SQLite 数据库服务"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            project_root = os.path.dirname(os.path.dirname(__file__))
            db_path = os.path.join(project_root, 'data', 'star.db')
        
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """初始化数据库连接和表结构"""
        self._conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        
        self._create_tables()
    
    def _create_tables(self):
        """创建所有表"""
        cursor = self._conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                id INTEGER PRIMARY KEY,
                version INTEGER NOT NULL,
                applied_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                operation TEXT NOT NULL,
                hwnd INTEGER,
                params TEXT,
                user TEXT DEFAULT 'default',
                role TEXT DEFAULT 'admin',
                result TEXT DEFAULT 'success',
                detail TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT NOT NULL,
                assigned_ais TEXT,
                dialogs TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id TEXT NOT NULL UNIQUE,
                name TEXT,
                config TEXT,
                is_custom INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_logs(operation)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task_history(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_created ON task_history(created_at)")
        
        cursor.execute("SELECT COUNT(*) as cnt FROM schema_version")
        if cursor.fetchone()['cnt'] == 0:
            cursor.execute(
                "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                (SCHEMA_VERSION, datetime.now().isoformat())
            )
    
    @contextmanager
    def get_cursor(self):
        """获取游标（线程安全）"""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
    
    # ========== 审计日志 ==========
    
    def insert_audit_log(self, entry: Dict[str, Any]) -> int:
        """插入一条审计日志"""
        with self.get_cursor() as cur:
            cur.execute("""
                INSERT INTO audit_logs (timestamp, operation, hwnd, params, user, role, result, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.get('timestamp', datetime.now().timestamp()),
                entry.get('operation', ''),
                entry.get('hwnd'),
                json.dumps(entry.get('params', {}), ensure_ascii=False),
                entry.get('user', 'default'),
                entry.get('role', 'admin'),
                entry.get('result', 'success'),
                entry.get('detail', '')
            ))
            return cur.lastrowid
    
    def query_audit_logs(self, limit: int = 50, offset: int = 0,
                         operation: str = None, hwnd: int = None,
                         result: str = None) -> Tuple[List[Dict], int]:
        """查询审计日志"""
        conditions = []
        params = []
        
        if operation:
            conditions.append("operation = ?")
            params.append(operation)
        if hwnd is not None:
            conditions.append("hwnd = ?")
            params.append(hwnd)
        if result:
            conditions.append("result = ?")
            params.append(result)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        with self.get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM audit_logs {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            cur.execute(f"""
                SELECT * FROM audit_logs {where_clause}
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            
            rows = []
            for row in cur.fetchall():
                d = dict(row)
                if d.get('params'):
                    try:
                        d['params'] = json.loads(d['params'])
                    except Exception:
                        pass
                rows.append(d)
            
            return rows, total
    
    # ========== 任务历史 ==========
    
    def upsert_task(self, task: Dict[str, Any]) -> str:
        """插入或更新任务"""
        task_id = task.get('id')
        now = datetime.now().isoformat()
        
        with self.get_cursor() as cur:
            cur.execute("SELECT id FROM task_history WHERE task_id = ?", (task_id,))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE task_history SET
                        title = ?, description = ?, status = ?,
                        assigned_ais = ?, dialogs = ?, updated_at = ?,
                        completed_at = ?
                    WHERE task_id = ?
                """, (
                    task.get('title', ''),
                    task.get('description', ''),
                    task.get('status', 'todo'),
                    json.dumps(task.get('assignedAIs', []), ensure_ascii=False),
                    json.dumps(task.get('dialogs', {}), ensure_ascii=False),
                    now,
                    now if task.get('status') == 'done' else None,
                    task_id
                ))
            else:
                cur.execute("""
                    INSERT INTO task_history 
                    (task_id, title, description, status, assigned_ais, dialogs,
                     created_at, updated_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task_id,
                    task.get('title', ''),
                    task.get('description', ''),
                    task.get('status', 'todo'),
                    json.dumps(task.get('assignedAIs', []), ensure_ascii=False),
                    json.dumps(task.get('dialogs', {}), ensure_ascii=False),
                    task.get('createdAt', now),
                    now,
                    now if task.get('status') == 'done' else None
                ))
            
            return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取单个任务"""
        with self.get_cursor() as cur:
            cur.execute("SELECT * FROM task_history WHERE task_id = ?", (task_id,))
            row = cur.fetchone()
            if not row:
                return None
            
            d = dict(row)
            for field in ['assigned_ais', 'dialogs']:
                if d.get(field):
                    try:
                        d[field] = json.loads(d[field])
                    except Exception:
                        pass
            
            return d
    
    def list_tasks(self, status: str = None, limit: int = 100, offset: int = 0) -> Tuple[List[Dict], int]:
        """列出任务"""
        conditions = []
        params = []
        
        if status:
            conditions.append("status = ?")
            params.append(status)
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        with self.get_cursor() as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM task_history {where_clause}", params)
            total = cur.fetchone()['cnt']
            
            cur.execute(f"""
                SELECT * FROM task_history {where_clause}
                ORDER BY datetime(created_at) DESC
                LIMIT ? OFFSET ?
            """, params + [limit, offset])
            
            rows = []
            for row in cur.fetchall():
                d = dict(row)
                for field in ['assigned_ais', 'dialogs']:
                    if d.get(field):
                        try:
                            d[field] = json.loads(d[field])
                        except Exception:
                            pass
                rows.append(d)
            
            return rows, total
    
    def delete_task(self, task_id: str) -> bool:
        """删除任务"""
        with self.get_cursor() as cur:
            cur.execute("DELETE FROM task_history WHERE task_id = ?", (task_id,))
            return cur.rowcount > 0
    
    # ========== 自定义 Agent 配置 ==========
    
    def save_custom_agent(self, agent_id: str, name: str, config: Dict) -> int:
        """保存自定义 Agent 配置"""
        now = datetime.now().isoformat()
        with self.get_cursor() as cur:
            cur.execute("SELECT id FROM agent_configs WHERE agent_id = ?", (agent_id,))
            existing = cur.fetchone()
            
            if existing:
                cur.execute("""
                    UPDATE agent_configs SET name = ?, config = ?, updated_at = ?
                    WHERE agent_id = ?
                """, (name, json.dumps(config, ensure_ascii=False), now, agent_id))
                return existing['id']
            else:
                cur.execute("""
                    INSERT INTO agent_configs (agent_id, name, config, is_custom, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?)
                """, (agent_id, name, json.dumps(config, ensure_ascii=False), now, now))
                return cur.lastrowid
    
    # ========== 健康检查 ==========
    
    def health_check(self) -> bool:
        """检查数据库是否正常"""
        try:
            with self.get_cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() is not None
        except Exception:
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None


_db_service: Optional[DatabaseService] = None


def get_db_service() -> DatabaseService:
    """获取数据库服务单例"""
    global _db_service
    if _db_service is None:
        _db_service = DatabaseService()
    return _db_service
