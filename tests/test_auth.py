import pytest
from fastapi import HTTPException
from star_api.auth import (
    has_permission,
    get_current_user,
    require_permission,
    is_auth_enabled,
    ROLE_PERMISSIONS,
)


class TestRolePermissions:
    def test_admin_has_all_permissions(self):
        assert has_permission('admin', 'read') is True
        assert has_permission('admin', 'write') is True
        assert has_permission('admin', 'control') is True
        assert has_permission('admin', 'admin') is True

    def test_viewer_read_only(self):
        assert has_permission('viewer', 'read') is True
        assert has_permission('viewer', 'write') is False
        assert has_permission('viewer', 'control') is False
        assert has_permission('viewer', 'admin') is False

    def test_unknown_role(self):
        assert has_permission('unknown', 'read') is False
        assert has_permission('unknown', 'admin') is False


class TestAuthEnabled:
    def test_auth_disabled_by_default(self):
        from star_api import state
        state.config = {'auth': {'enabled': False}}
        assert is_auth_enabled() is False

    def test_auth_enabled(self):
        from star_api import state
        state.config = {'auth': {'enabled': True}}
        assert is_auth_enabled() is True

    def test_no_config(self):
        from star_api import state
        state.config = {}
        assert is_auth_enabled() is False


class TestRequirePermission:
    @pytest.mark.asyncio
    async def test_require_read_returns_callable(self):
        from star_api.auth import require_read
        assert callable(require_read)

    @pytest.mark.asyncio
    async def test_require_read_allows_admin(self):
        from star_api.auth import require_read
        # auth disabled -> should not raise
        from star_api import state
        state.config = {'auth': {'enabled': False}}
        try:
            await require_read()
        except HTTPException:
            pytest.fail("Should not raise when auth is disabled")

    def test_require_control_blocks_viewer_logic(self):
        # 直接测试权限判断逻辑
        assert has_permission('viewer', 'control') is False
        assert has_permission('viewer', 'read') is True
        assert has_permission('admin', 'control') is True
