"""
数据库服务测试

测试 star_core.database 中的 DatabaseService
"""

import pytest
import os
import tempfile
from star_core.database import DatabaseService


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = f.name
    try:
        db = DatabaseService(db_path=db_path)
        yield db
        db.close()
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


class TestDatabaseService:
    """测试 DatabaseService"""

    def test_create_database(self, temp_db):
        assert temp_db is not None
        assert temp_db.db_path is not None

    def test_health_check(self, temp_db):
        assert temp_db.health_check() == True

    def test_tables_created(self, temp_db):
        with temp_db.get_cursor() as cur:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row['name'] for row in cur.fetchall()]
        assert 'audit_logs' in tables
        assert 'task_history' in tables
        assert 'agent_configs' in tables
        assert 'schema_version' in tables


class TestAuditLogOperations:
    """测试审计日志操作"""

    def test_insert_audit_log(self, temp_db):
        entry = {
            'operation': 'test_op',
            'hwnd': 12345,
            'params': {'x': 1, 'y': 2},
            'user': 'admin',
            'role': 'admin',
            'result': 'success',
            'detail': 'test detail',
        }
        log_id = temp_db.insert_audit_log(entry)
        assert log_id > 0

    def test_query_audit_logs_empty(self, temp_db):
        rows, total = temp_db.query_audit_logs()
        assert total == 0
        assert len(rows) == 0

    def test_query_audit_logs_with_data(self, temp_db):
        for i in range(5):
            temp_db.insert_audit_log({
                'operation': f'op_{i}',
                'result': 'success' if i % 2 == 0 else 'failed',
            })
        rows, total = temp_db.query_audit_logs(limit=3)
        assert total == 5
        assert len(rows) == 3

    def test_query_audit_logs_by_operation(self, temp_db):
        temp_db.insert_audit_log({'operation': 'click', 'result': 'success'})
        temp_db.insert_audit_log({'operation': 'type', 'result': 'success'})
        temp_db.insert_audit_log({'operation': 'click', 'result': 'failed'})

        rows, total = temp_db.query_audit_logs(operation='click')
        assert total == 2
        for row in rows:
            assert row['operation'] == 'click'

    def test_query_audit_logs_by_result(self, temp_db):
        temp_db.insert_audit_log({'operation': 'op1', 'result': 'success'})
        temp_db.insert_audit_log({'operation': 'op2', 'result': 'failed'})
        temp_db.insert_audit_log({'operation': 'op3', 'result': 'success'})

        rows, total = temp_db.query_audit_logs(result='success')
        assert total == 2
        for row in rows:
            assert row['result'] == 'success'

    def test_query_audit_logs_pagination(self, temp_db):
        for i in range(10):
            temp_db.insert_audit_log({'operation': f'op_{i}'})

        rows_page1, total = temp_db.query_audit_logs(limit=3, offset=0)
        assert total == 10
        assert len(rows_page1) == 3

        rows_page2, _ = temp_db.query_audit_logs(limit=3, offset=3)
        assert len(rows_page2) == 3

    def test_audit_log_params_json(self, temp_db):
        params = {'key1': 'value1', 'key2': 123}
        temp_db.insert_audit_log({
            'operation': 'test',
            'params': params,
        })
        rows, _ = temp_db.query_audit_logs(limit=1)
        assert len(rows) == 1
        assert rows[0]['params'] == params


class TestTaskHistoryOperations:
    """测试任务历史操作"""

    def test_upsert_task_new(self, temp_db):
        task = {
            'id': 'task_001',
            'title': '测试任务',
            'description': '这是一个测试任务',
            'status': 'todo',
            'assignedAIs': ['trae', 'cursor'],
            'dialogs': {'trae': 'hello'},
        }
        task_id = temp_db.upsert_task(task)
        assert task_id == 'task_001'

    def test_upsert_task_update(self, temp_db):
        task = {
            'id': 'task_001',
            'title': '测试任务',
            'status': 'todo',
        }
        temp_db.upsert_task(task)

        # 更新任务
        task['title'] = '更新后的任务'
        task['status'] = 'doing'
        task_id = temp_db.upsert_task(task)
        assert task_id == 'task_001'

        # 验证更新
        updated = temp_db.get_task('task_001')
        assert updated['title'] == '更新后的任务'
        assert updated['status'] == 'doing'

    def test_get_task_not_found(self, temp_db):
        task = temp_db.get_task('nonexistent')
        assert task is None

    def test_list_tasks_empty(self, temp_db):
        tasks, total = temp_db.list_tasks()
        assert total == 0
        assert len(tasks) == 0

    def test_list_tasks_with_data(self, temp_db):
        for i in range(5):
            temp_db.upsert_task({
                'id': f'task_{i}',
                'title': f'任务 {i}',
                'status': 'todo' if i < 3 else 'done',
            })
        tasks, total = temp_db.list_tasks()
        assert total == 5
        assert len(tasks) == 5

    def test_list_tasks_by_status(self, temp_db):
        for i in range(5):
            temp_db.upsert_task({
                'id': f'task_{i}',
                'title': f'任务 {i}',
                'status': 'todo' if i < 3 else 'done',
            })
        tasks, total = temp_db.list_tasks(status='todo')
        assert total == 3
        for t in tasks:
            assert t['status'] == 'todo'

    def test_delete_task(self, temp_db):
        temp_db.upsert_task({
            'id': 'task_to_delete',
            'title': '要删除的任务',
            'status': 'todo',
        })
        assert temp_db.get_task('task_to_delete') is not None

        result = temp_db.delete_task('task_to_delete')
        assert result == True
        assert temp_db.get_task('task_to_delete') is None

    def test_delete_task_not_found(self, temp_db):
        result = temp_db.delete_task('nonexistent')
        assert result == False

    def test_task_json_fields(self, temp_db):
        task = {
            'id': 'task_json',
            'title': 'JSON 字段测试',
            'status': 'doing',
            'assignedAIs': ['trae', 'cursor', 'claude'],
            'dialogs': {
                'trae': {'messages': []},
                'cursor': {'messages': []},
            },
        }
        temp_db.upsert_task(task)
        saved = temp_db.get_task('task_json')
        assert saved['assigned_ais'] == ['trae', 'cursor', 'claude']
        assert 'trae' in saved['dialogs']


class TestAgentConfigOperations:
    """测试自定义 Agent 配置操作"""

    def test_save_custom_agent_new(self, temp_db):
        config_id = temp_db.save_custom_agent(
            agent_id='custom_agent',
            name='自定义 Agent',
            config={'key': 'value'},
        )
        assert config_id > 0

    def test_save_custom_agent_update(self, temp_db):
        id1 = temp_db.save_custom_agent(
            agent_id='custom_agent',
            name='自定义 Agent',
            config={'key': 'value1'},
        )
        id2 = temp_db.save_custom_agent(
            agent_id='custom_agent',
            name='更新后的 Agent',
            config={'key': 'value2'},
        )
        # 同一个 agent_id 应该返回同一个 id
        assert id1 == id2
