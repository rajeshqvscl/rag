"""
Migration: Sync revenue trajectory data from extracted text for all existing pitch decks
This extracts revenue trajectory from the already-extracted text and updates the revenue_data field
"""
import sys
import os
import re

# Add the backend directory to the Python path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, backend_dir)

from sqlalchemy.orm import Session
from app.config.database import engine, get_db
from app.models.database import PitchDeck, Draft

def extract_revenue_from_text(text: str) -> list:
    """Extract year-revenue pairs from extracted text"""
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

def sync_pitch_deck_revenue_data():
    """Extract and sync revenue trajectory data from text for all drafts"""
    db = next(get_db())
    
    try:
        # Get all drafts
        drafts = db.query(Draft).all()
        total_count = len(drafts)
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        print(f"Found {total_count} drafts to process")
        
        for idx, draft in enumerate(drafts, 1):
            print(f"\n[{idx}/{total_count}] Processing: {draft.company}")
            
            try:
                # Extract revenue trajectory from analysis text
                text = draft.analysis or ""
                if not text:
                    print(f"  ⚠ No analysis text found")
                    skipped_count += 1
                    continue
                
                print(f"  Extracting revenue trajectory from analysis text...")
                revenue_trajectory = extract_revenue_from_text(text)
                
                # Remove duplicates and sort by year
                if revenue_trajectory:
                    # Update the draft with extracted data
                    draft.revenue_data = revenue_trajectory
                    db.commit()
                    updated_count += 1
                    print(f"  ✅ Updated with {len(revenue_trajectory)} data points: {revenue_trajectory}")
                else:
                    print(f"  ℹ No revenue trajectory data found in text")
                    skipped_count += 1
                    
            except Exception as e:
                error_count += 1
                print(f"  ❌ Error: {e}")
                db.rollback()
                continue
        
        print(f"\n{'='*60}")
        print(f"Migration Complete:")
        print(f"  Total drafts: {total_count}")
        print(f"  Updated: {updated_count}")
        print(f"  Skipped (no data): {skipped_count}")
        print(f"  Errors: {error_count}")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"Fatal error during migration: {e}")
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    sync_pitch_deck_revenue_data()
