import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.runs import stream_run_events
from app.domain.models import RunEvent
from app.main import app


def test_health_and_frontend_are_served():
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["version"] == "3.0.0"
        frontend = client.get("/")
        assert frontend.status_code == 200
        assert "OphAgent-Pro" in frontend.text


async def test_sse_pushes_new_event_without_polling_delay():
    class NotifyingStore:
        def __init__(self):
            self.queue = asyncio.Queue()
            self.subscribed = asyncio.Event()

        async def get_run(self, run_id):
            return SimpleNamespace(user_id=7)

        async def stream_events(self, run_id, after=0):
            self.subscribed.set()
            yield await self.queue.get()

    store = NotifyingStore()
    response = await stream_run_events(
        "run_stream",
        after_sequence=0,
        last_event_id=None,
        current_user=SimpleNamespace(id=7),
        store=store,
    )
    next_chunk = asyncio.create_task(anext(response.body_iterator))
    await asyncio.wait_for(store.subscribed.wait(), timeout=0.2)
    await store.queue.put(
        RunEvent(
            run_id="run_stream",
            trace_id="trace_stream",
            sequence=1,
            type="answer.delta",
            public_summary="正在生成回答",
            data={"delta": "第一段"},
        )
    )
    chunk = await asyncio.wait_for(next_chunk, timeout=0.2)
    assert "event: answer.delta" in chunk
    assert '"delta": "第一段"' in chunk
    await response.body_iterator.aclose()


def test_authenticated_management_endpoints():
    username = f"api_{uuid4().hex[:12]}"
    with TestClient(app) as client:
        registered = client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        assert registered.status_code == 200

        created = client.post(
            "/api/v1/memories",
            json={
                "category": "preference",
                "content": "报告使用简洁中文",
                "source": "用户设置",
                "key": "report-language",
            },
        )
        assert created.status_code == 200
        memory_id = created.json()["id"]
        confirmed = client.patch(
            f"/api/v1/memories/{memory_id}",
            json={"status": "confirmed"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"
        preference = client.patch(
            "/api/v1/memories/preference",
            json={"enabled": False},
        )
        assert preference.json() == {"enabled": False}

        plugins = client.get("/api/v1/plugins")
        assert plugins.status_code == 200
        assert {item["id"] for item in plugins.json()} == {
            "lesion_localizer",
            "aux_diagnosis",
            "report_generator",
        }
        assert client.get("/api/v1/skills").status_code == 200
        skill_update = client.patch(
            "/api/v1/skills/red_flag_triage",
            json={"status": "disabled"},
        )
        assert skill_update.status_code != 403
        assert client.get("/api/v1/knowledge/status").status_code == 200
        assert client.get("/api/v1/capabilities").status_code == 200
        evolution = client.get("/api/v1/evolution/status")
        assert evolution.status_code == 200
        assert evolution.json()["production_mutation"] == "disabled"
        assert evolution.json()["human_approval_required"] is True
        accepted_rebuild = client.post("/api/v1/knowledge/index?include_embeddings=false")
        assert accepted_rebuild.status_code == 202

        project = client.post(
            "/api/v1/projects",
            json={"name": "随访项目", "description": "统一整理相关对话和文件"},
        )
        assert project.status_code == 201
        assert project.json()["conversation_count"] == 0
        assert client.get("/api/v1/projects").status_code == 200
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": "项目内对话", "agent_type": "interactive_vqa"},
        ).json()
        assigned = client.patch(
            f"/api/v1/conversations/{conversation['id']}",
            json={"project_id": project.json()["id"]},
        )
        assert assigned.status_code == 200
        assert assigned.json()["project_id"] == project.json()["id"]
        assert client.get("/api/v1/projects").json()[0]["conversation_count"] == 1


def test_logout_revokes_session_and_password_change_revokes_all_sessions():
    username = f"session_{uuid4().hex[:10]}"
    with TestClient(app) as client:
        registered = client.post(
            "/auth/register",
            json={"username": username, "password": "old-password-2026"},
        )
        assert registered.status_code == 200
        assert client.get("/auth/me").status_code == 200

        assert client.post("/auth/logout").status_code == 204
        assert client.get("/auth/me").status_code == 401

        assert client.post(
            "/auth/login",
            json={"username": username, "password": "old-password-2026"},
        ).status_code == 200
        changed = client.post(
            "/auth/password",
            json={
                "current_password": "old-password-2026",
                "new_password": "new-password-2026",
            },
        )
        assert changed.status_code == 204
        assert client.get("/auth/me").status_code == 401
        assert client.post(
            "/auth/login",
            json={"username": username, "password": "old-password-2026"},
        ).status_code == 401
        assert client.post(
            "/auth/login",
            json={"username": username, "password": "new-password-2026"},
        ).status_code == 200


def test_attachment_is_typed_and_private():
    username_a = f"files_a_{uuid4().hex[:8]}"
    username_b = f"files_b_{uuid4().hex[:8]}"
    with TestClient(app) as client:
        assert client.post(
            "/auth/register",
            json={"username": username_a, "password": "test-password"},
        ).status_code == 200
        uploaded = client.post(
            "/api/v1/upload",
            files={"file": ("notes.md", b"# OCT notes", "text/markdown")},
        )
        assert uploaded.status_code == 200
        payload = uploaded.json()
        assert payload["kind"] == "document"
        assert payload["attachment_id"].startswith("att_")
        assert "file_path" not in payload
        assert not payload["url"].startswith("/static/uploads")
        assert client.get(payload["url"]).content == b"# OCT notes"

        assert client.post(
            "/auth/register",
            json={"username": username_b, "password": "test-password"},
        ).status_code == 200
        assert client.get(payload["url"]).status_code == 404


def test_docx_is_rejected_until_parser_is_implemented():
    username = f"docx_{uuid4().hex[:10]}"
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        response = client.post(
            "/api/v1/upload",
            files={"file": ("unsupported.docx", b"not-a-real-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 400


def test_run_api_rejects_direct_server_paths():
    username = f"paths_{uuid4().hex[:10]}"
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        response = client.post(
            "/api/v1/runs",
            json={
                "query": "解析这个文件",
                "plugin_id": "interactive_vqa",
                "document_paths": ["/etc/passwd"],
            },
        )
        assert response.status_code == 422
        assert "attachment_ids" in response.json()["detail"]


def test_direct_run_cannot_reference_another_users_conversation():
    username_a = f"run_owner_a_{uuid4().hex[:8]}"
    username_b = f"run_owner_b_{uuid4().hex[:8]}"
    with TestClient(app) as client_a, TestClient(app) as client_b:
        assert client_a.post(
            "/auth/register",
            json={"username": username_a, "password": "test-password"},
        ).status_code == 200
        conversation = client_a.post(
            "/api/v1/conversations",
            json={"title": "A 的私有会话"},
        ).json()

        assert client_b.post(
            "/auth/register",
            json={"username": username_b, "password": "test-password"},
        ).status_code == 200
        response = client_b.post(
            "/api/v1/runs",
            json={
                "query": "读取上下文",
                "conversation_id": conversation["id"],
            },
        )
        assert response.status_code == 404


def test_run_api_rejects_unimplemented_artifact_input():
    username = f"artifact_input_{uuid4().hex[:8]}"
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        response = client.post(
            "/api/v1/runs",
            json={"query": "继续分析", "artifact_ids": ["art_not_real"]},
        )
        assert response.status_code == 422
        assert "Artifact" in response.json()["detail"]


def test_websocket_chat_rejects_direct_server_paths():
    username = f"ws_paths_{uuid4().hex[:10]}"
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        with client.websocket_connect("/ws/chat") as websocket:
            assert websocket.receive_json()["type"] == "connected"
            websocket.send_json(
                {
                    "type": "chat",
                    "query": "解析这个文件",
                    "document_paths": ["/etc/passwd"],
                },
            )
            response = websocket.receive_json()
            assert response["type"] == "error"
            assert "attachment_ids" in response["message"]


def test_conversation_message_idempotency_reuses_message_and_waiting_run():
    username = f"idempotent_{uuid4().hex[:8]}"
    with TestClient(app) as client:
        client.post(
            "/auth/register",
            json={"username": username, "password": "test-password"},
        )
        conversation = client.post(
            "/api/v1/conversations",
            json={"title": "病灶定位", "agent_type": "interactive_vqa"},
        ).json()
        payload = {
            "content": "请定位病灶",
            "requested_plugins": ["lesion_localizer"],
            "idempotency_key": f"request-{uuid4().hex}",
        }
        first = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json=payload,
        )
        second = client.post(
            f"/api/v1/conversations/{conversation['id']}/messages",
            json=payload,
        )
        assert first.status_code == second.status_code == 202
        assert first.json()["message"]["id"] == second.json()["message"]["id"]
        assert first.json()["run"]["id"] == second.json()["run"]["id"]
        assert second.json()["run"]["status"] == "waiting_for_user"
