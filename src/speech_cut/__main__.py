"""CLI: ``speech-cut transcript.json --source clip.mp4 -o cutlist.json``.

Writes a cut list in the schema that `premiere-xml
<https://github.com/boyjustin76/premiere-xml>`_ reads, so the two compose::

    speech-cut transcript.json --source clip.mp4 -o cutlist.json
    premiere-xml cutlist.json -o sequence.xml

The cut list is plain JSON, so it is equally easy to feed ffmpeg, Resolve, or your
own tooling.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from typing import List

from .cut import cut_to_speech, label_for
from .silence import from_word_gaps
from .words import from_whisper


def _load_words(path: str):
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):  # {"segments": [...]} from openai-whisper
        data = data.get("segments", [])
    return from_whisper(data)


def _load_silences(path: str) -> List[tuple]:
    """Accept ``[[a, b], ...]`` or ``{"silences"|"silence": [[a, b], ...]}``."""
    with io.open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("silences") or data.get("silence") or []
    if data and isinstance(data[0], dict):
        data = data[0].get("silences") or data[0].get("silence") or []
    return [(float(a), float(b)) for a, b in data]


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="speech-cut",
        description="Cut video to what was said, from word-level timestamps.",
    )
    p.add_argument("transcript", help="word-timestamp JSON (Whisper-style)")
    p.add_argument("-o", "--out", required=True, help="cut list JSON to write")
    p.add_argument("--source", help="media path, recorded in the cut list")
    p.add_argument("--duration", type=float, default=0.0, help="media length in seconds")
    p.add_argument("--fps", type=float, default=29.97, help="for the cut list only")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--silences", help="measured silence JSON; omit to infer from word gaps")
    p.add_argument("--gap", type=float, default=0.30, help="pause that splits a clip")
    p.add_argument("--lead", type=float, default=0.10)
    p.add_argument("--tail", type=float, default=0.20)
    p.add_argument("--min-silence", type=float, default=0.35,
                   help="shorter pauses are left alone, so speech still breathes")
    p.add_argument("--keep-retakes", action="store_true",
                   help="do not remove material the speaker said again")
    p.add_argument("--retake-similarity", type=float, default=0.80,
                   help="0.80 is measured; see the README before changing it")
    p.add_argument("--no-leftovers", action="store_true",
                   help="omit the removed parts instead of adding them as disabled clips")
    a = p.parse_args(argv)

    words = _load_words(a.transcript)
    if not words:
        print("no word timestamps found in", a.transcript, file=sys.stderr)
        return 2

    silences = _load_silences(a.silences) if a.silences else from_word_gaps(words, a.min_silence)
    result = cut_to_speech(
        words,
        silences,
        gap=a.gap,
        lead=a.lead,
        tail=a.tail,
        min_silence=a.min_silence,
        drop_retakes=not a.keep_retakes,
        retake_similarity=a.retake_similarity,
        source_seconds=a.duration or None,
    )

    source = a.source or "SOURCE.mp4"
    key = os.path.splitext(os.path.basename(source))[0][:16] or "src"
    duration = a.duration or result.source_seconds
    cuts = [
        {"src": key, "in": c.start, "out": c.end, "label": label_for(words, c)}
        for c in result.keep
    ]
    if not a.no_leftovers:
        # Removed material is parked on V2, switched off: an editor can see what the
        # tool took out instead of taking its word for it.
        at = result.kept_seconds
        for start, end in result.drop:
            cuts.append({
                "src": key, "in": start, "out": end, "track": 2,
                "at": round(at, 3), "enabled": False,
                "label": "removed @%d s" % int(start),
            })
            at += end - start

    cutlist = {
        "name": os.path.splitext(os.path.basename(source))[0] or "speech_cut",
        "fps": a.fps, "width": a.width, "height": a.height,
        "sources": {key: {"path": source.replace("\\", "/"), "dur": round(duration, 3)}},
        "cuts": cuts,
    }
    with io.open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cutlist, fh, ensure_ascii=False, indent=1)

    s = result.summary()
    print(a.out)
    print(f'  {s["clips"]} clips, {s["kept_seconds"]:.1f}s kept of '
          f'{s["source_seconds"]:.1f}s  ({s["removed_percent"]}% removed)')
    print(f'  clip length {s["shortest"]}s - {s["longest"]}s')
    if not a.no_leftovers:
        print(f"  {len(result.drop)} removed stretches parked on V2, disabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
