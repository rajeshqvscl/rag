"""
Migration: Normalize revenue_data formats to use numeric years
Converts "Year X" formats to numeric years based on upload date
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.config.database import get_db
from app.models.database import Draft

def normalize_year_format(year_str, base_year=None):
    """Convert 'Year X' format to numeric year"""
    if not year_str:
        return None
    
    year_str = str(year_str).strip()
    
    # If already a 4-digit year, return as is
    if year_str.isdigit() and len(year_str) == 4:
        return year_str
    
    # If it's "Year X" format, convert to numeric year
    if "Year" in year_str:
        try:
            # Extract the number from "Year X" or "Year X (Post-Funding)"
            import re
            match = re.search(r'Year\s*(\d+)', year_str, re.IGNORECASE)
            if match:
                year_num = int(match.group(1))
                # If base_year is provided, calculate actual year
                if base_year:
                    # Year 1 = base_year, Year 2 = base_year + 1, etc.
                    actual_year = base_year + year_num - 1
                    return str(actual_year)
                else:
                    # Default to assuming Year 1 = 2024
                    actual_year = 2024 + year_num - 1
                    return str(actual_year)
        except:
            pass
    
    # If it's just a number (1-20), treat as year offset
    if year_str.isdigit():
        year_num = int(year_str)
        if 1 <= year_num <= 20:
            if base_year:
                actual_year = base_year + year_num - 1
                return str(actual_year)
            else:
                actual_year = 2024 + year_num - 1
                return str(actual_year)
    
    # Return original if can't convert
    return year_str

def normalize_revenue_data():
    """Normalize revenue_data formats for all drafts"""
    db = next(get_db())
    
    try:
        drafts = db.query(Draft).all()
        total_count = len(drafts)
        updated_count = 0
        
        print(f"Processing {total_count} drafts...")
        
        for draft in drafts:
            if not draft.revenue_data:
                print(f"  {draft.company}: No revenue_data to normalize")
                continue
            
            # Get base year from draft date
            base_year = draft.date.year if draft.date else 2024
            
            original_data = draft.revenue_data
            normalized_data = []
            
            for item in original_data:
                if not isinstance(item, dict):
                    continue
                
                year = item.get('year')
                revenue = item.get('revenue')
                
                if not year or revenue is None:
                    continue
                
                # Normalize year format
                normalized_year = normalize_year_format(year, base_year)
                
                normalized_data.append({
                    'year': normalized_year,
                    'revenue': revenue
                })
            
            # Sort by year
            def sort_key(item):
                year = item['year']
                if year.isdigit() and len(year) == 4:
                    return int(year)
                return 9999
            
            normalized_data = sorted(normalized_data, key=sort_key)
            
            # Check if data changed
            if normalized_data != original_data:
                draft.revenue_data = normalized_data
                updated_count += 1
                print(f"  {draft.company}: Normalized")
                print(f"    Before: {original_data[:2]}...")
                print(f"    After: {normalized_data[:2]}...")
            else:
                print(f"  {draft.company}: Already normalized")
        
        db.commit()
        
        print(f"\n{'='*60}")
        print(f"Normalization Complete:")
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
    normalize_revenue_data()
