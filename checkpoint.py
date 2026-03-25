"""
checkpoint.py
─────────────
Lightweight file-based checkpoint system for multi-step job application flows.

Each checkpoint captures the last completed modal step and every field value
submitted so far, allowing a crashed or interrupted run to resume without
re-filling earlier steps.

Public API
----------
save_checkpoint(job_id, step, filled_fields)  → None
load_checkpoint(job_id)                        → dict | None
clear_checkpoint(job_id)                       → None
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

CHECKPOINT_DIR = Path("output/checkpoints")


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _checkpoint_path(job_id: str) -> Path:
    """Return the path for *job_id*'s checkpoint file, creating the dir if needed."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    # Sanitise to a safe filename: keep alphanumerics, hyphens, underscores
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in job_id)[:120]
    return CHECKPOINT_DIR / f"{safe}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def save_checkpoint(job_id: str, step: int, filled_fields: dict[str, str]) -> None:
    """
    Persist progress for *job_id* after a modal step completes.

    Parameters
    ----------
    job_id:
        Stable identifier for the job posting (e.g. a sanitised URL slug).
    step:
        The step index that was *just completed* (0-based).  On resume the bot
        will advance through steps 0 … step-1 without re-filling, then resume
        normal filling from *step* onward.
    filled_fields:
        Accumulated mapping of ``field_label → submitted_value`` across every
        step completed so far.  Used for diagnostics and potential re-fill on
        resume if LinkedIn did not persist the values.
    """
    payload: dict = {
        "job_id": job_id,
        "step": step,
        "filled_fields": filled_fields,
        "saved_at": datetime.now().isoformat(),
    }
    _checkpoint_path(job_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_checkpoint(job_id: str) -> dict | None:
    """
    Return the saved checkpoint for *job_id*, or ``None`` if none exists or the
    file is unreadable.

    The returned dict contains:
    - ``"job_id"``       – the identifier passed to :func:`save_checkpoint`
    - ``"step"``         – last completed step index (int)
    - ``"filled_fields"``– accumulated label → value mapping (dict)
    - ``"saved_at"``     – ISO-8601 timestamp string
    """
    path = _checkpoint_path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def clear_checkpoint(job_id: str) -> None:
    """
    Delete the checkpoint file for *job_id*.

    Called after a successful application submission so stale checkpoints do
    not cause a future re-run to skip steps on a different job with the same
    sanitised slug.  Safe to call even if no checkpoint exists.
    """
    try:
        _checkpoint_path(job_id).unlink(missing_ok=True)
    except Exception:
        pass
