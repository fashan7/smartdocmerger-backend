import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

MOCK_IDEAS = [
    {
        "summary": "Auto-restart failed spiders",
        "full_text": "The system should automatically restart spider processes that fail or become unresponsive.",
        "section_title": "Infrastructure",
        "section_index": 0,
    },
    {
        "summary": "Health check monitoring",
        "full_text": "Implement periodic health checks on all spider processes and alert when they fail.",
        "section_title": "Monitoring",
        "section_index": 1,
    },
]


async def test_paste_document(auth_client: AsyncClient):
    with patch("app.services.processor.process_document", new_callable=AsyncMock):
        response = await auth_client.post("/documents/paste", json={
            "name": "Test Doc",
            "content": "This is a test document with some ideas about automation.",
            "file_type": "txt",
            "tags": ["test"],
            "priority": "normal",
        })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Doc"
    assert data["status"] == "processing"
    assert "id" in data


async def test_paste_document_empty_content(auth_client: AsyncClient):
    response = await auth_client.post("/documents/paste", json={
        "name": "Empty",
        "content": "   ",
        "file_type": "txt",
    })
    assert response.status_code == 400


async def test_paste_document_no_name(auth_client: AsyncClient):
    response = await auth_client.post("/documents/paste", json={
        "name": "",
        "content": "Some content here",
        "file_type": "txt",
    })
    assert response.status_code == 400


async def test_list_documents(auth_client: AsyncClient):
    with patch("app.services.processor.process_document", new_callable=AsyncMock):
        await auth_client.post("/documents/paste", json={
            "name": "List Test Doc",
            "content": "Content for listing test.",
            "file_type": "txt",
        })

    response = await auth_client.get("/documents")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert len(data["items"]) > 0


async def test_get_document(auth_client: AsyncClient):
    with patch("app.services.processor.process_document", new_callable=AsyncMock):
        create_resp = await auth_client.post("/documents/paste", json={
            "name": "Get Test Doc",
            "content": "Content to retrieve.",
            "file_type": "txt",
        })
    doc_id = create_resp.json()["id"]

    response = await auth_client.get(f"/documents/{doc_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == doc_id
    assert "original_text" in data
    assert "ideas" in data


async def test_get_document_not_found(auth_client: AsyncClient):
    response = await auth_client.get("/documents/nonexistent-id")
    assert response.status_code == 404


async def test_delete_document(auth_client: AsyncClient):
    with patch("app.services.processor.process_document", new_callable=AsyncMock):
        create_resp = await auth_client.post("/documents/paste", json={
            "name": "Delete Me",
            "content": "This will be deleted.",
            "file_type": "txt",
        })
    doc_id = create_resp.json()["id"]

    delete_resp = await auth_client.delete(f"/documents/{doc_id}")
    assert delete_resp.status_code == 204

    get_resp = await auth_client.get(f"/documents/{doc_id}")
    assert get_resp.status_code == 404


async def test_list_ideas_empty(auth_client: AsyncClient):
    response = await auth_client.get("/ideas")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


async def test_health(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_notifications_empty(auth_client: AsyncClient):
    response = await auth_client.get("/notifications")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "unread_count" in data


async def test_get_settings(auth_client: AsyncClient):
    response = await auth_client.get("/settings")
    assert response.status_code == 200
    data = response.json()
    assert "workspace_name" in data
    assert "similarity_threshold" in data
    assert "has_anthropic_key" in data


async def test_update_settings(auth_client: AsyncClient):
    response = await auth_client.patch("/settings", json={
        "workspace_name": "SherlockIT Workspace",
        "project_context": "Scraping company registry data",
        "similarity_threshold": 0.80,
    })
    assert response.status_code == 200

    get_resp = await auth_client.get("/settings")
    data = get_resp.json()
    assert data["workspace_name"] == "SherlockIT Workspace"
    assert data["similarity_threshold"] == 0.80


async def test_merge_queue_empty(auth_client: AsyncClient):
    response = await auth_client.get("/merge-queue")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "pending" in data


async def test_master_doc_get_creates_if_missing(auth_client: AsyncClient):
    response = await auth_client.get("/master-doc")
    assert response.status_code == 200
    data = response.json()
    assert "title" in data
    assert "sections" in data


async def test_master_doc_create_section(auth_client: AsyncClient):
    response = await auth_client.post("/master-doc/sections", json={
        "title": "Infrastructure",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Infrastructure"
    assert "id" in data


async def test_master_doc_update(auth_client: AsyncClient):
    response = await auth_client.patch("/master-doc", json={
        "title": "SherlockIT Automation Roadmap",
        "description": "Consolidated proposal",
    })
    assert response.status_code == 200
