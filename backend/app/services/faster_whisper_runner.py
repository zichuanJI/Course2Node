from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="base")
    parser.add_argument("--language", default="auto")
    args = parser.parse_args()

    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(args.model, device="auto", compute_type="default")
    segments_iter, info = model.transcribe(
        args.audio,
        language=None if args.language == "auto" else args.language,
        vad_filter=True,
        beam_size=5,
        word_timestamps=False,
    )

    payload = {
        "language": getattr(info, "language", args.language),
        "segments": [
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": segment.text.strip(),
            }
            for segment in segments_iter
            if segment.text.strip()
        ],
    }
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
