"""
Severity & Urgency Scoring
===========================
Assigns 0–100 severity score and low/medium/high/critical urgency.

Scoring factors:
  1. Category base score (terrorism > corruption > crime > etc.)
  2. Keyword amplifiers (death, many people, children, etc.)
  3. Scope indicators (widespread vs. isolated)
  4. Temporal urgency (active vs. historical)
  5. Confidence-weighted adjustment

Design principle: Explainable scoring — every score comes with reasoning.
"""

import re
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)

# Base severity scores by category (0–100)
CATEGORY_BASE_SCORES: Dict[str, int] = {
    "terrorism": 85,
    "corruption": 65,
    "crime_signals": 60,
    "public_safety": 70,
    "health_sanitation": 65,
    "environmental_risks": 50,
    "infrastructure": 45,
    "service_delivery": 35,
    "other": 25,
}

# Urgency thresholds
URGENCY_THRESHOLDS = {
    "critical": 80,
    "high": 60,
    "medium": 35,
    "low": 0,
}

# Keyword amplifiers (each adds/subtracts from severity score)
AMPLIFIER_KEYWORDS: List[Tuple[List[str], int, str]] = [
    # (keywords, score_delta, reason)
    (["dead", "death", "killed", "fatality", "fatalities", "murder"], +25, "Fatality indicators detected"),
    (["many people", "dozens", "hundreds", "mass", "widespread", "entire"], +20, "Large-scale impact indicated"),
    (["children", "child", "school", "hospital", "elderly", "women"], +20, "Vulnerable population affected"),
    (["explosion", "bomb", "attack", "shooting", "gunfire", "blast"], +25, "Violent incident indicators"),
    (["ongoing", "current", "right now", "happening now", "active"], +15, "Active/ongoing situation"),
    (["contamination", "outbreak", "epidemic", "spreading", "infectious"], +20, "Public health emergency indicators"),
    (["poison", "toxic", "chemical", "hazmat", "radiation"], +20, "Hazardous material indicators"),
    (["bribe", "embezzle", "millions", "billions", "official", "minister"], +15, "High-level corruption indicators"),
    (["isolated", "single", "one person", "small", "minor"], -15, "Limited scope indicator"),
    (["suspected", "might be", "possibly", "rumor", "heard that"], -10, "Unverified/uncertain report"),
    (["fixed", "resolved", "repaired", "was fixed"], -20, "Issue may be resolved"),
    (["yesterday", "last week", "months ago", "years ago"], -10, "Historical report (lower urgency)"),
]


class SeverityScorer:
    """Computes explainable severity and urgency scores."""

    def score(
        self,
        text: str,
        category: str,
        classification_confidence: float = 1.0,
    ) -> Dict:
        """
        Compute severity score (0–100) and urgency level.

        Args:
            text: Report content
            category: Classified category
            classification_confidence: Confidence from classifier (0–1)

        Returns:
            dict with severity_score, urgency_level, reasoning
        """
        reasoning_parts = []

        # 1. Base score from category
        base_score = CATEGORY_BASE_SCORES.get(category, 25)
        reasoning_parts.append(f"Base score for '{category}': {base_score}/100")

        # 2. Apply keyword amplifiers
        total_delta = 0
        text_lower = text.lower()

        for keywords, delta, reason in AMPLIFIER_KEYWORDS:
            if any(kw in text_lower for kw in keywords):
                total_delta += delta
                direction = "+" if delta > 0 else ""
                reasoning_parts.append(f"{reason}: {direction}{delta}")

        # 3. Length/detail bonus (detailed reports are more credible)
        word_count = len(text.split())
        if word_count > 100:
            total_delta += 5
            reasoning_parts.append("Detailed report (+5)")
        elif word_count < 10:
            total_delta -= 10
            reasoning_parts.append("Very brief report (-10)")

        # 4. Confidence adjustment
        if classification_confidence < 0.4:
            total_delta -= 10
            reasoning_parts.append(f"Low classification confidence ({classification_confidence:.0%}): -10")

        # 5. Compute final score
        raw_score = base_score + total_delta
        final_score = max(0, min(100, raw_score))

        # 6. Determine urgency
        urgency = self._compute_urgency(final_score)

        reasoning = "; ".join(reasoning_parts)
        reasoning += f". Final score: {final_score}/100 ({urgency})"

        logger.info(
            "severity_scored",
            category=category,
            score=final_score,
            urgency=urgency,
        )

        return {
            "severity_score": final_score,
            "urgency_level": urgency,
            "severity_reasoning": reasoning,
        }

    def _compute_urgency(self, score: int) -> str:
        """Map severity score to urgency level."""
        if score >= URGENCY_THRESHOLDS["critical"]:
            return "critical"
        elif score >= URGENCY_THRESHOLDS["high"]:
            return "high"
        elif score >= URGENCY_THRESHOLDS["medium"]:
            return "medium"
        else:
            return "low"

    def generate_ai_summary(
        self,
        text: str,
        category: str,
        severity: int,
        urgency: str,
        transcription: Optional[str] = None,
    ) -> str:
        """
        Generate a concise AI summary of the report.
        Used in analyst dashboard for quick triage.
        """
        # Truncate for summary
        content = transcription or text
        snippet = content[:200].strip()
        if len(content) > 200:
            snippet += "..."

        emoji_map = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
        }
        emoji = emoji_map.get(urgency, "⚪")

        category_labels = {
            "terrorism": "Terrorism",
            "corruption": "Corruption",
            "crime_signals": "Crime Signal",
            "public_safety": "Public Safety",
            "health_sanitation": "Health/Sanitation",
            "environmental_risks": "Environmental Risk",
            "infrastructure": "Infrastructure",
            "service_delivery": "Service Delivery",
        }
        cat_label = category_labels.get(category, category.title())

        return (
            f"{emoji} [{cat_label}] Severity {severity}/100 — {urgency.upper()} urgency. "
            f'Report excerpt: "{snippet}"'
        )


# Singleton
_scorer: Optional[SeverityScorer] = None


def get_scorer() -> SeverityScorer:
    global _scorer
    if _scorer is None:
        _scorer = SeverityScorer()
    return _scorer
