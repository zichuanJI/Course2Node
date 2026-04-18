from __future__ import annotations

from app.services.text_utils import extract_candidate_terms, split_text


def test_split_text_breaks_long_content_without_empty_chunks():
    text = (
        "Gradient descent repeatedly updates model weights to minimize loss for linear regression. "
        "This sentence is intentionally long so the splitter has to break it into multiple chunks "
        "without producing empty fragments."
    )

    chunks = split_text(text, max_chars=60, overlap=12)

    assert len(chunks) >= 2
    assert all(chunks)
    assert "gradient descent" in " ".join(chunks).lower()


def test_extract_candidate_terms_handles_mixed_english_and_chinese():
    text = "Gradient descent helps 线性回归 完成优化，梯度下降 会不断更新参数。"

    terms = extract_candidate_terms(text, top_k=10)

    assert "gradient" in terms
    assert any(term in terms for term in {"线性回归", "梯度下降", "优化"})
