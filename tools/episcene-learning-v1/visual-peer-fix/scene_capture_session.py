"""Optional, tested helper for reusing a provider session across visual chunks.

The caller remains responsible for saving each completed chunk before moving on.
"""
from contextlib import ExitStack


def capture_chunks(parts, cached_chunk, open_source, fingerprint, save_chunk, busy):
    """Yield chunk frames; open a provider only on the first cache miss.

    parts: iterable of (offset_ms, length_ms). The caller owns policy,
    duration validation and cache identity. On interruption the provider closes.
    """
    with ExitStack() as stack:
        source = None
        for offset, length in parts:
            if busy():
                raise ValueError("analysis_deferred")
            frames = cached_chunk(offset, length)
            if frames is None:
                if source is None:
                    source = stack.enter_context(open_source())
                if busy():
                    raise ValueError("analysis_deferred")
                frames = fingerprint(source, offset, length)
                save_chunk(offset, length, frames)
            yield frames
