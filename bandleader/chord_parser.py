"""
Shared chord parsing utilities for Bandleader.

All chord-symbol interpretation logic lives here. bass_generator and arp_generator
both import from this module to prevent divergence on edge cases.

Public API:
    NOTE_TO_PC              -- canonical note-name -> pitch-class mapping
    CHORD_TOKEN_RE          -- canonical chord regex
    clamp_int(x, lo, hi)    -- integer clamping utility
    pc_to_midi(pc, octave)  -- pitch class + octave -> MIDI note number
    parse_root_pc(token)    -- extract root pitch class from chord symbol
    parse_bass_pc(token)    -- extract bass pitch class from slash chords (e.g. C/G)
    parse_quality(token)    -- determine chord quality (maj, min, dim, aug, sus2, sus4)
    triad_pcs(root, qual)   -- [root, 3rd, 5th] pitch classes for a triad
    parse_progression_roots(prog)         -- (Legacy) bass-style parser
    parse_progression_with_quality(prog)  -- Standard parser (root, quality)
    parse_progression_full(prog)          -- Extended parser (root, quality, bass)
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Natural note letters only: CHORD_TOKEN_RE captures a single root letter and
# accidentals separately, so sharp/flat offsets are applied arithmetically.
NOTE_TO_PC: Dict[str, int] = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

# Updated to cleanly capture slash bass notes, keeping them out of the 'qual' group.
CHORD_TOKEN_RE = re.compile(
    r"""
    ^\s*
    (?P<root>[A-Ga-g])
    (?P<accidental>[#b]+)?
    (?P<qual>[^/]*)                                     # Quality stops at slash or end
    (?:/(?P<bass>[A-Ga-g])(?P<bass_accidental>[#b]+)?)? # Optional slash bass inversion
    \s*$
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def clamp_int(x: int, lo: int, hi: int) -> int:
    """Clamp integer x to [lo, hi]."""
    return max(lo, min(hi, x))


def pc_to_midi(pc: int, octave: int) -> int:
    """
    Pitch class + octave -> MIDI note number.
    C4 = 60 convention: midi = (octave + 1) * 12 + pc.
    """
    return (octave + 1) * 12 + (pc % 12)


# ---------------------------------------------------------------------------
# Token-level parsing
# ---------------------------------------------------------------------------

def parse_root_pc(token: str) -> int:
    """
    Extract root pitch class (0=C..11=B) from a chord token string.
    """
    token = token.strip()
    if not token:
        raise ValueError("Empty chord token")

    m = CHORD_TOKEN_RE.match(token)
    if not m:
        raise ValueError(f"Could not parse chord token: {token!r}")

    root = m.group("root").upper()
    accidental = (m.group("accidental") or "")

    base_pc = NOTE_TO_PC.get(root)
    if base_pc is None:
        raise ValueError(f"Unsupported chord root letter: {root!r} (from token {token!r})")

    acc = accidental.lower()
    offset = acc.count("#") - acc.count("b")

    return (base_pc + offset) % 12


def parse_bass_pc(token: str) -> Optional[int]:
    """
    Extract the bass pitch class from a slash chord (e.g., 'G' from 'C/G').
    Returns None if no slash bass is specified.
    """
    token = token.strip()
    if not token:
        return None
        
    m = CHORD_TOKEN_RE.match(token)
    if not m or not m.group("bass"):
        return None
        
    bass = m.group("bass").upper()
    accidental = (m.group("bass_accidental") or "")
    
    base_pc = NOTE_TO_PC.get(bass)
    if base_pc is None:
        return None
        
    acc = accidental.lower()
    offset = acc.count("#") - acc.count("b")
    
    return (base_pc + offset) % 12


def parse_quality(token: str) -> str:
    """
    Determine chord quality from a chord token string.
    Returns one of: "maj", "min", "dim", "aug", "sus2", "sus4"
    """
    m = CHORD_TOKEN_RE.match(token.strip())
    if not m:
        return "maj"

    q_raw = (m.group("qual") or "").strip()
    if not q_raw:
        return "maj"

    q = q_raw.lower()

    if "sus2" in q:
        return "sus2"
    if "sus" in q:
        return "sus4"

    if "aug" in q or "+" in q:
        return "aug"

    # Standalone 'o' (diminished shorthand) must not be a letter-adjacent 'o'
    # as in 'dom'; digits may follow it ('o7' = diminished seventh).
    if "dim" in q or "°" in q or "ø" in q or re.search(r"(?<![a-z])o(?![a-z])", q):
        return "dim"

    q_stripped = q.lstrip()
    if q_stripped.startswith("-"):
        return "min"
    if q_stripped.startswith("min"):
        return "min"
    if q_stripped.startswith("m") and not (q_stripped.startswith("maj") or q_stripped.startswith("major")):
        return "min"

    return "maj"


# ---------------------------------------------------------------------------
# Triad construction
# ---------------------------------------------------------------------------

def triad_pcs(root_pc: int, quality: str) -> List[int]:
    """
    Return [root, 3rd, 5th] intervals for various chord qualities.
    Used for Arpeggios and Pads.
    """
    intervals = {
        "maj":  [0, 4, 7],
        "min":  [0, 3, 7],
        "dim":  [0, 3, 6],
        "aug":  [0, 4, 8],
        "sus2": [0, 2, 7],
        "sus4": [0, 5, 7],
    }
    qual = (quality or "maj").lower()
    if qual not in intervals:
        qual = "maj"
    return [(root_pc + i) % 12 for i in intervals[qual]]


# ---------------------------------------------------------------------------
# Progression parsing (bar-level)
# ---------------------------------------------------------------------------

_BAR_SPLIT_RE = re.compile(r"\s*\|\s*")
_CHORD_SPLIT_RE = re.compile(r"\s+")


def _tokenize_bar(bar_text: str) -> List[str]:
    bar_text = (bar_text or "").strip()
    if not bar_text:
        return []
    bar_text = bar_text.replace(",", " ")
    tokens = [t for t in _CHORD_SPLIT_RE.split(bar_text) if t.strip()]
    return tokens


def parse_progression_roots(prog: str) -> List[List[int]]:
    """Legacy parser: returns only root PCs, grouped by bars."""
    if not prog or not prog.strip():
        raise ValueError("Empty progression")

    bars = [b.strip() for b in _BAR_SPLIT_RE.split(prog.strip()) if b.strip()]
    out: List[List[int]] = []
    for bar in bars:
        toks = _tokenize_bar(bar)
        if not toks:
            continue
        out.append([parse_root_pc(t) for t in toks])
    return out


def parse_progression_with_quality(prog: str) -> List[List[Tuple[int, str]]]:
    """
    Standard parser: returns (root_pc, quality) pairs, grouped by bars.
    Ignores slash/bass inversions to maintain strict 2-tuple backwards compatibility.
    """
    if not prog or not prog.strip():
        raise ValueError("Empty progression")

    bars = [b.strip() for b in _BAR_SPLIT_RE.split(prog.strip()) if b.strip()]
    out: List[List[Tuple[int, str]]] = []
    for bar in bars:
        toks = _tokenize_bar(bar)
        if not toks:
            continue
        out.append([(parse_root_pc(t), parse_quality(t)) for t in toks])
    return out


def parse_progression_full(prog: str) -> List[List[Tuple[int, str, Optional[int]]]]:
    """
    Extended parser: returns (root_pc, quality, bass_pc) pairs, grouped by bars.
    Use this API if building generators that support specific slash chord inversions.
    """
    if not prog or not prog.strip():
        raise ValueError("Empty progression")

    bars = [b.strip() for b in _BAR_SPLIT_RE.split(prog.strip()) if b.strip()]
    out: List[List[Tuple[int, str, Optional[int]]]] = []
    for bar in bars:
        toks = _tokenize_bar(bar)
        if not toks:
            continue
        out.append([(parse_root_pc(t), parse_quality(t), parse_bass_pc(t)) for t in toks])
    return out


# Alias used elsewhere (keep as canonical name)
parse_progression = parse_progression_with_quality