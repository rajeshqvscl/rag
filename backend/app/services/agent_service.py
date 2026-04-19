"""
Agent Controller — the decision-making brain of FinRAG.

Flow:
  Email/Query arrives
     ↓
  Agent → classify intent
     ↓
  Agent → need pitch context? (yes/no)
     ↓
  Agent → retrieve (BM25) if needed
     ↓  
  Agent → analyze pitch data
     ↓
  Agent → generate reply
     ↓
  Agent → schedule follow-up
     ↓
  Store + return structured result

State is per-request (dict). No global mutable state.
"""
import os
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

from app.services.agent_tools import (
    retrieve_chunks,
    analyze_pitch,
    classify_email,
    generate_reply,
    schedule_followup,
)


# ─────────────────────────────────────────────────────────
# Agent state factory
# ─────────────────────────────────────────────────────────

def _new_state(email: str = "", query: str = "", company: str = "") -> Dict:
    return {
        "email":        email,
        "query":        query,
        "company":      company,
        "intent":       None,
        "classification": None,
        "retrieved":    [],
        "analysis":     None,
        "reply":        None,
        "followup":     None,
        "steps":        [],      # execution trace
        "started_at":   time.time(),
    }


def _log(state: Dict, step: str, detail: str = ""):
    entry = {"step": step, "ts": round(time.time() - state["started_at"], 3)}
    if detail:
        entry["detail"] = detail
    state["steps"].append(entry)
    print(f"  [Agent] {step}" + (f" — {detail}" if detail else ""))


# ─────────────────────────────────────────────────────────
# Core: process_email_agent
# ─────────────────────────────────────────────────────────

def process_email_agent(
    email_text: str,
    company: str = "",
    store_result: bool = True,
) -> Dict:
    """
    Full agentic flow for an incoming email.

    Returns a structured result dict containing:
        intent, analysis, reply, followup, trace, elapsed_ms
    """
    state = _new_state(email=email_text, company=company)
    print(f"\n[Agent] ── Starting email processing for company='{company}' ──")

    # ── Step 1: Classify intent ──────────────────────────────────────
    _log(state, "classify_email")
    classification = classify_email(email_text)
    state["intent"] = classification.get("intent", "other")
    state["classification"] = classification
    state["company"] = company or classification.get("extracted_company") or ""
    _log(state, "intent_resolved", f"intent={state['intent']}, confidence={classification.get('confidence', 0):.2f}")

    # ── Step 2: Decide if we need pitch context ───────────────────────
    needs_context = classification.get("requires_pitch_context", False)
    if state["intent"] in ("interested", "due_diligence", "follow_up", "question"):
        needs_context = True

    # ── Step 3: Retrieve (only if needed) ─────────────────────────────
    if needs_context and state["company"]:
        _log(state, "retrieve_chunks", f"BM25 retrieval for '{state['company']}'")
        state["retrieved"] = retrieve_chunks(
            email_text,
            company=state["company"],
            k=6
        )
        _log(state, "retrieval_done", f"{len(state['retrieved'])} chunks found")
    elif needs_context:
        # No company name — still try retrieval on email text
        _log(state, "retrieve_chunks", "No company — retrieving on email content")
        state["retrieved"] = retrieve_chunks(email_text, k=4)
        _log(state, "retrieval_done", f"{len(state['retrieved'])} chunks found")
    else:
        _log(state, "skip_retrieval", f"intent={state['intent']} doesn't need pitch context")

    # ── Step 4: Analyze pitch data ────────────────────────────────────
    if state["retrieved"]:
        _log(state, "analyze_pitch")
        state["analysis"] = analyze_pitch(state["retrieved"], state["company"])
        _log(state, "analysis_done", f"recommendation={state['analysis'].get('recommendation')}")
    else:
        state["analysis"] = None
        _log(state, "skip_analysis", "No retrieved context")

    # ── Step 5: Generate reply ────────────────────────────────────────
    _log(state, "generate_reply", f"intent={state['intent']}")
    state["reply"] = generate_reply(
        email_text=email_text,
        intent=state["intent"],
        analysis=state["analysis"],
        context_chunks=state["retrieved"],
    )
    _log(state, "reply_generated")

    # ── Step 6: Schedule follow-up ────────────────────────────────────
    _log(state, "schedule_followup")
    state["followup"] = schedule_followup(
        company=state["company"],
        intent=state["intent"],
        analysis=state["analysis"],
    )
    _log(state, "followup_scheduled", state["followup"].get("action"))

    # ── Step 7: Persist to DB ─────────────────────────────────────────
    if store_result:
        _log(state, "store_result")
        _persist(state)

    elapsed = round((time.time() - state["started_at"]) * 1000)
    print(f"[Agent] ── Done in {elapsed}ms ──\n")

    return _to_response(state, elapsed)


# ─────────────────────────────────────────────────────────
# Core: process_query_agent
# ─────────────────────────────────────────────────────────

def process_query_agent(
    query: str,
    company: str = "",
    k: int = 5,
) -> Dict:
    """
    Agentic flow for a user query (search/analysis, no email involved).

    Instead of: Query → Claude → Answer
    We do:     Agent → decide → BM25 Retrieve → Analyze → Answer
    """
    state = _new_state(query=query, company=company)
    print(f"\n[Agent] ── Starting query agent for: '{query[:60]}' ──")

    # ── Step 1: Retrieve ──────────────────────────────────────────────
    _log(state, "retrieve_chunks", f"query='{query[:40]}'")
    state["retrieved"] = retrieve_chunks(query, company=company, k=k)
    _log(state, "retrieval_done", f"{len(state['retrieved'])} chunks")

    # ── Step 2: Analyze if we have pitch data ─────────────────────────
    if state["retrieved"]:
        _log(state, "analyze_pitch")
        state["analysis"] = analyze_pitch(state["retrieved"], company or query[:30])
        _log(state, "analysis_done")
    else:
        # No local data — fall back to Claude direct answer
        _log(state, "direct_claude_answer", "No local data found")
        state["analysis"] = _direct_answer(query)

    elapsed = round((time.time() - state["started_at"]) * 1000)
    print(f"[Agent] ── Query done in {elapsed}ms ──\n")

    return {
        "status":    "success",
        "query":     query,
        "company":   company,
        "retrieved": state["retrieved"],
        "analysis":  state["analysis"],
        "steps":     state["steps"],
        "elapsed_ms": elapsed,
    }


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def _direct_answer(query: str) -> Dict:
    """Ask Claude directly when there are no local documents."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=500,
            system="You are a VC analyst assistant. Answer concisely and factually.",
            messages=[{"role": "user", "content": query}]
        )
        return {
            "summary": response.content[0].text.strip(),
            "key_metrics": {},
            "red_flags": [],
            "recommendation": "N/A",
            "confidence": 0.8,
            "_source": "claude_direct"
        }
    except Exception as e:
        return {
            "summary": f"No local data found for this query. Claude also unavailable: {e}",
            "key_metrics": {},
            "red_flags": [],
            "recommendation": "INSUFFICIENT_DATA",
            "confidence": 0.0,
            "_source": "error"
        }


def _persist(state: Dict):
    """Save agent result to PostgreSQL EmailReply table."""
    try:
        from app.config.database import SessionLocal
        from app.models.database import EmailReply, User
        from datetime import datetime

        db = SessionLocal()
        try:
            user = db.query(User).filter_by(username="default").first()
            if not user:
                return

            classification = state.get("classification") or {}
            analysis = state.get("analysis") or {}
            followup = state.get("followup") or {}

            reply = EmailReply(
                user_id=user.id,
                sender_email="agent@finrag.com",
                sender_name="Agent System",
                sender_type=classification.get("sender_type", "unknown"),
                sender_confidence=float(classification.get("confidence", 0)),
                subject=f"Agent: {state.get('intent', 'process')} — {state.get('company', 'Unknown')}",
                body_text=state.get("email", ""),
                intent_status=state.get("intent", "other"),
                intent_keywords=classification.get("key_topics", []),
                intent_confidence=float(classification.get("confidence", 0)),
                combined_confidence=float(classification.get("confidence", 0)),
                classification_method="agentic_rag",
                is_claude_identified=classification.get("_source") == "claude",
                claude_analysis={
                    "analysis": analysis,
                    "followup": followup,
                    "steps": state.get("steps", []),
                },
                classification_reasoning=analysis.get("summary", ""),
                company=state.get("company", ""),
                received_at=datetime.utcnow(),
                processed=True,
                processed_at=datetime.utcnow(),
                notes=json.dumps(followup),
            )
            db.add(reply)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"[Agent] Persist failed (non-fatal): {e}")


def _to_response(state: Dict, elapsed: int) -> Dict:
    """Serialize state to clean API response."""
    return {
        "status":          "success",
        "company":         state.get("company", ""),
        "intent":          state.get("intent"),
        "classification":  state.get("classification"),
        "context_used":    len(state.get("retrieved", [])),
        "analysis":        state.get("analysis"),
        "reply":           state.get("reply"),
        "followup":        state.get("followup"),
        "steps":           state.get("steps"),
        "elapsed_ms":      elapsed,
    }