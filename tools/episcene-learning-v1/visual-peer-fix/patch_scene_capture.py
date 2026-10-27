#!/usr/bin/env python3
"""Fail-closed source patch: reuse one provider connection per capture.

Outputs a patched file, never changes a running worker or database.
Requires an exact known source shape; refuses unfamiliar source revisions.
"""
from pathlib import Path
import argparse
import ast

START = "    frames, cursor = [], start\n    measured = verified\n    while cursor < end:\n"
END = "    with db() as con:\n        return _save(con, asset, kind, start, length, frames)\n"
REPLACEMENT = """    frames, cursor = [], start
    measured = verified
    # Keep one provider session per capture; each successful chunk is saved.
    from contextlib import ExitStack
    with ExitStack() as sources:
        source = None
        protected_read = None
        while cursor < end:
            if busy():
                raise ValueError('analysis_deferred')
            part = min(CHUNK_MS, end - cursor)
            if 0 < end - cursor - part < 5000:
                part -= 5000
            with db() as con:
                row = _cache(con, asset, kind, cursor, part)
            if row:
                chunk = _window(row, asset).frames
            else:
                if source is None:
                    from skip_analysis_worker import busy_check
                    with db() as con:
                        playlist = con.execute(
                            'SELECT * FROM skip_analysis_playlists WHERE id=?',
                            (asset['playlist_id'],)).fetchone()
                    provider_busy = busy_check(db, [playlist])
                    def protected_read():
                        return busy() or provider_busy()
                    if protected_read():
                        raise ValueError('analysis_deferred')
                    source = sources.enter_context(
                        provider_proxy(source_url(playlist, asset), protected_read))
                if protected_read():
                    raise ValueError('analysis_deferred')
                if not measured:
                    duration, _ = probe(source, protected_read)
                    if abs(duration - asset['duration_ms']) > 500:
                        raise ValueError('visual_runtime_changed')
                    measured = True
                chunk = visual_fingerprint(source, cursor, part, STEP_MS, protected_read)
                with db() as con:
                    _save(con, asset, kind, cursor, part, chunk)
            frames.extend(chunk)
            cursor += part
    with db() as con:
        return _save(con, asset, kind, start, length, frames)
"""


def patch(text):
    if "with ExitStack() as sources:" in text:
        raise ValueError("ALREADY_PATCHED")
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError("UNRECOGNIZED_SCENE_SOURCE")
    before, remainder = text.split(START, 1)
    original_body, after = remainder.split(END, 1)
    if original_body.count("with provider_proxy(") != 1 or original_body.count("visual_fingerprint(") != 1:
        raise ValueError("UNRECOGNIZED_CAPTURE_BODY")
    result = before + REPLACEMENT + after
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("Output must differ from source")
    original = args.source.read_text()
    patched = patch(original)
    args.output.write_text(patched)
    print("PATCHED_OUTPUT_CREATED; NOT_DEPLOYED")


if __name__ == "__main__":
    main()
