"""Privacy gateway: what may leave the hospital when LoopShield asks a language model for help.

Built on Project NAVAJO (navajo-egp, MIT). Structured identifiers are never put in the prompt;
free text (a clinician's note) is masked on the local machine with NAVAJO v2 and reversible
placeholders; a final guard refuses to send if a hard identifier is still visible. The answer is
restored locally and the mapping is discarded.

Masking reduces exposure; it does not make data anonymous. Pseudonymised data remain personal
data, and the evaluation in bench/ reports what still gets through.
"""
from __future__ import annotations

import os
import re

from .navajo_v2 import NavajoV2

_LEXICON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "lexicon_train.json")

HARD_IDENTIFIERS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "emirates_id": re.compile(r"\b784[- ]?\d{4}[- ]?\d{7}[- ]?\d\b"),
    # 8+ digits joined by spaces, dashes or brackets (no dots: lab values such as 8.2 7.9 stay)
    "phone": re.compile(r"(?<![\w.])(?:\+|00)?\d{1,4}(?:[\s()-]{1,2}\d{2,4}){2,5}(?![\w.])"),
    "long_number": re.compile(r"(?<![\d.])\d{6,}(?![\d.])"),
}
PLACEHOLDER = re.compile(r"\[PHI_\d+\]")


def presidio_detector(language: str = "en"):
    """Optional second detector for maximum-protection mode (needs presidio-analyzer + a spaCy model)."""
    from presidio_analyzer import AnalyzerEngine
    engine = AnalyzerEngine()
    return lambda text: [(r.start, r.end) for r in engine.analyze(text=text, language=language)]


class PrivacyRefusal(RuntimeError):
    """Raised instead of sending when a hard identifier survives masking."""


class PrivacyGateway:
    def __init__(self, extra_detector=None, lexicon_path: str | None = _LEXICON):
        self.v2 = NavajoV2(lexicon_path if lexicon_path and os.path.exists(lexicon_path) else None)
        if lexicon_path and not os.path.exists(lexicon_path):
            raise FileNotFoundError(f"NAVAJO lexicon missing: {lexicon_path} (refusing to run weakened)")
        self.extra = extra_detector         # optional callable text -> [(start, end)], e.g. Presidio

    def spans(self, text: str):
        out = list(self.v2.detect(text))
        if self.extra is not None:
            out += list(self.extra(text))
        out.sort()
        merged = []
        for s, e in out:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            elif e > s:
                merged.append((s, e))
        return merged

    def mask(self, text: str, mapping: dict[str, str]) -> str:
        """Replace detected spans with [PHI_n]; the same value always gets the same placeholder."""
        reverse = {v: k for k, v in mapping.items()}
        parts, last = [], 0
        for s, e in self.spans(text):
            while e > s and text[e - 1].isspace():      # keep surrounding spaces outside the placeholder
                e -= 1
            while s < e and text[s].isspace():
                s += 1
            if e <= s:
                continue
            value = text[s:e]
            ph = reverse.get(value)
            if ph is None:
                ph = f"[PHI_{len(mapping) + 1}]"
                mapping[ph] = value
                reverse[value] = ph
            parts += [text[last:s], ph]
            last = e
        parts.append(text[last:])
        return "".join(parts)

    @staticmethod
    def guard(text: str) -> list[str]:
        found = []
        for name, rx in HARD_IDENTIFIERS.items():
            for m in rx.finditer(PLACEHOLDER.sub(" ", text)):
                if name == "phone" and sum(ch.isdigit() for ch in m.group()) < 8:
                    continue
                found.append(f"{name}:{len(m.group())}chars")
        return found

    def build_request(self, case, note: str = "", task: str = "patient_message") -> tuple[str, dict]:
        """Prompt for an external model and the local mapping needed to restore its answer.

        Only non-identifying case context is included: pathway, step, urgency, language.
        """
        if PLACEHOLDER.search(note or ""):
            raise PrivacyRefusal("note already contains placeholder-like text ([PHI_n]); restore would be ambiguous")
        mapping: dict[str, str] = {}
        masked_note = self.mask(note, mapping) if note else ""
        step = case.pending_step.state if case.pending_step else case.state
        prompt = (
            f"Task: {task}. Pathway: {case.pathway.title}. Current step: {case.state}; next step: {step}. "
            f"Urgent: {'yes' if case.urgent else 'no'}. Write for language '{case.language}', plain words, "
            "say this is a screening result and not a diagnosis, give one next action and how to reply. "
            "Keep every [PHI_n] placeholder exactly as written.\n"
            f"Clinician note (masked): {masked_note}"
        )
        leaks = self.guard(prompt)
        if leaks:
            mapping.clear()
            raise PrivacyRefusal(f"hard identifier still visible after masking: {leaks}")
        return prompt, mapping

    @staticmethod
    def restore(answer: str, mapping: dict[str, str]) -> str:
        out = PLACEHOLDER.sub(lambda m: mapping.get(m.group(), m.group()), answer)
        mapping.clear()                      # the mapping lives only for one request
        return out
