"""
Chart Data Structure Export for Frontend Visualization
Generates structured JSON data for CanvasJS/Chart.js rendering
"""
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ChartDataPoint:
    year: str
    value: float
    unit: str
    period: str = ""
    confidence: float = 0.0
    page: int = 0


@dataclass
class TrendMetrics:
    cagr: float = 0.0
    yoy_growth: List[float] = field(default_factory=list)
    latest_value: float = 0.0
    previous_value: float = 0.0


class ChartDataExporter:
    """Export structured chart data for frontend visualization"""
    
    UNIT_MAP = {
        "cr": "Cr", "crore": "Cr", "l": "Lakhs", "lakh": "Lakhs",
        "m": "Mn", "mn": "Mn", "k": "K", "b": "Bn", "bn": "Bn"
    }
    
    @staticmethod
    def _safe_parse_float(value_str: str) -> float:
        """Safely parse a cleaned number string, guarding against orphan decimals."""
        match = re.search(r"[\d.]+", value_str)
        if not match:
            return 0.0
        s = match.group()
        if s in ("", ".", "-.", "+."):
            return 0.0
        try:
            return float(s)
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def parse_value(value_str: str) -> tuple:
        value_str = str(value_str).lower().replace(",", "").replace("₹", "").replace("$", "")
        
        multipliers = {
            "cr": 1e7, "crore": 1e7, "l": 1e5, "lakh": 1e5,
            "m": 1e6, "mn": 1e6, "k": 1e3, "b": 1e9, "bn": 1e9
        }
        
        for unit, mult in multipliers.items():
            if unit in value_str:
                num = ChartDataExporter._safe_parse_float(value_str)
                if num != 0.0:
                    return num * mult, ChartDataExporter.UNIT_MAP.get(unit, "")
        
        return ChartDataExporter._safe_parse_float(value_str), ""
    
    @staticmethod
    def extract_fiscal_year(text: str) -> int:
        patterns = [
            r"(?:FY|F\.Y\.?|Fiscal\s*Year)[\s\-]*(\d{4})",
            r"(?:FY|F\.Y\.?)[\s\-]*(\d{2})(?:\s*/\s*(\d{2}))?"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                year_str = match.group(1)
                if len(year_str) == 2:
                    return int("20" + year_str) if int(year_str) < 50 else int("19" + year_str)
                elif len(year_str) == 4:
                    return int(year_str)
        return 0
    
    @classmethod
    def export_revenue_trend(cls, facts: List[Dict]) -> Dict:
        data = []
        
        for fact in facts:
            if "revenue" not in fact.get("name", "").lower() and "sales" not in fact.get("name", "").lower():
                continue
            
            value, unit = cls.parse_value(fact.get("value", ""))
            year = cls.extract_fiscal_year(fact.get("metadata", {}).get("period", ""))
            
            if year == 0:
                continue
            
            data.append({
                "year": f"FY{year}",
                "value": value,
                "unit": unit or "Cr",
                "period": "",
                "confidence": fact.get("confidence", 0),
                "page": fact.get("page", 0)
            })
        
        data.sort(key=lambda x: x["year"])
        
        if len(data) >= 2:
            latest = data[-1]["value"]
            previous = data[-2]["value"]
            yoy = ((latest - previous) / previous * 100) if previous > 0 else 0
            data[-1]["yoy_growth"] = round(yoy, 1)
        
        if len(data) >= 3:
            first_val = data[0]["value"]
            last_val = data[-1]["value"]
            years = len(data) - 1
            if first_val > 0 and years > 0:
                cagr = ((last_val / first_val) ** (1 / years) - 1) * 100
                data[-1]["cagr"] = round(cagr, 1)
        
        return {
            "type": "revenue_trend",
            "title": "Revenue Trend",
            "data": data,
            "display_unit": unit if data else "",
            "calculated": {
                "cagr": data[-1].get("cagr", 0) if data else 0,
                "yoy_growth": [d.get("yoy_growth", 0) for d in data if d.get("yoy_growth")]
            },
            "chart_options": {
                "x_axis": "year",
                "y_axis": "value",
                "unit": "Cr" if data else "Cr",
                "color_scheme": "revenue"
            }
        }
    
    @classmethod
    def export_growth_trend(cls, facts: List[Dict]) -> Dict:
        data = []
        
        for fact in facts:
            if "growth" not in fact.get("name", "").lower():
                continue
            
            value_str = str(fact.get("value", ""))
            match = re.search(r"(\d+(?:\.\d+)?)", value_str)
            if not match:
                continue
            
            value = float(match.group(1))
            year = cls.extract_fiscal_year(fact.get("metadata", {}).get("period", ""))
            
            if year == 0:
                year = 2024
            
            data.append({
                "year": f"FY{year}",
                "value": value,
                "unit": "%",
                "period": "",
                "confidence": fact.get("confidence", 0),
                "page": fact.get("page", 0)
            })
        
        data.sort(key=lambda x: x["year"])
        
        return {
            "type": "growth_trend",
            "title": "Growth Rate Trend",
            "data": data,
            "display_unit": "%",
            "calculated": {
                "average_growth": sum(d["value"] for d in data) / len(data) if data else 0,
                "latest_growth": data[-1]["value"] if data else 0
            },
            "chart_options": {
                "x_axis": "year",
                "y_axis": "value",
                "unit": "%",
                "color_scheme": "growth"
            }
        }
    
    @classmethod
    def export_margin_trend(cls, facts: List[Dict]) -> Dict:
        data = []
        
        for fact in facts:
            if "margin" not in fact.get("name", "").lower():
                continue
            
            value_str = str(fact.get("value", ""))
            match = re.search(r"(\d+(?:\.\d+)?)", value_str)
            if not match:
                continue
            
            value = float(match.group(1))
            year = cls.extract_fiscal_year(fact.get("metadata", {}).get("period", ""))
            
            if year == 0:
                year = 2024
            
            data.append({
                "year": f"FY{year}",
                "value": value,
                "unit": "%",
                "period": "",
                "confidence": fact.get("confidence", 0),
                "page": fact.get("page", 0)
            })
        
        data.sort(key=lambda x: x["year"])
        
        return {
            "type": "margin_trend",
            "title": "Margin Trend",
            "data": data,
            "display_unit": "%",
            "calculated": {
                "average_margin": sum(d["value"] for d in data) / len(data) if data else 0,
                "latest_margin": data[-1]["value"] if data else 0,
                "margin_expansion": (data[-1]["value"] - data[0]["value"]) if len(data) >= 2 else 0
            },
            "chart_options": {
                "x_axis": "year",
                "y_axis": "value",
                "unit": "%",
                "color_scheme": "margin"
            }
        }
    
    @classmethod
    def export_customer_trend(cls, facts: List[Dict]) -> Dict:
        data = []
        
        for fact in facts:
            if "customer" not in fact.get("name", "").lower() and "user" not in fact.get("name", "").lower():
                continue
            
            value_str = str(fact.get("value", "")).replace(",", "")
            match = re.search(r"(\d+)", value_str)
            if not match:
                continue
            
            value = float(match.group(1))
            year = cls.extract_fiscal_year(fact.get("metadata", {}).get("period", ""))
            
            if year == 0:
                year = 2024
            
            data.append({
                "year": f"FY{year}",
                "value": value,
                "unit": "users",
                "period": "",
                "confidence": fact.get("confidence", 0),
                "page": fact.get("page", 0)
            })
        
        data.sort(key=lambda x: x["year"])
        
        return {
            "type": "customer_trend",
            "title": "Customer Growth",
            "data": data,
            "display_unit": "users",
            "calculated": {
                "total_customers": data[-1]["value"] if data else 0,
                "growth_multiple": data[-1]["value"] / data[0]["value"] if data and data[0]["value"] > 0 else 0
            },
            "chart_options": {
                "x_axis": "year",
                "y_axis": "value",
                "unit": "users",
                "color_scheme": "customers"
            }
        }
    
    @classmethod
    def export_burn_rate_trend(cls, facts: List[Dict]) -> Dict:
        data = []
        
        for fact in facts:
            if "burn" not in fact.get("name", "").lower():
                continue
            
            value, unit = cls.parse_value(fact.get("value", ""))
            if value == 0:
                continue
            
            year = cls.extract_fiscal_year(fact.get("metadata", {}).get("period", ""))
            
            if year == 0:
                year = 2024
            
            data.append({
                "year": f"FY{year}",
                "value": value,
                "unit": unit or "Lakhs",
                "period": "",
                "confidence": fact.get("confidence", 0),
                "page": fact.get("page", 0)
            })
        
        data.sort(key=lambda x: x["year"])
        
        return {
            "type": "burn_rate_trend",
            "title": "Burn Rate Trend",
            "data": data,
            "display_unit": unit or "Lakhs",
            "calculated": {
                "latest_burn": data[-1]["value"] if data else 0,
                "runway_months": 0
            },
            "chart_options": {
                "x_axis": "year",
                "y_axis": "value",
                "unit": "Lakhs",
                "color_scheme": "burn"
            }
        }

    _CANONICAL_CHART_FIELDS = {
        "total_revenue": ("revenue", "Revenue"),
        "current_period_revenue": ("revenue", "Current Revenue"),
        "historical_revenue": ("revenue", "Historical Revenue"),
        "invoiced_amount": ("revenue", "Invoiced Revenue"),
        "tam": ("market", "TAM"),
        "sam": ("market", "SAM"),
        "som": ("market", "SOM"),
        "funding_raise": ("funding", "Current Raise"),
        "valuation": ("funding", "Valuation"),
        "purchase_order_value": ("revenue", "PO Value"),
        "government_grants": ("revenue", "Grants"),
        "expected_booking": ("revenue", "Expected Booking"),
        "pipeline_value": ("revenue", "Pipeline Value"),
        "arr_run_rate": ("revenue", "ARR Run Rate"),
        "customers": ("customers", "Customers"),
        "orders": ("orders", "Orders"),
        "gross_margin": ("margins", "Gross Margin"),
        "growth_rate": ("growth", "Growth Rate"),
    }

    @classmethod
    def _kpi_fallback(cls, canonical: dict) -> List[dict]:
        """Build a KPI summary card from canonical data when no timeline chart is possible."""
        kpis = []
        for canon_name, entry in canonical.items():
            if not isinstance(entry, dict):
                continue
            raw_value = entry.get("value", "")
            if isinstance(raw_value, dict):
                raw_value = str(raw_value.get("value", raw_value.get("display_value", "")))
            display = entry.get("display_value", raw_value)
            if not display or not isinstance(display, str):
                continue
            if display.strip() in ("", "0", "0.0"):
                continue
            label = entry.get("display_name", canon_name.replace("_", " ").title())
            kpis.append({
                "label": str(label)[:30],
                "value": str(display),
                "normalized": float(entry.get("normalized_value", 0) or 0),
                "confidence": float(entry.get("confidence", 0) or 0),
                "type": str(canon_name),
            })
        # Return top 6 sorted by normalized value desc
        kpis.sort(key=lambda x: x.get("normalized", 0), reverse=True)
        return kpis[:6]

    @classmethod
    def export_from_canonical(cls, canonical: dict) -> dict:
        """Build chart_data from canonical registry dict (structured_data['_canonical']).
        Always returns all chart keys (empty list if no data) for frontend stability.
        Every metric value is validated as a proper string/number — never a dict."""
        chart_data: Dict[str, List] = {
            "revenue": [],
            "market": [],
            "funding": [],
            "growth": [],
            "margins": [],
            "customers": [],
            "orders": [],
        }

        for canon_name, entry in canonical.items():
            if not isinstance(entry, dict):
                continue
            field_info = cls._CANONICAL_CHART_FIELDS.get(canon_name)
            if not field_info:
                continue
            chart_type, label = field_info
            raw_normalized = entry.get("normalized_value", 0)
            if isinstance(raw_normalized, dict):
                raw_normalized = 0
            try:
                normalized = float(raw_normalized) if raw_normalized else 0
            except (ValueError, TypeError):
                normalized = 0
            if not normalized:
                continue
            raw_display = entry.get("display_value", entry.get("value", ""))
            if isinstance(raw_display, dict):
                raw_display = str(raw_display.get("value", ""))
            display = str(raw_display) if raw_display else ""
            if not display:
                continue
            fy = str(entry.get("fiscal_year") or "")
            chart_data[chart_type].append({
                "label": str(label),
                "value": normalized,
                "display": display,
                "period": fy,
                "confidence": float(entry.get("confidence", 0) or 0),
                "type": str(canon_name),
            })

        for k in chart_data:
            chart_data[k].sort(key=lambda x: x.get("period", ""))

        result: Dict[str, Any] = {}

        if chart_data["revenue"]:
            result["revenue"] = {
                "type": "revenue_trend",
                "title": "Revenue",
                "data": chart_data["revenue"],
                "display_unit": "INR",
                "calculated": cls._calc_trend(chart_data["revenue"]),
                "chart_options": {"x_axis": "label", "y_axis": "value", "unit": "INR", "color_scheme": "revenue"}
            }

        if chart_data["market"]:
            result["market"] = {
                "type": "market_comparison",
                "title": "Market Sizing",
                "data": chart_data["market"],
                "display_unit": "INR",
                "chart_options": {"chart_type": "pie", "color_scheme": "market"}
            }

        if chart_data["funding"]:
            result["funding"] = {
                "type": "funding_overview",
                "title": "Funding",
                "data": chart_data["funding"],
                "display_unit": "INR",
                "chart_options": {"chart_type": "bar", "color_scheme": "funding"}
            }

        if chart_data["growth"]:
            result["growth"] = {
                "type": "growth_rate",
                "title": "Growth Rate",
                "data": chart_data["growth"],
                "display_unit": "%",
                "chart_options": {"chart_type": "bar", "color_scheme": "growth"}
            }

        if chart_data["margins"]:
            result["margins"] = {
                "type": "margin_trend",
                "title": "Margins",
                "data": chart_data["margins"],
                "display_unit": "%",
                "chart_options": {"chart_type": "bar", "color_scheme": "margin"}
            }

        if chart_data["customers"]:
            result["customers"] = {
                "type": "customer_growth",
                "title": "Customers",
                "data": chart_data["customers"],
                "display_unit": "users",
                "chart_options": {"chart_type": "bar", "color_scheme": "customers"}
            }

        if chart_data["orders"]:
            result["orders"] = {
                "type": "order_volume",
                "title": "Orders",
                "data": chart_data["orders"],
                "display_unit": "count",
                "chart_options": {"chart_type": "bar", "color_scheme": "orders"}
            }

        # KPI fallback card — shows top metrics even without timeline data
        kpi_cards = cls._kpi_fallback(canonical)
        if kpi_cards:
            result["kpi_summary"] = {
                "type": "kpi_cards",
                "title": "Key Metrics",
                "data": kpi_cards,
                "display_unit": "",
                "chart_options": {"chart_type": "cards", "color_scheme": "kpi"}
            }

        return result

    @staticmethod
    def _calc_trend(data: List[dict]) -> dict:
        if len(data) < 2:
            return {"cagr": 0, "yoy_growth": []}
        values = [d["value"] for d in data]
        yoy = []
        for i in range(1, len(values)):
            if values[i-1] > 0:
                yoy.append(round((values[i] - values[i-1]) / values[i-1] * 100, 1))
        cagr = 0
        if len(values) >= 2 and values[0] > 0:
            cagr = round((values[-1] / values[0]) ** (1 / max(len(values)-1, 1)) - 1, 2)
        return {"cagr": round(cagr * 100, 1), "yoy_growth": yoy}

    @classmethod
    def export_all_charts(cls, facts: List[Dict]) -> Dict:
        return {
            "revenue": cls.export_revenue_trend(facts),
            "growth": cls.export_growth_trend(facts),
            "margin": cls.export_margin_trend(facts),
            "customers": cls.export_customer_trend(facts),
            "burn_rate": cls.export_burn_rate_trend(facts)
        }


def export_chart_data_for_frontend(facts: List[Dict]) -> Dict:
    """Main export function (fact-based) - returns structured chart data"""
    return ChartDataExporter.export_all_charts(facts)


def export_chart_data_from_canonical(canonical: dict) -> Dict:
    """Export chart data from canonical registry dict"""
    return ChartDataExporter.export_from_canonical(canonical)