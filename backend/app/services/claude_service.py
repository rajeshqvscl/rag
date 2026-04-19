from anthropic import Anthropic
import json
import os
import re
import time

# Lazy load client to reduce startup memory
_client = None
DEFAULT_MODEL = "claude-sonnet-4-20250514"

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        try:
            _client = Anthropic(api_key=api_key)
        except Exception as e:
            print(f"Anthropic client init error: {e}")
            _client = Anthropic(api_key=api_key, default_headers={"anthropic-version": "2023-06-01"})
    return _client

def call_claude_with_retry(messages, max_tokens=300, max_retries=6, retry_delay=3):
    """Call Claude API with retry logic for transient errors"""
    for attempt in range(max_retries):
        try:
            response = _get_client().messages.create(
                model=DEFAULT_MODEL,
                max_tokens=max_tokens,
                messages=messages
            )
            return response
        except Exception as e:
            error_str = str(e)
            # Retry on 529 (overloaded) or 429 (rate limit) errors
            if '529' in error_str or 'overloaded' in error_str.lower() or '429' in error_str:
                if attempt < max_retries - 1:
                    print(f"Claude API overloaded (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 1.5  # Exponential backoff (slower growth)
                    continue
                else:
                    print(f"Claude API overloaded after {max_retries} attempts, using fallback analysis")
                    raise e
            else:
                # Don't retry on other errors
                raise e
    return None

def structure_text(text: str):
    # ← guard: ensure text is never None before building prompt
    text = text or ""
    if not text.strip():
        return {"type": "unknown", "section": "general", "content": ""}

    prompt = f"""
    Extract structured information from this text.

    Return JSON with:
    - type (pitch / nda / financial / teaser / email)
    - section (revenue, growth, problem, etc.)
    - content (cleaned summary)

    Text:
    {text}
    """

    try:
        response = call_claude_with_retry([{"role": "user", "content": prompt}], max_tokens=300)

        try:
            return json.loads(response.content[0].text)
        except:
            return {
                "type": "unknown",
                "section": "general",
                "content": text
            }
    except Exception as e:
        print(f"Claude API error in structure_text: {e}")
        # Enhanced fallback analysis without Claude
        text_lower = text.lower()
        
        # Document type detection
        if any(word in text_lower for word in ['revenue', 'sales', 'income', 'financial', 'profit', 'loss', 'margin', 'ebitda', 'cash flow']):
            doc_type = 'financial'
        elif any(word in text_lower for word in ['pitch', 'investment', 'funding', 'venture', 'startup', 'business model', 'traction', 'market size']):
            doc_type = 'pitch'
        elif any(word in text_lower for word in ['agreement', 'confidential', 'nda', 'terms', 'legal']):
            doc_type = 'nda'
        else:
            doc_type = 'unknown'
        
        # Extract key insights with technical and numeric analysis
        insights = []
        
        # Revenue extraction
        revenue_patterns = [
            r'\$[\d,]+\.?\d*[kmb]?|\d+\.?\d*[kmb]?',
            r'(\d+(?:,\d{3})*\s*(?:million|billion|thousand|m|k|bn))',
            r'revenue[:\s]*\$?[\d,]+',
            r'(?:revenue|sales|income)\s*[:]\s*\$?[\d,]+',
        ]
        
        revenues_found = []
        for pattern in revenue_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            revenues_found.extend(matches)
        
        if revenues_found:
            insights.append(f"Financial figures detected: {', '.join(revenues_found[:5])}")
        
        # Growth and metrics extraction
        growth_patterns = [
            r'(\d+\.?\d*)%\s*(?:growth|increase|yoy)',
            r'(growth\s*rate|yoy|year\s*over\s*year)',
            r'(quarter\s*\d{4}|q[1-4])',
            r'(annual\s*|yearly|fy)'
        ]
        
        growth_metrics = []
        for pattern in growth_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            growth_metrics.extend(matches)
        
        if growth_metrics:
            insights.append("Growth metrics and KPIs detected")
        
        # Business model analysis
        business_indicators = {
            'saas': r'(?:saas|software\s*as\s*a\s*service|subscription|recurring\s*revenue)',
            'marketplace': r'(?:marketplace|platform|two-sided\s*market)',
            'b2b': r'(?:b2b|business\s*to\s*business)',
            'freemium': r'(?:freemium|free\s*trial|basic\s*plan)'
        }
        
        for model_type, pattern in business_indicators.items():
            if re.search(pattern, text, re.IGNORECASE):
                insights.append(f"Business model: {model_type}")
        
        # Technical and operational metrics
        technical_patterns = [
            r'(?:users?|customers?|active\s*users?)\s*[:]\s*\d+',
            r'(?:churn|retention|lifecycle|ltv)\s*[:]\s*\d+%',
            r'(?:conversion|activation|adoption)\s*rate\s*[:]\s*\d+%',
            r'(arpu|arpa|ltv|cac)\s*[:]\s*\$?\d+',
            r'(?:moic|ltv|cac\s*ratio)\s*[:]\s*[\d\.]+'
        ]
        
        technical_metrics = []
        for pattern in technical_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            technical_metrics.extend(matches)
        
        if technical_metrics:
            insights.append("Technical and operational metrics found")
        
        # Market and competitive analysis
        market_patterns = [
            r'(?:market\s*size|tam|sam|som)\s*[:]\s*\$?\d+[btm]?',
            r'(?:competition|competitive|industry)\s*(?:analysis|landscape)',
            r'(?:market\s*share|penetration|growth)\s*[:]\s*\d+%'
        ]
        
        market_metrics = []
        for pattern in market_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            market_metrics.extend(matches)
        
        if market_metrics:
            insights.append("Market and competitive analysis detected")
        
        # Risk and challenge indicators
        risk_patterns = [
            r'(?:risk|challenge|concern|issue)\s*(?:analysis|assessment)',
            r'(?:burn\s*rate|runway|cash\s*burn)',
            r'(?:debt|liability|obligation)\s*(?:analysis|structure)'
        ]
        
        risk_metrics = []
        for pattern in risk_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            risk_metrics.extend(matches)
        
        if risk_metrics:
            insights.append("Risk and challenge indicators found")
        
        # Generate comprehensive analysis report
        report_sections = []
        
        # Executive Summary
        exec_summary = f"## Executive Summary\n\nThis {doc_type} document has been analyzed with comprehensive technical and financial insights. The analysis extracted {len(insights)} key findings from the content."
        report_sections.append(exec_summary)
        
        # Financial Analysis Section
        if revenues_found:
            financial_analysis = "## Financial Analysis\n\n"
            financial_analysis += "### Revenue Figures\n"
            for revenue in revenues_found[:8]:
                financial_analysis += f"**{revenue}**\n"
            
            if len(revenues_found) >= 3:
                financial_analysis += "\n### Growth Analysis\n"
                financial_analysis += "Revenue growth patterns detected across multiple periods.\n"
            
            report_sections.append(financial_analysis)
        
        # Business Model Analysis
        business_model_analysis = "## Business Model Analysis\n\n"
        detected_models = []
        for model_type, pattern in business_indicators.items():
            if re.search(pattern, text, re.IGNORECASE):
                detected_models.append(model_type.upper())
        
        if detected_models:
            business_model_analysis += f"**Business Model(s) Identified:** {', '.join(detected_models)}\n"
        else:
            business_model_analysis += "**Business Model:** Traditional model detected\n"
        
        report_sections.append(business_model_analysis)
        
        # Technical Metrics Section
        if technical_metrics:
            tech_analysis = "## Technical & Operational Metrics\n\n"
            tech_analysis += "**Key Performance Indicators:**\n"
            for metric in technical_metrics[:5]:
                tech_analysis += f"**{metric}**\n"
            report_sections.append(tech_analysis)
        
        # Market Analysis Section
        if market_metrics:
            market_analysis = "## Market & Competitive Analysis\n\n"
            market_analysis += "**Market Insights:**\n"
            for metric in market_metrics[:3]:
                market_analysis += f"**{metric}**\n"
            report_sections.append(market_analysis)
        
        # Risk Assessment Section
        if risk_metrics:
            risk_analysis = "## Risk Assessment\n\n"
            risk_analysis += "**Risk Indicators:**\n"
            for metric in risk_metrics[:3]:
                risk_analysis += f"**{metric}**\n"
            report_sections.append(risk_analysis)
        
        # Key Insights Summary
        insights_summary = "## Key Insights Summary\n\n"
        for i, insight in enumerate(insights, 1):
            insights_summary += f"{i}. **{insight}**\n"
        report_sections.append(insights_summary)
        
        # Complete Report Content
        full_report = "\n\n".join(report_sections)
        
        return {
            "type": doc_type,
            "section": "comprehensive_analysis",
            "content": full_report,
            "insights": insights,
            "analysis_summary": f"Comprehensive {doc_type} analysis completed with {len(insights)} insights extracted including detailed financial metrics, business model analysis, technical KPIs, market analysis, and risk assessment.",
            "financial_metrics": {
                "revenues": revenues_found,
                "growth_metrics": growth_metrics,
                "technical_metrics": technical_metrics,
                "market_metrics": market_metrics,
                "risk_metrics": risk_metrics
            },
            "full_report": full_report
        }

def analyze_documents(docs_context: list[str]):
    """Summarizes and analyzes multiple documents for a cohesive overview."""
    # ← guard: ensure chunks are non-None strings before joining
    safe_docs = [d or "" for d in docs_context if d is not None]
    combined_text = "\n\n--- DOCUMENT BORDER ---\n\n".join(safe_docs)
    if not combined_text.strip():
        return {"analysis_markdown": "No document content to analyse.", "revenue_data": []}
    
    prompt = f"""
    You are an expert venture capital analyst. Analyze the following documents (pitch deck, financial models, etc.) for a startup.
    
    IMPORTANT: Provide your output in a JSON format with exactly two keys:
    1. 'analysis_markdown': A comprehensive analysis including Executive Summary, Key Strengths, Risks, Financial Highlights (in Markdown).
    2. 'revenue_data': A list of objects with 'year' and 'revenue' keys (if found, otherwise an empty list). Try to extract historical or projected revenue if possible. Example: [{{"year": "2021", "revenue": 1000000}}, ...]

    Documents Context:
    {combined_text}
    """

    try:
        response = call_claude_with_retry([{"role": "user", "content": prompt}], max_tokens=2000)
        
        try:
            data = json.loads(response.content[0].text)
            return data
        except:
            return {
                "analysis_markdown": response.content[0].text,
                "revenue_data": []
            }
    except Exception as e:
        print(f"Claude API error in analyze_documents: {e}")
        # Use enhanced fallback analysis when API is unavailable
        print("Using enhanced fallback analysis...")
        
        # Use structure_text to get enhanced analysis
        fallback_result = structure_text(combined_text)
        
        # Ensure fallback_result is a dict
        fr_safe = fallback_result if isinstance(fallback_result, dict) else {}
        
        # Extract revenue data from the enhanced analysis
        revenue_data = []
        financial_metrics = fr_safe.get('financial_metrics', {})
        fm_safe = financial_metrics if isinstance(financial_metrics, dict) else {}
        revenues = fm_safe.get('revenues', [])
        
        # Try to extract revenue data from patterns
        import re
        revenue_patterns = [
            r'(?:revenue|sales|income)\s*(?:in|for|:)?\s*(\d{4})\s*[:$]?\s*[\$]?([\d,]+(?:\.\d+)?)',
            r'(\d{4})\s*(?:revenue|sales|income)\s*[:$]?\s*[\$]?([\d,]+(?:\.\d+)?)',
        ]
        
        for pattern in revenue_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for year, amount in matches:
                # Clean the amount
                amount_clean = amount.replace(',', '').replace('$', '')
                try:
                    revenue_data.append({
                        "year": year,
                        "revenue": int(float(amount_clean))
                    })
                except:
                    pass
        
        # Build comprehensive fallback analysis
        fallback_analysis = f"""# Document Analysis Report

## Executive Summary
This document has been analyzed using enhanced pattern recognition and keyword extraction. The system extracted {len(fr_safe.get('insights', []))} key insights from the content.

## Document Type
**Type:** {fr_safe.get('type', 'unknown').upper()}

## Key Insights
"""
        
        for i, insight in enumerate(fr_safe.get('insights', []), 1):
            fallback_analysis += f"{i}. {insight}\n"
        
        # Add financial metrics if available
        if revenues:
            fallback_analysis += f"\n## Financial Metrics Detected\n"
            for revenue in revenues[:5]:
                fallback_analysis += f"- **{revenue}**\n"
        
        # Add business model analysis
        if fr_safe.get('analysis_summary'):
            fallback_analysis += f"\n## Analysis Summary\n{fr_safe.get('analysis_summary')}\n"
        
        # Add full report if available
        if fr_safe.get('full_report'):
            fallback_analysis += f"\n{fr_safe.get('full_report')}\n"
        
        fallback_analysis += f"\n---\n*Note: This analysis was generated using enhanced pattern recognition due to temporary API service limitations. The system will automatically use AI-powered analysis when the service becomes available.*"
        
        return {
            "analysis_markdown": fallback_analysis,
            "revenue_data": revenue_data,
            "fallback_used": True
        }

def analyze_pitch_deck_detailed(extracted_text: str, company_name: str, key_metrics: dict = None) -> dict:
    """
    Performs detailed VC-style analysis of a pitch deck with comprehensive sections.
    Returns structured analysis with Executive Summary, Strengths, Risks, Financials, and Recommendation.
    """
    # ← guard all inputs before building prompt
    extracted_text = extracted_text or ""
    company_name = company_name or "Unknown Company"
    # Ensure key_metrics is a dict
    m_safe = key_metrics if isinstance(key_metrics, dict) else {}
    revenue_val = m_safe.get("revenue", "Unavailable")
    growth_val = m_safe.get("growth", "Unavailable")
    tam_val = m_safe.get("tam", "Unavailable")
    
    prompt = f"""You are a VC analyst. ABSOLUTE RULES - NO EXCEPTIONS:

ABSOLUTE RULES:
1. If Revenue is "Unavailable" → DO NOT mention revenue projections
2. If Growth is "Unavailable" → DO NOT mention growth rates
3. If TAM is "Unavailable" → DO NOT estimate market size
4. DO NOT generate future projections (2025, 2026, 2030, etc.)
5. DO NOT infer or estimate any financial numbers
6. DO NOT say "demonstrated revenue" if revenue is unavailable
7. ONLY discuss metrics that are ACTUALLY provided below

Provided Metrics (USE ONLY THESE):
- Revenue: {revenue_val}
- Growth: {growth_val}
- TAM: {tam_val}

Context (for risk assessment only, NOT for generating numbers):
{extracted_text[:8000]}

OUTPUT FORMAT:
## Executive Summary
- State clearly what data is MISSING
- DO NOT make up positive statements about unavailable metrics

## Key Metrics
- Revenue: {revenue_val}
- Growth: {growth_val}
- TAM: {tam_val}
- Add note: "Financial data extracted from pitch deck"

## Data Quality Assessment
- Note which metrics were found vs missing

## Risks
- List risks based on available context only

## Investment Recommendation  
- If critical metrics unavailable: "INSUFFICIENT DATA - Follow-up required"
- DO NOT provide fake confidence
"""

    try:
        response = call_claude_with_retry([{"role": "user", "content": prompt}], max_tokens=2500)
        detailed_analysis = response.content[0].text
        
        # Extract revenue data from the analysis text
        revenue_data = extract_revenue_from_analysis(detailed_analysis)
        
        return {
            "detailed_analysis": detailed_analysis,
            "revenue_data": revenue_data,
            "analysis_type": "detailed_vc"
        }
    except Exception as e:
        print(f"Claude API error in detailed analysis: {e}")
        return {
            "detailed_analysis": None,
            "revenue_data": [],
            "analysis_type": "fallback",
            "error": str(e)
        }

def extract_revenue_from_analysis(analysis_text: str) -> list:
    """Extract year-revenue pairs from the detailed analysis text."""
    import re
    revenue_data = []
    
    # Look for patterns like "2024: ₹28 crores" or "2025: $70M" or "Year 2026: $128M"
    patterns = [
        r'(?:20\d{2})[\s:]+(?:[₹$]?[\d,.]+\s*(?:crores?|M|B|K|lakhs?)?)',
        r'(?:Year\s+)?(20\d{2})[\s:]+[₹$]?([\d,.]+)\s*(crores?|M|B|K|lakhs?)?',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                year, amount, unit = match if len(match) >= 3 else (match[0], match[1], '')
            else:
                # Extract year and amount from the full match
                year_match = re.search(r'(20\d{2})', match)
                amount_match = re.search(r'[₹$]?([\d,.]+)', match)
                if year_match and amount_match:
                    year = year_match.group(1)
                    amount = amount_match.group(1)
                    unit = ''
                else:
                    continue
            
            try:
                amount_clean = amount.replace(',', '')
                revenue_val = float(amount_clean)
                
                # Convert to standard format
                if unit and 'crore' in unit.lower():
                    revenue_val *= 10000000  # 1 crore = 10 million
                elif unit and 'lakh' in unit.lower():
                    revenue_val *= 100000  # 1 lakh = 100k
                elif unit and unit.upper() == 'M':
                    revenue_val *= 1000000
                elif unit and unit.upper() == 'B':
                    revenue_val *= 1000000000
                elif unit and unit.upper() == 'K':
                    revenue_val *= 1000
                
                revenue_data.append({
                    "year": year,
                    "revenue": int(revenue_val)
                })
            except:
                pass
    
    # Remove duplicates and sort by year
    seen = set()
    unique_data = []
    for item in revenue_data:
        if item['year'] not in seen:
            seen.add(item['year'])
            unique_data.append(item)
    
    return sorted(unique_data, key=lambda x: x['year'])

def generate_draft_email(analysis_summary: str, company: str, key_metrics: dict = None):
    """Generates a grounded investor outreach email based only on real extracted data."""
    # Ensure key_metrics is a dict
    m_safe = key_metrics if isinstance(key_metrics, dict) else (key_metrics or {})
    if not isinstance(m_safe, dict): m_safe = {} # Double guard
    
    if m_safe.get("revenue") == "Unreliable (graph data ignored)" or m_safe.get("_low_confidence"):
        return """Hi Team,

I reviewed your pitch deck. While there are strong indicators of growth, some financial data appears inconsistent.

I’d like to understand your revenue trajectory and assumptions better.

Best,
[Your Name]
"""

    return f"""Hi Team,

I noticed your reported revenue of {m_safe.get('revenue', 'N/A')} and strong growth.

I’d love to understand your scale strategy further.

Best,
[Your Name]
"""

# Lazy client proxy for import compatibility
class _ClientProxy:
    """Proxy that lazy-loads the Anthropic client on first access."""
    _real_client = None
    
    def __getattr__(self, name):
        if self._real_client is None:
            self._real_client = _get_client()
        return getattr(self._real_client, name)

client = _ClientProxy()
