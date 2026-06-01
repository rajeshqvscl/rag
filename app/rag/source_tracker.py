"""
Source Attribution Layer
Tracks which chunks/sections extracted facts come from
"""
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SourceAttribution:
    """Represents the source of an extracted fact"""
    text: str
    page: int = 0
    section: str = "unknown"
    chunk_index: int = -1
    doc_id: str = ""
    doc_name: str = ""
    confidence: float = 1.0
    extract_method: str = "direct"
    original_text: str = ""


@dataclass
class ExtractedFact:
    """A fact extracted from documents with source tracking"""
    name: str
    value: Any
    normalized_value: str = ""
    attribution: Optional[SourceAttribution] = None
    confidence: float = 1.0
    extraction_time: datetime = field(default_factory=datetime.now)
    verified: bool = False
    fiscal_period: str = ""
    fiscal_year: int = 0
    comparison_period: str = ""
    growth_percentage: float = 0.0
    unit: str = ""
    provenance: List[Dict] = field(default_factory=list)


class SourceTracker:
    """
    Tracks source information for all extracted facts
    Enables citation and verification
    """

    def __init__(self):
        self.facts: List[ExtractedFact] = []
        self.chunk_sources: Dict[str, List[SourceAttribution]] = {}

    def add_fact(self, name: str, value: Any, source: SourceAttribution,
                 confidence: float = 1.0, normalized_value: str = "") -> ExtractedFact:
        """Add an extracted fact with source attribution"""
        fact = ExtractedFact(
            name=name,
            value=value,
            normalized_value=normalized_value,
            attribution=source,
            confidence=confidence
        )
        self.facts.append(fact)
        return fact

    def add_chunk_source(self, chunk_text: str, source: SourceAttribution):
        """Register a chunk with its source information"""
        if chunk_text not in self.chunk_sources:
            self.chunk_sources[chunk_text] = []
        self.chunk_sources[chunk_text].append(source)

    def get_facts_by_section(self, section: str) -> List[ExtractedFact]:
        """Get all facts from a specific section"""
        return [
            f for f in self.facts
            if f.attribution and f.attribution.section == section
        ]

    def get_facts_by_page(self, page: int) -> List[ExtractedFact]:
        """Get all facts from a specific page"""
        return [
            f for f in self.facts
            if f.attribution and f.attribution.page == page
        ]

    def verify_fact(self, fact_name: str) -> bool:
        """Check if a fact appears in multiple sources (higher confidence)"""
        matching = [f for f in self.facts if f.name == fact_name]
        if len(matching) >= 2:
            for fact in matching:
                fact.verified = True
                fact.confidence = min(fact.confidence + 0.2, 1.0)
            return True
        return False

    def to_citation_format(self) -> List[Dict]:
        """Convert facts to citation format"""
        citations = []
        for fact in self.facts:
            if fact.attribution:
                citations.append({
                    "fact": fact.name,
                    "value": fact.normalized_value or str(fact.value),
                    "source": {
                        "page": fact.attribution.page,
                        "section": fact.attribution.section,
                        "text": fact.attribution.text[:100] + "..." if len(fact.attribution.text) > 100 else fact.attribution.text,
                        "doc_name": fact.attribution.doc_name
                    },
                    "confidence": fact.confidence,
                    "verified": fact.verified
                })
        return citations

    def get_verification_report(self) -> Dict:
        """Generate a report on fact verification status"""
        total = len(self.facts)
        verified = sum(1 for f in self.facts if f.verified)
        high_conf = sum(1 for f in self.facts if f.confidence >= 0.8)

        by_section = {}
        for fact in self.facts:
            if fact.attribution:
                section = fact.attribution.section
                if section not in by_section:
                    by_section[section] = {"total": 0, "verified": 0}
                by_section[section]["total"] += 1
                if fact.verified:
                    by_section[section]["verified"] += 1

        return {
            "total_facts": total,
            "verified_facts": verified,
            "high_confidence_facts": high_conf,
            "verification_rate": verified / total if total > 0 else 0,
            "by_section": by_section
        }


def create_attribution(chunks: List[str], metadata: Dict[str, Any],
                       extraction_result: Dict) -> SourceTracker:
    """
    Create source attribution for extracted data

    Args:
        chunks: List of document chunks used for extraction
        metadata: Document metadata (doc_id, doc_name, etc.)
        extraction_result: The structured extraction result

    Returns:
        SourceTracker with attribution information
    """
    tracker = SourceTracker()

    for idx, chunk in enumerate(chunks):
        attribution = SourceAttribution(
            text=chunk[:200] + "..." if len(chunk) > 200 else chunk,
            page=metadata.get("page", 0),
            section=metadata.get("section", "unknown"),
            chunk_index=idx,
            doc_id=metadata.get("doc_id", ""),
            doc_name=metadata.get("doc_name", "Unknown Document")
        )
        tracker.add_chunk_source(chunk, attribution)

    def extract_facts_from_dict(data: Dict, prefix: str = ""):
        """Recursively extract facts from nested dict"""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                extract_facts_from_dict(value, full_key)
            elif value and not isinstance(value, list):
                matching_chunks = [
                    c for c in chunks
                    if str(value).lower() in c.lower()
                ]
                if matching_chunks:
                    source = SourceAttribution(
                        text=matching_chunks[0][:150] + "...",
                        doc_id=metadata.get("doc_id", ""),
                        doc_name=metadata.get("doc_name", "Unknown"),
                        extract_method="text_match"
                    )
                    tracker.add_fact(full_key, value, source, confidence=0.8)

    extract_facts_from_dict(extraction_result)

    return tracker


def format_with_citations(extraction: Dict, tracker: SourceTracker) -> str:
    """
    Format extraction result with source citations

    Example output:
    Revenue: ₹5.1 Cr [Source: Page 14, Financials]
    """
    output_parts = []

    for key, value in extraction.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if sub_value and not isinstance(sub_value, list):
                    facts = [
                        f for f in tracker.facts
                        if f.name == f"{key}.{sub_key}" and f.attribution
                    ]
                    if facts:
                        attr = facts[0].attribution
                        source_note = f"[Page {attr.page}, {attr.section.title()}]"
                        output_parts.append(f"- **{sub_key}**: {sub_value} {source_note}")
        elif value and not isinstance(value, list):
            facts = [f for f in tracker.facts if f.name == key and f.attribution]
            if facts:
                attr = facts[0].attribution
                source_note = f"[Page {attr.page}, {attr.section.title()}]"
                output_parts.append(f"- **{key}**: {value} {source_note}")

    return "\n".join(output_parts)


def generate_citation_summary(tracker: SourceTracker) -> Dict:
    """
    Generate a summary of all citations and their sources
    """
    citations = tracker.to_citation_format()

    summary = {
        "total_facts": len(citations),
        "verified_count": sum(1 for c in citations if c.get("verified")),
        "pages_used": sorted(set(c["source"]["page"] for c in citations if c["source"].get("page"))),
        "sections_covered": list(set(c["source"]["section"] for c in citations)),
        "high_confidence_facts": [
            c for c in citations if c["confidence"] >= 0.8
        ]
    }

    return summary


def format_verified_metrics(extraction: Dict, tracker: SourceTracker) -> str:
    """
    Format metrics with verification status

    Returns:
        Formatted string showing VERIFIED vs AI INSIGHT
    """
    verified = []
    insights = []

    for fact in tracker.facts:
        if not fact.attribution:
            continue

        attr = fact.attribution
        source = f"Page {attr.page}, {attr.section.title()}"

        if fact.verified:
            verified.append(f"- **{fact.name}**: {fact.normalized_value or fact.value} [Verified: {source}]")
        elif fact.confidence >= 0.7:
            verified.append(f"- **{fact.name}**: {fact.normalized_value or fact.value} [Source: {source}]")
        else:
            insights.append(f"- **{fact.name}**: {fact.normalized_value or fact.value} [AI Insight]")

    output = ["### VERIFIED METRICS"]
    output.extend(verified[:10])

    if insights:
        output.append("\n### AI INSIGHTS")
        output.extend(insights[:5])

    return "\n".join(output)