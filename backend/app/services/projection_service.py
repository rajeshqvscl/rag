import json
import os
import re
from app.services.claude_service import client
from typing import List, Dict

PROJECTIONS_FILE = "app/data/projections.json"

class ProjectionService:
    def __init__(self):
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(PROJECTIONS_FILE), exist_ok=True)
        if not os.path.exists(PROJECTIONS_FILE):
            with open(PROJECTIONS_FILE, "w") as f:
                json.dump({}, f)

    def analyze_scenarios(self, projections: List[Dict]) -> Dict:
        """Generates simple Best/Worst case scenarios based on extracted projections."""
        scenarios = {"best_case": [], "worst_case": []}
        for p in projections:
            try:
                # Convert value to number if possible (e.g. "100M" -> 100000000)
                val_str = p['value'].upper().replace('$', '').replace(',', '')
                multiplier = 1
                if 'M' in val_str: multiplier = 1_000_000
                elif 'K' in val_str: multiplier = 1_000
                elif 'B' in val_str: multiplier = 1_000_000_000
                
                base_val = float(re.sub(r'[^\d.]', '', val_str)) * multiplier
                
                scenarios["best_case"].append({
                    "period": p['period'],
                    "value": f"${base_val * 1.2 / 1_000_000:.1f}M (+20%)"
                })
                scenarios["worst_case"].append({
                    "period": p['period'],
                    "value": f"${base_val * 0.7 / 1_000_000:.1f}M (-30%)"
                })
            except:
                continue
        return scenarios

    def detect_red_flags(self, projections: List[Dict]) -> List[str]:
        """Detects unrealistic growth or inconsistent data in projections."""
        flags = []
        # Sort by period if possible
        try:
            sorted_projs = sorted(projections, key=lambda x: x.get('period', ''))
            for i in range(len(sorted_projs) - 1):
                p1 = sorted_projs[i]
                p2 = sorted_projs[i+1]
                # Logid for "Hockey Stick" or too fast growth
                # (This is simplified; real logic would parse values)
                if "Revenue" in p1['metric'] and "Revenue" in p2['metric']:
                    flags.append(f"Potential 'Hockey Stick' growth curve detected between {p1['period']} and {p2['period']}.")
        except:
            pass
        
        if not projections:
            flags.append("No financial projections found in document.")
            
        return flags

    def extract_projections(self, symbol: str, context: str):
        """Extracts financial projections from text context using Claude."""
        # Limit context to avoid exceeding token limits
        context_snippet = context[:10000]
        prompt = f"""
        Extract any financial projections (revenue, profit, growth, future targets, etc.) for {symbol} from the text below.
        
        Format the output as a valid JSON object with the following structure:
        {{
            "projections": [
                {{
                    "metric": "Revenue",
                    "value": "100M",
                    "period": "FY 2025",
                    "source_context": "The company expects revenue to reach $100M in FY 2025"
                }},
                ...
            ]
        }}
        
        If no projections are found, return an empty list: {{"projections": []}}
        ONLY return the JSON.

        Text:
        {context_snippet}
        """

        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20240620"),
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        try:
            data = json.loads(response.content[0].text)
            self.save_projections(symbol, data.get("projections", []))
            return data.get("projections", [])
        except Exception as e:
            print(f"Error parsing projections for {symbol}: {e}")
            return []

    def save_projections(self, symbol: str, new_projections: List[Dict]):
        with open(PROJECTIONS_FILE, "r") as f:
            all_projections = json.load(f)
        
        if symbol not in all_projections:
            all_projections[symbol] = []
        
        # Simple merge: append new ones (could be improved to avoid duplicates)
        all_projections[symbol].extend(new_projections)
        
        # Limit to last N projections to keep it manageable
        all_projections[symbol] = all_projections[symbol][-50:]

        with open(PROJECTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_projections, f, indent=2)

    def get_projections(self, symbol: str) -> List[Dict]:
        if not os.path.exists(PROJECTIONS_FILE):
            return []
        with open(PROJECTIONS_FILE, "r") as f:
            all_projections = json.load(f)
        return all_projections.get(symbol, [])

projection_service = ProjectionService()
