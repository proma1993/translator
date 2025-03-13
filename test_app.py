import pytest
from app import app
import json

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_index_page(client):
    """Тест загрузки главной страницы"""
    response = client.get('/')
    assert response.status_code == 200
    assert b'Многоязычный переводчик' in response.data

def test_translate_endpoint_missing_params(client):
    """Тест эндпоинта перевода с отсутствующими параметрами"""
    response = client.post('/translate', json={})
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_translate_endpoint_invalid_language(client):
    """Тест эндпоинта перевода с неподдерживаемым языком"""
    response = client.post('/translate', json={
        'text': 'Hello',
        'source_lang': 'invalid',
        'target_lang': 'ru',
        'style': 'formal'
    })
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_translate_endpoint_invalid_style(client):
    """Тест эндпоинта перевода с неподдерживаемым стилем"""
    response = client.post('/translate', json={
        'text': 'Hello',
        'source_lang': 'en',
        'target_lang': 'ru',
        'style': 'invalid'
    })
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_translate_endpoint_valid_request(client):
    """Тест эндпоинта перевода с корректными параметрами"""
    response = client.post('/translate', json={
        'text': 'Hello',
        'source_lang': 'en',
        'target_lang': 'ru',
        'style': 'formal'
    })
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'translated_text' in data or 'error' in data 