"""
Graph and Chart Generation Service for Pitch Deck Reports
Generates data visualizations from extracted metrics
"""
import json
from typing import Dict, List, Optional, Any
from datetime import datetime


class GraphGenerator:
    """Generate charts and graphs for pitch deck analysis"""
    
    def __init__(self):
        self.supported_charts = [
            "revenue_trajectory",
            "growth_trend",
            "user_growth",
            "market_comparison",
            "metrics_summary"
        ]
    
    def generate_revenue_chart(self, revenue_data: List[Dict], projections: List[Dict] = None) -> Dict:
        """
        Generate revenue trajectory chart data
        
        Args:
            revenue_data: List of {year, revenue} data points
            projections: Optional future projections
            
        Returns:
            Chart configuration for frontend rendering
        """
        if not revenue_data and not projections:
            return {"status": "no_data", "message": "No revenue data available"}
        
        # Combine historical and projected data
        all_points = []
        
        for point in (revenue_data or []):
            all_points.append({
                "year": point.get("year", ""),
                "value": point.get("revenue", point.get("value", 0)),
                "type": "actual",
                "display": self._format_currency(point.get("revenue", point.get("value", 0)))
            })
        
        for point in (projections or []):
            all_points.append({
                "year": point.get("year", ""),
                "value": point.get("revenue", point.get("value", 0)),
                "type": "projected",
                "display": self._format_currency(point.get("revenue", point.get("value", 0)))
            })
        
        # Sort by year
        all_points.sort(key=lambda x: str(x["year"]))
        
        return {
            "status": "ok",
            "chart_type": "line",
            "title": "Revenue Trajectory",
            "x_label": "Year",
            "y_label": "Revenue",
            "data": all_points,
            "has_projections": bool(projections),
            "summary": self._generate_revenue_summary(all_points)
        }
    
    def generate_metrics_summary_chart(self, metrics: Dict) -> Dict:
        """
        Generate a summary chart of key metrics
        
        Args:
            metrics: Dictionary with revenue, growth, users, tam
            
        Returns:
            Chart configuration for metrics dashboard
        """
        cards = []
        
        # Revenue card
        if metrics.get("revenue"):
            cards.append({
                "metric": "Revenue",
                "value": metrics["revenue"],
                "icon": "dollar",
                "color": "green",
                "confidence": metrics.get("_revenue_confidence", 0.7)
            })
        
        # Growth card
        if metrics.get("growth"):
            cards.append({
                "metric": "Growth Rate",
                "value": metrics["growth"],
                "icon": "trending_up",
                "color": "blue",
                "confidence": metrics.get("_growth_confidence", 0.7)
            })
        
        # Users card
        if metrics.get("users"):
            cards.append({
                "metric": "Users/Customers",
                "value": metrics["users"],
                "icon": "users",
                "color": "purple",
                "confidence": metrics.get("_users_confidence", 0.7)
            })
        
        # TAM card
        if metrics.get("tam"):
            cards.append({
                "metric": "Market Size (TAM)",
                "value": metrics["tam"],
                "icon": "globe",
                "color": "orange",
                "confidence": metrics.get("_tam_confidence", 0.7)
            })
        
        # Stage card
        if metrics.get("stage"):
            cards.append({
                "metric": "Funding Stage",
                "value": metrics["stage"],
                "icon": "flag",
                "color": "indigo",
                "confidence": 0.9
            })
        
        return {
            "status": "ok" if cards else "no_data",
            "chart_type": "metrics_cards",
            "title": "Key Metrics Summary",
            "cards": cards,
            "overall_confidence": metrics.get("_confidence_score", 0.5)
        }
    
    def generate_growth_trend_chart(self, growth_data: List[Dict]) -> Dict:
        """
        Generate growth rate trend chart
        
        Args:
            growth_data: List of {period, growth_rate} data points
            
        Returns:
            Chart configuration
        """
        if not growth_data:
            return {"status": "no_data", "message": "No growth data available"}
        
        return {
            "status": "ok",
            "chart_type": "bar",
            "title": "Growth Rate Trend",
            "x_label": "Period",
            "y_label": "Growth Rate (%)",
            "data": [
                {
                    "period": d.get("period", ""),
                    "value": d.get("growth_rate", 0),
                    "display": f"{d.get('growth_rate', 0)}%"
                }
                for d in growth_data
            ]
        }
    
    def generate_market_comparison_chart(self, company_tam: str, competitor_data: List[Dict] = None) -> Dict:
        """
        Generate market size comparison chart
        
        Args:
            company_tam: Company's TAM as formatted string
            competitor_data: Optional competitor market sizes
            
        Returns:
            Chart configuration
        """
        tam_value = self._parse_currency(company_tam)
        
        if not tam_value:
            return {"status": "no_data", "message": "No market size data available"}
        
        data = [
            {
                "company": "This Company",
                "market_size": tam_value,
                "display": company_tam,
                "highlight": True
            }
        ]
        
        if competitor_data:
            for comp in competitor_data[:4]:  # Limit to 4 competitors
                comp_tam = self._parse_currency(comp.get("tam", "0"))
                if comp_tam:
                    data.append({
                        "company": comp.get("name", "Competitor"),
                        "market_size": comp_tam,
                        "display": comp.get("tam", "$0"),
                        "highlight": False
                    })
        
        return {
            "status": "ok",
            "chart_type": "bar",
            "title": "Total Addressable Market (TAM)",
            "x_label": "Company",
            "y_label": "Market Size",
            "data": data
        }
    
    def generate_full_report_charts(self, extracted_data: Dict) -> Dict:
        """
        Generate all charts for a complete report
        
        Args:
            extracted_data: Full extraction data from pitch deck
            
        Returns:
            Dictionary of all generated charts
        """
        metrics = extracted_data.get("key_metrics", {})
        revenue_trajectory = extracted_data.get("revenue_data_from_charts", [])
        structured_data = extracted_data.get("structured_data", {})
        
        charts = {}
        
        # Generate metrics summary
        charts["metrics_summary"] = self.generate_metrics_summary_chart(metrics)
        
        # Generate revenue chart
        if revenue_trajectory:
            charts["revenue_chart"] = self.generate_revenue_chart(revenue_trajectory)
        elif structured_data.get("financial_metrics", {}).get("revenue"):
            # Create single point from current revenue
            charts["revenue_chart"] = self.generate_revenue_chart([{
                "year": "Current",
                "revenue": self._parse_currency(structured_data["financial_metrics"]["revenue"])
            }])
        
        # Generate growth chart if growth data exists
        if metrics.get("growth"):
            charts["growth_chart"] = self.generate_growth_trend_chart([{
                "period": "Current",
                "growth_rate": self._parse_percentage(metrics["growth"])
            }])
        
        # Generate market comparison
        if metrics.get("tam"):
            charts["market_chart"] = self.generate_market_comparison_chart(metrics["tam"])
        
        return {
            "status": "ok",
            "generated_at": datetime.utcnow().isoformat(),
            "charts": charts,
            "total_charts": len(charts)
        }
    
    def _format_currency(self, value: float) -> str:
        """Format a number as currency"""
        if not value or value == 0:
            return "$0"
        
        if value >= 1e9:
            return f"${value/1e9:.1f}B"
        elif value >= 1e6:
            return f"${value/1e6:.1f}M"
        elif value >= 1e3:
            return f"${value/1e3:.0f}K"
        else:
            return f"${value:,.0f}"
    
    def _parse_currency(self, value_str: str) -> Optional[float]:
        """Parse currency string to float"""
        if not value_str:
            return None
        
        # Remove $ and commas
        clean = str(value_str).replace('$', '').replace(',', '').strip()
        
        # Handle suffixes
        multiplier = 1
        if clean.upper().endswith('B'):
            multiplier = 1e9
            clean = clean[:-1]
        elif clean.upper().endswith('M'):
            multiplier = 1e6
            clean = clean[:-1]
        elif clean.upper().endswith('K'):
            multiplier = 1e3
            clean = clean[:-1]
        
        try:
            return float(clean) * multiplier
        except (ValueError, TypeError):
            return None
    
    def _parse_percentage(self, value_str: str) -> float:
        """Parse percentage string to float"""
        if not value_str:
            return 0.0
        
        clean = str(value_str).replace('%', '').strip()
        try:
            return float(clean)
        except (ValueError, TypeError):
            return 0.0
    
    def _generate_revenue_summary(self, data_points: List[Dict]) -> str:
        """Generate a text summary of revenue trend"""
        if not data_points:
            return "No revenue data available"
        
        actual_points = [p for p in data_points if p.get("type") == "actual"]
        projected_points = [p for p in data_points if p.get("type") == "projected"]
        
        if not actual_points:
            return "Projected revenue only"
        
        current = actual_points[-1].get("value", 0)
        
        if len(actual_points) >= 2:
            previous = actual_points[-2].get("value", 0)
            if previous > 0:
                growth = ((current - previous) / previous) * 100
                return f"Revenue grew {growth:.0f}% to {self._format_currency(current)}"
        
        return f"Current revenue: {self._format_currency(current)}"


# Singleton instance
graph_generator = GraphGenerator()
