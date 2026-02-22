"""
Report Classifier
==================
Zero-shot classification using facebook/bart-large-mnli.

Classifies reports into predefined categories WITHOUT training data.
Uses Natural Language Inference (NLI) to match report text to category descriptions.

Categories:
  1. public_safety      — Physical safety threats, accidents, violence
  2. infrastructure     — Roads, bridges, utilities, public buildings
  3. crime_signals      — Criminal activity indicators, suspicious behavior
  4. health_sanitation  — Disease outbreaks, contamination, sanitation failures
  5. environmental_risks — Pollution, deforestation, waste dumping
  6. service_delivery   — Government service failures, corruption in services
  7. terrorism          — Terrorist activity, extremist threats
  8. corruption         — Bribery, embezzlement, abuse of power
"""

from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)

# Category definitions — carefully worded for zero-shot accuracy
CATEGORIES = {
    "public_safety": (
        "public safety threat, physical danger, accident, emergency, violence, "
        "assault, weapon, explosion, fire, flooding, crowd danger, road accident"
    ),
    "infrastructure": (
        "infrastructure failure, broken road, damaged bridge, water pipe leak, "
        "power outage, structural damage, public building collapse, utility failure"
    ),
    "crime_signals": (
        "criminal activity, theft, robbery, drug dealing, gang activity, "
        "illegal weapons, suspicious behavior, burglary, human trafficking"
    ),
    "health_sanitation": (
        "health risk, disease outbreak, contaminated water, food poisoning, "
        "unsanitary conditions, medical emergency, epidemic, sewage, waste"
    ),
    "environmental_risks": (
        "environmental damage, pollution, illegal dumping, toxic waste, "
        "deforestation, oil spill, air pollution, water contamination, wildlife harm"
    ),
    "service_delivery": (
        "government service failure, public service not working, hospital closed, "
        "school problem, electricity not restored, garbage not collected, welfare denied"
    ),
    "terrorism": (
        "terrorism, terrorist threat, bomb threat, extremist activity, "
        "militant group, planned attack, radicalization, violent extremism"
    ),
    "corruption": (
        "corruption, bribery, embezzlement, abuse of power, kickbacks, "
        "official misconduct, nepotism, fraud, misuse of public funds, extortion"
    ),
}

CATEGORY_LABELS = list(CATEGORIES.keys())
CATEGORY_DESCRIPTIONS = list(CATEGORIES.values())


class ReportClassifier:
    """Zero-shot classifier using facebook/bart-large-mnli."""

    def __init__(self, model_name: str = "facebook/bart-large-mnli"):
        self.model_name = model_name
        self._pipeline = None
        logger.info("classifier_initialized", model=model_name)

    def _get_pipeline(self):
        """Lazy load the classification pipeline."""
        if self._pipeline is None:
            from transformers import pipeline

            logger.info("loading_classification_model", model=self.model_name)
            self._pipeline = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                # Use CPU; set device=0 for GPU
                device=-1,
            )
            logger.info("classification_model_loaded")
        return self._pipeline

    async def classify(
        self, text: str, multi_label: bool = False
    ) -> Dict:
        """
        Classify report text into categories.

        Args:
            text: Report content to classify
            multi_label: If True, multiple categories can be true simultaneously

        Returns:
            dict with keys: category, confidence, all_scores, reasoning
        """
        if not text or len(text.strip()) < 5:
            return {
                "category": "other",
                "subcategory": None,
                "confidence": 0.0,
                "all_scores": {},
                "reasoning": "Insufficient text for classification",
            }

        try:
            pipeline = self._get_pipeline()

            # Truncate text to prevent OOM (BART has 1024 token limit)
            truncated_text = text[:1024]

            result = pipeline(
                truncated_text,
                candidate_labels=CATEGORY_DESCRIPTIONS,
                multi_label=multi_label,
            )

            # Map description back to category key
            scores_by_category = {}
            for label, score in zip(result["labels"], result["scores"]):
                # Find which category this description belongs to
                for cat_key, cat_desc in CATEGORIES.items():
                    if label == cat_desc:
                        scores_by_category[cat_key] = score
                        break

            # Top category
            top_category = max(scores_by_category, key=scores_by_category.get)
            top_confidence = scores_by_category[top_category]

            # Generate reasoning
            reasoning = self._generate_reasoning(text, top_category, top_confidence, scores_by_category)

            logger.info(
                "classification_complete",
                category=top_category,
                confidence=round(top_confidence, 3),
            )

            return {
                "category": top_category,
                "subcategory": None,
                "confidence": round(top_confidence, 4),
                "all_scores": {k: round(v, 4) for k, v in scores_by_category.items()},
                "reasoning": reasoning,
            }

        except Exception as e:
            logger.error("classification_failed", error=str(e))
            return {
                "category": "other",
                "subcategory": None,
                "confidence": 0.0,
                "all_scores": {},
                "reasoning": f"Classification failed: {type(e).__name__}",
            }

    def _generate_reasoning(
        self,
        text: str,
        category: str,
        confidence: float,
        all_scores: Dict[str, float],
    ) -> str:
        """Generate human-readable classification reasoning."""
        confidence_label = (
            "high" if confidence > 0.7
            else "moderate" if confidence > 0.4
            else "low"
        )

        # Second best category
        sorted_cats = sorted(all_scores.items(), key=lambda x: x[1], reverse=True)
        second_cat = sorted_cats[1] if len(sorted_cats) > 1 else None

        reasoning = (
            f"Classified as '{category}' with {confidence_label} confidence "
            f"({confidence:.1%}). "
        )

        if second_cat and second_cat[1] > 0.2:
            reasoning += (
                f"Secondary indicator: '{second_cat[0]}' ({second_cat[1]:.1%}). "
            )

        # Key word hints
        text_lower = text.lower()
        if "brib" in text_lower or "money" in text_lower:
            reasoning += "Financial irregularity keywords detected. "
        if "body" in text_lower or "dead" in text_lower or "kill" in text_lower:
            reasoning += "High-severity violence keywords detected. "
        if "water" in text_lower and ("dirty" in text_lower or "contam" in text_lower):
            reasoning += "Water contamination indicators present. "

        return reasoning.strip()


# Singleton
_classifier: Optional[ReportClassifier] = None


def get_classifier(model_name: str = "facebook/bart-large-mnli") -> ReportClassifier:
    global _classifier
    if _classifier is None:
        _classifier = ReportClassifier(model_name=model_name)
    return _classifier
