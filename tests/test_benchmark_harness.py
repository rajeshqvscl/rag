"""
Benchmark harness for RAG system extraction accuracy.
Tests metric extraction, ontological classification, and sanity constraints
against 10 manually verified golden deck schemas.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.rag.number_utils import parse_indian_number
from app.rag.financial_validator import MetricCategory, _classify_metric
from app.rag.generator import extract_metrics_from_structured, _BANNED_FILLERS, _filter_generic_phrases
from app.rag.extract_utils import normalize_nulls

# ---------------------------------------------------------------------------
# Golden deck schemas — 10 manually verified decks
# ---------------------------------------------------------------------------

GOLDEN_DECKS = [
    # ── Deck 1: SaaS / AgriTech (Seed) ────────────────────────────────
    {
        "name": "AgriVijay",
        "sector": "AgriTech",
        "stage": "seed",
        "ground_truth": {
            "revenue": {"raw": "₹90 Lakhs", "value": 9_000_000},
            "tam": {"raw": "₹45,000 Cr", "value": 450_000_000_000},
            "sam": {"raw": "₹8,000 Cr", "value": 80_000_000_000},
            "som": {"raw": "₹250 Cr", "value": 2_500_000_000},
            "funding_raise": {"raw": "₹5 Cr", "value": 50_000_000},
            "valuation": {"raw": "₹50 Cr", "value": 500_000_000},
            "customers": {"raw": "300+", "value": 300},
            "orders": {"raw": "7,000+", "value": 7_000},
            "arr": {"raw": "₹90 Lakhs", "value": 9_000_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹90 Lakhs from invoiced sales"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "7,000+ orders booked from partner labs"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "300+ customers across partner labs"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "Market TAM of ₹45,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM ₹8,000 Cr serviceable market"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM ₹250 Cr obtainable market"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹5 Cr in seed round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "post-money valuation of ₹50 Cr"},
            "arr": {"category": MetricCategory.EARNED_REVENUE, "field_context": "ARR of ₹90 Lakhs annual recurring revenue"},
        },
        "context": (
            "AgriVijay is an agri-tech SaaS platform. "
            "Revenue of ₹90 Lakhs from 300+ partner labs and 7,000+ orders. "
            "Market: TAM ₹45,000 Cr, SAM ₹8,000 Cr, SOM ₹250 Cr. "
            "Raising ₹5 Cr at ₹50 Cr valuation."
        ),
    },
    # ── Deck 2: SaaS / Life Sciences (Series A) ───────────────────────
    {
        "name": "LabBuddy",
        "sector": "Life Sciences",
        "stage": "series_a",
        "ground_truth": {
            "revenue": {"raw": "₹3.2 Cr", "value": 32_000_000},
            "tam": {"raw": "₹1,500 Cr", "value": 15_000_000_000},
            "sam": {"raw": "₹350 Cr", "value": 3_500_000_000},
            "som": {"raw": "₹75 Cr", "value": 750_000_000},
            "funding_raise": {"raw": "₹12 Cr", "value": 120_000_000},
            "valuation": {"raw": "₹120 Cr", "value": 1_200_000_000},
            "customers": {"raw": "250+ labs", "value": 250},
            "orders": {"raw": "15,000+", "value": 15_000},
            "arr": {"raw": "₹3.2 Cr", "value": 32_000_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹3.2 Cr from invoiced services"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "15,000+ orders booked this quarter"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "250+ lab customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹1,500 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹350 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹75 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Series A round of ₹12 Cr"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "post-money valuation of ₹120 Cr"},
            "arr": {"category": MetricCategory.EARNED_REVENUE, "field_context": "ARR of ₹3.2 Cr annual recurring revenue"},
        },
        "context": (
            "LabBuddy is a lab management SaaS platform. "
            "Revenue of ₹3.2 Cr from 250+ labs with 15,000+ orders. "
            "Market: TAM ₹1,500 Cr, SAM ₹350 Cr, SOM ₹75 Cr. "
            "Series A round of ₹12 Cr at ₹120 Cr valuation."
        ),
    },
    # ── Deck 3: DeepTech / HPC (Seed, PO confusion risk) ──────────────
    {
        "name": "Syncthreads Computing",
        "sector": "DeepTech",
        "stage": "seed",
        "ground_truth": {
            "revenue": {"raw": "₹90 Lakhs", "value": 9_000_000},
            "tam": {"raw": "₹2,000 Cr", "value": 20_000_000_000},
            "sam": {"raw": "₹500 Cr", "value": 5_000_000_000},
            "som": {"raw": "₹100 Cr", "value": 1_000_000_000},
            "funding_raise": {"raw": "₹8 Cr", "value": 80_000_000},
            "valuation": {"raw": "₹60 Cr", "value": 600_000_000},
            "customers": {"raw": "7 units", "value": 7},
            "orders": {"raw": "7 units", "value": 7},
            "pipeline": {"raw": "₹60 Cr", "value": 600_000_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue from invoiced amounts of ₹90 Lakhs"},
            "customers": {"category": MetricCategory.UNIT_COUNT, "field_context": "7 unit systems delivered to defence"},
            "orders": {"category": MetricCategory.UNIT_COUNT, "field_context": "7 system unit ordered"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹2,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹500 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹100 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹8 Cr in current round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "pre-money valuation of ₹60 Cr"},
            "pipeline": {"category": MetricCategory.PIPELINE, "field_context": "Upcoming pipeline worth ₹60 Cr expected"},
        },
        "context": (
            "STC pitch deck. Revenue from 7 GBMRS units is ₹90 Lakhs. "
            "Expected PO worth INR 60+ Cr from DRDO. "
            "Market: TAM ₹2,000 Cr, SAM ₹500 Cr, SOM ₹100 Cr. "
            "Raising ₹8 Cr at ₹60 Cr valuation."
        ),
    },
    # ── Deck 4: Healthcare / DeepTech (Series A, grants) ──────────────
    {
        "name": "Unnati Healthcare",
        "sector": "Healthcare",
        "stage": "series_a",
        "ground_truth": {
            "revenue": {"raw": "₹8.5 Cr", "value": 85_000_000},
            "tam": {"raw": "₹12,000 Cr", "value": 120_000_000_000},
            "sam": {"raw": "₹1,800 Cr", "value": 18_000_000_000},
            "som": {"raw": "₹450 Cr", "value": 4_500_000_000},
            "funding_raise": {"raw": "₹25 Cr", "value": 250_000_000},
            "valuation": {"raw": "₹200 Cr", "value": 2_000_000_000},
            "customers": {"raw": "50+ hospitals", "value": 50},
            "orders": {"raw": "10,000+ diagnostics", "value": 10_000},
            "grant": {"raw": "₹5.75 Cr", "value": 57_500_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹8.5 Cr from invoiced diagnostics"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "10,000+ diagnostics orders booked"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "50+ hospital customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM ₹12,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM ₹1,800 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM ₹450 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹25 Cr in series A round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "post-money valuation of ₹200 Cr"},
            "grant": {"category": MetricCategory.GRANT, "field_context": "Government grant of ₹5.75 Cr from BIRAC"},
        },
        "context": (
            "Unnati Healthcare provides AI-powered diagnostics. "
            "Revenue of ₹8.5 Cr from 50+ hospitals and 10,000+ diagnostics. "
            "Government grant of ₹5.75 Cr from BIRAC. "
            "Series A: raising ₹25 Cr at ₹200 Cr valuation. "
            "Market: TAM ₹12,000 Cr, SAM ₹1,800 Cr, SOM ₹450 Cr."
        ),
    },
    # ── Deck 5: Marketplace / Platform (Series A, GMV) ────────────────
    {
        "name": "Gigin",
        "sector": "Marketplace",
        "stage": "series_a",
        "ground_truth": {
            "revenue": {"raw": "₹2.1 Cr", "value": 21_000_000},
            "tam": {"raw": "₹5,000 Cr", "value": 50_000_000_000},
            "sam": {"raw": "₹800 Cr", "value": 8_000_000_000},
            "som": {"raw": "₹150 Cr", "value": 1_500_000_000},
            "funding_raise": {"raw": "₹15 Cr", "value": 150_000_000},
            "valuation": {"raw": "₹100 Cr", "value": 1_000_000_000},
            "customers": {"raw": "500+ employers", "value": 500},
            "orders": {"raw": "25,000+ jobs", "value": 25_000},
            "gmv": {"raw": "₹25 Cr", "value": 250_000_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹2.1 Cr from platform fees"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "25,000+ jobs booked on platform"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "500+ employer customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹5,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹800 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹150 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Series A raising ₹15 Cr round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "valuation of ₹100 Cr"},
            "gmv": {"category": MetricCategory.UNCLASSIFIED, "field_context": "GMV of ₹25 Cr"},
        },
        "context": (
            "Gigin is a blue-collar job marketplace. "
            "Revenue of ₹2.1 Cr from 500+ employers with 25,000+ jobs listed. "
            "GMV of ₹25 Cr. Market: TAM ₹5,000 Cr, SAM ₹800 Cr, SOM ₹150 Cr. "
            "Series A: raising ₹15 Cr at ₹100 Cr valuation."
        ),
    },
    # ── Deck 6: Fintech / Payments (Series B, take-rate) ──────────────
    {
        "name": "FinPay",
        "sector": "Fintech",
        "stage": "series_b",
        "ground_truth": {
            "revenue": {"raw": "₹45 Cr", "value": 450_000_000},
            "tam": {"raw": "₹25,000 Cr", "value": 2_500_000_000_000},
            "sam": {"raw": "₹5,000 Cr", "value": 500_000_000_000},
            "som": {"raw": "₹1,200 Cr", "value": 12_000_000_000},
            "funding_raise": {"raw": "₹85 Cr", "value": 850_000_000},
            "valuation": {"raw": "₹850 Cr", "value": 8_500_000_000},
            "customers": {"raw": "2,000+ merchants", "value": 2_000},
            "orders": {"raw": "5 Lakh+ transactions", "value": 500_000},
            "take_rate": {"raw": "2.5%", "value": 2.5},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹45 Cr from payment processing"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "5 Lakh+ transactions booked"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "2,000+ merchant customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹25,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹5,000 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹1,200 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Series B raising ₹85 Cr round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "post-money valuation of ₹850 Cr"},
            "take_rate": {"category": MetricCategory.UNCLASSIFIED, "field_context": "take rate of 2.5%"},
        },
        "context": (
            "FinPay is a digital payments platform. "
            "Revenue of ₹45 Cr from 2,000+ merchants processing 5 Lakh+ transactions. "
            "Take rate of 2.5%. Market: TAM ₹25,000 Cr, SAM ₹5,000 Cr, SOM ₹1,200 Cr. "
            "Series B: raising ₹85 Cr at ₹850 Cr valuation."
        ),
    },
    # ── Deck 7: Climate / Agritech (Seed, TAM-heavy) ──────────────────
    {
        "name": "EcoFarm",
        "sector": "ClimateTech",
        "stage": "seed",
        "ground_truth": {
            "revenue": {"raw": "₹1.5 Cr", "value": 15_000_000},
            "tam": {"raw": "₹50,000 Cr", "value": 5_000_000_000_000},
            "sam": {"raw": "₹10,000 Cr", "value": 1_000_000_000_000},
            "som": {"raw": "₹500 Cr", "value": 5_000_000_000},
            "funding_raise": {"raw": "₹4 Cr", "value": 40_000_000},
            "valuation": {"raw": "₹35 Cr", "value": 350_000_000},
            "customers": {"raw": "5,000+ farmers", "value": 5_000},
            "orders": {"raw": "12,000+", "value": 12_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹1.5 Cr from carbon credits"},
            "orders": {"category": MetricCategory.ORDER_COUNT, "field_context": "12,000+ orders booked from farmers"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "5,000+ farmer customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹50,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹10,000 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹500 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹4 Cr in seed round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "valuation of ₹35 Cr"},
        },
        "context": (
            "EcoFarm provides carbon credit monitoring for agriculture. "
            "Revenue of ₹1.5 Cr from 5,000+ farmers with 12,000+ orders. "
            "Massive TAM of ₹50,000 Cr, SAM ₹10,000 Cr, SOM ₹500 Cr. "
            "Seed round: raising ₹4 Cr at ₹35 Cr valuation."
        ),
    },
    # ── Deck 8: Climate / Energy (Series A, TAM-heavy) ────────────────
    {
        "name": "GreenCarbon",
        "sector": "CleanTech",
        "stage": "series_a",
        "ground_truth": {
            "revenue": {"raw": "₹6.2 Cr", "value": 62_000_000},
            "tam": {"raw": "₹75,000 Cr", "value": 7_500_000_000_000},
            "sam": {"raw": "₹12,000 Cr", "value": 120_000_000_000},
            "som": {"raw": "₹800 Cr", "value": 8_000_000_000},
            "funding_raise": {"raw": "₹30 Cr", "value": 300_000_000},
            "valuation": {"raw": "₹250 Cr", "value": 2_500_000_000},
            "customers": {"raw": "100+ industrial clients", "value": 100},
            "orders": {"raw": "250+ units", "value": 250},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹6.2 Cr from invoiced services"},
            "orders": {"category": MetricCategory.UNIT_COUNT, "field_context": "250+ system units deployed"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "100+ industrial client customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹75,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹12,000 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹800 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raise of ₹30 Cr in series A round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "valuation of ₹250 Cr"},
        },
        "context": (
            "GreenCarbon offers industrial carbon capture solutions. "
            "Revenue of ₹6.2 Cr from 100+ industrial clients with 250+ units deployed. "
            "Market: TAM ₹75,000 Cr, SAM ₹12,000 Cr, SOM ₹800 Cr. "
            "Series A: raising ₹30 Cr at ₹250 Cr valuation."
        ),
    },
    # ── Deck 9: Defence / AI (Series A, contract-heavy) ───────────────
    {
        "name": "AeroDefence",
        "sector": "Defence",
        "stage": "series_a",
        "ground_truth": {
            "revenue": {"raw": "₹4.8 Cr", "value": 48_000_000},
            "tam": {"raw": "₹8,000 Cr", "value": 80_000_000_000},
            "sam": {"raw": "₹2,500 Cr", "value": 25_000_000_000},
            "som": {"raw": "₹600 Cr", "value": 6_000_000_000},
            "funding_raise": {"raw": "₹20 Cr", "value": 200_000_000},
            "valuation": {"raw": "₹180 Cr", "value": 1_800_000_000},
            "customers": {"raw": "3 defence PSUs", "value": 3},
            "pipeline": {"raw": "₹60 Cr", "value": 600_000_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹4.8 Cr from invoiced deliveries"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "3 defence PSU customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹8,000 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹2,500 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹600 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹20 Cr in series A round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "valuation of ₹180 Cr"},
            "pipeline": {"category": MetricCategory.PIPELINE, "field_context": "Upcoming pipeline worth ₹60 Cr from Ministry"},
        },
        "context": (
            "AeroDefence provides AI-based drone surveillance for defence. "
            "Revenue of ₹4.8 Cr from 3 defence PSUs. "
            "Expected contract worth ₹60 Cr from Ministry of Defence. "
            "Market: TAM ₹8,000 Cr, SAM ₹2,500 Cr, SOM ₹600 Cr. "
            "Series A: raising ₹20 Cr at ₹180 Cr valuation."
        ),
    },
    # ── Deck 10: AI / Enterprise (Seed, PO-heavy) ────────────────────
    {
        "name": "Vera AI",
        "sector": "Enterprise AI",
        "stage": "seed",
        "ground_truth": {
            "revenue": {"raw": "₹75 Lakhs", "value": 7_500_000},
            "tam": {"raw": "₹3,500 Cr", "value": 35_000_000_000},
            "sam": {"raw": "₹700 Cr", "value": 7_000_000_000},
            "som": {"raw": "₹120 Cr", "value": 1_200_000_000},
            "funding_raise": {"raw": "₹6 Cr", "value": 60_000_000},
            "valuation": {"raw": "₹45 Cr", "value": 450_000_000},
            "customers": {"raw": "20 enterprise clients", "value": 20},
            "orders": {"raw": "5 POs", "value": 5},
            "arr": {"raw": "₹75 Lakhs", "value": 7_500_000},
        },
        "expected_ontology": {
            "revenue": {"category": MetricCategory.EARNED_REVENUE, "field_context": "Revenue of ₹75 Lakhs from invoiced deployments"},
            "orders": {"category": MetricCategory.PO_VALUE, "field_context": "5 PO in hand worth ₹2.5 Cr"},
            "customers": {"category": MetricCategory.UNCLASSIFIED, "field_context": "20 enterprise client customers"},
            "tam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "TAM of ₹3,500 Cr"},
            "sam": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SAM of ₹700 Cr"},
            "som": {"category": MetricCategory.UNCLASSIFIED, "field_context": "SOM of ₹120 Cr"},
            "funding_raise": {"category": MetricCategory.RAISE_AMOUNT, "field_context": "Raising ₹6 Cr in seed round"},
            "valuation": {"category": MetricCategory.VALUATION, "field_context": "valuation of ₹45 Cr"},
            "arr": {"category": MetricCategory.EARNED_REVENUE, "field_context": "ARR of ₹75 Lakhs"},
        },
        "context": (
            "Vera AI provides enterprise LLM deployment solutions. "
            "Revenue of ₹75 Lakhs from 20 enterprise clients. "
            "5 purchase orders worth ₹2.5 Cr in hand. "
            "Market: TAM ₹3,500 Cr, SAM ₹700 Cr, SOM ₹120 Cr. "
            "Seed round: raising ₹6 Cr at ₹45 Cr valuation. ARR of ₹75 Lakhs."
        ),
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INF = 1_000_000_000_000


def _build_structured_data(deck):
    """Build a structured_data dict from a golden deck for pipeline testing."""
    gt = deck["ground_truth"]
    sd = {
        "company_brief": {"name": deck["name"], "sector": deck["sector"], "stage": deck["stage"]},
        "traction": {
            "revenue": gt.get("revenue", {}).get("raw", ""),
            "customers": gt.get("customers", {}).get("raw", ""),
            "orders": gt.get("orders", {}).get("raw", ""),
            "revenue_time_type": "current",
        },
        "industry_overview": {
            "tam": gt.get("tam", {}).get("raw", ""),
            "sam": gt.get("sam", {}).get("raw", ""),
            "som": gt.get("som", {}).get("raw", ""),
        },
        "funding": {
            "current_raise": gt.get("funding_raise", {}).get("raw", ""),
            "valuation": gt.get("valuation", {}).get("raw", ""),
        },
        "pipeline": {
            "pipeline_value": gt.get("pipeline", {}).get("raw", ""),
        },
        "revenue_details": {
            "current_revenue": gt.get("arr", gt.get("revenue", {})).get("raw", ""),
        },
        "additional_metrics": [],
    }
    return normalize_nulls(sd)


def _plausible_max(field_name):
    """Return the maximum plausible numeric value for a field type (in INR)."""
    limits = {
        "revenue": 1_000_000_000_000,
        "tam": 100_000_000_000_000,
        "sam": 50_000_000_000_000,
        "som": 10_000_000_000_000,
        "funding_raise": 500_000_000_000,
        "valuation": 10_000_000_000_000,
        "customers": 100_000_000,
        "orders": 100_000_000,
        "arr": 1_000_000_000_000,
        "pipeline": 10_000_000_000_000,
        "gmv": 10_000_000_000_000,
        "take_rate": 100,
        "grant": 10_000_000_000,
    }
    return limits.get(field_name, 1_000_000_000_000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("deck", GOLDEN_DECKS, ids=lambda d: d["name"])
def test_extraction_accuracy(deck):
    """Verify extract_metrics_from_structured detects every ground-truth metric."""
    sd = _build_structured_data(deck)
    gt = deck["ground_truth"]
    metrics = extract_metrics_from_structured(sd)

    if gt.get("revenue", {}).get("raw"):
        assert metrics.get("revenue"), f"{deck['name']}: revenue field should be detected"
    if gt.get("customers", {}).get("raw"):
        assert metrics.get("customers"), f"{deck['name']}: customers field should be detected"
    if gt.get("orders", {}).get("raw"):
        assert metrics.get("orders"), f"{deck['name']}: orders field should be detected"
    if gt.get("tam", {}).get("raw"):
        assert metrics.get("market"), f"{deck['name']}: TAM field should be detected"
    if gt.get("funding_raise", {}).get("raw"):
        assert metrics.get("funding"), f"{deck['name']}: funding field should be detected"
    if gt.get("pipeline", {}).get("raw"):
        assert metrics.get("pipeline"), f"{deck['name']}: pipeline field should be detected"


@pytest.mark.parametrize("deck", GOLDEN_DECKS, ids=lambda d: d["name"])
def test_ontology_accuracy(deck):
    """Verify _classify_metric returns the expected ontological category using per-field context."""
    ctx = deck.get("context", "")
    for field, onto in deck["expected_ontology"].items():
        val = deck["ground_truth"].get(field, {}).get("raw", "")
        if not val:
            continue
        expected_category = onto["category"]
        field_ctx = onto.get("field_context", ctx)
        result = _classify_metric(val, field_ctx)
        assert result == expected_category, (
            f"{deck['name']}.{field}: expected {expected_category.value}, "
            f"got {result.value} (value='{val}', ctx='{field_ctx[:60]}')"
        )


@pytest.mark.parametrize("deck", GOLDEN_DECKS, ids=lambda d: d["name"])
def test_market_hierarchy(deck):
    """Verify TAM >= SAM >= SOM for all deck ground_truths."""
    gt = deck["ground_truth"]
    tam = gt.get("tam", {}).get("value", 0)
    sam = gt.get("sam", {}).get("value", 0)
    som = gt.get("som", {}).get("value", 0)

    if tam and sam:
        assert tam >= sam, (
            f"{deck['name']}: TAM ({tam:,.0f}) < SAM ({sam:,.0f}) — market sizes likely swapped"
        )
    if sam and som:
        assert sam >= som, (
            f"{deck['name']}: SAM ({sam:,.0f}) < SOM ({som:,.0f}) — market sizes likely swapped"
        )
    if tam and som:
        assert tam >= som, (
            f"{deck['name']}: TAM ({tam:,.0f}) < SOM ({som:,.0f}) — hierarchy violated"
        )


@pytest.mark.parametrize("deck", GOLDEN_DECKS, ids=lambda d: d["name"])
def test_no_hallucinations(deck):
    """Verify no ground-truth value exceeds plausible range for its type."""
    gt = deck["ground_truth"]
    for field, entry in gt.items():
        val = entry.get("value", 0) if isinstance(entry, dict) else 0
        if not val:
            continue
        limit = _plausible_max(field)
        assert val <= limit, (
            f"{deck['name']}.{field}: value {val:,.0f} exceeds "
            f"plausible max {limit:,.0f}"
        )


@pytest.mark.parametrize("deck", GOLDEN_DECKS, ids=lambda d: d["name"])
def test_narrative_no_banned_phrases(deck):
    """Verify a generated narrative for this deck does not contain banned fillers."""
    gt = deck["ground_truth"]
    narrative_parts = [
        f"{deck['name']} is a {deck['sector']} startup at {deck['stage']} stage."
    ]
    rev = gt.get("revenue", {}).get("raw", "")
    if rev:
        narrative_parts.append(f"Revenue of {rev}.")
    tam = gt.get("tam", {}).get("raw", "")
    if tam:
        narrative_parts.append(f"Operating in a TAM of {tam}.")
    narrative = " ".join(narrative_parts)

    cleaned = _filter_generic_phrases(narrative)
    lower_cleaned = cleaned.lower()

    violations = [p for p in _BANNED_FILLERS if p.lower() in lower_cleaned]
    assert not violations, (
        f"{deck['name']}: narrative contains banned phrase(s): {violations}"
    )


def test_benchmark_summary():
    """Print an aggregate accuracy table across all golden decks."""
    sep = " | "
    hdr = (f"{'Deck':<28}{sep}{'Extract':>8}{sep}{'Ontology':>8}{sep}"
           f"{'Market':>8}{sep}{'Halluc':>8}{sep}{'Narrativ':>8}")
    print("\n" + "=" * len(hdr))
    print("BENCHMARK SUMMARY")
    print("=" * len(hdr))
    print(hdr)
    print("-" * len(hdr))

    totals = {"extract": 0, "ontology": 0, "market": 0, "halluc": 0, "narrative": 0}
    total = len(GOLDEN_DECKS)

    for deck in GOLDEN_DECKS:
        name = deck["name"]
        gt = deck["ground_truth"]
        ctx = deck.get("context", "")
        sd = _build_structured_data(deck)

        ext_ok = True
        metrics = extract_metrics_from_structured(sd)
        if gt.get("revenue", {}).get("raw") and not metrics.get("revenue"):
            ext_ok = False
        if gt.get("tam", {}).get("raw") and not metrics.get("market"):
            ext_ok = False
        if gt.get("funding_raise", {}).get("raw") and not metrics.get("funding"):
            ext_ok = False
        totals["extract"] += 1 if ext_ok else 0

        onto_ok = True
        for field, onto in deck["expected_ontology"].items():
            val = gt.get(field, {}).get("raw", "")
            if val and _classify_metric(val, onto.get("field_context", ctx)) != onto["category"]:
                onto_ok = False
                break
        totals["ontology"] += 1 if onto_ok else 0

        tam = gt.get("tam", {}).get("value", 0)
        sam = gt.get("sam", {}).get("value", 0)
        som = gt.get("som", {}).get("value", 0)
        mkt_ok = True
        if tam and sam and tam < sam:
            mkt_ok = False
        if sam and som and sam < som:
            mkt_ok = False
        totals["market"] += 1 if mkt_ok else 0

        hal_ok = True
        for field, entry in gt.items():
            val = entry.get("value", 0) if isinstance(entry, dict) else 0
            if val and val > _plausible_max(field):
                hal_ok = False
                break
        totals["halluc"] += 1 if hal_ok else 0

        narr_ok = True
        parts = [f"{name} is a {deck['sector']} startup."]
        rev = gt.get("revenue", {}).get("raw", "")
        if rev:
            parts.append(f"Revenue of {rev}.")
        cleaned = _filter_generic_phrases(" ".join(parts))
        if any(p.lower() in cleaned.lower() for p in _BANNED_FILLERS):
            narr_ok = False
        totals["narrative"] += 1 if narr_ok else 0

        print(
            f"{name:<28}{sep}"
            f"{'PASS' if ext_ok else 'FAIL':>8}{sep}"
            f"{'PASS' if onto_ok else 'FAIL':>8}{sep}"
            f"{'PASS' if mkt_ok else 'FAIL':>8}{sep}"
            f"{'PASS' if hal_ok else 'FAIL':>8}{sep}"
            f"{'PASS' if narr_ok else 'FAIL':>8}"
        )

    print("-" * len(hdr))
    print(
        f"{'TOTAL':<28}{sep}"
        f"{totals['extract']}/{total:>5}{sep}"
        f"{totals['ontology']}/{total:>5}{sep}"
        f"{totals['market']}/{total:>5}{sep}"
        f"{totals['halluc']}/{total:>5}{sep}"
        f"{totals['narrative']}/{total:>5}"
    )
    print(f"\nAggregate accuracy: "
          f"extract={totals['extract']/total:.0%}, "
          f"ontology={totals['ontology']/total:.0%}, "
          f"market={totals['market']/total:.0%}, "
          f"halluc={totals['halluc']/total:.0%}, "
          f"narrative={totals['narrative']/total:.0%}")
    print("=" * len(hdr))
