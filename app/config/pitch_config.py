"""
Pitch Deck Configuration System
Allows FinRAG to adapt its presentation for different audiences:
- investor: VC/angel pitch with ROI focus
- enterprise: C-suite with business outcomes
- technical: Engineering leadership with architecture
- general: Default balanced view
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class PitchMode(Enum):
    INVESTOR = "investor"
    ENTERPRISE = "enterprise"
    TECHNICAL = "technical"
    GENERAL = "general"


@dataclass
class PositioningConfig:
    """Primary positioning for different modes"""
    tagline: str
    primary_benefit: str
    target_audience: str
    pain_narrative: str
    trust_focus: str
    agent_identity: str


@dataclass
class ROIMetric:
    """Business impact metrics"""
    label: str
    value: str
    subtext: str
    icon: str
    category: str  # time, cost, risk, quality


@dataclass
class AgentConfig:
    """AI Agent branding configuration"""
    technical_name: str
    branded_name: str
    description: str
    autonomy_level: str  # assistant, copilot, autonomous
    outcomes: List[str]


@dataclass
class TrustLayerConfig:
    """Trust and verification marketing"""
    contradiction_engine: str
    citations: str
    knowledge_graph: str
    multi_source: str
    verification: str


class PitchConfig:
    """Main pitch configuration engine"""
    
    # Mode-specific positioning
    POSITIONING: Dict[PitchMode, PositioningConfig] = {
        PitchMode.INVESTOR: PositioningConfig(
            tagline="AI Intelligence Infrastructure for Investment Decisions",
            primary_benefit="10x faster due diligence with verifiable intelligence",
            target_audience="VCs, Angel Investors, Family Offices",
            pain_narrative="Investment teams lose 40+ hours per deal on manual document analysis, missing critical signals in fragmented data",
            trust_focus="Proprietary contradiction detection eliminates valuation errors",
            agent_identity="Investment Analysis Copilot"
        ),
        PitchMode.ENTERPRISE: PositioningConfig(
            tagline="Enterprise Research Brain",
            primary_benefit="Single source of truth for all document-driven decisions",
            target_audience="C-Suite, Heads of Strategy, Compliance Officers",
            pain_narrative="Enterprises drown in fragmented intelligence, losing millions because decisions are made from disconnected documents",
            trust_focus="Hallucination Risk Engine with verifiable citations",
            agent_identity="Autonomous Due Diligence Agent"
        ),
        PitchMode.TECHNICAL: PositioningConfig(
            tagline="Multi-Agent Intelligence Cloud",
            primary_benefit="Production-grade RAG with enterprise memory and orchestration",
            target_audience="CTOs, VPs Engineering, AI Leads",
            pain_narrative="Current RAG implementations lack multi-document reasoning, contradiction detection, and persistent memory",
            trust_focus="Cross-document lineage tracking with confidence scoring",
            agent_identity="Research Intelligence Agents"
        ),
        PitchMode.GENERAL: PositioningConfig(
            tagline="AI Intelligence Cloud",
            primary_benefit="Powerful document analysis with workflows",
            target_audience="General users, analysts",
            pain_narrative="Manual document analysis is time-consuming and error-prone",
            trust_focus="Contradiction detection and citations",
            agent_identity="AI Analysis Agents"
        )
    }
    
    # Agent branding for different modes
    AGENTS: Dict[PitchMode, List[AgentConfig]] = {
        PitchMode.INVESTOR: [
            AgentConfig(
                technical_name="investment_agent",
                branded_name="Investment Analyst Agent",
                description="Autonomous due diligence with market intelligence",
                autonomy_level="copilot",
                outcomes=["4 hours saved per deal", "67% faster TAT", "20+ checks automated"]
            ),
            AgentConfig(
                technical_name="contradiction_agent",
                branded_name="Risk Detection Agent",
                description="Identifies valuation contradictions and red flags",
                autonomy_level="autonomous",
                outcomes=["93% accuracy", "250+ signals detected"]
            ),
            AgentConfig(
                technical_name="market_agent",
                branded_name="Market Intelligence Agent",
                description="Real-time market research and competitor analysis",
                autonomy_level="autonomous",
                outcomes=["Live data integration", "20+ sources aggregated"]
            )
        ],
        PitchMode.ENTERPRISE: [
            AgentConfig(
                technical_name="investment_agent",
                branded_name="Autonomous Due Diligence Agent",
                description="End-to-end due diligence with audit trail",
                autonomy_level="autonomous",
                outcomes=["44 days → 2 weeks", "1400 hours saved annually"]
            ),
            AgentConfig(
                technical_name="contradiction_agent",
                branded_name="AI Hallucination Risk Engine",
                description="Verifies claims across all documents with confidence scores",
                autonomy_level="autonomous",
                outcomes=["99.5% accuracy", "Fraud detection"]
            ),
            AgentConfig(
                technical_name="workflow_agent",
                branded_name="Enterprise Workflow Orchestrator",
                description="Coordinated multi-agent workflows with governance",
                autonomy_level="autonomous",
                outcomes=["20+ tools replaced", "Unified platform"]
            )
        ],
        PitchMode.TECHNICAL: [
            AgentConfig(
                technical_name="investment_agent",
                branded_name="Research Intelligence Agent",
                description="Multi-document reasoning with graph memory",
                autonomy_level="autonomous",
                outcomes=["Cross-document lineage", "Entity evolution tracking"]
            ),
            AgentConfig(
                technical_name="contradiction_agent",
                branded_name="Contradiction Detection Engine",
                description="Semantic comparison with confidence scoring",
                autonomy_level="autonomous",
                outcomes=["Multi-source verification", "Source trust scoring"]
            ),
            AgentConfig(
                technical_name="graph_agent",
                branded_name="Knowledge Graph Agent",
                description="Enterprise memory with relationship tracking",
                autonomy_level="autonomous",
                outcomes=["Persistent memory", "Data flywheel"]
            )
        ],
        PitchMode.GENERAL: [
            AgentConfig(
                technical_name="investment_agent",
                branded_name="Analysis Agent",
                description="Document analysis and insights",
                autonomy_level="assistant",
                outcomes=["Faster analysis", "Better insights"]
            ),
            AgentConfig(
                technical_name="contradiction_agent",
                branded_name="Contradiction Checker",
                description="Find conflicting information",
                autonomy_level="assistant",
                outcomes=["More thorough analysis"]
            )
        ]
    }
    
    # ROI Metrics for different modes
    ROI_METRICS: Dict[PitchMode, List[ROIMetric]] = {
        PitchMode.INVESTOR: [
            ROIMetric("Analyst Hours Saved", "4+ hours", "per deal analysis", "clock", "time"),
            ROIMetric("Processing Speed", "67% faster", "turnaround time", "zap", "time"),
            ROIMetric("Risk Detection", "250+ signals", "per pitch deck", "shield", "risk"),
            ROIMetric("Contradiction Rate", "93% accuracy", "red flag detection", "target", "quality"),
            ROIMetric("Documents Analyzed", "10,000+", "across portfolio", "files", "quality"),
            ROIMetric("Cost Reduction", "$50K+ annually", "per analyst", "dollar", "cost")
        ],
        PitchMode.ENTERPRISE: [
            ROIMetric("TAT Reduction", "44 → 14 days", "due diligence cycle", "trending-down", "time"),
            ROIMetric("Hours Saved", "1,400 hours", "per year annually", "clock", "time"),
            ROIMetric("Tool Consolidation", "20+ → 1", "unified platform", "layers", "cost"),
            ROIMetric("Accuracy", "99.5%", "verification rate", "check-circle", "quality"),
            ROIMetric("Risk Reduction", "85%", "decision errors", "shield", "risk"),
            ROIMetric("ROI", "10x", "implementation cost", "trending-up", "cost")
        ],
        PitchMode.TECHNICAL: [
            ROIMetric("Query Accuracy", "94%", "retrieval precision", "target", "quality"),
            ROIMetric("Latency", "<200ms", "p95 response time", "zap", "time"),
            ROIMetric("Memory", "Persistent", "graph-based storage", "database", "quality"),
            ROIMetric("Agents", "5+", "orchestrated agents", "bot", "quality"),
            ROIMetric("Sources", "20+", "integrated sources", "globe", "quality"),
            ROIMetric("Uptime", "99.9%", "production ready", "activity", "quality")
        ],
        PitchMode.GENERAL: [
            ROIMetric("Processing Time", "50% faster", "document analysis", "clock", "time"),
            ROIMetric("Accuracy", "High", "AI-powered analysis", "target", "quality"),
            ROIMetric("Insights", "Deeper", "cross-document analysis", "brain", "quality")
        ]
    }
    
    # Trust Layer Configuration
    TRUST_LAYER: Dict[PitchMode, TrustLayerConfig] = {
        PitchMode.INVESTOR: TrustLayerConfig(
            contradiction_engine="Risk Detection Engine",
            citations="Verified Source Citations",
            knowledge_graph="Investment Memory Graph",
            multi_source="Multi-Source Intelligence",
            verification="Valuation Verification"
        ),
        PitchMode.ENTERPRISE: TrustLayerConfig(
            contradiction_engine="AI Hallucination Risk Engine",
            citations="Verifiable Intelligence Layer",
            knowledge_graph="Enterprise Memory Graph",
            multi_source="Decision-Grade Intelligence",
            verification="Trust Infrastructure"
        ),
        PitchMode.TECHNICAL: TrustLayerConfig(
            contradiction_engine="Contradiction Detection",
            citations="Source Attribution",
            knowledge_graph="Knowledge Graph",
            multi_source="Multi-source Analysis",
            verification="Confidence Scoring"
        ),
        PitchMode.GENERAL: TrustLayerConfig(
            contradiction_engine="Contradiction Checker",
            citations="Citations",
            knowledge_graph="Relationship Graph",
            multi_source="Multi-document Analysis",
            verification="Verification"
        )
    }
    
    # Vertical Positioning Options
    VERTICALS = {
        "vc_investment": {
            "name": "VC / Investment Research",
            "pitch": "Autonomous due diligence for investment decisions",
            "metrics": ["deals_analyzed", "time_saved", "signals_detected"]
        },
        "consulting": {
            "name": "Consulting Intelligence",
            "pitch": "Client research and analysis acceleration",
            "metrics": ["research_time", "client_insights", "report_generation"]
        },
        "legal": {
            "name": "Legal Intelligence",
            "pitch": "Contract analysis and precedent research",
            "metrics": ["contracts_reviewed", "risk_flags", "precedents_found"]
        },
        "compliance": {
            "name": "Enterprise Compliance",
            "pitch": "Regulatory intelligence and audit support",
            "metrics": ["audit_time", "risk_detection", "compliance_score"]
        },
        "pharma": {
            "name": "Pharma Research",
            "pitch": "Scientific literature synthesis and drug discovery",
            "metrics": ["papers_analyzed", "relationships_found", "insights_generated"]
        },
        "cyber": {
            "name": "Threat Intelligence",
            "pitch": "Security research and threat analysis",
            "metrics": ["threats_detected", "sources_correlated", "reports_generated"]
        }
    }
    
    @classmethod
    def get_config(cls, mode: PitchMode) -> dict:
        """Get full configuration for a pitch mode"""
        return {
            "mode": mode.value,
            "positioning": cls.POSITIONING[mode].__dict__,
            "agents": [agent.__dict__ for agent in cls.AGENTS[mode]],
            "roi_metrics": [metric.__dict__ for metric in cls.ROI_METRICS[mode]],
            "trust_layer": cls.TRUST_LAYER[mode].__dict__,
            "verticals": cls.VERTICALS
        }
    
    @classmethod
    def get_positioning(cls, mode: PitchMode) -> PositioningConfig:
        return cls.POSITIONING[mode]
    
    @classmethod
    def get_agents(cls, mode: PitchMode) -> List[AgentConfig]:
        return cls.AGENTS[mode]
    
    @classmethod
    def get_roi_metrics(cls, mode: PitchMode) -> List[ROIMetric]:
        return cls.ROI_METRICS[mode]
    
    @classmethod
    def get_trust_layer(cls, mode: PitchMode) -> TrustLayerConfig:
        return cls.TRUST_LAYER[mode]
    
    @classmethod
    def get_verticals(cls) -> dict:
        return cls.VERTICALS