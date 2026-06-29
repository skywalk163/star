import pytest
from fastapi.testclient import TestClient
from star_api.main import app


client = TestClient(app)


class TestHealthEndpoints:
    def test_root_redirect(self):
        response = client.get('/')
        assert response.status_code in (200, 307)

    def test_health_check(self):
        response = client.get('/health')
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data or 'ok' in str(data).lower()


class TestStarEndpoints:
    def test_list_stars(self):
        response = client.get('/api/stars/')
        assert response.status_code == 200
        data = response.json()
        assert 'stars' in data or 'total' in data

    def test_star_types(self):
        response = client.get('/api/stars/types')
        assert response.status_code == 200


class TestNovaEndpoints:
    def test_list_novas(self):
        response = client.get('/api/novas/')
        assert response.status_code == 200

    def test_create_nova_minimal(self):
        payload = {
            'title': 'Test Nova',
            'starlight': 'test instruction',
            'assigned_star': 'auto',
            'priority': 'normal',
        }
        response = client.post('/api/novas/', json=payload)
        assert response.status_code in (200, 201, 422)


class TestEmissaryEndpoints:
    def test_list_adapters(self):
        response = client.get('/api/emissary/adapters')
        assert response.status_code == 200
        data = response.json()
        assert 'adapters' in data or 'total' in data

    def test_list_regions(self):
        response = client.get('/api/emissary/regions')
        assert response.status_code == 200


class TestStatsEndpoints:
    def test_system_stats(self):
        response = client.get('/api/stats')
        assert response.status_code == 200


class TestConfigEndpoints:
    def test_get_config(self):
        response = client.get('/api/config')
        assert response.status_code == 200
