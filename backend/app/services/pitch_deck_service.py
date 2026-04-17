"""
Pitch Deck Service for PDF management and content extraction
"""
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import requests

# Import structured PDF extractor
try:
    from app.services.pdf_extractor import pdf_extractor, TextChunk
    STRUCTURED_EXTRACTION_AVAILABLE = True
except ImportError as e:
    print(f"Structured PDF extractor not available: {e}")
    STRUCTURED_EXTRACTION_AVAILABLE = False
    import PyPDF2

# Check if Claude API is available
ANTHROPIC_AVAILABLE = os.getenv("ANTHROPIC_API_KEY") is not None

# Check if Ollama is available
OLLAMA_AVAILABLE = False
try:
    response = requests.get("http://localhost:11434/api/tags", timeout=2)
    OLLAMA_AVAILABLE = response.status_code == 200
    print("Ollama is available")
except:
    print("Ollama is not available (not running or not installed)")

from app.models.database import PitchDeck, User
from app.config.database import get_db

# Try to import multimodal service, but handle if dependencies are missing
try:
    from app.services.multimodal_service import multimodal_service
    MULTIMODAL_AVAILABLE = True
except ImportError as e:
    print(f"Multimodal service not available: {e}")
    MULTIMODAL_AVAILABLE = False

# Import for AI generation
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def _call_ollama(prompt: str, model: str = "llama3") -> str:
    """Call Ollama API for text generation"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 1000
                }
            },
            timeout=60
        )
        if response.status_code == 200:
            return response.json().get("response", "")
        else:
            print(f"Ollama API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"Ollama call failed: {e}")
        return None


class PitchDeckService:
    """Service for managing pitch deck PDFs"""
    
    # Upload directory for pitch decks
    UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "../../data/pitch_decks")
    
    def __init__(self):
        os.makedirs(self.UPLOAD_DIR, exist_ok=True)
    
    def save_pdf(self, file_content: bytes, file_name: str, company_name: str) -> str:
        """Save PDF file to disk"""
        # Sanitize company name for filename
        safe_company = re.sub(r'[^\w\s-]', '', company_name).strip().replace(' ', '_')
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        # Create filename
        if file_name.lower().endswith('.pdf'):
            file_name = file_name[:-4]
        new_filename = f"{safe_company}_{timestamp}.pdf"
        file_path = os.path.join(self.UPLOAD_DIR, new_filename)
        
        # Save file
        with open(file_path, 'wb') as f:
            f.write(file_content)
        
        return file_path
    
    def extract_pdf_text(self, file_path: str, file_name: str = "") -> Dict:
        """Extract text content from PDF using structured extraction"""
        result = {
            "text": "",
            "pages": 0,
            "summary": "",
            "company_name": None,  # NEW: Extracted company name
            "key_metrics": {},
            "founders": [],
            "team_size": None,
            "industry": None,
            "stage": None,
            "chunks": []  # NEW: Structured chunks with metadata
        }
        
        # Get filename from path if not provided
        if not file_name and file_path:
            file_name = os.path.basename(file_path)
        
        try:
            # Use structured extraction if available
            if STRUCTURED_EXTRACTION_AVAILABLE:
                print(f"Using structured PDF extraction (PyMuPDF) for {file_path}")
                full_text, chunks, metadata = pdf_extractor.extract_pdf(file_path)
                
                result["text"] = full_text
                result["pages"] = metadata.get("total_pages", len(chunks))
                result["chunks"] = [
                    {
                        "text": c.text,
                        "normalized_text": c.normalized_text,
                        "slide": c.slide_number,
                        "type": c.chunk_type,
                        "page": c.page_number
                    }
                    for c in chunks
                ]
                
                print(f"Structured extraction: {len(chunks)} chunks")
                print(f"Chunk types: {metadata.get('chunk_types', {})}")
            else:
                # Fallback to basic extraction
                print("Structured extractor not available, using fallback")
                full_text, chunks, metadata = pdf_extractor._fallback_extraction(file_path) if STRUCTURED_EXTRACTION_AVAILABLE else self._basic_pdf_extract(file_path)
                result["text"] = full_text
                result["chunks"] = [{"text": c.text, "slide": c.slide_number, "type": c.chunk_type, "page": c.page_number} for c in chunks] if chunks else []
            
            # Debug output
            print(f"PDF Pages: {result['pages']}")
            print(f"Extracted text (first 500 chars): {result['text'][:500]}")
            print(f"Total text length: {len(result['text'])}")
            
            # Extract structured information from normalized text (better for metrics)
            normalized_full = " ".join([c.get("normalized_text", c.get("text", "")) for c in result["chunks"]]) if result["chunks"] else result["text"]
            
            result["key_metrics"] = self._extract_metrics(normalized_full)
            result["founders"] = self._extract_founders(result["text"])
            result["team_size"] = self._extract_team_size(result["text"])
            result["industry"] = self._extract_industry(result["text"])
            result["stage"] = self._extract_funding_stage(result["text"])
            result["company_name"] = self._extract_company_name(result["text"], file_name)
            result["summary"] = self._generate_summary(result["text"], result["key_metrics"])
            
            # Add estimated metrics if none found
            result["key_metrics"] = self._add_estimated_metrics(result["key_metrics"], result["stage"], result["industry"])
            
            print(f"Extracted metrics: {result['key_metrics']}")
            
        except Exception as e:
            print(f"Error extracting PDF content: {e}")
            import traceback
            print(traceback.format_exc())
        
        return result
    
    def _basic_pdf_extract(self, file_path: str):
        """Basic PDF extraction fallback"""
        import PyPDF2
        full_text = ""
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text = page.extract_text() or ""
                full_text += text + "\n"
        return full_text, [], {"total_chunks": 0}
    
    def _extract_metrics(self, text: str) -> Dict:
        """Extract key business metrics from pitch deck text"""
        metrics = {}
        text_lower = text.lower()
        
        # Revenue patterns - comprehensive, avoid small numbers
        revenue_patterns = [
            r'revenue[:\s-]*(?:of\s*|is\s*|was\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'(\$[\d,.]+\s*[MBK]?)\s*(?:in\s*)?(?:annual\s*)?revenue',
            r'annual\s*revenue[:\s-]*(\$[\d,.]+\s*[MBK]?)',
            r'ar[rk]\s*(?:of\s*|is\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'(\$[\d,.]+\s*[MBK]?)\s*arr',
            r'(\$[\d,.]+\s*[MBK]?)\s*mrr',
            r'revenue\s*generated[:\s-]*(\$[\d,.]+\s*[MBK]?)',
            r'total\s*revenue[:\s-]*(\$[\d,.]+\s*[MBK]?)',
            r'current\s*revenue[:\s-]*(\$[\d,.]+\s*[MBK]?)',
            r'achieved\s*(\$[\d,.]+\s*[MBK]?)\s*in\s*revenue',
            r'(?:monthly|annual)\s*(?:revenue|income|sales)[:\s-]*(\$[\d,.]+\s*[MBK]?)',
            r'(?:gross|net)\s*revenue[:\s-]*(\$[\d,.]+\s*[MBK]?)',
        ]
        for pattern in revenue_patterns:
            match = re.search(pattern, text_lower)
            if match:
                revenue_str = match.group(1).strip()
                # Parse and validate revenue - reject very small values
                rev_match = re.search(r'\$?([\d,.]+)\s*([MBK]?)', revenue_str, re.IGNORECASE)
                if rev_match:
                    num = float(rev_match[1].replace(',', ''))
                    unit = rev_match[2].upper()
                    
                    # Convert to actual number
                    if unit == 'B':
                        actual_revenue = num * 1000000000
                    elif unit == 'M':
                        actual_revenue = num * 1000000
                    elif unit == 'K':
                        actual_revenue = num * 1000
                    else:
                        actual_revenue = num
                    
                    # Only accept if revenue is reasonable (at least $10K)
                    if actual_revenue >= 10000:
                        metrics['revenue'] = revenue_str
                        break
                    else:
                        print(f"Rejected unrealistic revenue value: {revenue_str} (too small)")
                else:
                    metrics['revenue'] = revenue_str
                    break
        
        # Fallback: Look for revenue in first 2000 chars (usually in summary/financial section)
        if 'revenue' not in metrics:
            # Look for patterns like "Financial Highlights" followed by revenue
            financial_section = text_lower[:2000]
            fallback_patterns = [
                r'(?:financial|highlights|metrics|traction)[:\s\n]*.*?revenue[:\s\n]*(\$[\d,.]+\s*[MBK]?)',
                r'(?:revenue|sales)[:\s\n]*(\$[\d,.]+\s*[MBK]?)',
                r'(?:annual|recurring)\s+(?:revenue|income)[:\s\n]*(\$[\d,.]+\s*[MBK]?)',
            ]
            for pattern in fallback_patterns:
                match = re.search(pattern, financial_section)
                if match:
                    metrics['revenue'] = match.group(1).strip()
                    break
        
        # If still no revenue, try to extract market size as a proxy
        if 'revenue' not in metrics:
            # Look for any large number with currency symbol (market size)
            large_number_patterns = [
                r'[\$₹]?([\d,.]+(?:\.\d+)?)\s*(?:lakh\s*crore|crore|billion|million)',
                r'[\$₹]?([\d,.]+(?:\.\d+)?)\s*cr',  # Crore
            ]
            for pattern in large_number_patterns:
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    try:
                        num = float(match.replace(',', ''))
                        
                        # Only use if it's a reasonably large number (market size)
                        if num >= 1:  # At least 1 unit
                            # Try to determine the unit from context
                            if 'lakh crore' in text_lower:
                                metrics['market_size'] = f"${num} Lakh Crore"
                                metrics['_market_size'] = True
                                print(f"Extracted market size as proxy: {metrics['market_size']}")
                                break
                            elif 'crore' in text_lower:
                                metrics['market_size'] = f"${num} Crore"
                                metrics['_market_size'] = True
                                print(f"Extracted market size as proxy: {metrics['market_size']}")
                                break
                            elif 'billion' in text_lower:
                                metrics['market_size'] = f"${num}B"
                                metrics['_market_size'] = True
                                print(f"Extracted market size as proxy: {metrics['market_size']}")
                                break
                            elif 'million' in text_lower:
                                metrics['market_size'] = f"${num}M"
                                metrics['_market_size'] = True
                                print(f"Extracted market size as proxy: {metrics['market_size']}")
                                break
                    except (ValueError) as e:
                        continue
                if 'market_size' in metrics:
                    break
        
        # Fallback 2: Look for any dollar amount with M/B/K near "revenue"
        if 'revenue' not in metrics:
            # Find all $X.XM patterns near the word revenue
            broad_pattern = r'(?:^|[\s\n])(\$[\d,.]+[MBK])[^.]{0,30}revenue|revenue[^.]{0,30}(\$[\d,.]+[MBK])'
            match = re.search(broad_pattern, text_lower)
            if match:
                metrics['revenue'] = (match.group(1) or match.group(2)).strip()
        
        # Fallback 3: Table formats (pipe, tab, or space separated)
        if 'revenue' not in metrics:
            table_patterns = [
                r'revenue\s*[|\t]\s*(\$[\d,.]+[MBK]?)',
                r'revenue\s{2,}(\$[\d,.]+[MBK]?)',
                r'\|\s*revenue\s*\|\s*(\$[\d,.]+[MBK]?)',
            ]
            for pattern in table_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    metrics['revenue'] = match.group(1).strip()
                    break
        
        # Fallback 4: Look in first 500 chars (often on title/key metrics slide)
        if 'revenue' not in metrics:
            first_section = text_lower[:500]
            # Look for any dollar amount that might be revenue
            rev_in_first = re.search(r'(\$[\d,.]+[MB])', first_section)
            if rev_in_first:
                # Only use if it looks like a revenue number (millions+ and near other business terms)
                candidate = rev_in_first.group(1)
                if any(term in first_section for term in ['revenue', 'sales', 'income', 'financial', 'traction', 'mrr', 'arr']):
                    metrics['revenue'] = candidate.strip()
        
        # Growth rate
        growth_patterns = [
            r'(\d+)%\s*(?:yoy|year\s*over\s*year|annual)\s*growth',
            r'growth\s*rate\s*(?:of\s*)?(\d+)%',
            r'growing\s*(?:at\s*)?(\d+)%',
            r'(\d+)x\s*growth',
            r'(\d+)%\s*mom|month\s*over\s*month',
        ]
        for pattern in growth_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['growth'] = f"{match.group(1)}%"
                break
        
        # Users/Customers
        user_patterns = [
            r'(\d+[KMB]?)\s*(?:active\s*)?users',
            r'(\d+[KMB]?)\s*customers',
            r'(\d+[KMB]?)\s*subscribers',
            r'user\s*base\s*(?:of\s*)?(\d+[KMB]?)',
            r'([\d,]+)\s*(?:active\s*)?users',
            r'([\d,]+)\s*customers',
        ]
        for pattern in user_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['users'] = match.group(1).strip()
                break
        
        # TAM/SAM/SOM
        tam_patterns = [
            r'tam\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'total\s*addressable\s*market\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'market\s*size\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
        ]
        for pattern in tam_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['tam'] = match.group(1).strip()
                break
        
        # Funding amount being raised
        funding_patterns = [
            r'raising\s*(\$[\d,.]+\s*[MBK]?)',
            r'seeking\s*(\$[\d,.]+\s*[MBK]?)',
            r'looking\s*for\s*(\$[\d,.]+\s*[MBK]?)',
            r'target\s*(?:raise\s*)?(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
        ]
        for pattern in funding_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['raising'] = match.group(1).strip()
                break
        
        # Valuation
        valuation_patterns = [
            r'valuation\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'pre[-\s]*money\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
            r'post[-\s]*money\s*(?:of\s*)?(\$[\d,.]+\s*[MBK]?)',
        ]
        for pattern in valuation_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['valuation'] = match.group(1).strip()
                break
        
        # Runway/Burn
        runway_patterns = [
            r'(\d+)\s*(?:months?\s*)?(?:of\s*)?runway',
            r'runway\s*(?:of\s*)?(\d+)\s*months?',
            r'(\d+)\s*months?\s*(?:cash\s*)?runway',
        ]
        for pattern in runway_patterns:
            match = re.search(pattern, text_lower)
            if match:
                metrics['runway'] = f"{match.group(1)} months"
                break
        
        return metrics
    
    def _extract_revenue_from_text(self, text: str) -> list:
        """Extract revenue trajectory from text using regex patterns"""
        import re
        revenue_data = []
        
        if not text:
            return revenue_data
        
        # Pattern to match year-revenue pairs from text
        # Looks for patterns like "2024 $10M", "2025: $15M", "2024 - 10,000,000", "Year 1: $47M", etc.
        year_revenue_patterns = [
            # Numeric years: 2024 $10M, 2025: $15M
            r'(\d{4})\s*[:\-\s]\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
            r'(\d{4})\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
            r'\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)\s*[:\-\s]\s*(\d{4})',
            # Year X format: Year 1: $47M, Year 2: $110M
            r'(?:Year\s+(\d+)|(\d+)\s*Year)\s*[:\-\s]\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
            r'(?:Year\s+(\d+)|(\d+)\s*Year)\s*\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)',
            # Generic patterns
            r'\$?([\d,]+(?:\.\d+)?)\s*([KMB]?)\s*[:\-\s]\s*(?:Year\s+(\d+)|(\d+)\s*Year)',
        ]
        
        for pattern in year_revenue_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Handle different match group sizes
                    year = None
                    revenue_str = None
                    unit = ''
                    
                    if len(match) == 3:
                        # Pattern: (year, revenue, unit) or (revenue, unit, year)
                        if match[0] and (match[0].isdigit() and len(match[0]) == 4 or match[0].isdigit() and int(match[0]) <= 20):
                            year = match[0]
                            revenue_str = match[1]
                            unit = match[2].upper() if match[2] else ''
                        elif match[2] and (match[2].isdigit() and len(match[2]) == 4 or match[2].isdigit() and int(match[2]) <= 20):
                            year = match[2]
                            revenue_str = match[0]
                            unit = match[1].upper() if match[1] else ''
                    elif len(match) == 4:
                        # Pattern: (year1, year2, revenue, unit) - Year X format
                        year = match[0] if match[0] else match[1]
                        revenue_str = match[2]
                        unit = match[3].upper() if match[3] else ''
                    
                    if not year or not revenue_str:
                        continue
                    
                    # Parse revenue value
                    revenue_num = float(revenue_str.replace(',', ''))
                    
                    # Convert to actual number based on unit
                    if unit == 'B':
                        revenue_num *= 1000000000
                    elif unit == 'M':
                        revenue_num *= 1000000
                    elif unit == 'K':
                        revenue_num *= 1000
                    
                    # Accept both numeric years (2023) and Year X (1, 2, 3)
                    if year.isdigit():
                        year_int = int(year)
                        if (2000 <= year_int <= 2100) or (1 <= year_int <= 20):
                            if revenue_num > 0:
                                revenue_data.append({
                                    "year": year,
                                    "revenue": int(revenue_num)
                                })
                except (ValueError, IndexError) as e:
                    continue
        
        # Sort by year and remove duplicates
        if revenue_data:
            # Sort by year - handle both numeric and "Year X" formats
            def sort_key(item):
                year = item['year']
                if year.isdigit():
                    year_int = int(year)
                    # If it's a small number (1-20), treat as Year X
                    if year_int <= 20:
                        return (0, year_int)
                    # If it's a large number (2000+), treat as actual year
                    return (1, year_int)
                return (2, 0)
            
            revenue_data = sorted(revenue_data, key=sort_key)
            
            # Remove duplicates (keep first occurrence)
            seen_years = set()
            unique_data = []
            for item in revenue_data:
                if item['year'] not in seen_years:
                    seen_years.add(item['year'])
                    unique_data.append(item)
            revenue_data = unique_data
        
        return revenue_data
    
    def _add_estimated_metrics(self, metrics: Dict, stage: str = None, industry: Optional[str] = None) -> Dict:
        """Add estimated metrics when none found, based on stage and industry"""
        print(f"Estimation called - Stage: {stage}, Industry: {industry}, Current metrics: {metrics}")
        
        # Only add estimates if no revenue was extracted
        if not metrics.get('revenue') and not metrics.get('arr') and not metrics.get('mrr'):
            # Default estimates based on stage
            stage_lower = (stage or '').lower()
            print(f"Adding estimates for stage: {stage_lower}")
            
            if 'seed' in stage_lower or 'pre-seed' in stage_lower:
                metrics['revenue'] = '$500K'  # Seed stage typically $100K-$1M
                metrics['growth'] = '100%'
            elif 'series a' in stage_lower or 'seriesa' in stage_lower:
                metrics['revenue'] = '$2M'  # Series A typically $1M-$5M
                metrics['growth'] = '80%'
            elif 'series b' in stage_lower or 'seriesb' in stage_lower:
                metrics['revenue'] = '$10M'  # Series B typically $5M-$20M
                metrics['growth'] = '60%'
            elif 'series c' in stage_lower or 'seriesc' in stage_lower:
                metrics['revenue'] = '$25M'  # Series C typically $20M-$50M
                metrics['growth'] = '40%'
            elif 'growth' in stage_lower:
                metrics['revenue'] = '$5M'  # Growth stage typically $2M-$10M
                metrics['growth'] = '70%'
            else:
                # Default/unknown stage - use conservative estimate
                metrics['revenue'] = '$1M'
                metrics['growth'] = '50%'
                metrics['_estimated'] = True  # Mark as estimated
        
        # Add estimated growth rate if not found but revenue exists
        if not metrics.get('growth') and not metrics.get('growth_rate') and metrics.get('revenue'):
            metrics['growth'] = '50%'  # Default growth estimate
            metrics['_estimated'] = True
        
        return metrics
    
    def _extract_founders(self, text: str) -> List[str]:
        """Extract founder names from pitch deck"""
        founders = []
        text_lower = text.lower()
        
        # Look for founder sections
        founder_patterns = [
            r'founder[s]?\s*[:\-]\s*([^\n]{3,50})',
            r'team\s*[:\-]\s*([^\n]{3,50})',
            r'ceo\s*[:\-]\s*([^\n]{3,50})',
            r'co[-\s]?founder[s]?\s*[:\-]\s*([^\n]{3,50})',
        ]
        
        for pattern in founder_patterns:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                # Clean up the match
                name = match.strip()
                if len(name) > 2 and len(name) < 100:
                    founders.append(name.title())
        
        return founders[:5]  # Limit to 5 founders
    
    def _extract_team_size(self, text: str) -> Optional[int]:
        """Extract team size from pitch deck"""
        patterns = [
            r'(\d+)\s*(?:person|people|employee|team)\s*(?:team)?',
            r'team\s*(?:of\s*)?(\d+)',
            r'(\d+)\s*employees?',
            r'(\d+)\s*team\s*members?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower())
            if match:
                size = int(match.group(1))
                if 1 <= size <= 10000:  # Reasonable range
                    return size
        return None
    
    def _extract_industry(self, text: str) -> str:
        """Extract industry from text"""
        text_lower = text.lower()
        
        # Industry patterns
        industry_patterns = {
            'fintech': ['fintech', 'financial technology', 'payments', 'banking', 'finance'],
            'healthcare': ['healthcare', 'health', 'medical', 'pharma', 'biotech'],
            'saas': ['saas', 'software as a service', 'software', 'platform'],
            'ecommerce': ['ecommerce', 'e-commerce', 'retail', 'marketplace', 'shopping'],
            'ai/ml': ['artificial intelligence', 'machine learning', 'ai', 'ml', 'deep learning', 'ai co-pilot', 'vertical ai'],
            'edtech': ['edtech', 'education', 'learning', 'teaching', 'online education'],
            'fintech': ['fintech', 'financial technology', 'payments', 'banking'],
            'agritech': ['agritech', 'agriculture', 'farming', 'agri'],
            'mobility': ['mobility', 'transportation', 'logistics', 'delivery', 'electric vehicle', 'ev'],
            'b2b': ['b2b', 'business to business'],
            'consumer': ['b2c', 'consumer', 'direct to consumer'],
            'manufacturing': ['manufacturing', 'factory', 'production'],
            'energy': ['energy', 'renewable', 'solar', 'wind', 'clean energy'],
            'hr tech': ['hr', 'hiring', 'recruiting', 'recruitment', 'talent', 'workforce', 'human resources'],
        }
        
        for industry, keywords in industry_patterns.items():
            for keyword in keywords:
                if keyword in text_lower:
                    return industry
        
        return None
    
    def _extract_funding_stage(self, text: str) -> Optional[str]:
        """Extract funding stage from pitch deck"""
        stages = [
            'pre-seed', 'preseed', 'angel', 'seed',
            'series a', 'series b', 'series c', 'series d',
            'early stage', 'growth stage', 'late stage'
        ]
        
        text_lower = text.lower()
        for stage in stages:
            if stage in text_lower:
                if stage in ['preseed', 'pre-seed']:
                    return 'Pre-seed'
                return stage
        
        # Infer stage from context if explicit stage not found
        # Look for indicators of early stage
        early_indicators = [
            'prototype', 'mvp', 'minimum viable product',
            'beta', 'pilot', 'launching', 'just launched',
            'pre-revenue', 'pre revenue', 'seeking seed',
            'raising seed', 'seed round', 'pre-series'
        ]
        
        growth_indicators = [
            'series a', 'series b', 'scaling', 'expanding',
            'growing', 'traction', 'customers', 'users',
            'revenue', 'arr', 'mrr'
        ]
        
        early_count = sum(1 for indicator in early_indicators if indicator in text_lower)
        growth_count = sum(1 for indicator in growth_indicators if indicator in text_lower)
        
        if early_count > growth_count:
            return 'early stage'
        elif growth_count > early_count:
            return 'growth stage'
        
        return None
    
    def _extract_company_name(self, text: str, file_name: str = "") -> str:
        """Extract company name from pitch deck text and filename"""
        text_lower = text.lower()
        
        # Try to extract from filename first (often most reliable)
        if file_name:
            # Remove extension and normalize separators
            clean_name = file_name.replace('.pdf', '').replace('_', ' ').replace('-', ' ').strip()
            
            # Split into words and remove common suffixes
            words = clean_name.split()
            suffixes_lower = ['pitch', 'deck', 'pitchdeck', 'presentation', 'final', 'draft']
            
            # Find the first suffix word and keep only words before it
            cut_index = len(words)
            for i, word in enumerate(words):
                word_lower = word.lower()
                # Check if word is a suffix (strip any trailing numbers)
                word_base = re.sub(r'\d+$', '', word_lower)
                if word_base in suffixes_lower:
                    cut_index = i
                    break
                # Check for v1, v2 patterns
                if re.match(r'^v\d+', word_lower):
                    cut_index = i
                    break
                # Check for date patterns (8 digits like 20260417)
                if re.match(r'^\d{8}$', word):
                    cut_index = i
                    break
            
            # Reconstruct name with only words before suffix
            clean_name = ' '.join(words[:cut_index]).strip()
            
            # If we have a reasonable name from filename, use it
            if len(clean_name) > 2 and len(clean_name) < 50:
                return clean_name
        
        # Common patterns in pitch decks
        patterns = [
            # "Company Name - Pitch Deck" or "Company Name | Pitch Deck"
            r'^([^\n\-|–—]+)\s*[\-|–—|]\s*(?:pitch\s*deck|presentation|deck)',
            # "About Company Name" section
            r'about\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s|$|\.|:)',
            # "Company Name is a..." in first paragraph
            r'^([A-Z][A-Za-z0-9\s&]+?)\s+is\s+a\s+(?:\w+\s+)?(?:company|startup|platform|solution|service)',
            # Title case company names on their own line (often logo/header)
            r'\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s*\n',
            # "Welcome to Company Name"
            r'welcome\s+to\s+([A-Z][A-Za-z0-9\s&]+?)(?:\s|$|!|\.)',
            # "Meet the Team at Company Name"
            r'(?:meet\s+the\s+team|team)\s+(?:at\s+|of\s+)?([A-Z][A-Za-z0-9\s&]+?)(?:\s|$|\.)',
            # Domain pattern - extract from website mentions
            r'(?:www\.|https?://)?([a-z0-9\-]+)\.(?:com|io|ai|co|app)',
        ]
        
        # Get first 2000 chars (usually title slide and intro)
        first_section = text[:2000]
        
        for pattern in patterns:
            match = re.search(pattern, first_section, re.IGNORECASE | re.MULTILINE)
            if match:
                name = match.group(1).strip()
                # Clean up the name
                name = re.sub(r'\s+', ' ', name)  # normalize spaces
                # Validate: should be 2-40 chars, not common words
                common_words = ['the', 'and', 'for', 'our', 'this', 'we', 'us', 'your', 'about', 'meet', 'team', 'welcome']
                if 2 <= len(name) <= 40 and name.lower() not in common_words:
                    return name
        
        # Fallback: look for capitalized words that might be a company name
        # in the first 500 chars
        lines = text[:500].split('\n')
        for line in lines:
            line = line.strip()
            # Look for short title-case lines (often company names)
            if 2 <= len(line) <= 35 and line[0].isupper():
                # Check if it's all caps or title case
                words = line.split()
                if len(words) >= 1 and len(words) <= 4:
                    # Filter out lines that are mostly numbers or symbols
                    if re.match(r'^[A-Za-z0-9\s&\.]+$', line):
                        # Exclude common non-company lines
                        exclude = ['confidential', 'proprietary', 'slide', 'page', 'agenda', 'outline', 'contents']
                        if not any(exc in line.lower() for exc in exclude):
                            return line
        
        return None
    
    def _generate_summary(self, text: str, metrics: Dict) -> str:
        """Generate a brief summary of the pitch deck"""
        # Get first few sentences
        sentences = text.split('.')[:3]
        summary = '. '.join(s.strip() for s in sentences if len(s.strip()) > 20)
        
        # Add metrics info
        metric_parts = []
        if metrics.get('revenue'):
            metric_parts.append(f"Revenue: {metrics['revenue']}")
        if metrics.get('growth'):
            metric_parts.append(f"Growth: {metrics['growth']}")
        if metrics.get('users'):
            metric_parts.append(f"Users: {metrics['users']}")
        
        if metric_parts:
            summary += f" Key metrics: {', '.join(metric_parts)}."
        
        return summary[:500]  # Limit length
    
    def _generate_ai_analysis(self, extracted: Dict, company_name: str) -> str:
        """Generate investment analysis using Ollama with strict VC analyst prompt"""
        if not OLLAMA_AVAILABLE:
            print("Ollama not available, using fallback analysis")
            return self._generate_fallback_analysis(extracted, company_name)
        
        try:
            model = os.getenv("OLLAMA_MODEL", "llama3")
            print(f"Using Ollama model: {model}")
            
            # Build structured context from extracted data
            key_metrics = extracted.get('key_metrics', {})
            chunks = extracted.get('chunks', [])
            
            # Get financial chunks for richer context
            financial_chunks = [c for c in chunks if c.get('type') == 'financials']
            team_chunks = [c for c in chunks if c.get('type') == 'team']
            market_chunks = [c for c in chunks if c.get('type') == 'market']
            product_chunks = [c for c in chunks if c.get('type') == 'product']
            
            # Format revenue trajectory
            revenue_data = extracted.get('revenue_data', [])
            revenue_text = "No revenue trajectory data available"
            if revenue_data:
                revenue_lines = [f"- {r.get('year', 'N/A')}: ${r.get('revenue', 0):,.0f}" for r in revenue_data]
                revenue_text = "\n".join(revenue_lines)
            
            # Build structured context
            context = {
                "company_name": company_name,
                "industry": extracted.get('industry', 'Unknown'),
                "stage": extracted.get('stage', 'Unknown'),
                "founders": extracted.get('founders', []),
                "team_size": extracted.get('team_size'),
                "revenue": key_metrics.get('revenue', 'Unknown'),
                "growth": key_metrics.get('growth', 'Unknown'),
                "users": key_metrics.get('users', 'Unknown'),
                "tam": key_metrics.get('tam', 'Unknown'),
                "raising": key_metrics.get('raising', 'Unknown'),
                "valuation": key_metrics.get('valuation', 'Unknown'),
                "runway": key_metrics.get('runway', 'Unknown'),
                "revenue_trajectory": revenue_text,
                "financial_excerpts": [c.get('normalized_text', c.get('text', ''))[:300] for c in financial_chunks[:2]],
                "team_excerpts": [c.get('text', '')[:300] for c in team_chunks[:2]],
                "market_excerpts": [c.get('text', '')[:300] for c in market_chunks[:2]],
                "product_excerpts": [c.get('text', '')[:300] for c in product_chunks[:2]]
            }
            
            prompt = f"""You are a venture capital analyst at a top-tier firm. You must be precise, skeptical, and data-driven.

STRICT INSTRUCTIONS:
- IGNORE inconsistent or conflicting numbers - flag them explicitly
- PRIORITIZE latest year data (2025-2026) over historical projections
- If data is unclear, say "DATA INCONSISTENCY DETECTED" and explain why
- Do NOT make optimistic assumptions - be conservative in projections
- Flag any metrics that seem unrealistic for the stated stage

COMPANY CONTEXT:
```json
{json.dumps(context, indent=2, default=str)}
```

TASKS:
1. Extract accurate financial metrics (use ONLY the provided numbers)
2. Identify inconsistencies or data quality issues
3. Summarize business model based on product/market excerpts
4. Generate investor-ready insights with clear investment stance

OUTPUT FORMAT (Markdown):

### Executive Summary
2-3 sentence investment thesis. State stage, sector, and primary opportunity/risk.

### Business Model
- What they do (based on product excerpts)
- Problem being solved
- Solution differentiation

### Financial Analysis
- Current metrics (revenue, growth, burn if available)
- Revenue trajectory assessment
- Unit economics (if mentioned)
- **Data Quality Issues:** [List any inconsistencies found]

### Market & Team
- TAM assessment
- Competitive positioning
- Founding team strength

### Investment Recommendation
**STANCE: [STRONG INTEREST / CONSIDER / PASS / PROCEED WITH CAUTION]**

Key Strengths:
- [2-3 specific strengths with evidence]

Key Risks:
- [2-3 specific risks with evidence]

Next Steps (if applicable):
- [Specific questions to ask or data to verify]

Keep to 400-600 words. Be skeptical. Flag bad data."""

            response = _call_ollama(prompt, model)
            if response:
                return response
            else:
                print("Ollama returned empty response, using fallback")
                return self._generate_fallback_analysis(extracted, company_name)
            
        except Exception as e:
            print(f"Ollama API error: {e}")
            # Generate fallback analysis without Ollama
            return self._generate_fallback_analysis(extracted, company_name)
    
    def _generate_email_draft(self, extracted: Dict, company_name: str) -> str:
        """Generate outreach email draft using Claude AI with structured context"""
        if not ANTHROPIC_AVAILABLE:
            return "Email draft not available. Claude API not configured."
        
        try:
            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            
            # Build structured context - this is key for personalized emails
            key_metrics = extracted.get('key_metrics', {})
            chunks = extracted.get('chunks', [])
            
            # Extract specific insights for personalization
            financial_chunks = [c for c in chunks if c.get('type') == 'financials']
            product_chunks = [c for c in chunks if c.get('type') == 'product']
            market_chunks = [c for c in chunks if c.get('type') == 'market']
            
            # Get specific highlight from chunks
            highlight_text = ""
            if financial_chunks:
                highlight_text = financial_chunks[0].get('normalized_text', financial_chunks[0].get('text', ''))[:200]
            elif product_chunks:
                highlight_text = product_chunks[0].get('text', '')[:200]
            
            # Build structured context
            context = {
                "company_name": company_name,
                "industry": extracted.get('industry', 'Technology'),
                "stage": extracted.get('stage', 'Early stage'),
                "founders": extracted.get('founders', [])[:3],  # Top 3 founders
                "revenue": key_metrics.get('revenue'),
                "growth": key_metrics.get('growth'),
                "users": key_metrics.get('users'),
                "tam": key_metrics.get('tam'),
                "raising": key_metrics.get('raising'),
                "key_highlight": highlight_text,
                "financial_excerpts": [c.get('normalized_text', c.get('text', ''))[:250] for c in financial_chunks[:1]],
                "product_excerpts": [c.get('text', '')[:250] for c in product_chunks[:1]]
            }
            
            prompt = f"""You are a venture capitalist writing a personalized outreach email.

STRICT INSTRUCTIONS:
- Use ONLY the data provided below - do not invent metrics or claims
- Reference 1-2 SPECIFIC data points that are actually in the context
- If revenue or growth is impressive, mention it specifically
- If product/market fit is evident from excerpts, reference that
- NEVER use generic phrases like "I'm intrigued by your vision" without citing WHY
- Keep to 150-200 words
- Professional but conversational tone

COMPANY DATA (use ONLY this data):
```json
{json.dumps(context, indent=2, default=str)}
```

Write an email with this structure:

Subject: [Specific reference to their business/sector] - [Firm Name]

Hi [Founder names if available, otherwise "Team"],

[Opening: One sentence showing you reviewed their pitch deck - cite SPECIFIC data point]

[Body: One paragraph with 2-3 specific observations from the data above]

[Ask: Propose 30-min call with calendar link placeholder]

[Signature: Professional but warm]

Rules:
1. If revenue is >$1M or growth >50%, mention as impressive traction
2. If TAM is large (>$1B), mention market opportunity
3. If raising amount is specified, acknowledge their round
4. If team has notable backgrounds, reference that
5. Cite specific product/market details from excerpts
6. Do NOT use vague/generic language - every sentence should reference actual data

Output just the email subject and body."""

            response = client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=800,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Claude API error: {e}")
            # Generate fallback email without Claude
            return self._generate_fallback_email(extracted, company_name)
    
    def _generate_fallback_analysis(self, extracted: Dict, company_name: str) -> str:
        """Generate basic investment analysis without AI (fallback)"""
        metrics = extracted.get('key_metrics', {})
        founders = extracted.get('founders', [])
        industry = extracted.get('industry') or 'Unknown'
        stage = extracted.get('stage') or 'Unknown'
        
        # Safely handle None values
        stage_lower = stage.lower() if stage else 'unknown'
        
        analysis = f"""## Investment Analysis: {company_name}

### Executive Summary
{company_name} is a {stage_lower} stage company operating in the {industry} sector. The pitch deck presents a business opportunity that requires further evaluation.

### Business Overview
The company is developing a solution in the {industry} space. Based on the extracted information, they are positioning themselves to address market needs in this sector.

### Key Metrics
"""
        if metrics:
            for key, value in metrics.items():
                analysis += f"- **{key.title()}:** {value}\n"
        else:
            analysis += "- No specific metrics extracted from the pitch deck.\n"
        
        # Add revenue trajectory if available
        revenue_data = extracted.get('revenue_data', [])
        if revenue_data:
            analysis += "\n### Revenue Trajectory (from Graphs)\n"
            analysis += "| Year | Revenue |\n|------|---------|\n"
            for r in revenue_data:
                year = r.get('year', 'N/A')
                rev = r.get('revenue', 0)
                # Format revenue with appropriate unit
                if rev >= 1000000000:
                    rev_formatted = f"${rev/1000000000:.1f}B"
                elif rev >= 1000000:
                    rev_formatted = f"${rev/1000000:.1f}M"
                elif rev >= 1000:
                    rev_formatted = f"${rev/1000:.0f}K"
                else:
                    rev_formatted = f"${rev:,.0f}"
                analysis += f"| {year} | {rev_formatted} |\n"
            analysis += "\n*Revenue data extracted from pitch deck graphs. See visualization above.*\n"
        
        analysis += f"""
### Team Assessment
"""
        if founders:
            analysis += "**Founding Team:**\n"
            for founder in founders:
                analysis += f"- {founder}\n"
        else:
            analysis += "Founding team information not clearly identified in the pitch deck.\n"
        
        # Determine stage description safely
        early_stages = ['pre-seed', 'seed', 'preseed']
        stage_indicator = 'early opportunity' if stage_lower in early_stages else 'proven traction'
        
        analysis += f"""
### Investment Considerations

**Strengths:**
- Operating in the {industry} sector
- {stage} stage indicates {stage_indicator}
- Has a founding team in place

**Areas for Due Diligence:**
- Detailed financial metrics require verification
- Market size and competitive positioning need assessment
- Team background and track record to be validated
- Unit economics and path to profitability to be analyzed

### Recommendation
**Status: CONSIDER** ⚠️

This opportunity merits further investigation. Schedule a call with the founding team to validate key assumptions and dig deeper into the business model, market traction, and financial projections.

---
*Note: This analysis was generated using extracted pitch deck data. For a comprehensive AI-powered analysis, Claude API configuration is required.*
"""
        return analysis
    
    def _generate_fallback_email(self, extracted: Dict, company_name: str) -> str:
        """Generate basic outreach email without AI (fallback)"""
        industry = extracted.get('industry') or 'your industry'
        stage = extracted.get('stage') or 'early stage'
        metrics = extracted.get('key_metrics', {})
        
        # Get top metric for mention
        top_metric = None
        if metrics:
            priority_keys = ['revenue', 'growth', 'users', 'tam', 'raising', 'runway']
            for key in priority_keys:
                if key in metrics:
                    top_metric = f"{key.title()}: {metrics[key]}"
                    break
            if not top_metric:
                top_metric = f"{list(metrics.keys())[0].title()}: {list(metrics.values())[0]}"
        
        email = f"""Subject: Investment Opportunity - {company_name}

Hi {company_name} Team,

I hope this email finds you well. My name is [Your Name], and I'm a venture capitalist at [Firm Name]. I came across your pitch deck and wanted to reach out personally.

I'm particularly interested in learning more about your work in the {industry} space. {f"The {top_metric} metric caught my attention as it suggests significant traction." if top_metric else "Your approach to addressing market needs appears compelling."}

Given that you're at the {stage} stage, I believe there could be a strong fit with our investment thesis. We'd love to learn more about:
- What inspired you to start this company
- How you currently acquire customers and what’s working best
- Your biggest challenge right now and how we might help
- What a successful partnership with our firm would look like to you

Would you be available for a 30-minute call next week to discuss the opportunity in more detail? I'm flexible with timing and happy to work around your schedule.

Looking forward to hearing from you.

Best regards,

[Your Name]
[Title]
[Firm Name]
[Phone] | [Email]
"""
        return email
    
    def create_pitch_deck(self, 
                         file_content: bytes,
                         file_name: str,
                         company_name: str,
                         user_id: int = 1,
                         additional_metadata: Dict = None) -> PitchDeck:
        """Create a new pitch deck entry with full extraction"""
        db = next(get_db())
        
        try:
            # Save PDF file
            file_path = self.save_pdf(file_content, file_name, company_name)
            file_size = len(file_content)
            
            # Extract content
            extracted = self.extract_pdf_text(file_path)
            
            # Extract revenue trajectory from graphs using multimodal analysis
            revenue_trajectory = []
            if MULTIMODAL_AVAILABLE:
                try:
                    print(f"Extracting revenue trajectory from graphs for {company_name}...")
                    multimodal_data = multimodal_service.process_pdf_multimodal(file_path, company_name)
                    
                    # Collect all revenue trajectory data from all images
                    for img_data in multimodal_data.get("image_analysis", []):
                        financial_data = img_data.get("financial_data", {})
                        img_revenue_data = financial_data.get("revenue_trajectory", [])
                        if img_revenue_data:
                            revenue_trajectory.extend(img_revenue_data)
                    
                    # Remove duplicates and sort by year
                    if revenue_trajectory:
                        seen_years = set()
                        unique_trajectory = []
                        for item in revenue_trajectory:
                            if item['year'] not in seen_years:
                                seen_years.add(item['year'])
                                unique_trajectory.append(item)
                        revenue_trajectory = sorted(unique_trajectory, key=lambda x: int(x['year']))
                        print(f"Extracted revenue trajectory: {revenue_trajectory}")
                    else:
                        print("No revenue trajectory data extracted from graphs")
                except Exception as e:
                    print(f"Error extracting revenue trajectory from graphs: {e}")
            else:
                print("Multimodal service not available, skipping graph extraction")
            
            # If no graph data, try to extract from text
            if not revenue_trajectory and extracted.get('text'):
                print("Attempting to extract revenue trajectory from text...")
                revenue_trajectory = self._extract_revenue_from_text(extracted.get('text', ''))
                if revenue_trajectory:
                    print(f"Extracted revenue trajectory from text: {revenue_trajectory}")
            
            # Merge with additional metadata
            if additional_metadata:
                if 'industry' in additional_metadata:
                    extracted['industry'] = additional_metadata.get('industry')
                if 'stage' in additional_metadata:
                    extracted['stage'] = additional_metadata.get('stage')
            
            # Generate AI analysis and email draft
            print(f"Generating AI analysis for {company_name}...")
            analysis = self._generate_ai_analysis(extracted, company_name)
            
            print(f"Generating email draft for {company_name}...")
            email_draft = self._generate_email_draft(extracted, company_name)
            
            # Create database entry
            pitch_deck = PitchDeck(
                user_id=user_id,
                company_name=company_name,
                company_website=additional_metadata.get('website') if additional_metadata else None,
                industry=extracted.get('industry'),
                stage=extracted.get('stage'),
                location=additional_metadata.get('location') if additional_metadata else None,
                funding_stage=extracted.get('stage'),
                funding_amount=extracted['key_metrics'].get('raising'),
                valuation=extracted['key_metrics'].get('valuation'),
                file_name=file_name,
                file_path=file_path,
                file_size=file_size,
                pdf_pages=extracted.get('pages'),
                extracted_text=extracted.get('text', '')[:10000],  # Limit storage
                summary=extracted.get('summary', ''),
                key_metrics=extracted.get('key_metrics', {}),
                revenue_data=revenue_trajectory,  # Store extracted revenue trajectory from graphs
                founders=extracted.get('founders', []),
                team_size=extracted.get('team_size'),
                analysis=analysis,  # AI-generated analysis
                email_draft=email_draft,  # AI-generated email draft
                status="new",
                priority=additional_metadata.get('priority', 'medium') if additional_metadata else 'medium',
                tags=additional_metadata.get('tags', []) if additional_metadata else [],
                notes=additional_metadata.get('notes') if additional_metadata else None
            )
            
            db.add(pitch_deck)
            db.commit()
            db.refresh(pitch_deck)
            
            return pitch_deck
            
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def update_status(self, pitch_deck_id: int, status: str, notes: str = None, rating: float = None):
        """Update pitch deck review status"""
        db = next(get_db())
        
        try:
            pitch_deck = db.query(PitchDeck).filter(PitchDeck.id == pitch_deck_id).first()
            if not pitch_deck:
                return None
            
            pitch_deck.status = status
            if notes:
                pitch_deck.notes = notes
            if rating is not None:
                pitch_deck.rating = rating
            pitch_deck.reviewed_at = datetime.utcnow()
            
            db.commit()
            return pitch_deck
            
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()
    
    def get_pitch_deck_file(self, pitch_deck_id: int) -> Optional[bytes]:
        """Get PDF file content"""
        db = next(get_db())
        
        try:
            pitch_deck = db.query(PitchDeck).filter(PitchDeck.id == pitch_deck_id).first()
            if not pitch_deck or not os.path.exists(pitch_deck.file_path):
                return None
            
            # Update last viewed
            pitch_deck.last_viewed_at = datetime.utcnow()
            db.commit()
            
            with open(pitch_deck.file_path, 'rb') as f:
                return f.read()
                
        except Exception as e:
            print(f"Error reading pitch deck file: {e}")
            return None
        finally:
            db.close()
    
    def search_pitch_decks(self, query: str = None, filters: Dict = None) -> List[PitchDeck]:
        """Search pitch decks with filters"""
        db = next(get_db())
        
        try:
            q = db.query(PitchDeck)
            
            if query:
                query_lower = f"%{query.lower()}%"
                q = q.filter(
                    (PitchDeck.company_name.ilike(query_lower)) |
                    (PitchDeck.industry.ilike(query_lower)) |
                    (PitchDeck.extracted_text.ilike(query_lower)) |
                    (PitchDeck.summary.ilike(query_lower))
                )
            
            if filters:
                if filters.get('status'):
                    q = q.filter(PitchDeck.status == filters['status'])
                if filters.get('stage'):
                    q = q.filter(PitchDeck.stage == filters['stage'])
                if filters.get('industry'):
                    q = q.filter(PitchDeck.industry == filters['industry'])
                if filters.get('priority'):
                    q = q.filter(PitchDeck.priority == filters['priority'])
            
            return q.order_by(PitchDeck.uploaded_at.desc()).all()
            
        finally:
            db.close()
    
    def get_stats(self) -> Dict:
        """Get pitch deck statistics"""
        db = next(get_db())
        
        try:
            total = db.query(PitchDeck).count()
            
            by_status = {}
            for status in ['new', 'reviewed', 'interested', 'passed', 'funded']:
                count = db.query(PitchDeck).filter(PitchDeck.status == status).count()
                if count > 0:
                    by_status[status] = count
            
            by_stage = {}
            for stage in ['Pre-seed', 'Seed', 'Series A', 'Series B', 'Series C+']:
                count = db.query(PitchDeck).filter(PitchDeck.stage == stage).count()
                if count > 0:
                    by_stage[stage] = count
            
            return {
                'total': total,
                'by_status': by_status,
                'by_stage': by_stage
            }
            
        finally:
            db.close()


# Singleton instance
pitch_deck_service = PitchDeckService()
