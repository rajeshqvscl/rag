"""
Query Intent Detection v3 - Enhanced classification with weighted scoring, multi-intent, and LLM fallback
"""

import os
import json
from app.core.llm_client import get_safe_client

INTENT_KEYWORDS = {
    "financial": {
        "keywords": [
            "revenue", "profit", "margin", "income", "expense", "cost", "arr", "mrr",
            "growth", "growth rate", "traction", "sales", "earnings", "ebitda",
            "financial", "funding", "investment", "valuation", "runway", "cash",
            "burn rate", "gross profit", "net profit", "roi", "return", "cap table",
            "equity", "shares", "valuation", "dissolve", "profitability", "cash flow"
        ],
        "weight": 1.2
    },
    "technical": {
        "keywords": [
            "technology", "tech", "product", "platform", "ai", "ml", "software",
            "hardware", "engine", "engineered", "architecture", "infrastructure",
            "api", "feature", "capability", "innovation", "patent", "stack",
            "development", "code", "database", "security", "scalability", "integration",
            "algorithm", "model", "patent", "ip", "r&d", "prototype"
        ],
        "weight": 1.2
    },
    "comparative": {
        "keywords": [
            "compare", "versus", "vs", "difference", "between", "better", "worse",
            "advantage", "disadvantage", "competition", "competitor", "alternatives",
            "compared to", "opposed to", "compared with", "comparison", "similarly",
            "like", "similar to", "differ from", "distinguish"
        ],
        "weight": 1.5
    },
    "summary": {
        "keywords": [
            "summarize", "summary", "overview", "what is", "tell me about", "explain",
            "describe", "brief", "high level", "quick summary", "quick overview",
            "intro", "introduction", "basic", "key points", "highlights", "snapshot"
        ],
        "weight": 1.0
    },
    "competitive": {
        "keywords": [
            "competitor", "competition", "market share", "landscape", "players",
            "industry", "market size", "competitors", "rivals", "替代", "market position",
            "leading", "leader", "challenger", "incumbent", "disruption", "moat"
        ],
        "weight": 1.3
    },
    "pipeline": {
        "keywords": [
            "pipeline", "orders", "contracts", "deal", "pipeline", "backlog",
            "forecast", "upcoming", "committed", "意向", "sales pipeline", "conversion",
            "pipeline value", "deal flow", "pending", "negotiation", "closing"
        ],
        "weight": 1.4
    },
    "team": {
        "keywords": [
            "team", "founder", "ceo", "cto", "coo", "leadership", "executive",
            "management", "advisor", "board", "employee", "staff", "headcount",
            "hiring", "recruitment", "key person", "experience", "background", "cv"
        ],
        "weight": 1.3
    },
    "market": {
        "keywords": [
            "market", "tam", "sam", "som", "addressable", "market size", "opportunity",
            "customer", "user", "adoption", "penetration", "target audience", "segment",
            "demographic", "go-to-market", "gtm", "channels", "pricing"
        ],
        "weight": 1.3
    },
    "risk": {
        "keywords": [
            "risk", "challenge", "concern", "issue", "problem", "weakness", "threat",
            "vulnerability", "competition risk", "regulatory", "compliance", "legal",
            "patent risk", "market risk", "execution risk", "dilution", "downside"
        ],
        "weight": 1.4
    },
    "milestone": {
        "keywords": [
            "milestone", "achievement", "progress", "achieved", "roadmap", "timeline",
            "plan", "goal", "target", "objective", "quarterly", "annual", "roadmap",
            "product launch", "release", "beta", "launch", "expansion", "IPO"
        ],
        "weight": 1.3
    }
}

SECTION_MAPPING = {
    "financial": "financials",
    "technical": "tech",
    "comparative": None,
    "summary": None,
    "competitive": "financials",
    "pipeline": "financials",
    "team": "team",
    "market": "market",
    "risk": "risks",
    "milestone": "milestones"
}




def _llm_classify(query: str) -> dict:
    """Fallback LLM classification for ambiguous queries"""
    client = get_safe_client()
    if not client:
        return None

    prompt = f"""
Classify this investor query into ONE primary intent category.

Categories: financial, technical, comparative, summary, competitive, pipeline, team, market, risk, milestone

Return ONLY JSON:
{{"intent": "category", "confidence": 0.0-1.0, "reason": "short explanation"}}

Query: {query[:500]}
"""

    try:
        content = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        if "{" in content and "}" in content:
            content = content[content.find("{"):content.rfind("}")+1]
        data = json.loads(content)
        return data
    except:
        return None


def classify_intent(query: str, use_llm_fallback: bool = True) -> dict:
    """
    Enhanced classify query intent with weighted scoring + multi-intent detection
    Returns: {intent, confidence, suggested_sections, keywords_found, all_intents}
    """
    query_lower = query.lower()

    scores = {}
    keywords_found = {}

    for intent, config in INTENT_KEYWORDS.items():
        score = 0
        found = []
        keywords = config["keywords"]
        weight = config["weight"]

        for keyword in keywords:
            if keyword in query_lower:
                score += weight
                found.append(keyword)

        if found:
            scores[intent] = score
            keywords_found[intent] = found

    if not scores:
        if use_llm_fallback:
            llm_result = _llm_classify(query)
            if llm_result:
                return {
                    "intent": llm_result.get("intent", "general"),
                    "confidence": min(llm_result.get("confidence", 0.5), 0.8),
                    "suggested_sections": [],
                    "keywords_found": [],
                    "all_intents": [],
                    "method": "llm_fallback"
                }

        return {
            "intent": "general",
            "confidence": 0.3,
            "suggested_sections": [],
            "keywords_found": [],
            "all_intents": [],
            "method": "keyword"
        }

    sorted_intents = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_intent = sorted_intents[0][0]
    best_score = sorted_intents[0][1]

    total_score = sum(scores.values())
    confidence = min(best_score / max(total_score, 1), 1.0)

    if best_score >= 5:
        confidence = min(confidence + 0.15, 1.0)

    top_intents = [item[0] for item in sorted_intents[:3] if item[1] >= best_score * 0.5]

    suggested_sections = []
    for intent in top_intents:
        if intent in SECTION_MAPPING and SECTION_MAPPING[intent]:
            if SECTION_MAPPING[intent] not in suggested_sections:
                suggested_sections.append(SECTION_MAPPING[intent])

    if best_intent in SECTION_MAPPING and SECTION_MAPPING[best_intent]:
        if SECTION_MAPPING[best_intent] not in suggested_sections:
            suggested_sections.insert(0, SECTION_MAPPING[best_intent])

    return {
        "intent": best_intent,
        "confidence": round(confidence, 2),
        "suggested_sections": suggested_sections,
        "keywords_found": keywords_found.get(best_intent, []),
        "all_intents": top_intents,
        "scores": {k: round(v, 1) for k, v in sorted_intents},
        "method": "llm_fallback" if use_llm_fallback and confidence < 0.4 else "keyword"
    }


def get_retrieval_config(intent_result: dict) -> dict:
    """
    Get retrieval configuration based on detected intent
    """
    intent = intent_result.get("intent", "general")
    confidence = intent_result.get("confidence", 0.3)
    all_intents = intent_result.get("all_intents", [])

    config = {
        "section": None,
        "top_k": 5,
        "rerank": False,
        "boost_recent": False,
        "include_sections": []
    }

    if intent == "financial" or "financial" in all_intents:
        config["section"] = "financials"
        config["top_k"] = 7
        config["include_sections"] = ["financials", "pipeline"]
    elif intent == "technical":
        config["section"] = "tech"
        config["top_k"] = 5
        config["include_sections"] = ["tech"]
    elif intent == "pipeline":
        config["section"] = "financials"
        config["top_k"] = 5
    elif intent == "comparative":
        config["top_k"] = 10
        config["include_sections"] = ["financials", "tech", "market"]
        config["rerank"] = True
    elif intent == "summary":
        config["top_k"] = 3
        config["boost_recent"] = True
        config["include_sections"] = ["overview", "financials", "tech"]
    elif intent == "team":
        config["section"] = "team"
        config["top_k"] = 5
    elif intent == "market":
        config["section"] = "market"
        config["top_k"] = 6
    elif intent == "risk":
        config["section"] = "risks"
        config["top_k"] = 5
    elif intent == "milestone":
        config["section"] = "milestones"
        config["top_k"] = 5
    elif intent == "competitive":
        config["section"] = "financials"
        config["top_k"] = 6

    if confidence < 0.5:
        config["top_k"] = min(config["top_k"] + 3, 15)
        if not config.get("include_sections"):
            config["include_sections"] = []

    return config