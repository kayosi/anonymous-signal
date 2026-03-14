"""
False Report Detection
=======================
Phase 1: Spam / content quality filter
Phase 2: Cosine similarity duplicate detection

Integrated into the AI pipeline — runs before classification.
Results stored in report_ai_analysis table via credibility_score + flags.
"""

import re
import unicodedata
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

# ─── Phase 1: Spam / Content Quality Filter ──────────────────────────────────

# Minimum meaningful content length (characters)
MIN_CONTENT_LENGTH = 20
# Maximum ratio of repeated characters (e.g. "aaaaaaa")
MAX_REPEAT_RATIO = 0.4
# Maximum ratio of non-alphabetic characters (e.g. "!!!!!!!")
MAX_NOISE_RATIO = 0.6
# Known spam/test patterns
SPAM_PATTERNS = [
    r'^test\s*$',
    r'^hello\s*$',
    r'^testing\s*$',
    r'^asdf+$',
    r'^(.)\1{9,}$',          # 10+ repeated same char
    r'^\d+$',                 # only numbers
    r'^[^a-zA-Z]{0,5}$',     # almost no letters
    r'(buy now|click here|free money|congratulations you won)',
]

class ContentQualityResult:
    def __init__(
        self,
        passed: bool,
        credibility_score: float,  # 0.0 - 1.0
        flags: list[str],
        rejection_reason: Optional[str] = None,
    ):
        self.passed = passed
        self.credibility_score = credibility_score
        self.flags = flags
        self.rejection_reason = rejection_reason

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "credibility_score": round(self.credibility_score, 3),
            "flags": self.flags,
            "rejection_reason": self.rejection_reason,
        }


def _normalize(text: str) -> str:
    """Normalize unicode, strip whitespace."""
    text = unicodedata.normalize("NFKC", text)
    return text.strip().lower()


def phase1_content_filter(text: str) -> ContentQualityResult:
    """
    Phase 1: Spam and content quality filter.
    Returns a ContentQualityResult with pass/fail and credibility score.
    """
    flags = []
    score = 1.0  # start at full credibility, deduct for issues

    if not text or not text.strip():
        return ContentQualityResult(
            passed=False,
            credibility_score=0.0,
            flags=["empty_content"],
            rejection_reason="Report content is empty.",
        )

    normalized = _normalize(text)
    length = len(normalized)

    # ── Length check ──────────────────────────────────────────────────────────
    if length < MIN_CONTENT_LENGTH:
        return ContentQualityResult(
            passed=False,
            credibility_score=0.1,
            flags=["too_short"],
            rejection_reason=f"Content too short ({length} chars). Minimum is {MIN_CONTENT_LENGTH}.",
        )

    # ── Spam pattern check ────────────────────────────────────────────────────
    for pattern in SPAM_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return ContentQualityResult(
                passed=False,
                credibility_score=0.0,
                flags=["spam_pattern"],
                rejection_reason="Content matches known spam pattern.",
            )

    # ── Repeated character ratio ──────────────────────────────────────────────
    if length > 5:
        max_run = max(
            len(list(g)) for _, g in
            __import__('itertools').groupby(normalized)
        )
        repeat_ratio = max_run / length
        if repeat_ratio > MAX_REPEAT_RATIO:
            flags.append("high_repetition")
            score -= 0.3

    # ── Noise ratio (non-alphabetic) ──────────────────────────────────────────
    alpha_count = sum(1 for c in normalized if c.isalpha())
    noise_ratio = 1.0 - (alpha_count / max(length, 1))
    if noise_ratio > MAX_NOISE_RATIO:
        flags.append("high_noise_ratio")
        score -= 0.25

    # ── All caps check ────────────────────────────────────────────────────────
    upper_ratio = sum(1 for c in text if c.isupper()) / max(len(text), 1)
    if upper_ratio > 0.7 and len(text) > 30:
        flags.append("excessive_caps")
        score -= 0.1

    # ── Very short word variety (possible gibberish) ──────────────────────────
    words = normalized.split()
    unique_words = set(words)
    if len(words) > 5 and len(unique_words) / len(words) < 0.3:
        flags.append("low_vocabulary_diversity")
        score -= 0.2

    score = max(0.0, min(1.0, score))
    passed = score >= 0.4 and "spam_pattern" not in flags

    logger.info(
        "phase1_content_filter",
        passed=passed,
        score=round(score, 3),
        flags=flags,
        length=length,
    )

    return ContentQualityResult(
        passed=passed,
        credibility_score=score,
        flags=flags,
        rejection_reason=None if passed else f"Content quality too low. Issues: {', '.join(flags)}",
    )


# ─── Phase 2: Cosine Similarity Duplicate Detection ──────────────────────────

class DuplicateDetectionResult:
    def __init__(
        self,
        is_duplicate: bool,
        similarity_score: float,
        similar_report_id: Optional[str],
        credibility_penalty: float,
    ):
        self.is_duplicate = is_duplicate
        self.similarity_score = similarity_score
        self.similar_report_id = similar_report_id
        self.credibility_penalty = credibility_penalty

    def to_dict(self) -> dict:
        return {
            "is_duplicate": self.is_duplicate,
            "similarity_score": round(self.similarity_score, 3),
            "similar_report_id": self.similar_report_id,
            "credibility_penalty": round(self.credibility_penalty, 3),
        }


# Threshold above which a report is considered a near-duplicate
DUPLICATE_THRESHOLD = 0.92
# Threshold above which it is flagged as suspicious (but not rejected)
SUSPICIOUS_THRESHOLD = 0.75
# How many recent reports to compare against (sliding window)
COMPARISON_WINDOW = 100


async def phase2_duplicate_detection(
    text: str,
    report_id: str,
    category: str,
    pool,  # asyncpg pool
) -> DuplicateDetectionResult:
    """
    Phase 2: Compare new report against recent reports in same category
    using cosine similarity on TF-IDF vectors (no ML model needed).
    Falls back to embedding similarity if MiniLM is available.
    """
    try:
        # Fetch recent reports in same category
        rows = await pool.fetch(
            """
            SELECT r.id, r.encrypted_content
            FROM reports r
            WHERE r.user_category = $1
              AND r.id != $2
              AND r.is_archived = false
              AND r.submitted_at > NOW() - INTERVAL '7 days'
            ORDER BY r.submitted_at DESC
            LIMIT $3
            """,
            category,
            report_id,
            COMPARISON_WINDOW,
        )

        if not rows:
            return DuplicateDetectionResult(
                is_duplicate=False,
                similarity_score=0.0,
                similar_report_id=None,
                credibility_penalty=0.0,
            )

        # Try embedding-based similarity first
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            model = SentenceTransformer("all-MiniLM-L6-v2")

            # We need to decrypt existing reports to compare
            # Import encryption inline to avoid circular deps
            import os
            from cryptography.fernet import Fernet
            enc_key = os.getenv("ENCRYPTION_KEY", "")
            fernet = Fernet(enc_key.encode()) if enc_key else None

            candidates = []
            for row in rows:
                try:
                    if fernet and row["encrypted_content"]:
                        import json
                        decrypted = fernet.decrypt(row["encrypted_content"].encode()).decode()
                        content = json.loads(decrypted)
                        candidate_text = content.get("text", "")
                        if candidate_text:
                            candidates.append((str(row["id"]), candidate_text))
                except Exception:
                    continue

            if candidates:
                texts = [text] + [c[1] for c in candidates]
                embeddings = model.encode(texts, normalize_embeddings=True)
                new_emb = embeddings[0]
                candidate_embs = embeddings[1:]

                similarities = np.dot(candidate_embs, new_emb)
                max_idx = int(np.argmax(similarities))
                max_sim = float(similarities[max_idx])
                most_similar_id = candidates[max_idx][0]

                is_dup = max_sim >= DUPLICATE_THRESHOLD
                penalty = max(0.0, (max_sim - SUSPICIOUS_THRESHOLD) * 2) if max_sim > SUSPICIOUS_THRESHOLD else 0.0

                logger.info(
                    "phase2_duplicate_embedding",
                    max_similarity=round(max_sim, 3),
                    is_duplicate=is_dup,
                    similar_to=most_similar_id[:8] if is_dup else None,
                )

                return DuplicateDetectionResult(
                    is_duplicate=is_dup,
                    similarity_score=max_sim,
                    similar_report_id=most_similar_id if max_sim > SUSPICIOUS_THRESHOLD else None,
                    credibility_penalty=penalty,
                )

        except ImportError:
            pass  # Fall through to TF-IDF

        # ── TF-IDF cosine similarity fallback ─────────────────────────────────
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        # Collect decrypted texts
        import os, json
        from cryptography.fernet import Fernet
        enc_key = os.getenv("ENCRYPTION_KEY", "")
        fernet = Fernet(enc_key.encode()) if enc_key else None

        candidates = []
        for row in rows:
            try:
                if fernet and row["encrypted_content"]:
                    decrypted = fernet.decrypt(row["encrypted_content"].encode()).decode()
                    content = json.loads(decrypted)
                    candidate_text = content.get("text", "")
                    if candidate_text and len(candidate_text) > 10:
                        candidates.append((str(row["id"]), candidate_text))
            except Exception:
                continue

        if not candidates:
            return DuplicateDetectionResult(False, 0.0, None, 0.0)

        all_texts = [text] + [c[1] for c in candidates]
        vectorizer = TfidfVectorizer(max_features=500, stop_words="english")
        tfidf_matrix = vectorizer.fit_transform(all_texts)
        sims = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])[0]
        max_idx = int(np.argmax(sims))
        max_sim = float(sims[max_idx])
        most_similar_id = candidates[max_idx][0]

        is_dup = max_sim >= DUPLICATE_THRESHOLD
        penalty = max(0.0, (max_sim - SUSPICIOUS_THRESHOLD) * 1.5) if max_sim > SUSPICIOUS_THRESHOLD else 0.0

        logger.info(
            "phase2_duplicate_tfidf",
            max_similarity=round(max_sim, 3),
            is_duplicate=is_dup,
        )

        return DuplicateDetectionResult(
            is_duplicate=is_dup,
            similarity_score=max_sim,
            similar_report_id=most_similar_id if max_sim > SUSPICIOUS_THRESHOLD else None,
            credibility_penalty=penalty,
        )

    except Exception as e:
        logger.warning("phase2_duplicate_detection_failed", error=str(e))
        return DuplicateDetectionResult(False, 0.0, None, 0.0)


# ─── Combined Credibility Assessment ─────────────────────────────────────────

class CredibilityAssessment:
    def __init__(
        self,
        should_reject: bool,
        credibility_score: float,
        flags: list[str],
        rejection_reason: Optional[str],
        is_duplicate: bool,
        duplicate_of: Optional[str],
    ):
        self.should_reject = should_reject
        self.credibility_score = credibility_score
        self.flags = flags
        self.rejection_reason = rejection_reason
        self.is_duplicate = is_duplicate
        self.duplicate_of = duplicate_of

    def to_dict(self) -> dict:
        return {
            "should_reject": self.should_reject,
            "credibility_score": round(self.credibility_score, 3),
            "flags": self.flags,
            "rejection_reason": self.rejection_reason,
            "is_duplicate": self.is_duplicate,
            "duplicate_of": self.duplicate_of,
        }


async def assess_credibility(
    text: str,
    report_id: str,
    category: str,
    pool,
) -> CredibilityAssessment:
    """
    Run full credibility assessment (Phase 1 + Phase 2).
    Returns combined result used by the AI pipeline.
    """
    # Phase 1
    quality = phase1_content_filter(text)
    if not quality.passed:
        return CredibilityAssessment(
            should_reject=True,
            credibility_score=quality.credibility_score,
            flags=quality.flags,
            rejection_reason=quality.rejection_reason,
            is_duplicate=False,
            duplicate_of=None,
        )

    # Phase 2 (only if Phase 1 passed)
    duplicate = await phase2_duplicate_detection(text, report_id, category, pool)

    all_flags = quality.flags.copy()
    final_score = quality.credibility_score - duplicate.credibility_penalty

    if duplicate.is_duplicate:
        all_flags.append("near_duplicate")
    elif duplicate.similar_report_id:
        all_flags.append("similar_to_existing")

    final_score = max(0.0, min(1.0, final_score))
    should_reject = duplicate.is_duplicate and final_score < 0.1

    return CredibilityAssessment(
        should_reject=should_reject,
        credibility_score=final_score,
        flags=all_flags,
        rejection_reason="Near-duplicate of an existing report." if should_reject else None,
        is_duplicate=duplicate.is_duplicate,
        duplicate_of=duplicate.similar_report_id,
    )