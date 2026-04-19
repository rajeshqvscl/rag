"""
Structured Data Extractor
Forces JSON output, no guessing, no fallbacks
"""
import json
import re
import os
from typing import Dict, Any, Optional


class StructuredExtractor:
    """Extract structured data from pitch deck text using AI"""
    
    def __init__(self):
        self.anthropic_available = False
        
        # Check for Claude
        try:
            from anthropic import Anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                self.anthropic_client = Anthropic(api_key=api_key)
                self.anthropic_available = True
                print("Claude API available for structured extraction")
            else:
                print("ANTHROPIC_API_KEY not set")
        except ImportError:
            print("anthropic package not installed")
    
    def extract(self, text: str) -> Dict[str, Any]:
        """
        Extract structured metrics from pitch deck text
        
        Returns:
            Dict with revenue, growth_rate, users, market_size, stage, etc.
            Missing values are set to None (not guessed)
            
        Raises:
            Exception: If extraction fails completely
        """
        if not self.anthropic_available:
            raise Exception("Claude API not available - structured extraction requires AI model")
        
        # Truncate text if too long
        max_chars = 12000
        truncated_text = text[:max_chars]
        
        prompt = """You are a venture capital data extraction specialist. Extract structured information from this pitch deck.

PITCH DECK TEXT:
""" + truncated_text + """

EXTRACTION RULES (STRICT):
1. Extract ONLY data that is EXPLICITLY stated in the text
2. If a metric is not mentioned, return null (do NOT guess or estimate)
3. Do not infer - only extract what is directly stated
4. Return ONLY valid JSON - no explanations, no markdown code blocks

REQUIRED JSON FORMAT:
{
  "revenue": "Current revenue as stated (e.g., '$7.6M', '$500K') or null",
  "revenue_confidence": 0.0-1.0,
  "growth_rate": "Growth rate as stated (e.g., '50%', '3x YoY') or null",
  "growth_confidence": 0.0-1.0,
  "users": "User/customer count as stated (e.g., '388K', '1M') or null",
  "users_confidence": 0.0-1.0,
  "market_size": "TAM/market size as stated (e.g., '$50B', '$10M') or null",
  "market_confidence": 0.0-1.0,
  "stage": "Funding stage: 'Pre-seed', 'Seed', 'Series A', 'Series B', 'Series C' or null",
  "stage_confidence": 0.0-1.0,
  "funding_raising": "Amount raising (e.g., '$5M', '$10M Series A') or null",
  "funding_confidence": 0.0-1.0,
  "company_name": "Company name as stated or null",
  "industry": "Industry/sector or null",
  "extraction_summary": "Brief summary of what was found"
}

CONFIDENCE SCORING:
- 1.0 = Explicitly stated with clear number (e.g., "We have $7.6M ARR")
- 0.7 = Mentioned but slightly unclear (e.g., "revenue around 7 million")
- 0.5 = Implied or partial data
- 0.0 = Not found or null

Return ONLY JSON. No other text."""

        try:
            response = self.anthropic_client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=2000,
                temperature=0.1,  # Low temperature for consistency
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', result_text)
            if json_match:
                result_text = json_match.group(0)
            
            data = json.loads(result_text)
            
            # Validate required fields
            required_fields = [
                "revenue", "growth_rate", "users", "market_size",
                "stage", "funding_raising", "company_name", "industry"
            ]
            
            for field in required_fields:
                if field not in data:
                    data[field] = None
            
            print(f"[SUCCESS] Structured extraction complete:")
            print(f"  Revenue: {data.get('revenue') or 'null'}")
            print(f"  Growth: {data.get('growth_rate') or 'null'}")
            print(f"  Users: {data.get('users') or 'null'}")
            print(f"  Market: {data.get('market_size') or 'null'}")
            
            return data
            
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse extraction JSON: {e}")
        except Exception as e:
            error_text = str(e)
            if "invalid x-api-key" in error_text.lower():
                raise Exception("Anthropic authentication failed: invalid API key")
            raise Exception(error_text)
    
    def calculate_overall_confidence(self, data: Dict) -> float:
        """Calculate overall extraction confidence"""
        confidences = [
            data.get("revenue_confidence", 0),
            data.get("growth_confidence", 0),
            data.get("users_confidence", 0),
            data.get("market_confidence", 0),
            data.get("stage_confidence", 0),
            data.get("funding_confidence", 0)
        ]
        
        valid_confidences = [c for c in confidences if c > 0]
        if not valid_confidences:
            return 0.0
        
        return sum(valid_confidences) / len(valid_confidences)


# Singleton instance
structured_extractor = StructuredExtractor()
