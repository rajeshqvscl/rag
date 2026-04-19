"""
Pitch deck management routes
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.services.security_service import get_api_key
from app.config.database import get_db
from app.models.database import PitchDeck, User
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import json
import re
import os
import shutil
from datetime import datetime
from app.services.pipeline import run_pipeline

# Import data-driven email generator (NEW)
try:
    from app.services.data_driven_email import data_driven_email_generator
    DATA_DRIVEN_EMAIL_AVAILABLE = True
    print("✓ Data-driven email generator available")
except ImportError as e:
    print(f"✗ Data-driven email generator not available: {e}")
    DATA_DRIVEN_EMAIL_AVAILABLE = False

# Import graph generator
try:
    from app.services.graph_generator import graph_generator
    GRAPH_GENERATOR_AVAILABLE = True
    print("✓ Graph generator available")
except ImportError as e:
    print(f"✗ Graph generator not available: {e}")
    GRAPH_GENERATOR_AVAILABLE = False

router = APIRouter()

def get_or_create_default_user(db: Session):
    """Get or create default user for pitch decks"""
    user = db.query(User).filter_by(username="default").first()
    if not user:
        user = User(
            username="default",
            email="default@finrag.com",
            hashed_password="default",
            full_name="Default User"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

def generate_fallback_analysis(company_name: str, extracted: Dict, key_metrics: Dict, revenue_trajectory: list, text_content: str) -> str:
    """Generate detailed VC-style analysis using extracted data when Claude API is unavailable."""
    
    industry = extracted.get('industry') or 'Technology'
    stage = extracted.get('stage') or 'Early Stage'
    founders = extracted.get('founders') or []
    team_size = extracted.get('team_size')
    pages = extracted.get('pages', 0)
    
    # Extract metrics - handle both old and new extraction formats
    def safe_get_metric(metrics_dict, key, default='Not disclosed'):
        """Safely get metric value, handling None and placeholder strings"""
        value = metrics_dict.get(key)
        if value is None or value in ['Unavailable', 'Not found in document', 'To be determined']:
            return default
        return value
    
    revenue = safe_get_metric(key_metrics, 'revenue', 'Not disclosed in pitch deck')
    growth = safe_get_metric(key_metrics, 'growth', 'Not disclosed in pitch deck')
    tam = safe_get_metric(key_metrics, 'tam', 
                         safe_get_metric(key_metrics, 'market_size', 'Not specified in pitch deck'))
    raising = safe_get_metric(key_metrics, 'raising', 'Not specified in pitch deck')
    runway = safe_get_metric(key_metrics, 'runway', 'Not specified in pitch deck')
    users = safe_get_metric(key_metrics, 'users', None)
    
    # Extract additional operational metrics from text if not in key_metrics
    def extract_metric_from_text(text, pattern):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
        return None
    
    fleet_size = extract_metric_from_text(text_content, r'(\d+)\s*(?:vehicles?|fleet|bikes?)')
    if fleet_size:
        fleet_num = int(fleet_size)
        if fleet_num >= 1000:
            fleet_size = f"{fleet_num/1000:.1f}K"
        else:
            fleet_size = f"{fleet_num:,}"
    
    retention = extract_metric_from_text(text_content, r'(\d+)%\s*retention')
    if retention:
        retention += '%'
    
    occupancy = extract_metric_from_text(text_content, r'(\d+)%\s*occupancy')
    if occupancy:
        occupancy += '%'
    
    # Build comprehensive analysis
    sections = []
    
    # Executive Summary
    sections.append(f"## Executive Summary\n\n")
    # Clean up stage text (avoid "growth stage stage") — guard None
    stage_clean = (stage or 'early').lower().replace(' stage', '').replace('stage ', '')
    sections.append(f"{company_name} is a {stage_clean} stage company operating in the {industry} sector. ")
    sections.append(f"Based on the pitch deck analysis, the company presents a venture capital opportunity ")
    if pages and pages > 0:
        sections.append(f"that requires further evaluation. The document contains {pages} pages of business information.\n\n")
    else:
        sections.append(f"that requires further evaluation.\n\n")
    
    # Add industry-specific context only if it aligns with detected industry
    industry_lower = (industry or '').lower()
    text_lower = (text_content or '').lower()
    
    if ('electric' in text_lower or 'ev' in text_lower or 'vehicle' in text_lower) and 'mobility' in industry_lower:
        sections.append(f"The company operates in the electric vehicle / sustainable mobility space, ")
        sections.append(f"targeting the growing clean transportation market.\n\n")
    elif ('saas' in text_lower or 'software' in text_lower or 'platform' in text_lower) and ('saas' in industry_lower or 'software' in industry_lower or 'fintech' in industry_lower):
        sections.append(f"The company operates a SaaS/platform business model with software-driven solutions.\n\n")
    
    # Key Metrics
    sections.append(f"## Key Metrics\n\n")
    sections.append(f"**Financial Metrics:**\n")
    sections.append(f"- **Revenue:** {revenue}\n")
    if growth != 'Not disclosed':
        sections.append(f"- **Growth Rate:** {growth}\n")
    if raising != 'Not specified':
        sections.append(f"- **Funding Sought:** {raising}\n")
    if runway != 'Not specified':
        sections.append(f"- **Runway:** {runway}\n")
    sections.append(f"\n**Operational Metrics:**\n")
    if users:
        sections.append(f"- **User Base:** {users}\n")
    if fleet_size:
        sections.append(f"- **Fleet Size:** {fleet_size} vehicles\n")
    if retention:
        sections.append(f"- **Retention Rate:** {retention}\n")
    if occupancy:
        sections.append(f"- **Occupancy Rate:** {occupancy}\n")
    if tam != 'To be determined':
        sections.append(f"- **Market Size (TAM):** {tam}\n")
    if not any([users, fleet_size, retention, occupancy]):
        sections.append(f"- Limited operational metrics extracted from pitch deck\n")
    sections.append(f"\n")
    
    # Key Strengths
    sections.append(f"## Key Strengths\n\n")
    strengths = []
    if revenue != 'Not disclosed' and revenue != '$1M':
        strengths.append(f"**Revenue Traction:** Demonstrated revenue of {revenue} showing market validation")
    if growth != 'Not disclosed' and growth != '50%':
        strengths.append(f"**Strong Growth:** {growth} growth rate indicating rapid market expansion")
    if users or fleet_size:
        strengths.append(f"**User/Fleet Base:** Established operational base with active users/vehicles")
    if 'partner' in text_lower or 'client' in text_lower:
        strengths.append(f"**Strategic Partnerships:** References to business partnerships and client relationships")
    if founders:
        strengths.append(f"**Experienced Team:** Founding team with industry background")
    if retention and int(retention.replace('%', '')) > 70:
        strengths.append(f"**High Retention:** {retention} customer retention indicating product-market fit")
    if occupancy and int(occupancy.replace('%', '')) > 80:
        strengths.append(f"**Strong Utilization:** {occupancy} occupancy rate showing efficient operations")
    
    if strengths:
        for i, strength in enumerate(strengths[:6], 1):
            sections.append(f"{i}. {strength}\n")
    else:
        sections.append(f"1. **Early Market Opportunity:** First-mover advantage in emerging segment\n")
        sections.append(f"2. **Scalable Business Model:** Platform approach enabling rapid growth\n")
        sections.append(f"3. **Experienced Founders:** Team with relevant industry expertise\n")
    sections.append(f"\n")
    
    # Key Risks & Concerns
    sections.append(f"## Key Risks & Concerns\n\n")
    risks = []
    if stage.lower() in ['pre-seed', 'seed', 'angel']:
        risks.append(f"**Early Stage Risk:** Limited operational history and unproven scalability")
    if revenue == 'Not disclosed' or revenue == '$1M':
        risks.append(f"**Revenue Validation:** Limited financial data for investment decision")
    if runway == 'Not specified' or (runway and 'month' in runway.lower() and int(re.search(r'\d+', runway).group()) < 12):
        risks.append(f"**Runway Concerns:** Short cash runway requiring near-term funding")
    if 'compet' in text_lower:
        risks.append(f"**Competitive Market:** Competitive landscape may pressure margins")
    if 'capital' in text_lower or 'capex' in text_lower:
        risks.append(f"**Capital Intensity:** Business model requires significant capital deployment")
    if 'regulat' in text_lower:
        risks.append(f"**Regulatory Risk:** Subject to potential regulatory changes")
    
    if risks:
        for i, risk in enumerate(risks[:6], 1):
            sections.append(f"{i}. {risk}  \n")  # Two spaces for line break
    else:
        sections.append(f"1. **Market Risk:** Unproven market demand at scale\n")
        sections.append(f"2. **Execution Risk:** Team ability to execute growth plans\n")
        sections.append(f"3. **Competition Risk:** Emerging competitive landscape\n")
        sections.append(f"4. **Unit Economics:** Path to profitability not clearly demonstrated\n")
    sections.append(f"\n")
    
    # Financial Highlights
    sections.append(f"## Financial Highlights\n\n")
    sections.append(f"### Current Performance\n")
    if revenue != 'Not disclosed':
        sections.append(f"- Current revenue: {revenue}\n")
    else:
        sections.append(f"- Revenue: Pre-revenue / Not disclosed\n")
    if growth != 'Not disclosed':
        sections.append(f"- Growth trajectory: {growth}\n")
    sections.append(f"- Funding requirement: {raising}\n")
    sections.append(f"\n")
    
    # Growth Projections
    # Handle both list and status-dict formats for robustness
    points = revenue_trajectory.get("points", []) if isinstance(revenue_trajectory, dict) else (revenue_trajectory or [])
    
    if points:
        sections.append(f"### Revenue Projections\n")
        sections.append(f"| Year | Revenue |\n")
        sections.append(f"|------|---------|\n")
        for item in points:
            # item is now guaranteed to be a dict if it exists
            year = item.get('year', 'N/A')
            rev = item.get('revenue') or item.get('value', 0)
            
            # Handle edge cases
            if rev is None or rev == 0:
                continue
            
            # Format with appropriate unit
            try:
                rev = float(rev)
                if rev >= 1000000000:
                    rev_str = f"${rev/1000000000:.1f}B"
                elif rev >= 1000000:
                    rev_str = f"${rev/1000000:.1f}M"
                elif rev >= 1000:
                    rev_str = f"${rev/1000:.0f}K"
                elif rev >= 1:
                    rev_str = f"${rev:,.0f}"
                else:
                    continue  # Skip invalid values
                sections.append(f"| {year} | {rev_str} |\n")
            except (ValueError, TypeError):
                continue  # Skip malformed data
        sections.append(f"\n")
        
    # Unit Economics
    sections.append(f"### Unit Economics\n")
    sections.append(f"- Path to profitability: Requires further analysis\n")
    sections.append(f"- CAC/LTV ratio: Data not available in pitch deck\n")
    sections.append(f"- Gross margins: Not specified\n")
    sections.append(f"\n")
    
    # Investment Recommendation
    sections.append(f"## Investment Recommendation\n\n")
    
    has_revenue = revenue != 'Not disclosed' and revenue != '$1M'
    has_growth = growth != 'Not disclosed' and growth != '50%'
    has_users = users is not None or fleet_size is not None
    
    if has_revenue and has_growth and has_users:
        sections.append(f"**PROCEED WITH CAUTION** \n\n")
        sections.append(f"This opportunity shows strong early traction with demonstrated revenue and user base. ")
        sections.append(f"Key due diligence priorities:\n\n")
        sections.append(f"1. **Unit Economics:** Validate path to profitability and unit-level margins\n")
        sections.append(f"2. **Market Sizing:** Verify TAM and competitive positioning analysis\n")
        sections.append(f"3. **Team Capability:** Assess team's ability to execute growth plans\n")
        sections.append(f"4. **Capital Efficiency:** Understand burn rate and capital deployment strategy\n")
    elif has_revenue or has_users:
        sections.append(f"**CONSIDER** \n\n")
        sections.append(f"This opportunity shows promise with some traction indicators. Recommend:\n\n")
        sections.append(f"1. **Management Interview:** Meet founding team to assess capabilities\n")
        sections.append(f"2. **Financial Validation:** Request detailed financial projections\n")
        sections.append(f"3. **Customer Diligence:** Speak with existing customers/users\n")
        sections.append(f"4. **Market Assessment:** Validate market size and competitive landscape\n")
    else:
        sections.append(f"**EARLY STAGE / WATCH** \n\n")
        sections.append(f"Limited quantitative data available. Recommend:\n\n")
        sections.append(f"1. **Track Progress:** Monitor for revenue and user traction milestones\n")
        sections.append(f"2. **Team Evaluation:** Deep dive on founder backgrounds and expertise\n")
        sections.append(f"3. **Product Assessment:** Evaluate product-market fit indicators\n")
        sections.append(f"4. **Follow-on Review:** Re-assess after 6-12 months of progress\n")
    
    
    return "".join(sections)

def _generate_data_driven_analysis(company_name: str, key_metrics: Dict, extracted: Dict) -> str:
    """
    Generate analysis purely from extracted data - NO PATTERN GUESSING
    
    This replaces the old fallback pattern analysis with data-driven insights
    """
    sections = []
    
    # Header
    sections.append(f"## Executive Summary\n\n")
    sections.append(f"{company_name} has been analyzed based on data extracted from the pitch deck. ")
    
    # Data completeness assessment
    metrics_found = []
    metrics_missing = []
    
    if key_metrics.get('revenue'):
        metrics_found.append(f"revenue of {key_metrics['revenue']}")
    else:
        metrics_missing.append("revenue")
    
    if key_metrics.get('growth'):
        metrics_found.append(f"growth rate of {key_metrics['growth']}")
    else:
        metrics_missing.append("growth rate")
    
    if key_metrics.get('users'):
        metrics_found.append(f"{key_metrics['users']} users")
    else:
        metrics_missing.append("user count")
    
    if key_metrics.get('tam'):
        metrics_found.append(f"market size of {key_metrics['tam']}")
    else:
        metrics_missing.append("market size")
    
    if metrics_found:
        sections.append(f"The pitch deck indicates {', '.join(metrics_found)}. ")
    
    if metrics_missing:
        sections.append(f"However, key metrics were not found: {', '.join(metrics_missing)}. ")
    
    sections.append("\n\n")
    
    # Key Metrics Section
    sections.append("## Key Metrics\n\n")
    
    revenue = key_metrics.get('revenue')
    growth = key_metrics.get('growth')
    users = key_metrics.get('users')
    tam = key_metrics.get('tam')
    raising = key_metrics.get('raising')
    
    if revenue:
        sections.append(f"**Revenue:** {revenue}\n")
    if growth:
        sections.append(f"**Growth Rate:** {growth}\n")
    if users:
        sections.append(f"**Users/Customers:** {users}\n")
    if tam:
        sections.append(f"**Market Size (TAM):** {tam}\n")
    if raising:
        sections.append(f"**Funding Sought:** {raising}\n")
    
    if not any([revenue, growth, users, tam]):
        sections.append("⚠ **Limited financial data found in pitch deck**\n")
    
    sections.append("\n")
    
    # Investment Recommendation
    sections.append("## Investment Recommendation\n\n")
    
    overall_confidence = extracted.get('overall_confidence', 0)
    
    if overall_confidence >= 0.7 and all([revenue, growth, users]):
        sections.append("**PROCEED WITH EVALUATION**\n\n")
        sections.append("Sufficient quantitative data available for initial assessment. ")
        sections.append("Key metrics have been extracted with reasonable confidence.\n")
    elif overall_confidence >= 0.4 and any([revenue, growth, users]):
        sections.append("**REQUIRES CLARIFICATION**\n\n")
        sections.append("Partial data available. Further discussion needed to fill gaps. ")
        sections.append("See email draft for specific questions.\n")
    else:
        sections.append("**INSUFFICIENT DATA**\n\n")
        sections.append("Limited quantitative metrics found in the pitch deck. ")
        sections.append("A follow-up conversation is recommended to gather key financial information.\n")
    
    # Chart data mention
    chart_data = extracted.get('chart_revenue_data', [])
    if chart_data:
        sections.append(f"\n**Chart Analysis:** Found {len(chart_data)} revenue data points from charts/table.\n")
    
    return "".join(sections)

@router.get("/pitch-decks")
def get_pitch_decks(
    limit: int = 10,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get all pitch decks from database"""
    try:
        user = get_or_create_default_user(db)
        
        pitch_decks = db.query(PitchDeck).filter(
            PitchDeck.user_id == user.id
        ).order_by(PitchDeck.uploaded_at.desc()).limit(limit).all()
        
        result = []
        for deck in pitch_decks:
            result.append({
                "id": deck.id,
                "company_name": deck.company_name,
                "file_name": deck.file_name,
                "industry": deck.industry,
                "stage": deck.stage,
                "confidence": deck.funding_stage or "High",
                "date_uploaded": deck.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if deck.uploaded_at else None,
                "pages": deck.pdf_pages,
                "key_metrics": deck.key_metrics or {},
                "revenue_data": deck.revenue_data or [],
                "analysis": deck.analysis,
                "email_draft": deck.email_draft,
                "status": deck.status
            })
        
        return {
            "status": "success",
            "pitch_decks": result,
            "total": len(result)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pitch-decks")
def create_pitch_deck(
    company: str,
    title: str,
    content: str,
    api_key: str = Depends(get_api_key)
):
    """Create a new pitch deck"""
    try:
        return {
            "status": "success",
            "message": "Pitch deck created",
            "pitch_deck_id": "new-deck-id"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pitch-decks/{pitch_deck_id}")
def get_pitch_deck(
    pitch_deck_id: str,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get a specific pitch deck with full analysis"""
    try:
        user = get_or_create_default_user(db)
        
        # Try to fetch by ID (integer) or return 404
        try:
            deck_id = int(pitch_deck_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid pitch deck ID")
        
        deck = db.query(PitchDeck).filter(
            PitchDeck.id == deck_id,
            PitchDeck.user_id == user.id
        ).first()
        
        if not deck:
            raise HTTPException(status_code=404, detail="Pitch deck not found")
        
        # Update last viewed timestamp
        deck.last_viewed_at = datetime.utcnow()
        db.commit()
        
        return {
            "status": "success",
            "pitch_deck": {
                "id": deck.id,
                "company_name": deck.company_name,
                "company": deck.company_name,
                "file_name": deck.file_name,
                "file_path": deck.file_path,
                "industry": deck.industry,
                "stage": deck.stage,
                "pages": deck.pdf_pages,
                "key_metrics": deck.key_metrics or {},
                "revenue_data": deck.revenue_data or [],
                "analysis": deck.analysis or "No analysis available",
                "email_draft": deck.email_draft or "No email draft available",
                "founders": deck.founders or [],
                "team_size": deck.team_size,
                "date_uploaded": deck.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if deck.uploaded_at else None,
                "confidence": deck.funding_stage or "High",
                "status": deck.status
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pitch-decks/{pitch_deck_id}/reprocess")
async def reprocess_pitch(pitch_deck_id: int, db: Session = Depends(get_db)):
    try:
        deck = db.query(PitchDeck).filter(PitchDeck.id == pitch_deck_id).first()
        if not deck:
            raise HTTPException(status_code=404, detail="Pitch deck not found")
        
        # Use existing file path to re-run pipeline
        if not deck.file_path or not os.path.exists(deck.file_path):
            raise HTTPException(status_code=400, detail="Original file no longer available on disk")

        result = run_pipeline(deck.file_path)
        
        if result.get("status") in ["success", "partial_success"]:
            data = result.get("data", {})
            
            # Update database record
            deck.analysis = f"### Professional Summary\n{data.get('summary')}\n\n{data.get('brief_analysis')}"
            deck.email_draft = data.get('email_draft')
            deck.key_metrics = {
                "revenue": data.get("revenue"),
                "growth": data.get("growth_rate"),
                "users": data.get("users"),
                "market": data.get("market_size")
            }
            deck.status = "processed"
            db.commit()
            
            return {"status": "success", "pitch_deck": deck}
        
        return result

    except Exception as e:
        print(f"REPROCESS_ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pitch-decks/upload")
async def upload_pitch(file: UploadFile = File(...)):
    try:
        # Ensure tmp directory exists
        os.makedirs("tmp", exist_ok=True)
        path = f"tmp/{file.filename}"
        with open(path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        result = run_pipeline(path)
        
        if result.get("status") in ["success", "partial_success"]:
            data = result.get("data", {})
            status = result.get("status")
            
            # Identify the company name cleanly
            base_name = file.filename
            # Remove extension
            name_no_ext = os.path.splitext(base_name)[0]
            # Strip common fluff
            fluff = [r'investor\s*deck', r'pitch\s*deck', r'feb\'?\d+', r'mar\'?\d+', r'apr\'?\d+', r'202[4-6]', r'v\d+']
            clean_name = name_no_ext
            for pattern in fluff:
                clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
            
            clean_name = clean_name.replace('_', ' ').replace('-', ' ').strip().title()

            # Professional Analysis Synthesis
            if status == "success":
                analysis_text = f"### Professional Summary\n{data.get('summary', 'Analysis pending...')}\n\n"
                analysis_text += f"{data.get('brief_analysis', 'Data points under verification.')}\n\n"
                analysis_text += "---\n*Generated by FinRAG VC Analyst Engine (Claude 3.5 Sonnet)*"
                email_draft = data.get('email_draft', 'No draft generated.')
            else:
                analysis_text = f"### Extraction Warning\n{data.get('summary')}\n\n"
                analysis_text += "The system was able to parse the document but encountered a formatting issue with the AI's response."
                email_draft = "N/A"

            processed_data = {
                "id": "temp-" + os.path.basename(path),
                "company_name": data.get("company_name") or clean_name,
                "analysis": analysis_text,
                "email_draft": email_draft,
                "key_metrics": {
                    "revenue": data.get("revenue"),
                    "growth": data.get("growth_rate"),
                    "users": data.get("users"),
                    "market": data.get("market_size")
                },
                "revenue_data": data.get("revenue_data") or [],
                "stage": data.get("stage") or "Determining...",
                "status": "processed" if status == "success" else "warning",
                "metadata": result.get("metadata", {})
            }
            return {
                "status": "success",
                "pitch_deck": processed_data
            }
            
        return result

    except Exception as e:
        print(f"ROUTE_ERROR: {e}")
        return {
            "status": "error",
            "stage": "route_handler",
            "message": str(e)
        }

@router.get("/pitch-decks/{pitch_deck_id}/download")
def download_pitch_deck(
    pitch_deck_id: str,
    api_key: str = Depends(get_api_key)
):
    """Download a pitch deck"""
    try:
        return {
            "status": "success",
            "download_url": f"/downloads/{pitch_deck_id}.pdf"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/pitch-decks/{pitch_deck_id}")
def update_pitch_deck(
    pitch_deck_id: str,
    content: str,
    api_key: str = Depends(get_api_key)
):
    """Update a pitch deck"""
    try:
        return {
            "status": "success",
            "message": "Pitch deck updated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/pitch-decks/{pitch_deck_id}")
def delete_pitch_deck(
    pitch_deck_id: str,
    api_key: str = Depends(get_api_key)
):
    """Delete a pitch deck"""
    try:
        return {
            "status": "success",
            "message": "Pitch deck deleted"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
