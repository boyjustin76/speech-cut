# Contributing

Thanks for looking.

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

Tests use word lists, not media files, and never load a recogniser. Please keep it
that way — a test that needs a 1 GB model is a test nobody runs.

## The most useful thing you can send

**A case where it cut something it should have kept, or kept something it should have
cut.** Attach the word timestamps for that stretch (thirty seconds is plenty) and say
what you expected. That turns straight into a regression test, and it is how the
thresholds in the README were set in the first place.

Especially wanted:

- **English and other languages at length.** The defaults were measured on Korean
  talking-head footage. If `0.80` is wrong for your language, the fix is a number in
  a table, but somebody has to measure it.
- **Conversational / multi-speaker audio.** Untested. Retake detection assumes one
  person redoing their own line.
- **Other recognisers.** `from_whisper` handles the common shapes; if yours needs a
  loader, add one next to it.

## Design rules

- **Standard library only in `src/`.** The whole point is that it drops into any
  pipeline. Transcription, silence measurement and rendering stay outside.
- **Numbers in the code must be measured, and the measurement must be written down.**
  Every threshold here has a paragraph saying what footage it came from and what the
  alternative cost. If you change one, change the paragraph.
- **Comments explain the symptom, not the mechanism.** "Recognisers stretch a word's
  end to meet the next word, so the clip holds on room tone" is worth ten lines
  describing the loop.
- When something fails silently, make it raise, and add a test whose docstring says
  what the silent failure looked like.

## Scope

This library decides *where to cut*. It does not transcribe, render, detect speakers,
or write subtitles. Keeping that line is why it has no dependencies.
