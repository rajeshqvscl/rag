"""
Migration: Re-process existing drafts with improved extraction logic
Updates industry, stage, and revenue/market_size fields for all existing drafts
"""
import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config.database import get_db
from app.models.database import Draft

def extract_industry(text):
    """Extract industry from text"""
    if not text:
        return None
    text_lower = text.lower()
    
    industry_patterns = {
        'hr tech': ['hr', 'hiring', 'recruiting', 'recruitment', 'talent', 'workforce', 'human resources'],
        'ai/ml': ['artificial intelligence', 'machine learning', 'ai', 'ml', 'deep learning', 'ai co-pilot', 'vertical ai'],
        'fintech': ['fintech', 'financial technology', 'payments', 'banking', 'finance'],
        'healthcare': ['healthcare', 'health', 'medical', 'pharma', 'biotech'],
        'saas': ['saas', 'software as a service', 'software', 'platform'],
        'ecommerce': ['ecommerce', 'e-commerce', 'retail', 'marketplace', 'shopping'],
        'agritech': ['agritech', 'agriculture', 'farming', 'agri'],
        'mobility': ['mobility', 'transportation', 'logistics', 'delivery', 'electric vehicle', 'ev'],
    }
    
    for industry, keywords in industry_patterns.items():
        for keyword in keywords:
            if keyword in text_lower:
                return industry
    return None

def extract_stage(text):
    """Extract stage from text"""
    if not text:
        return None
    text_lower = text.lower()
    stages = [
        'pre-seed', 'preseed', 'angel', 'seed',
        'series a', 'series b', 'series c', 'series d',
        'early stage', 'growth stage', 'late stage'
    ]
    
    for stage in stages:
        if stage in text_lower:
            if stage in ['preseed', 'pre-seed']:
                return 'Pre-seed'
            return stage
    
    # Infer stage from context if explicit stage not found
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

def extract_revenue_from_analysis(analysis):
    """Extract revenue or market size from analysis text"""
    if not analysis:
        return None
    
    text_lower = analysis.lower()
    
    # First try to extract actual revenue
    revenue_patterns = [
        r'revenue[:\s-]*(?:of\s*|is\s*|was\s*)?(\$[\d,.]+\s*[MBK]?)',
        r'(\$[\d,.]+\s*[MBK]?)\s*(?:in\s*)?(?:annual\s*)?revenue',
        r'annual\s*revenue[:\s-]*(\$[\d,.]+\s*[MBK]?)',
        r'ar[rk]\s*(?:of\s*|is\s*)?(\$[\d,.]+\s*[MBK]?)',
        r'(\$[\d,.]+\s*[MBK]?)\s*arr',
        r'(\$[\d,.]+\s*[MBK]?)\s*mrr',
    ]
    
    for pattern in revenue_patterns:
        match = re.search(pattern, text_lower)
        if match:
            revenue_str = match.group(1).strip()
            # Validate revenue - reject very small values
            rev_match = re.search(r'\$?([\d,.]+)\s*([MBK]?)', revenue_str, re.IGNORECASE)
            if rev_match:
                try:
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
                        return revenue_str
                    else:
                        print(f"  Rejected unrealistic revenue value: {revenue_str}")
                except:
                    pass
    
    # If no company revenue found, try market size as proxy
    large_number_patterns = [
        r'[\$₹]?([\d,.]+(?:\.\d+)?)\s*(?:lakh\s*crore|crore|billion|million)',
        r'[\$₹]?([\d,.]+(?:\.\d+)?)\s*cr',
    ]
    for pattern in large_number_patterns:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            try:
                num = float(match.replace(',', ''))
                if num >= 1:
                    if 'lakh crore' in text_lower:
                        return f"${num} Lakh Crore (market size)"
                    elif 'crore' in text_lower:
                        return f"${num} Crore (market size)"
                    elif 'billion' in text_lower:
                        return f"${num}B (market size)"
                    elif 'million' in text_lower:
                        return f"${num}M (market size)"
            except:
                continue
    
    return None

def reprocess_drafts():
    """Re-process all existing drafts with improved extraction logic"""
    db = next(get_db())
    
    try:
        drafts = db.query(Draft).all()
        total_count = len(drafts)
        updated_count = 0
        
        print(f"Processing {total_count} drafts...")
        
        for draft in drafts:
            print(f"\nProcessing: {draft.company}")
            
            # Extract from analysis text
            analysis = draft.analysis or ""
            
            # Extract industry
            industry = extract_industry(analysis)
            if industry:
                print(f"  Industry: {industry}")
                # Update key_metrics with industry
                if not draft.analysis or 'Unknown sector' in draft.analysis:
                    # Replace "Unknown sector" with extracted industry
                    draft.analysis = draft.analysis.replace('Unknown sector', industry.capitalize())
                    updated_count += 1
            
            # Extract stage
            stage = extract_stage(analysis)
            if stage:
                print(f"  Stage: {stage}")
                # Update key_metrics with stage
                if not draft.analysis or 'unknown stage' in draft.analysis.lower():
                    # Replace "unknown stage" with extracted stage
                    draft.analysis = draft.analysis.replace('unknown stage', stage)
                    updated_count += 1
            
            # Extract revenue/market size
            revenue = extract_revenue_from_analysis(analysis)
            if revenue:
                print(f"  Revenue/Market Size: {revenue}")
                # Update key_metrics with revenue
                if not draft.analysis or 'Revenue: $2' in draft.analysis:
                    # Replace "$2" with extracted revenue
                    draft.analysis = draft.analysis.replace('Revenue: $2', f'Revenue: {revenue}')
                    updated_count += 1
        
        db.commit()
        
        print(f"\n{'='*60}")
        print(f"Re-processing Complete:")
        print(f"  Total drafts: {total_count}")
        print(f"  Updated: {updated_count}")
        print(f"{'='*60}")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    reprocess_drafts()
