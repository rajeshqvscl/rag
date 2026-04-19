"""
Agent Tools — 5 standalone Python functions the agent controller can invoke.

Tool 1: retrieve_chunks(query, company, k)   → BM25 retrieval
Tool 2: analyze_pitch(context, company)       → structured VC analysis via Claude
Tool 3: classify_email(email_text)            → intent classification via Claude
Tool 4: generate_reply(context, intent, meta) → professional email draft
Tool 5: schedule_followup(company, intent)    → follow-up timing decision
"""
import os
import re
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional


# ─────────────────────────────────────────────
# Tool 1: retrieve_chunks
# ─────────────────────────────────────────────

def retrieve_chunks(query: str, company: str = None, k: int = 6) -> List[Dict]:
    """
    BM25 retrieval over the stored pitch deck / financial corpus.
    Sources: PostgreSQL pitch deck extracted text.
    Returns top-k relevant chunks with scores.
    """
    results = _retrieve_from_postgres(query, company=company, k=k)

    # Sort by BM25 score and cap at k
    results.sort(key=lambda x: x.get("bm25_score", 0), reverse=True)
    return results[:k]


def _retrieve_from_postgres(query: str, company: str = None, k: int = 6) -> List[Dict]:
    """
    Retrieve pitch deck content stored in PostgreSQL using BM25-style term scoring.
    This is the primary source for pitch deck data since PDF text is stored in Neon DB.
    """
    try:
        from app.config.database import SessionLocal
        from app.models.database import PitchDeck, User

        db = SessionLocal()
        try:
            # Get user
            user = db.query(User).filter_by(username="default").first()
            if not user:
                return []

            # Fetch candidate decks
            q = db.query(PitchDeck).filter(PitchDeck.user_id == user.id)
            if company:
                # Filter by company name (case-insensitive) if provided
                from sqlalchemy import or_, func
                q = q.filter(
                    or_(
                        func.lower(PitchDeck.company_name).contains(company.lower()),
                        PitchDeck.extracted_text.ilike(f"%{company}%")
                    )
                )
            decks = q.limit(20).all()

            if not decks:
                # No company match — take all decks and score by query
                decks = db.query(PitchDeck).filter(
                    PitchDeck.user_id == user.id,
                    PitchDeck.extracted_text.isnot(None)
                ).limit(10).all()

            # Build BM25-like scored chunks from extracted text
            import re, math
            query_terms = set(re.sub(r'[^\w\s]', ' ', query.lower()).split())

            chunks = []
            for deck in decks:
                text = deck.extracted_text or ""
                if not text.strip():
                    continue

                # Score: count query term hits in text
                text_lower = text.lower()
                score = sum(text_lower.count(term) for term in query_terms if len(term) > 2)
                score = min(score / max(len(text.split()), 1) * 100, 10.0)  # Normalize

                # Chunk the text into segments
                segments = [s.strip() for s in re.split(r'\n{2,}', text) if s.strip()]
                for seg in segments[:8]:  # Max 8 chunks per deck
                    seg_lower = seg.lower()
                    seg_score = sum(seg_lower.count(t) for t in query_terms if len(t) > 2)
                    chunks.append({
                        "text": seg,
                        "type": "pitch_deck",
                        "symbol": deck.company_name,
                        "company_name": deck.company_name,
                        "source": f"{deck.company_name} — {deck.file_name}",
                        "bm25_score": round(float(seg_score) / max(len(seg.split()), 1) * 50, 3),
                    })

            # Sort by score and return top k
            chunks.sort(key=lambda x: x["bm25_score"], reverse=True)
            return chunks[:k]

        finally:
            db.close()

    except Exception as e:
        print(f"[retrieve_from_postgres] Error: {e}")
        return []


# ─────────────────────────────────────────────
# Tool 2: analyze_pitch
# ─────────────────────────────────────────────

def analyze_pitch(context: List[Dict], company: str) -> Dict:
    """
    Structured VC-style pitch analysis from retrieved context.
    Returns: { summary, key_metrics, red_flags, recommendation, confidence }
    """
    if not context:
        return {
            "summary": f"No pitch data found for {company} in the knowledge base.",
            "key_metrics": {},
            "red_flags": [],
            "recommendation": "INSUFFICIENT_DATA",
            "confidence": 0.0
        }

    # Build condensed context string (max 4000 chars)
    context_text = "\n\n".join(
        f"[{c.get('type','doc')}] {c.get('text','')}" for c in context
    )[:4000]

    prompt = f"""You are a senior VC investment analyst. Analyze the following pitch deck excerpts for {company}.

PITCH DATA:
{context_text}

Return a JSON object with EXACTLY this structure (no markdown, raw JSON only):
{{
    "summary": "2-3 sentence executive summary",
    "key_metrics": {{
        "revenue": "extracted or null",
        "growth_rate": "extracted or null", 
        "runway": "extracted or null",
        "tam": "extracted or null",
        "raising": "extracted or null",
        "stage": "Pre-seed/Seed/Series A/B/C or null"
    }},
    "strengths": ["strength 1", "strength 2"],
    "red_flags": ["concern 1", "concern 2"],
    "recommendation": "PASS | WATCH | CONSIDER | PROCEED",
    "confidence": 0.0
}}

Be specific. Extract real numbers. confidence is 0.0-1.0."""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r'^```json\s*|```$', '', raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        result["_source"] = "claude"
        return result
    except (json.JSONDecodeError, Exception) as e:
        # Local fallback — extract what we can from context
        return _local_analyze_pitch(context_text, company, str(e))


def _local_analyze_pitch(context_text: str, company: str, error: str) -> Dict:
    """Offline fallback when Claude is unavailable."""
    text = context_text.lower()

    # Extract metrics with regex
    revenue_match = re.search(r'\$[\d,.]+\s*[MBK]?\b', context_text)
    growth_match = re.search(r'(\d+)%\s+(?:growth|yoy|cagr)', context_text, re.IGNORECASE)
    runway_match = re.search(r'(\d+)\s+months?\s+runway', context_text, re.IGNORECASE)

    key_metrics = {
        "revenue": revenue_match.group(0) if revenue_match else None,
        "growth_rate": f"{growth_match.group(1)}%" if growth_match else None,
        "runway": f"{runway_match.group(1)} months" if runway_match else None,
        "tam": None, "raising": None, "stage": None
    }

    red_flags = []
    if not key_metrics["revenue"]:
        red_flags.append("No revenue data found in pitch materials")
    if "competition" in text or "competitive" in text:
        red_flags.append("Competitive landscape mentioned — differentiation unclear")

    return {
        "summary": f"Analysis of {company} based on {len(context_text.split())} words of pitch data. Claude unavailable ({error[:60]}).",
        "key_metrics": key_metrics,
        "strengths": ["Pitch materials available for review"],
        "red_flags": red_flags,
        "recommendation": "WATCH",
        "confidence": 0.3,
        "_source": "local_fallback"
    }


# ─────────────────────────────────────────────
# Tool 3: classify_email
# ─────────────────────────────────────────────

def classify_email(email_text: str) -> Dict:
    """
    Classify incoming email intent.
    Returns: { intent, confidence, requires_context, sender_type, urgency }
    """
    prompt = f"""Classify this investor/startup email. Return raw JSON only (no markdown):

EMAIL:
{email_text[:2000]}

JSON format:
{{
    "intent": "interested | not_interested | due_diligence | follow_up | introduction | question | other",
    "confidence": 0.0,
    "requires_pitch_context": true,
    "sender_type": "investor | startup | unknown",
    "urgency": "high | medium | low",
    "key_topics": ["topic1", "topic2"],
    "extracted_company": "company name or null"
}}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r'^```json\s*|```$', '', raw, flags=re.MULTILINE).strip()
        result = json.loads(raw)
        result["_source"] = "claude"
        return result
    except Exception:
        return _local_classify_email(email_text)


def _local_classify_email(email_text: str) -> Dict:
    """Keyword-based email classification fallback."""
    text = email_text.lower()

    intent_keywords = {
        "interested": ["interested", "love to learn", "exciting", "impressed", "opportunity", "invest"],
        "not_interested": ["not a fit", "pass", "decline", "not interested", "moving forward without"],
        "due_diligence": ["due diligence", "financials", "data room", "cap table", "metrics", "audit"],
        "follow_up": ["follow up", "checking in", "following up", "any update", "status"],
        "introduction": ["introduction", "introduce", "reaching out", "hello", "hi team"],
        "question": ["question", "clarify", "can you explain", "what is", "how does"],
    }

    scores = {intent: sum(1 for kw in kws if kw in text) for intent, kws in intent_keywords.items()}
    top_intent = max(scores, key=scores.get) if max(scores.values()) > 0 else "other"
    confidence = min(scores.get(top_intent, 0) / 3.0, 1.0)

    requires_context = top_intent in ["interested", "due_diligence", "question"]

    sender_keywords = {"investor": ["vc", "fund", "capital", "investment", "investor"],
                       "startup": ["startup", "founder", "ceo", "company", "product"]}
    sender_type = "unknown"
    for st, kws in sender_keywords.items():
        if any(kw in text for kw in kws):
            sender_type = st
            break

    company_match = re.search(r'(?:company|startup|firm)\s+(?:is\s+)?([A-Z][a-zA-Z]+)', email_text)

    return {
        "intent": top_intent,
        "confidence": confidence,
        "requires_pitch_context": requires_context,
        "sender_type": sender_type,
        "urgency": "high" if top_intent in ["due_diligence", "interested"] else "medium",
        "key_topics": [k for k, v in scores.items() if v > 0],
        "extracted_company": company_match.group(1) if company_match else None,
        "_source": "local_keywords"
    }


# ─────────────────────────────────────────────
# Tool 4: generate_reply
# ─────────────────────────────────────────────

def generate_reply(
    email_text: str,
    intent: str,
    analysis: Optional[Dict] = None,
    context_chunks: Optional[List[Dict]] = None
) -> str:
    """
    Generate a professional email reply tailored to intent and pitch analysis.
    """
    company = ""
    if analysis:
        # Extract company from analysis if available
        for chunk in (context_chunks or []):
            if chunk.get("symbol"):
                company = chunk["symbol"]
                break

    metrics_block = ""
    if analysis and analysis.get("key_metrics"):
        m = analysis["key_metrics"]
        metrics_block = "\n".join(
            f"- {k.replace('_',' ').title()}: {v}"
            for k, v in m.items() if v
        )

    prompt = f"""You are a professional VC analyst drafting an email reply.

ORIGINAL EMAIL:
{email_text[:1500]}

INTENT CLASSIFIED AS: {intent}
RECOMMENDATION: {analysis.get('recommendation', 'N/A') if analysis else 'N/A'}

KEY METRICS FROM PITCH:
{metrics_block or 'No pitch data available'}

RED FLAGS:
{chr(10).join('- ' + f for f in (analysis.get('red_flags', []) if analysis else [])[:3])}

Write a professional email reply. Rules:
- Match tone to intent (warm for interested, polite decline for not_interested)
- Reference specific data from pitch if available  
- Include clear next step (call, data request, or polite pass)
- Keep under 200 words
- NO placeholders like [Name] — use professional generic language
- Start with: "Thank you for reaching out..."
"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception:
        return _template_reply(intent, company, analysis)


def _template_reply(intent: str, company: str, analysis: Optional[Dict]) -> str:
    """Template-based reply fallback."""
    templates = {
        "interested": (
            f"Thank you for reaching out about {company or 'your company'}. "
            "We've reviewed your materials and find the opportunity interesting. "
            "We'd love to schedule a 30-minute call to learn more. "
            "Could you share your availability for next week?\n\n"
            "Best regards,\nFinRAG Investment Team"
        ),
        "not_interested": (
            f"Thank you for sharing details about {company or 'your company'}. "
            "After careful consideration, this opportunity isn't the right fit for our portfolio at this time. "
            "We wish you great success and encourage you to reach out if your situation changes significantly.\n\n"
            "Best regards,\nFinRAG Investment Team"
        ),
        "due_diligence": (
            f"Thank you for progressing to due diligence for {company or 'your company'}. "
            "Please share access to your data room when ready. "
            "We'll need: cap table, last 12 months financials, and customer references.\n\n"
            "Best regards,\nFinRAG Investment Team"
        ),
    }
    return templates.get(intent, templates["interested"])


# ─────────────────────────────────────────────
# Tool 5: schedule_followup
# ─────────────────────────────────────────────

def schedule_followup(company: str, intent: str, analysis: Optional[Dict] = None) -> Dict:
    """
    Decide follow-up timing and action based on intent and analysis.
    Returns: { action, followup_date, priority, notes }
    """
    now = datetime.utcnow()
    recommendation = analysis.get("recommendation", "WATCH") if analysis else "WATCH"

    schedule_map = {
        # (intent, recommendation): (days, priority, action)
        ("interested", "PROCEED"):          (2,  "high",   "Schedule founding team call"),
        ("interested", "CONSIDER"):         (3,  "high",   "Request additional financials"),
        ("interested", "WATCH"):            (7,  "medium", "Monitor and re-evaluate next quarter"),
        ("interested", "PASS"):             (0,  "low",    "Send polite decline"),
        ("due_diligence", "PROCEED"):       (1,  "high",   "Send data room request"),
        ("due_diligence", "CONSIDER"):      (2,  "high",   "Request cap table + customer references"),
        ("follow_up", "PROCEED"):           (1,  "high",   "Respond immediately"),
        ("follow_up", "CONSIDER"):          (3,  "medium", "Provide status update"),
        ("not_interested", "PASS"):         (0,  "low",    "Log as passed — no followup"),
        ("introduction", "WATCH"):          (14, "low",    "Add to watchlist — revisit in 2 weeks"),
    }

    key = (intent, recommendation)
    days, priority, action = schedule_map.get(key, (7, "low", "Review and determine next step"))

    followup_date = (now + timedelta(days=days)).strftime("%Y-%m-%d") if days > 0 else None

    return {
        "company": company,
        "action": action,
        "followup_date": followup_date,
        "priority": priority,
        "intent": intent,
        "recommendation": recommendation,
        "notes": f"Auto-scheduled by agent at {now.strftime('%Y-%m-%d %H:%M')} UTC"
    }
