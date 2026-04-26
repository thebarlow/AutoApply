"""Job scorer: scores SCRAPED jobs using Claude and transitions their state."""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from typing import Optional

import anthropic
from sqlalchemy.orm import Session

from core.types import JobState, UserProfile, WorkHistoryEntry, EducationEntry
from db.database import SessionLocal
from db.models import Config, Job, UserProfileModel


def compute_final_score(w1: float, w2: float, desirability: float, fit: float) -> float:
    """Compute weighted final score, clamped to [0.0, 1.0]."""
    return max(0.0, min(1.0, w1 * desirability + w2 * fit))


def determine_state(
    final: float, reject_threshold: float, approve_threshold: float
) -> JobState:
    """Map a final score to a JobState based on thresholds."""
    if final < reject_threshold:
        return JobState.REJECTED
    if final > approve_threshold:
        return JobState.APPROVED
    return JobState.PENDING_REVIEW
