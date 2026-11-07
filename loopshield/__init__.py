# SPDX-FileCopyrightText: 2026 Francisco Angulo de Lafuente
# SPDX-License-Identifier: MIT
# Research-Project: LoopShield
# Research-Author: Francisco Angulo de Lafuente
# Research-ORCID: https://orcid.org/0009-0001-1634-7063
# Research-Date: 2026-11-07
"""LoopShield: privacy-first closed-loop tracking of actionable screening results."""
from .engine import AuditLog, Case, CaseEngine, TransitionError
from .pathways import ABNORMAL_MAMMOGRAM, FIT_POSITIVE, PATHWAYS, Pathway, Step

__version__ = "0.1.0"
__all__ = ["AuditLog", "Case", "CaseEngine", "TransitionError", "Pathway", "Step", "PATHWAYS",
           "FIT_POSITIVE", "ABNORMAL_MAMMOGRAM"]
