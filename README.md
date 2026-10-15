# speech-cut

**Cut video to what was actually said.** Word-level timestamps in, edit decisions out —
including the retakes that volume-based cutters leave in.

[![tests](https://github.com/boyjustin76/speech-cut/actions/workflows/tests.yml/badge.svg)](https://github.com/boyjustin76/speech-cut/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

```console
$ speech-cut transcript.json --source take.mp4 --duration 36.8 -o cutlist.json
cutlist.json
  4 clips, 18.3s kept of 36.8s  (50.3% removed)
  clip length 4.2s - 5.7s
  4 removed stretches parked on V2, disabled
```

---

## The problem with cutting by volume

Silence detectors are great at silence. Here is what they do with a flubbed line:

```
  18.2s  "Enter at the close of the candle where the dot turns ma—"   ← stopped
  24.0s  "Enter at the close of the candle where the dot turns magenta."
```

Both are loud. Both survive. Your edit says the sentence twice, and you go fix it by
hand — which is most of the work you were trying to avoid.

Deciding which one to drop means knowing *what was said*. That is the whole reason
this library takes a transcript instead of an audio level.

|  | cuts by | removes retakes |
|---|---|---|
| auto-editor, and most open-source cutters | loudness / motion | ✗ |
| Descript, TimeBolt | transcript | ✓ (paid apps) |
| **speech-cut** | **transcript** | **✓ (a library, MIT)** |

## Quickstart

```bash
pip install speech-cut            # no dependencies
```

You need word-level timestamps. Any source works — here is Whisper:

```bash
pip install faster-whisper
python -c "
from faster_whisper import WhisperModel
import json
segments, _ = WhisperModel('medium').transcribe('take.mp4', word_timestamps=True)
json.dump([{'words': [{'word': w.word, 'start': w.start, 'end': w.end,
                       'probability': w.probability} for w in s.words]}
           for s in segments], open('transcript.json', 'w'))
"
```

Then:

```bash
speech-cut transcript.json --source take.mp4 -o cutlist.json
```

`cutlist.json` is plain JSON — feed it to ffmpeg, Resolve, or your own tooling. It is
also exactly what [premiere-xml](https://github.com/boyjustin76/premiere-xml) reads,
so a timeline is one more command:

```bash
premiere-xml cutlist.json -o sequence.xml      # File → Import in Premiere
```

The parts it removed arrive on V2, switched off. You can see what the tool took out
instead of taking its word for it.

## How it decides what is a retake

Three things make this harder than string comparison, and all three are why the
naive version does not work.

**1. Word times do not separate the takes.** Recognisers stretch a word's `end` to
meet the next word, so take A's last word and take B's first word sit flush against
each other across a real pause. We measured one word written as 6.9 s long: the
speaker had stopped, paused, and started again inside it. Splitting on word gaps
finds nothing there. We split on *silence that straddles the junction* too.

**2. The repeat is usually a tail.** Someone who gets three clauses in and stumbles
repeats the third clause only. The earlier chunk still holds good material, so it is
trimmed from the end rather than discarded.

**3. Neighbouring lines look like retakes.** This is the dangerous one — dropping one
deletes content the speaker meant to keep:

```
  "Enter at the close of the candle where the dot turns magenta."
  "Exit  at the close of the candle where the dot turns teal."
```

Word-for-word identical except the first and last word. What separates them is that
**a retake opens with the same word**: someone redoing a line restarts it. A parallel
clause does not. That single check does most of the work.

### The numbers behind the defaults

Measured on two prompted talking-head recordings, 12 and 16 minutes, 216 speech
chunks. Every adjacent pair was scored, then read by a human:

| | similarity |
|---|---|
| real retakes | 1.00, 1.00, 0.98, 0.98, 0.96 · 1.00, 1.00, 0.91, 0.84, 0.83, 0.81 |
| parallel clauses — **must not drop** | 0.72, 0.63, 0.62 |

The default threshold is **0.80**: above every false positive observed, below every
confident retake. On those two recordings the shipped defaults caught **6 of 7**
known retakes and **0 of 3** parallel clauses. The miss scored 0.84 but opened with a
different word.

That trade is deliberate. A false positive silently deletes something you wanted; a
miss leaves an extra take for you to remove. Tune with `--retake-similarity`.

## Everything else it does

| | why |
|---|---|
| snaps cuts to word boundaries | not to a dB threshold, so it never clips a syllable |
| **keeps short pauses** | cutting every breath makes speech sound machine-gunned; only pauses ≥ `--min-silence` go |
| never ends a clip on silence | an over-long word `end` would otherwise hold on room tone for seconds |
| drops short, low-confidence clips | a 0.6 s burst the recogniser was unsure about is a cough, not a line |
| trims a repeated word at a splice | otherwise you hear "the the" across the join |
| glues sub-second fragments back on | a 0.4 s clip is a flash, not an edit |
| reports what it removed | so a human can review the decision |

One detail worth stealing even if you never use this library: when the same word
appears at the end of one clip and the start of the next, **matching text cannot tell
you whether somebody stammered or whether one word is straddling the cut.** Trim on
text alone and you delete words that were only said once. Compare word *identity*
instead — see `says_it_twice`.

## Python API

```python
import json
from speech_cut import from_whisper, cut_to_speech, label_for

words = from_whisper(json.load(open("transcript.json", encoding="utf-8")))
result = cut_to_speech(words, silences, min_silence=0.35, retake_similarity=0.80)

for clip in result.keep:
    print(f"{clip.start:7.2f} {clip.end:7.2f}  {label_for(words, clip)}")

print(result.summary())
print(result.drop)      # what came out, for review
```

`Word(start, end, text, confidence)` is a `NamedTuple`. Build them from anything —
Whisper, WhisperX, Deepgram, AssemblyAI, a forced aligner, a CSV.

A measured silence map is optional but worth supplying; without one,
`from_word_gaps()` approximates from the gaps between words and cannot see the
silence an over-long word is hiding. Any tool will do:

```bash
ffmpeg -i take.mp4 -af silencedetect=noise=-35dB:d=0.35 -f null -
```

## What it does not do

- **It does not render.** It decides. Hand the cut list to ffmpeg or an NLE.
- **It does not remove stammers mid-sentence.** Only those landing on a cut boundary,
  where you would hear the word twice in a row.
- **It does not know your script.** Retake detection is similarity-based and needs no
  script. If you have per-line spans from a forced alignment, `speech_cut.script`
  can additionally trim off-script chatter.
- **No filler-word list.** "Um" and "uh" usually go anyway, as short low-confidence
  clips — but there is no dictionary, and none is planned.
- **No speaker diarisation**, no multicam.

## Verified on

Two real recordings (12 and 16 minutes, prompted but unscripted delivery, Korean),
and the synthetic example in `examples/`. Tests run with no media files and no
recogniser — they operate on word lists.

Not tested: English long-form at scale, conversational multi-speaker audio, languages
without spaces. Reports welcome; a transcript plus "this should/should not have been
cut" is enough to turn into a test.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
pip install -e ".[dev]" && pytest
```

## License

MIT — see [LICENSE](LICENSE).

한국어 설명은 [README.ko.md](README.ko.md).
