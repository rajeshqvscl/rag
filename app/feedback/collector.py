"""
User Feedback System
Collects and manages user feedback for continuous improvement
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum


class FeedbackType(str, Enum):
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT = "incorrect"
    MISSING_CONTEXT = "missing_context"
    SUGGESTION = "suggestion"
    BUG = "bug"


class FeedbackRating(int, Enum):
    TERRIBLE = 1
    POOR = 2
    OK = 3
    GOOD = 4
    EXCELLENT = 5


@dataclass
class FeedbackEntry:
    """Single feedback entry"""
    query: str
    response: str
    rating: int
    feedback_type: str
    corrections: Optional[str] = None
    timestamp: datetime = None
    metadata: Dict = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict:
        return {
            "query": self.query,
            "response": self.response[:500] if self.response else "",
            "rating": self.rating,
            "feedback_type": self.feedback_type,
            "corrections": self.corrections,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


class FeedbackCollector:
    """In-memory feedback collector (for demo)"""

    def __init__(self):
        self.feedback_entries: List[FeedbackEntry] = []
        self._feedback_by_rating = {i: [] for i in range(1, 6)}

    def add(self, entry: FeedbackEntry):
        """Add a feedback entry"""
        self.feedback_entries.append(entry)
        self._feedback_by_rating[entry.rating].append(entry)

    def get_all(self) -> List[FeedbackEntry]:
        return self.feedback_entries

    def get_by_rating(self, min_rating: int = 1, max_rating: int = 5) -> List[FeedbackEntry]:
        """Get feedback entries within rating range"""
        results = []
        for rating in range(min_rating, max_rating + 1):
            results.extend(self._feedback_by_rating.get(rating, []))
        return results

    def get_low_rated(self, threshold: int = 2) -> List[FeedbackEntry]:
        """Get entries with rating below threshold"""
        return self.get_by_rating(min_rating=1, max_rating=threshold)

    def get_high_rated(self, threshold: int = 4) -> List[FeedbackEntry]:
        """Get entries with rating above threshold"""
        return self.get_by_rating(min_rating=threshold, max_rating=5)

    def get_by_type(self, feedback_type: str) -> List[FeedbackEntry]:
        """Get feedback by type"""
        return [e for e in self.feedback_entries if e.feedback_type == feedback_type]

    def get_stats(self) -> Dict:
        """Get feedback statistics"""
        total = len(self.feedback_entries)
        if total == 0:
            return {
                "total": 0,
                "avg_rating": 0,
                "by_type": {},
                "by_rating": {}
            }

        ratings = [e.rating for e in self.feedback_entries]

        by_type = {}
        for entry in self.feedback_entries:
            ft = entry.feedback_type
            by_type[ft] = by_type.get(ft, 0) + 1

        by_rating = {i: len(self._feedback_by_rating[i]) for i in range(1, 6)}

        return {
            "total": total,
            "avg_rating": sum(ratings) / len(ratings),
            "by_type": by_type,
            "by_rating": by_rating,
            "low_rated_count": len(self.get_low_rated()),
            "high_rated_count": len(self.get_high_rated()),
            "corrections_count": sum(1 for e in self.feedback_entries if e.corrections)
        }

    def analyze_patterns(self) -> Dict:
        """Analyze common issues from feedback"""
        low_rated = self.get_low_rated()

        patterns = {
            "missing_context_issues": 0,
            "incorrect_facts": 0,
            "poor_formatting": 0,
            "incomplete_responses": 0,
            "unclear_thesis": 0
        }

        for entry in low_rated:
            response_lower = entry.response.lower() if entry.response else ""

            if entry.feedback_type == FeedbackType.MISSING_CONTEXT.value:
                patterns["missing_context_issues"] += 1

            if any(word in response_lower for word in ["incorrect", "wrong", "error"]):
                patterns["incorrect_facts"] += 1

            if len(entry.response) < 100:
                patterns["incomplete_responses"] += 1

            if "thesis" not in response_lower and "outlook" not in response_lower:
                patterns["unclear_thesis"] += 1

        return {
            "total_issues": len(low_rated),
            "patterns": patterns,
            "top_issues": sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:3]
        }


# Global feedback collector
FEEDBACK_COLLECTOR = FeedbackCollector()


def submit_feedback(
    query: str,
    response: str,
    rating: int,
    feedback_type: str,
    corrections: Optional[str] = None,
    metadata: Dict = None
) -> Dict:
    """
    Submit user feedback

    Args:
        query: Original user query
        response: System response
        rating: 1-5 rating
        feedback_type: Type of feedback
        corrections: User-provided corrections
        metadata: Additional metadata

    Returns:
        Confirmation of feedback submission
    """
    if not 1 <= rating <= 5:
        return {"success": False, "error": "Rating must be between 1 and 5"}

    entry = FeedbackEntry(
        query=query,
        response=response,
        rating=rating,
        feedback_type=feedback_type,
        corrections=corrections,
        metadata=metadata or {}
    )

    FEEDBACK_COLLECTOR.add(entry)

    return {
        "success": True,
        "message": "Feedback submitted successfully",
        "feedback_id": len(FEEDBACK_COLLECTOR.feedback_entries)
    }


def get_feedback_stats() -> Dict:
    """Get feedback statistics"""
    return FEEDBACK_COLLECTOR.get_stats()


def get_feedback_analysis() -> Dict:
    """Get detailed analysis of feedback patterns"""
    return FEEDBACK_COLLECTOR.analyze_patterns()


def get_improvement_suggestions() -> List[str]:
    """
    Generate improvement suggestions based on feedback analysis
    """
    analysis = FEEDBACK_COLLECTOR.analyze_patterns()
    suggestions = []

    patterns = analysis.get("patterns", {})

    if patterns.get("missing_context_issues", 0) > 2:
        suggestions.append("Increase retrieval top_k for more context")
        suggestions.append("Improve chunking to preserve more context")

    if patterns.get("incorrect_facts", 0) > 2:
        suggestions.append("Add fact verification layer")
        suggestions.append("Improve validation rules for extracted metrics")

    if patterns.get("unclear_thesis", 0) > 3:
        suggestions.append("Strengthen investment thesis generation prompt")
        suggestions.append("Add template for thesis structure")

    if patterns.get("incomplete_responses", 0) > 2:
        suggestions.append("Review output length constraints")
        suggestions.append("Ensure all sections have content")

    if not suggestions:
        suggestions.append("System is performing well based on feedback")

    return suggestions


def export_training_data() -> List[Dict]:
    """
    Export feedback data for potential fine-tuning
    """
    high_rated = FEEDBACK_COLLECTOR.get_high_rated(threshold=4)

    training_data = []
    for entry in high_rated:
        training_data.append({
            "instruction": f"Query: {entry.query}\nFeedback Type: {entry.feedback_type}",
            "response": entry.response,
            "rating": entry.rating,
            "metadata": entry.metadata
        })

    return training_data