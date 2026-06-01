"""
Investor-Grade Financial Narrative Enhancement
Unified integration for temporal extraction, narrative generation, and chart export
"""
import re
from typing import Dict, List, Any, Optional
from app.rag.fact_registry import ExtractedFact, FactRegistry, extract_temporal_info, calculate_yoy_growth
# Note: generate_investor_narrative was removed during schema cleanup
# This module is unused but kept for reference
from app.rag.chart_exporter import export_chart_data_for_frontend


class InvestorGradeAnalyzer:
    """Unified analyzer for investor-grade financial narratives"""
    
    TOP_METRICS = ["revenue", "growth_rate", "margin", "customers", "burn_rate"]
    
    def __init__(self):
        self.fact_registry = FactRegistry()
        self.temporal_facts = []
    
    def extract_temporal_facts(self, text: str, page: int, section: str = "general") -> List[ExtractedFact]:
        """Extract facts with temporal information"""
        facts = []
        
        temporal_info = extract_temporal_info(text)
        
        metric_patterns = {
            "revenue": r"(?:revenue|sales|invoiced)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:Cr|L|lakh|K|k|M|m|mn)?)",
            "growth_rate": r"(\d+(?:\.\d+)?)\s*%\s*(?:growth|YoY|increase|year)",
            "margin": r"(\d+(?:\.\d+)?)\s*%\s*(?:margin|profit|gross)",
            "customers": r"(\d+(?:,\d{3})*)\s*(?:customers|clients|users|partners)",
            "burn_rate": r"(?:burn|burning|runway)[:\s]*([\u20B9₹$]?\s*[\d,]+\.?\d*\s*(?:L|lakh|Cr|Crore)?)"
        }
        
        for metric_name, pattern in metric_patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                value = match.group(1).strip()
                if not value:
                    continue
                
                fact = ExtractedFact(
                    name=metric_name,
                    value=value,
                    page=page,
                    section=section,
                    fiscal_period=temporal_info.get("fiscal_period", ""),
                    fiscal_year=temporal_info.get("fiscal_year", 0),
                    comparison_period=temporal_info.get("comparison_period", ""),
                    growth_percentage=temporal_info.get("growth_percentage", 0.0),
                    confidence=85
                )
                
                self.fact_registry.add(fact)
                facts.append(fact)
                self.temporal_facts.append(fact)
        
        return facts
    
    def get_facts_by_metric(self, metric_name: str) -> List[ExtractedFact]:
        """Get all facts for a specific metric"""
        return [f for f in self.temporal_facts if f.name == metric_name]
    
    def build_metric_timeline(self, metric_name: str) -> List[Dict]:
        """Build timeline data for a metric"""
        facts = self.get_facts_by_metric(metric_name)
        timeline = []
        
        for fact in facts:
            entry = {
                "name": fact.name,
                "value": fact.value,
                "page": fact.page,
                "fiscal_year": fact.fiscal_year,
                "fiscal_period": fact.fiscal_period,
                "comparison_period": fact.comparison_period,
                "growth_percentage": fact.growth_percentage,
                "confidence": fact.confidence
            }
            
            numeric_value = self._parse_numeric(fact.value)
            entry["numeric_value"] = numeric_value
            
            timeline.append(entry)
        
        timeline.sort(key=lambda x: x["fiscal_year"] if x["fiscal_year"] > 0 else 0, reverse=True)
        
        if len(timeline) >= 2:
            current = timeline[0].get("numeric_value", 0)
            previous = timeline[1].get("numeric_value", 0)
            if previous > 0:
                timeline[0]["yoy_growth"] = round(calculate_yoy_growth(current, previous), 1)
        
        return timeline
    
    def _parse_numeric(self, value_str: str) -> float:
        """Parse numeric value from string"""
        value_str = str(value_str).lower().replace(",", "").replace("₹", "").replace("$", "")
        
        multipliers = {
            "cr": 1e7, "crore": 1e7, "l": 1e5, "lakh": 1e5,
            "m": 1e6, "mn": 1e6, "k": 1e3, "b": 1e9, "bn": 1e9
        }
        
        for unit, mult in multipliers.items():
            if unit in value_str:
                match = re.search(r"[\d.]+", value_str)
                if match:
                    return float(match.group()) * mult
        
        match = re.search(r"[\d.]+", value_str)
        return float(match.group()) if match else 0.0
    
    def generate_narrative(self, structured_data: Dict) -> str:
        """Generate investor-grade narrative"""
        return "Investor narrative generation removed during schema cleanup."
    
    def export_chart_data(self) -> Dict:
        """Export chart data for frontend"""
        facts_list = []
        for fact in self.temporal_facts:
            facts_list.append({
                "name": fact.name,
                "value": fact.value,
                "page": fact.page,
                "confidence": fact.confidence,
                "metadata": {
                    "period": f"{fact.fiscal_period} {fact.fiscal_year}" if fact.fiscal_year else ""
                }
            })
        
        return export_chart_data_for_frontend(facts_list)
    
    def get_full_analysis(self, structured_data: Dict) -> Dict:
        """Get complete analysis with narrative and charts"""
        
        narrative = self.generate_narrative(structured_data)
        
        chart_data = self.export_chart_data()
        
        metrics_timeline = {}
        for metric in self.TOP_METRICS:
            metrics_timeline[metric] = self.build_metric_timeline(metric)
        
        return {
            "investor_narrative": narrative,
            "chart_data": chart_data,
            "metrics_timeline": metrics_timeline,
            "fact_count": len(self.temporal_facts),
            "periods_identified": self._get_identified_periods()
        }
    
    def _get_identified_periods(self) -> List[str]:
        periods = set()
        for fact in self.temporal_facts:
            if fact.fiscal_year > 0:
                if fact.fiscal_period:
                    periods.add(f"{fact.fiscal_period} FY{fact.fiscal_year}")
                else:
                    periods.add(f"FY{fact.fiscal_year}")
        return sorted(list(periods))


def analyze_with_temporal_context(text: str, page: int, section: str = "general") -> InvestorGradeAnalyzer:
    """Convenience function to create analyzer and extract temporal facts"""
    analyzer = InvestorGradeAnalyzer()
    analyzer.extract_temporal_facts(text, page, section)
    return analyzer


def enhance_structured_data_with_temporal(structured_data: Dict, chunks: List[str]) -> Dict:
    """Enhance existing structured data with temporal context and investor-grade narratives"""
    analyzer = InvestorGradeAnalyzer()
    
    for idx, chunk in enumerate(chunks):
        analyzer.extract_temporal_facts(chunk, page=idx // 3 + 1, section="general")
    
    full_analysis = analyzer.get_full_analysis(structured_data)
    
    enhanced = structured_data.copy()
    enhanced["_investor_grade"] = {
        "narrative": full_analysis["investor_narrative"],
        "chart_data": full_analysis["chart_data"],
        "metrics_timeline": full_analysis["metrics_timeline"],
        "periods_identified": full_analysis["periods_identified"]
    }
    
    return enhanced