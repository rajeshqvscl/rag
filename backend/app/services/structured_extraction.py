"""
Structured JSON Extraction Layer for Pitch Decks
Extracts structured data with schema validation using Claude/GPT
"""
import json
import re
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime


class FinancialMetrics(BaseModel):
    """Financial metrics with confidence scoring"""
    revenue: Optional[str] = Field(None, description="Current revenue (e.g., '$7.6M')")
    revenue_confidence: float = Field(0.0, description="Confidence score 0-1")
    revenue_source: Optional[str] = Field(None, description="Source: text/chart/table")
    
    growth_rate: Optional[str] = Field(None, description="Growth rate (e.g., '50% YoY')")
    growth_confidence: float = Field(0.0, description="Confidence score 0-1")
    growth_source: Optional[str] = Field(None, description="Source: text/chart/table")
    
    arr: Optional[str] = Field(None, description="Annual Recurring Revenue")
    arr_confidence: float = Field(0.0)
    
    mrr: Optional[str] = Field(None, description="Monthly Recurring Revenue")
    mrr_confidence: float = Field(0.0)
    
    funding_sought: Optional[str] = Field(None, description="Amount raising (e.g., '$5M Series A')")
    funding_confidence: float = Field(0.0)
    
    runway: Optional[str] = Field(None, description="Cash runway (e.g., '18 months')")
    runway_confidence: float = Field(0.0)


class OperationalMetrics(BaseModel):
    """Operational metrics with confidence scoring"""
    users: Optional[str] = Field(None, description="User count (e.g., '50K users')")
    users_confidence: float = Field(0.0)
    users_source: Optional[str] = Field(None)
    
    customers: Optional[str] = Field(None, description="Customer count")
    customers_confidence: float = Field(0.0)
    
    fleet_size: Optional[str] = Field(None, description="Fleet/vehicle count")
    fleet_confidence: float = Field(0.0)
    
    retention_rate: Optional[str] = Field(None, description="Customer retention (e.g., '85%')")
    retention_confidence: float = Field(0.0)
    
    churn_rate: Optional[str] = Field(None, description="Churn rate")
    churn_confidence: float = Field(0.0)
    
    team_size: Optional[int] = Field(None, description="Team/employee count")
    team_confidence: float = Field(0.0)


class MarketMetrics(BaseModel):
    """Market metrics with confidence scoring"""
    tam: Optional[str] = Field(None, description="Total Addressable Market")
    tam_confidence: float = Field(0.0)
    tam_source: Optional[str] = Field(None)
    
    sam: Optional[str] = Field(None, description="Serviceable Addressable Market")
    sam_confidence: float = Field(0.0)
    
    som: Optional[str] = Field(None, description="Serviceable Obtainable Market")
    som_confidence: float = Field(0.0)
    
    market_growth: Optional[str] = Field(None, description="Market growth rate")
    market_growth_confidence: float = Field(0.0)


class CompanyInfo(BaseModel):
    """Company information with confidence scoring"""
    company_name: Optional[str] = Field(None, description="Company name")
    company_confidence: float = Field(1.0, description="Confidence in name extraction")
    
    industry: Optional[str] = Field(None, description="Industry/sector")
    industry_confidence: float = Field(0.0)
    
    stage: Optional[str] = Field(None, description="Funding stage (e.g., 'Seed', 'Series A')")
    stage_confidence: float = Field(0.0)
    
    business_model: Optional[str] = Field(None, description="Business model (e.g., 'SaaS', 'Marketplace')")
    model_confidence: float = Field(0.0)
    
    location: Optional[str] = Field(None, description="Headquarters location")
    location_confidence: float = Field(0.0)


class TeamInfo(BaseModel):
    """Team information with confidence scoring"""
    founders: List[str] = Field(default_factory=list, description="Founder names and roles")
    founders_confidence: float = Field(0.0)
    
    team_size: Optional[int] = Field(None, description="Total team size")
    team_confidence: float = Field(0.0)
    
    key_hires: List[str] = Field(default_factory=list, description="Key executive hires")
    key_hires_confidence: float = Field(0.0)


class Claim(BaseModel):
    """Individual claim extracted from pitch deck"""
    claim: str = Field(..., description="The claim made by the company")
    claim_type: str = Field(..., description="Type: traction/product/market/financial/team")
    confidence: float = Field(0.0, description="Confidence this claim is supported")
    source: str = Field(..., description="Where claim was found (slide number/section)")
    evidence: Optional[str] = Field(None, description="Supporting evidence if available")


class Risk(BaseModel):
    """Risk factor extracted from pitch deck"""
    risk: str = Field(..., description="Risk factor identified")
    risk_type: str = Field(..., description="Type: market/competition/execution/regulatory/financial")
    severity: str = Field(..., description="Severity: low/medium/high")
    confidence: float = Field(0.0, description="Confidence in risk identification")
    source: str = Field(..., description="Where risk was mentioned")


class StructuredExtraction(BaseModel):
    """Complete structured extraction from pitch deck"""
    company_info: CompanyInfo = Field(default_factory=CompanyInfo)
    financial_metrics: FinancialMetrics = Field(default_factory=FinancialMetrics)
    operational_metrics: OperationalMetrics = Field(default_factory=OperationalMetrics)
    market_metrics: MarketMetrics = Field(default_factory=MarketMetrics)
    team_info: TeamInfo = Field(default_factory=TeamInfo)
    
    claims: List[Claim] = Field(default_factory=list, description="Key claims made in deck")
    risks: List[Risk] = Field(default_factory=list, description="Identified risk factors")
    
    extraction_method: str = Field(..., description="Method used: claude/gpt/pattern")
    extraction_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    overall_confidence: float = Field(0.0, description="Overall confidence in extraction")
    
    contradictions: List[Dict] = Field(default_factory=list, description="Detected contradictions")


class StructuredExtractor:
    """Extract structured data from pitch deck text using AI"""
    
    def __init__(self):
        self.anthropic_available = False
        self.openai_available = False
        
        # Check for Claude
        try:
            from anthropic import Anthropic
            import os
            if os.getenv("ANTHROPIC_API_KEY"):
                self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                self.anthropic_available = True
                print("Claude API available for structured extraction")
        except ImportError:
            print("Claude not available for structured extraction")
        
        # Check for OpenAI
        try:
            import openai
            import os
            if os.getenv("OPENAI_API_KEY"):
                openai.api_key = os.getenv("OPENAI_API_KEY")
                self.openai_available = True
                print("OpenAI API available for structured extraction")
        except ImportError:
            print("OpenAI not available for structured extraction")
    
    def extract_structured_data(self, text: str, chunks: List[Dict] = None) -> StructuredExtraction:
        """
        Extract structured data from pitch deck text using AI
        
        Args:
            text: Full text from pitch deck
            chunks: Optional structured chunks from PDF
            
        Returns:
            StructuredExtraction object with all extracted data
        """
        if self.anthropic_available:
            return self._extract_with_claude(text, chunks)
        elif self.openai_available:
            return self._extract_with_openai(text, chunks)
        else:
            return self._extract_with_patterns(text, chunks)
    
    def _extract_with_claude(self, text: str, chunks: List[Dict] = None) -> StructuredExtraction:
        """Extract structured data using Claude API"""
        try:
            # Build context from chunks if available
            chunk_context = ""
            if chunks:
                # Get first 20 chunks for context
                for chunk in chunks[:20]:
                    chunk_context += f"\n[Slide {chunk.get('slide', chunk.get('page', '?'))} - {chunk.get('type', 'unknown')}]\n"
                    chunk_context += chunk.get('text', '')[:300] + "\n"
            
            prompt = f"""You are a venture capital data extraction specialist. Extract structured information from this pitch deck.

PITCH DECK TEXT:
{text[:8000]}

{chunk_context if chunk_context else ""}

STRICT INSTRUCTIONS:
1. Extract ONLY data that is explicitly stated in the text
2. If a metric is not mentioned, return null for that field (do not guess)
3. Assign confidence scores (0.0 to 1.0) based on how explicit the data is:
   - 1.0 = Explicitly stated with numbers
   - 0.7 = Mentioned but unclear
   - 0.5 = Implied from context
   - 0.3 = Possible but uncertain
   - 0.0 = Not found or guessed
4. For source field, specify: "text", "chart", "table", or "implied"
5. Identify key claims the company makes (traction, product, market, financial, team)
6. Identify risk factors mentioned or implied

Return ONLY valid JSON matching this schema:
{StructuredExtraction.schema_json()}

Do not include any explanations outside the JSON."""

            response = self.anthropic_client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=4000,
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text
            
            # Parse JSON response
            # Extract JSON from response (handle potential markdown code blocks)
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
            
            data = json.loads(result_text)
            
            # Validate with Pydantic
            extraction = StructuredExtraction(**data)
            extraction.extraction_method = "claude"
            extraction.overall_confidence = self._calculate_overall_confidence(extraction)
            
            # Detect contradictions
            extraction.contradadictions = self._detect_contradictions(extraction)
            
            return extraction
            
        except Exception as e:
            print(f"Claude extraction failed: {e}")
            return self._extract_with_patterns(text, chunks)
    
    def _extract_with_openai(self, text: str, chunks: List[Dict] = None) -> StructuredExtraction:
        """Extract structured data using OpenAI API"""
        try:
            import openai
            
            prompt = f"""Extract structured information from this pitch deck.

PITCH DECK TEXT:
{text[:8000]}

Return ONLY valid JSON matching this schema:
{json.dumps(StructuredExtraction.schema(), indent=2)}

Extract ONLY explicitly stated data. If not mentioned, use null. Assign confidence scores 0-1."""

            response = openai.ChatCompletion.create(
                model="gpt-4-turbo-preview",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=4000
            )
            
            result_text = response.choices[0].message.content
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
            
            data = json.loads(result_text)
            extraction = StructuredExtraction(**data)
            extraction.extraction_method = "gpt"
            extraction.overall_confidence = self._calculate_overall_confidence(extraction)
            extraction.contradictions = self._detect_contradictions(extraction)
            
            return extraction
            
        except Exception as e:
            print(f"OpenAI extraction failed: {e}")
            return self._extract_with_patterns(text, chunks)
    
    def _extract_with_patterns(self, text: str, chunks: List[Dict] = None) -> StructuredExtraction:
        """Fallback pattern-based extraction when AI unavailable"""
        print("Using pattern-based extraction (AI unavailable)")
        
        extraction = StructuredExtraction(
            extraction_method="pattern",
            overall_confidence=0.4
        )
        
        # Extract company name
        company_patterns = [
            r'^([A-Z][a-zA-Z\s&]+)\s+(?:is|presents)',
            r'About\s+([A-Z][a-zA-Z\s&]+)',
            r'([A-Z][a-zA-Z\s&]+)\s+Pitch Deck'
        ]
        for pattern in company_patterns:
            match = re.search(pattern, text[:2000], re.MULTILINE)
            if match:
                extraction.company_info.company_name = match.group(1).strip()
                extraction.company_info.company_confidence = 0.6
                break
        
        # Extract revenue
        revenue_patterns = [
            r'\$?([\d,]+(?:\.\d+)?)\s*(?:M|million)\s*(?:revenue|ARR|annual)',
            r'revenue\s*(?:of|:)?\s*\$?([\d,]+(?:\.\d+)?)\s*(?:M|million|K|thousand)',
            r'ARR\s*(?:of|:)?\s*\$?([\d,]+(?:\.\d+)?)\s*(?:M|million)'
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1)
                if 'M' in match.group(0).upper() or 'million' in match.group(0).lower():
                    extraction.financial_metrics.revenue = f"${value}M"
                else:
                    extraction.financial_metrics.revenue = f"${value}"
                extraction.financial_metrics.revenue_confidence = 0.5
                extraction.financial_metrics.revenue_source = "text"
                break
        
        # Extract stage
        stage_patterns = ['pre-seed', 'seed', 'series a', 'series b', 'series c']
        for stage in stage_patterns:
            if stage.lower() in text.lower():
                extraction.company_info.stage = stage.title()
                extraction.company_info.stage_confidence = 0.7
                break
        
        # Extract industry
        industry_keywords = {
            'mobility': ['electric vehicle', 'ev', 'mobility', 'transportation'],
            'saas': ['saas', 'software as a service', 'subscription'],
            'fintech': ['fintech', 'financial technology', 'payments'],
            'healthcare': ['healthcare', 'medical', 'health'],
            'agritech': ['agritech', 'agriculture', 'farming']
        }
        for industry, keywords in industry_keywords.items():
            if any(kw in text.lower() for kw in keywords):
                extraction.company_info.industry = industry.title()
                extraction.company_info.industry_confidence = 0.6
                break
        
        # Extract team size
        team_match = re.search(r'(\d+)\s*(?:team|employees?|people)', text, re.IGNORECASE)
        if team_match:
            extraction.team_info.team_size = int(team_match.group(1))
            extraction.team_info.team_confidence = 0.6
        
        # Extract user count
        user_match = re.search(r'(\d+[KMB]?)\s*(?:users?|customers?)', text, re.IGNORECASE)
        if user_match:
            extraction.operational_metrics.users = user_match.group(1)
            extraction.operational_metrics.users_confidence = 0.6
            extraction.operational_metrics.users_source = "text"
        
        return extraction
    
    def _calculate_overall_confidence(self, extraction: StructuredExtraction) -> float:
        """Calculate overall confidence score from all metrics"""
        confidences = []
        
        # Financial metrics
        confidences.append(extraction.financial_metrics.revenue_confidence)
        confidences.append(extraction.financial_metrics.growth_confidence)
        
        # Operational metrics
        confidences.append(extraction.operational_metrics.users_confidence)
        
        # Company info
        confidences.append(extraction.company_info.company_confidence)
        confidences.append(extraction.company_info.stage_confidence)
        
        # Filter out zeros and calculate average
        valid_confidences = [c for c in confidences if c > 0]
        if valid_confidences:
            return sum(valid_confidences) / len(valid_confidences)
        return 0.0
    
    def _detect_contradictions(self, extraction: StructuredExtraction) -> List[Dict]:
        """Detect contradictions between different data sources"""
        contradictions = []
        
        # Check revenue consistency
        if extraction.financial_metrics.revenue and extraction.financial_metrics.arr:
            # Try to compare numeric values
            try:
                rev_num = self._parse_currency(extraction.financial_metrics.revenue)
                arr_num = self._parse_currency(extraction.financial_metrics.arr)
                
                if rev_num and arr_num:
                    # ARR should be close to or higher than revenue
                    if abs(rev_num - arr_num) / max(rev_num, arr_num) > 0.5:
                        contradictions.append({
                            "type": "revenue_arr_mismatch",
                            "severity": "medium",
                            "message": f"Revenue ({extraction.financial_metrics.revenue}) and ARR ({extraction.financial_metrics.arr}) differ significantly"
                        })
            except:
                pass
        
        # Check growth rate consistency
        if extraction.financial_metrics.growth_rate and extraction.market_metrics.market_growth:
            # Company growth should ideally be higher than market growth
            try:
                company_growth = self._parse_percentage(extraction.financial_metrics.growth_rate)
                market_growth = self._parse_percentage(extraction.market_metrics.market_growth)
                
                if company_growth and market_growth and company_growth < market_growth:
                    contradictions.append({
                        "type": "growth_below_market",
                        "severity": "low",
                        "message": f"Company growth ({extraction.financial_metrics.growth_rate}) below market growth ({extraction.market_metrics.market_growth})"
                    })
            except:
                pass
        
        return contradictions
    
    def _parse_currency(self, value: str) -> Optional[float]:
        """Parse currency string to float"""
        if not value:
            return None
        value = value.upper().replace('$', '').replace(',', '').strip()
        multiplier = 1
        if value.endswith('B'):
            multiplier = 1e9
            value = value[:-1]
        elif value.endswith('M'):
            multiplier = 1e6
            value = value[:-1]
        elif value.endswith('K'):
            multiplier = 1e3
            value = value[:-1]
        try:
            return float(value) * multiplier
        except:
            return None
    
    def _parse_percentage(self, value: str) -> Optional[float]:
        """Parse percentage string to float"""
        if not value:
            return None
        value = value.replace('%', '').strip()
        try:
            return float(value)
        except:
            return None


# Singleton instance
structured_extractor = StructuredExtractor()
