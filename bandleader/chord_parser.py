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
    voice_chord_set(triad, prev, center)  -- voice-leading voicing for pad mode
"""

from __future__ import annotations

import re
from itertools import product
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NOTE_TO_PC: Dict[str, int] = {
    "C": 0,  "B#": 0,
    "C#": 1, "DB": 1,
    "D": 2,
    "D#": 3, "EB": 3,
    "E": 4,  "FB": 4,
    "F": 5,  "E#": 5,
    "F#": 6, "GB": 6,
    "G": 7,
    "G#": 8, "AB": 8,
    "A": 9,
    "A#": 10, "BB": 10,
    "B": 11, "CB": 11,
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

    if "dim" in q or "°" in q or "ø" in q or re.search(r"(?<!maj)(?<!major)\bo\b", q):
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


# ---------------------------------------------------------------------------
# Voicing helper (pad mode)
# ---------------------------------------------------------------------------

def voice_chord_set(
    chord_pcs: List[int],
    prev_notes: Optional[List[int]] = None,
    *,
    center: int = 60,
    search_octaves: Tuple[int, int] = (2, 6),
) -> List[int]:
    """
    Given a set of chord pitch classes, pick a voiced chord (MIDI notes) that is:
      - close to the previous voicing (minimize movement) if provided
      - close to a center MIDI note (default 60=C4)
      - reasonably compact (avoid huge spreads)
    """
    prev_notes = sorted(prev_notes or [])
    pcs = sorted({pc % 12 for pc in chord_pcs})
    if not pcs:
        return []

    # Candidate MIDI notes for each pc across a limited octave range
    lo_oct, hi_oct = search_octaves
    candidates_by_pc = {
        pc: [pc_to_midi(pc, o) for o in range(lo_oct, hi_oct + 1)]
        for pc in pcs
    }

    # If no previous voicing, choose the closest set to center by greedy selection
    if not prev_notes:
        chosen = [min(candidates_by_pc[pc], key=lambda n: abs(n - center)) for pc in pcs]
        return sorted(chosen)

    # Otherwise, brute-force a small search: choose one octave per pc, score against prev+center
    best_score = float("inf")
    best_voicing: List[int] = []

    pc_lists = [candidates_by_pc[pc] for pc in pcs]
    for combo in product(*pc_lists):
        voicing = sorted(combo)
        pair_len = min(len(voicing), len(prev_notes))
        move = sum(abs(voicing[i] - prev_notes[i]) for i in range(pair_len))
        chord_center = sum(voicing) / len(voicing)
        center_pen = abs(chord_center - center)
        spread_pen = (voicing[-1] - voicing[0]) * 0.1

        score = move + 0.5 * center_pen + spread_pen
        if score < best_score:
            best_score = score
            best_voicing = voicing

    return best_voicing