from __future__ import annotations

from app.core.types import CourseSession, EvidenceChunk, SourceKind
from app.storage.local import save_session


def test_pdf_api_flow_and_reupload_invalidates_stale_graph_and_notes(client, monkeypatch):
    import app.services.ingestion as ingestion_module
    import app.services.notes as notes_module

    def fake_pdf_ingest(source):
        source_id = str(source.source_id)
        return [
            EvidenceChunk(
                chunk_id=f"{source_id}-p1-1",
                source_id=source_id,
                source_type=SourceKind.pdf,
                text="Linear regression uses gradient descent to minimize loss on training data.",
                summary="Linear regression uses gradient descent.",
                keywords=["linear regression", "gradient descent"],
                embedding=[],
            ),
            EvidenceChunk(
                chunk_id=f"{source_id}-p2-1",
                source_id=source_id,
                source_type=SourceKind.pdf,
                text="Gradient descent updates parameters repeatedly until linear regression converges.",
                summary="Gradient descent updates parameters.",
                keywords=["gradient descent", "parameters"],
                embedding=[],
            ),
        ]

    monkeypatch.setattr(ingestion_module, "_ingest_pdf", fake_pdf_ingest)

    upload_response = client.post(
        "/upload/pdf",
        data={"course_title": "CS229", "lecture_title": "Linear Regression"},
        files={"file": ("lecture.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_response.status_code == 200
    upload_payload = upload_response.json()
    session_id = upload_payload["session_id"]
    source_id = upload_payload["source_id"]

    status_payload = client.get(f"/sessions/{session_id}/status").json()
    assert status_payload["status"] == "uploaded"
    assert status_payload["stats"]["document_count"] == 1
    assert status_payload["stats"]["concept_count"] == 0

    ingest_response = client.post("/ingest/pdf", json={"session_id": session_id, "source_id": source_id})
    assert ingest_response.status_code == 200

    status_payload = client.get(f"/sessions/{session_id}/status").json()
    assert status_payload["status"] == "uploaded"
    assert status_payload["stats"]["chunk_count"] == 2

    graph_response = client.post("/build_graph", json={"session_id": session_id})
    assert graph_response.status_code == 200
    assert graph_response.json()["concept_count"] > 0

    search_response = client.post(
        "/search",
        json={"session_id": session_id, "query": "gradient descent", "limit": 5},
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["concepts"]
    assert search_payload["chunks"]

    monkeypatch.setattr(
        notes_module,
        "_generate_note_with_llm",
        lambda graph, lecture_title, topic="": notes_module.LLMNoteDocument.model_validate(
            {
                "title": "Linear Regression - 图谱笔记",
                "summary": "基于当前图谱生成的课堂笔记。",
                "sections": [
                    {
                        "title": "梯度下降",
                        "content_md": "梯度下降反复更新参数，帮助线性回归收敛。",
                        "concept_ids": [graph.concepts[0].concept_id],
                    }
                ],
            }
        ),
    )
    note_response = client.post(
        "/generate_notes",
        json={"session_id": session_id},
    )
    assert note_response.status_code == 200
    note_payload = note_response.json()
    assert note_payload["sections"]

    markdown_response = client.get(f"/export/{session_id}/markdown")
    assert markdown_response.status_code == 200
    assert "# Linear Regression - 图谱笔记" in markdown_response.text

    assert client.get(f"/graph/{session_id}").status_code == 200
    assert client.get(f"/notes/{session_id}").status_code == 200

    reupload_response = client.post(
        "/upload/pdf",
        data={"session_id": session_id},
        files={"file": ("appendix.pdf", b"fake-bytes", "application/octet-stream")},
    )
    assert reupload_response.status_code == 200

    status_payload = client.get(f"/sessions/{session_id}/status").json()
    assert status_payload["status"] == "uploaded"
    assert status_payload["stats"]["document_count"] == 2
    assert status_payload["stats"]["chunk_count"] == 0
    assert status_payload["stats"]["concept_count"] == 0

    assert client.get(f"/graph/{session_id}").status_code == 404
    assert client.get(f"/notes/{session_id}").status_code == 404


def test_missing_artifacts_and_invalid_export_return_expected_status_codes(client):
    session = CourseSession(course_title="CS229", lecture_title="Unprocessed Lecture")
    save_session(session)

    graph_response = client.get(f"/graph/{session.session_id}")
    assert graph_response.status_code == 404

    note_response = client.get(f"/notes/{session.session_id}")
    assert note_response.status_code == 404

    export_response = client.get(f"/export/{session.session_id}/pdf")
    assert export_response.status_code == 400

    build_response = client.post("/build_graph", json={"session_id": str(session.session_id)})
    assert build_response.status_code == 400
    assert "No ingest artifacts found" in build_response.text
