"""
Clustering Module
==================
Detects patterns, similar reports, and emerging threats.

Pipeline:
  1. Encode report text → embedding vector (sentence-transformers)
  2. Compare to existing cluster centroids (cosine similarity)
  3. If similar cluster found → assign to cluster
  4. If no match → create new cluster
  5. Update cluster metadata and trigger alerts if surge detected

Used to detect:
  - Multiple reports of same incident (verification signal)
  - Geographic hotspots (if location hints provided)
  - Category surges (e.g., 15 health complaints in 24h)
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import structlog

logger = structlog.get_logger(__name__)

# Similarity threshold for cluster assignment (cosine similarity)
# 0.8 = very similar, 0.5 = somewhat related
CLUSTER_SIMILARITY_THRESHOLD = 0.72


class EmbeddingService:
    """Generates semantic embeddings for report text."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("loading_embedding_model", model=self.model_name)
            self._model = SentenceTransformer(self.model_name)
            logger.info("embedding_model_loaded")
        return self._model

    def encode(self, text: str) -> List[float]:
        """Encode text to embedding vector."""
        if not text:
            return []
        try:
            model = self._get_model()
            embedding = model.encode(text, normalize_embeddings=True)
            return embedding.tolist()
        except Exception as e:
            logger.error("embedding_failed", error=str(e))
            return []

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        if not vec1 or not vec2:
            return 0.0
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


class ClusteringService:
    """
    Manages report clusters using centroid-based online clustering.
    Designed to work with async database operations.
    """

    def __init__(self, embedding_service: EmbeddingService):
        self.embeddings = embedding_service

    async def assign_cluster(
        self,
        report_id: str,
        text: str,
        category: str,
        db,
        alert_service,
    ) -> Optional[str]:
        """
        Assign a report to an existing cluster or create a new one.

        Returns:
            cluster_id (UUID string) or None if clustering fails
        """
        from sqlalchemy import select, update, desc
        from app.models.models import Cluster, Alert

        # Generate embedding for this report
        embedding = self.embeddings.encode(text)
        use_category_fallback = not embedding

        # Load active clusters for same category
        result = await db.execute(
            select(Cluster)
            .where(
                Cluster.category == category,
                Cluster.is_active == True,
            )
            .order_by(desc(Cluster.last_updated))
            .limit(20)
        )
        existing_clusters = result.scalars().all()

        # Find best matching cluster
        best_cluster = None
        best_similarity = 0.0

        if use_category_fallback:
            # No embeddings available — use category-based clustering as fallback
            # Group all reports in same category into one cluster per category
            if existing_clusters:
                best_cluster = existing_clusters[0]
                best_similarity = CLUSTER_SIMILARITY_THRESHOLD  # force assignment
        else:
            for cluster in existing_clusters:
                if cluster.centroid_embedding:
                    sim = self.embeddings.cosine_similarity(
                        embedding, cluster.centroid_embedding
                    )
                    if sim > best_similarity:
                        best_similarity = sim
                        best_cluster = cluster

        if best_cluster and best_similarity >= CLUSTER_SIMILARITY_THRESHOLD:
            # Assign to existing cluster and update centroid
            new_count = best_cluster.report_count + 1

            # Rolling average centroid update (skip if no embeddings)
            if embedding and best_cluster.centroid_embedding:
                old_centroid = np.array(best_cluster.centroid_embedding)
                new_embedding = np.array(embedding)
                updated_centroid = (
                    (old_centroid * best_cluster.report_count + new_embedding) / new_count
                ).tolist()
            else:
                updated_centroid = best_cluster.centroid_embedding

            await db.execute(
                update(Cluster)
                .where(Cluster.id == best_cluster.id)
                .values(
                    report_count=new_count,
                    centroid_embedding=updated_centroid,
                    last_updated=datetime.utcnow(),
                )
            )

            # Check for surge alert
            await self._check_surge_alert(
                best_cluster, new_count, category, db, alert_service
            )

            logger.info(
                "report_assigned_to_cluster",
                cluster_id=str(best_cluster.id)[:8],
                similarity=round(best_similarity, 3),
                cluster_size=new_count,
            )
            return str(best_cluster.id)

        else:
            # Create new cluster
            new_cluster = Cluster(
                id=uuid.uuid4(),
                category=category,
                label=self._generate_cluster_label(text, category),
                centroid_embedding=embedding if embedding else None,
                report_count=1,
                is_active=True,
            )
            db.add(new_cluster)

            logger.info(
                "new_cluster_created",
                cluster_id=str(new_cluster.id)[:8],
                category=category,
            )
            return str(new_cluster.id)

    def _generate_cluster_label(self, text: str, category: str) -> str:
        """Generate a descriptive label for a new cluster."""
        # Extract first meaningful sentence as cluster label
        sentences = text.split(".")
        first_sentence = sentences[0].strip() if sentences else text[:80]

        cat_prefix = {
            "terrorism": "🔴 Terror Signal",
            "corruption": "💰 Corruption Report",
            "crime_signals": "🚨 Crime Signal",
            "public_safety": "⚠️ Safety Incident",
            "health_sanitation": "🏥 Health Report",
            "environmental_risks": "🌿 Environmental Issue",
            "infrastructure": "🏗️ Infrastructure Issue",
            "service_delivery": "📋 Service Failure",
        }.get(category, "📍 Report Cluster")

        label = f"{cat_prefix}: {first_sentence[:60]}"
        if len(first_sentence) > 60:
            label += "..."

        return label

    async def _check_surge_alert(
        self,
        cluster,
        new_count: int,
        category: str,
        db,
        alert_service,
    ):
        """
        Trigger alert if cluster grows faster than expected.
        Surge thresholds:
          - 5 reports in same cluster → medium alert
          - 15 reports → high alert
          - 30 reports → critical alert
        """
        from sqlalchemy import select, func
        from app.models.models import Alert, ReportAIAnalysis

        # Count reports in this cluster in last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)

        recent_count = await db.scalar(
            select(func.count(ReportAIAnalysis.id))
            .where(
                ReportAIAnalysis.cluster_id == cluster.id,
                ReportAIAnalysis.analyzed_at >= cutoff,
            )
        )

        # Determine if alert threshold crossed
        alert_threshold = None
        alert_severity = None

        if recent_count >= 30 and new_count % 10 == 0:  # Alert every 10 after 30
            alert_threshold = 30
            alert_severity = "critical"
        elif recent_count >= 15 and new_count == 15:
            alert_threshold = 15
            alert_severity = "high"
        elif recent_count >= 5 and new_count == 5:
            alert_threshold = 5
            alert_severity = "medium"

        if alert_threshold:
            alert = Alert(
                alert_type="surge",
                category=category,
                cluster_id=cluster.id,
                title=f"Report surge: {cluster.label or category}",
                description=(
                    f"{recent_count} reports matching pattern '{cluster.label}' "
                    f"detected in the last 24 hours. "
                    f"Category: {category}. Immediate review recommended."
                ),
                severity_level=alert_severity,
                report_count=recent_count,
                time_window_hours=24,
            )
            db.add(alert)
            logger.warning(
                "surge_alert_created",
                category=category,
                count=recent_count,
                severity=alert_severity,
            )


# Singleton instances
_embedding_service: Optional[EmbeddingService] = None
_clustering_service: Optional[ClusteringService] = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


def get_clustering_service() -> ClusteringService:
    global _clustering_service
    if _clustering_service is None:
        emb = get_embedding_service()
        _clustering_service = ClusteringService(emb)
    return _clustering_service