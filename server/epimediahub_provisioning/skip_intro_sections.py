"""File-local intro sections: overlapping suggestions compete; separate intros coexist.

All kinds remain `intro` at the player protocol layer. Human-confirmed role is
metadata, not evidence that a repeat belongs to a particular streaming brand.
"""
from __future__ import annotations

INTRO_ROLES = {"unknown", "provider", "series"}


def overlaps(first, second):
    """True only if two ranges actually overlap; a gap is never a duplicate."""
    return (int(first["start_ms"]) < int(second["end_ms"])
            and int(second["start_ms"]) < int(first["end_ms"]))


def section_groups(rows):
    """Cluster overlapping candidates from one file/kind/runtime.

    Input must belong to the same file, segment_type and runtime. This function
    is deliberately independent of confidence, author and approval status.
    """
    result = []
    for row in sorted(rows, key=lambda x: (int(x["start_ms"]), int(x["end_ms"]), int(x["id"]))):
        matching = [i for i, group in enumerate(result)
                    if any(overlaps(row, member) for member in group)]
        if not matching:
            result.append([row])
        else:
            head = result[matching[0]]
            head.append(row)
            for i in reversed(matching[1:]):
                head.extend(result.pop(i))
    return result


def role_label(role):
    return {"provider": "Anbieter-Vorspann", "series": "Serienintro"}.get(
        role, "Intro (noch nicht zugeordnet)")
