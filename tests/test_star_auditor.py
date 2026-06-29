import time
import pytest
from star_core.star_auditor import AuditLogEntry, AuditLogger


class TestAuditLogEntry:
    def test_entry_creation(self):
        entry = AuditLogEntry('click', hwnd=12345, params={'x': 0.5}, user='tester')
        assert entry.operation == 'click'
        assert entry.hwnd == 12345
        assert entry.params == {'x': 0.5}
        assert entry.user == 'tester'
        assert entry.role == 'admin'
        assert entry.result == 'success'
        assert entry.timestamp > 0

    def test_entry_to_dict(self):
        entry = AuditLogEntry('send_text', hwnd=0, params={'text': 'hello'})
        d = entry.to_dict()
        assert d['operation'] == 'send_text'
        assert d['hwnd'] == 0
        assert d['params'] == {'text': 'hello'}
        assert 'time_str' in d
        assert 'timestamp' in d

    def test_entry_repr(self):
        entry = AuditLogEntry('test_op', result='success')
        assert 'test_op' in repr(entry)
        assert '✓' in repr(entry)

        entry_fail = AuditLogEntry('test_op', result='error')
        assert '✗' in repr(entry_fail)


class TestAuditLogger:
    def test_log_single_entry(self):
        logger = AuditLogger(max_entries=10)
        entry = logger.log('click', hwnd=100, params={'x': 0.5})
        assert entry.operation == 'click'
        assert len(logger._entries) == 1

    def test_log_multiple_entries(self):
        logger = AuditLogger(max_entries=10)
        for i in range(5):
            logger.log(f'op_{i}', hwnd=i)
        assert len(logger._entries) == 5

    def test_max_entries_ring_buffer(self):
        logger = AuditLogger(max_entries=3)
        for i in range(5):
            logger.log(f'op_{i}')
        assert len(logger._entries) == 3
        # 最早的两条应该被挤出
        ops = [e.operation for e in logger._entries]
        assert 'op_0' not in ops
        assert 'op_1' not in ops
        assert 'op_2' in ops

    def test_query_all(self):
        logger = AuditLogger(max_entries=10)
        logger.log('click')
        logger.log('send_text')
        logger.log('hotkey')
        results = logger.query(limit=10)
        assert len(results) == 3
        assert results[0]['operation'] == 'hotkey'  # 最新的在前

    def test_query_by_operation(self):
        logger = AuditLogger(max_entries=10)
        logger.log('click')
        logger.log('send_text')
        logger.log('click')
        results = logger.query(limit=10, operation='click')
        assert len(results) == 2
        assert all(r['operation'] == 'click' for r in results)

    def test_query_by_result(self):
        logger = AuditLogger(max_entries=10)
        logger.log('click', result='success')
        logger.log('send', result='error')
        results = logger.query(limit=10, result='error')
        assert len(results) == 1
        assert results[0]['result'] == 'error'

    def test_query_pagination(self):
        logger = AuditLogger(max_entries=10)
        for i in range(10):
            logger.log(f'op_{i}')
        page1 = logger.query(limit=3, offset=0)
        page2 = logger.query(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        assert page1[0]['operation'] != page2[0]['operation']

    def test_stats_empty(self):
        logger = AuditLogger(max_entries=100)
        stats = logger.stats()
        assert stats['total_entries'] == 0
        assert stats['max_capacity'] == 100

    def test_stats_with_data(self):
        logger = AuditLogger(max_entries=100)
        logger.log('click', user='alice')
        logger.log('send', user='bob', result='error')
        logger.log('click', user='alice')
        stats = logger.stats()
        assert stats['total_entries'] == 3
        assert 'click' in stats['operations']
        assert 'send' in stats['operations']
        assert 'success' in stats['results']
        assert 'error' in stats['results']
        assert 'alice' in stats['users']
        assert 'bob' in stats['users']

    def test_thread_safety(self):
        import threading
        logger = AuditLogger(max_entries=1000)
        errors = []

        def worker():
            try:
                for i in range(50):
                    logger.log('click', params={'i': i})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(logger._entries) == 200

    def test_default_params_empty_dict(self):
        entry = AuditLogEntry('test')
        assert entry.params == {}
