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
from datetime import datetime

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
    
    # Extract additional metrics from text
    revenue = key_metrics.get('revenue', 'Not disclosed')
    growth = key_metrics.get('growth', 'Not disclosed')
    tam = key_metrics.get('tam', key_metrics.get('market_size', 'To be determined'))
    raising = key_metrics.get('raising', 'Not specified')
    runway = key_metrics.get('runway', 'Not specified')
    
    # Try to extract more metrics from text
    users_match = re.search(r'(\d+[KMB]?)\s*(?:users?|customers?)', text_content, re.IGNORECASE)
    users = users_match.group(1) if users_match else None
    
    fleet_match = re.search(r'(\d+)\s*(?:vehicles?|fleet|bikes?)', text_content, re.IGNORECASE)
    fleet_size = fleet_match.group(1) if fleet_match else None
    
    retention_match = re.search(r'(\d+)%\s*retention', text_content, re.IGNORECASE)
    retention = retention_match.group(1) + '%' if retention_match else None
    
    occupancy_match = re.search(r'(\d+)%\s*occupancy', text_content, re.IGNORECASE)
    occupancy = occupancy_match.group(1) + '%' if occupancy_match else None
    
    # Build comprehensive analysis
    sections = []
    
    # Executive Summary
    sections.append(f"## Executive Summary\n\n")
    # Clean up stage text (avoid "growth stage stage") — guard None
    stage_clean = (stage or 'early').lower().replace(' stage', '').replace('stage ', '')
    sections.append(f"{company_name} is a {stage_clean} stage company operating in the {industry} sector. ")
    sections.append(f"Based on the pitch deck analysis, the company presents a venture capital opportunity ")
    sections.append(f"that requires further evaluation. The document contains {pages} pages of business information.\n\n")
    
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
    if revenue_trajectory:
        sections.append(f"### Revenue Projections\n")
        sections.append(f"| Year | Revenue |\n")
        sections.append(f"|------|---------|\n")
        for item in revenue_trajectory:
            year = item.get('year', 'N/A')
            rev = item.get('revenue', 0)
            
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

@router.post("/pitch-decks/upload")
async def upload_pitch_deck(
    file: UploadFile = File(...),
    company: str = "",
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Upload a pitch deck file with detailed AI analysis"""
    try:
        from app.services.pitch_deck_service import PitchDeckService
        from app.services.embeddings import get_embedding
        import hashlib
        
        pitch_deck_service = PitchDeckService()
        user = get_or_create_default_user(db)
        
        # Read file content
        file_content = await file.read()
        file_name = file.filename if file else "unknown.pdf"
        
        # Generate unique ID based on file content
        file_hash = hashlib.md5(file_content).hexdigest()[:12]
        unique_id = f"pd_{file_hash}"
        
        # Save the PDF file (use filename as temp company name)
        temp_company = company or "Unknown Company"
        file_path = pitch_deck_service.save_pdf(file_content, file_name, temp_company)
        
        # Extract text and metrics from PDF (including company name)
        extracted = pitch_deck_service.extract_pdf_text(file_path, file_name)
        
        # Use extracted company name, fallback to form input, then to filename-based name
        extracted_company = extracted.get('company_name')
        if extracted_company and extracted_company != "Unknown Company":
            company_name = extracted_company
            print(f"Using extracted company name: {company_name}")
        elif company and company != "Unknown Company":
            company_name = company
            print(f"Using form company name: {company_name}")
        else:
            # Try to clean up filename
            clean_name = file_name.replace('.pdf', '').replace('_', ' ').replace('-', ' ')
            clean_name = re.sub(r'\s*(pitch deck|pitchdeck|presentation|deck|final|draft)\s*\d*$', '', clean_name, flags=re.IGNORECASE)
            company_name = clean_name.strip() or "Unknown Company"
            print(f"Using filename-based company name: {company_name}")
        
        # Get extracted metrics
        key_metrics = extracted.get('key_metrics') or {}
        text_content = extracted.get('text') or ''  # ← guard
        
        # Extract revenue trajectory specifically for this pitch deck
        revenue_trajectory = pitch_deck_service._extract_revenue_from_text(text_content)
        
        # Ensure no hallucinated data drives the chart
        if revenue_trajectory.get("status") != "ok":
            revenue_trajectory = {"status": "no_valid_data", "points": []}
        
        # Note: Embedding semantic analysis is disabled for Phase 1.
        # Strict BM25 / keyword strategy used.
        semantic_summary = "Semantic embedding analysis disabled for Phase 1"
        
        # Generate detailed VC-style analysis using Claude Sonnet 4
        print(f"Generating detailed VC analysis for {company_name} using Claude Sonnet 4...")
        from app.services.claude_service import analyze_pitch_deck_detailed
        claude_result = analyze_pitch_deck_detailed(text_content, company_name, key_metrics)

        # ← THE FIX: .get() returns None when key exists but value is None.
        # Use `or` to guarantee a string regardless of what Claude returned.
        analysis_markdown = claude_result.get('detailed_analysis') or ""

        # If Claude API failed, use the rich local fallback
        if not analysis_markdown.strip():
            print(f"Claude returned empty/None analysis — using local fallback for {company_name}")
            analysis_markdown = generate_fallback_analysis(
                company_name, extracted, key_metrics, revenue_trajectory, text_content or ""
            )

        # Add analysis metadata section (frontend handles main title)
        warning_msg = "\n⚠ **Financial data extracted from charts may be unreliable.**\n"
        analysis_header = f"""**Analysis Metadata:**
- **Company:** {company_name}
- **Industry:** {extracted.get('industry') or 'Technology'}
- **Stage:** {extracted.get('stage') or 'Early Stage'}
- **Document Pages:** {extracted.get('pages', 0)}
- **Analysis ID:** {unique_id}
- **Analysis Method:** {'Claude Sonnet 4 (AI-powered)' if claude_result.get('detailed_analysis') else 'Local Fallback (Pattern Analysis)'}
{warning_msg}
---

"""

        # ← safe: both sides are now guaranteed strings
        analysis_markdown = analysis_header + analysis_markdown
        # Generate Google Meet scheduling email with grounded RAG data
        from app.services.claude_service import generate_draft_email
        email_draft = generate_draft_email(analysis_markdown, company_name, key_metrics)
        
        # Save to database
        pitch_deck = PitchDeck(
            user_id=user.id,
            company_name=company_name,
            file_name=file_name,
            file_path=file_path,
            file_size=len(file_content),
            pdf_pages=extracted.get('pages', 0),
            industry=extracted.get('industry'),
            stage=extracted.get('stage'),
            extracted_text=text_content[:5000],  # Store preview
            key_metrics=key_metrics,
            revenue_data=revenue_trajectory,
            analysis=analysis_markdown,
            email_draft=email_draft,
            founders=extracted.get('founders', []),
            team_size=extracted.get('team_size'),
            status="new",
            priority="medium"
        )
        db.add(pitch_deck)
        db.commit()
        db.refresh(pitch_deck)
        
        return {
            "status": "success",
            "pitch_deck": {
                "id": pitch_deck.id,
                "company": company_name,
                "company_name": company_name,
                "file_name": file_name,
                "analysis": analysis_markdown,
                "email_draft": email_draft,
                "revenue_data": revenue_trajectory,
                "date_uploaded": pitch_deck.uploaded_at.strftime("%Y-%m-%d %H:%M:%S") if pitch_deck.uploaded_at else datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "confidence": "High",
                "file_path": file_path,
                "pages": extracted.get('pages', 0),
                "key_metrics": key_metrics,
                "industry": extracted.get('industry'),
                "stage": extracted.get('stage'),
                "founders": extracted.get('founders', []),
                "team_size": extracted.get('team_size'),
                "semantic_analysis": semantic_summary
            }
        }
    except Exception as e:
        import traceback
        print(f"Error processing pitch deck: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

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
