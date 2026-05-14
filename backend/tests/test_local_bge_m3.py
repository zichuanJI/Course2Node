from __future__ import annotations

import pytest
import torch

from app.providers.embed.local_bge_m3 import LocalBGEM3EmbedProvider


class _FakeBatch(dict):
    def to(self, _device: str):
        return self


class _FakeTokenizer:
    model_max_length = 4096

    def __call__(self, texts, *, padding, truncation, max_length, return_tensors):
        assert padding is True
        assert truncation is True
        assert max_length == 4096
        assert return_tensors == "pt"
        batch = len(texts)
        return _FakeBatch(
            {
                "input_ids": torch.ones((batch, 3), dtype=torch.long),
                "attention_mask": torch.ones((batch, 3), dtype=torch.long),
            }
        )


class _FakeModel:
    def to(self, _device: str):
        return self

    def eval(self):
        return self

    def half(self):
        return self

    def __call__(self, **_kwargs):
        return type(
            "FakeOutput",
            (),
            {
                "last_hidden_state": torch.tensor(
                    [
                        [[3.0, 4.0], [0.0, 0.0], [0.0, 0.0]],
                        [[5.0, 12.0], [0.0, 0.0], [0.0, 0.0]],
                    ],
                    dtype=torch.float32,
                )
            },
        )()


def test_local_bge_m3_provider_returns_normalized_cls_vectors(monkeypatch):
    import transformers

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", lambda *args, **kwargs: _FakeTokenizer())
    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", lambda *args, **kwargs: _FakeModel())

    provider = LocalBGEM3EmbedProvider(model_name="BAAI/bge-m3", device="cpu", use_fp16=False)
    vectors = provider.embed(["a", "b"])

    assert len(vectors) == 2
    assert vectors[0] == pytest.approx([0.6, 0.8], rel=1e-6)
    assert vectors[1] == pytest.approx([5 / 13, 12 / 13], rel=1e-6)


def test_local_bge_m3_provider_uses_safe_max_length_when_tokenizer_value_is_invalid(monkeypatch):
    import transformers

    class _TokenizerWithHugeMaxLength(_FakeTokenizer):
        model_max_length = 10**30

        def __call__(self, texts, *, padding, truncation, max_length, return_tensors):
            assert max_length == 8192
            batch = len(texts)
            return _FakeBatch(
                {
                    "input_ids": torch.ones((batch, 3), dtype=torch.long),
                    "attention_mask": torch.ones((batch, 3), dtype=torch.long),
                }
            )

    monkeypatch.setattr(transformers.AutoTokenizer, "from_pretrained", lambda *args, **kwargs: _TokenizerWithHugeMaxLength())
    monkeypatch.setattr(transformers.AutoModel, "from_pretrained", lambda *args, **kwargs: _FakeModel())

    provider = LocalBGEM3EmbedProvider(model_name="BAAI/bge-m3", device="cpu", use_fp16=False)
    vectors = provider.embed(["demo", "demo-2"])

    assert len(vectors) == 2
