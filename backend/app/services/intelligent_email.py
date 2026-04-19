"""
Intelligent Email Draft Generator with Intent Classification
Generates context-aware outreach emails based on pitch deck analysis
"""
import os
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class IntentType(Enum):
    """Email intent classification"""
    STRONG_INTEREST = "strong_interest"
    MODERATE_INTEREST = "moderate_interest"
    NEEDS_CLARIFICATION = "needs_clarification"
    SOFT_DECLINE = "soft_decline"
    FOLLOW_UP = "follow_up"
    INITIAL_OUTREACH = "initial_outreach"


class Tone(Enum):
    """Email tone classification"""
    ENTHUSIASTIC = "enthusiastic"
    PROFESSIONAL = "professional"
    CAUTIOUS = "cautious"
    CURIOUS = "curious"
    DIRECT = "direct"


class EmailIntentClassifier:
    """Classify email intent based on pitch deck analysis"""
    
    def classify(self, extraction_data: Dict, overall_confidence: float) -> Dict:
        """
        Classify the intent and tone for the email
        
        Args:
            extraction_data: Structured extraction data from pitch deck
            overall_confidence: Overall confidence score (0-1)
            
        Returns:
            Dictionary with intent, tone, priority, and reasoning
        """
        financial_metrics = extraction_data.get("financial_metrics", {})
        operational_metrics = extraction_data.get("operational_metrics", {})
        market_metrics = extraction_data.get("market_metrics", {})
        company_info = extraction_data.get("company_info", {})
        claims = extraction_data.get("claims", [])
        risks = extraction_data.get("risks", [])
        contradictions = extraction_data.get("contradictions", [])
        
        # Calculate signal strength
        signal_strength = self._calculate_signal_strength(
            financial_metrics, operational_metrics, market_metrics, claims
        )
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(risks, contradictions, overall_confidence)
        
        # Determine intent
        intent = self._determine_intent(signal_strength, risk_level, overall_confidence)
        
        # Determine tone
        tone = self._determine_tone(intent, risk_level, overall_confidence)
        
        # Determine priority
        priority = self._determine_priority(intent, signal_strength, overall_confidence)
        
        return {
            "intent": intent.value,
            "tone": tone.value,
            "priority": priority,
            "signal_strength": signal_strength,
            "risk_level": risk_level,
            "overall_confidence": overall_confidence,
            "reasoning": self._generate_reasoning(intent, tone, signal_strength, risk_level)
        }
    
    def _calculate_signal_strength(self, financial: Dict, operational: Dict, market: Dict, claims: List) -> float:
        """Calculate overall signal strength from metrics"""
        score = 0.0
        max_score = 10.0
        
        # Revenue signal
        if financial.get("revenue") and financial.get("revenue_confidence", 0) > 0.7:
            score += 2.5
        elif financial.get("revenue"):
            score += 1.0
        
        # Growth signal
        if financial.get("growth_rate") and financial.get("growth_confidence", 0) > 0.7:
            score += 2.0
        elif financial.get("growth_rate"):
            score += 0.5
        
        # Users/customers signal
        if operational.get("users") and operational.get("users_confidence", 0) > 0.7:
            score += 2.0
        elif operational.get("users"):
            score += 0.5
        
        # Market size signal
        if market.get("tam") and market.get("tam_confidence", 0) > 0.7:
            score += 1.5
        elif market.get("tam"):
            score += 0.5
        
        # Claims signal
        if len(claims) >= 3:
            score += 1.0
        elif len(claims) >= 1:
            score += 0.5
        
        return min(score / max_score, 1.0)
    
    def _calculate_risk_level(self, risks: List, contradictions: List, confidence: float) -> str:
        """Calculate risk level: low, medium, high"""
        risk_score = 0
        
        # Count high-severity risks
        high_risks = [r for r in risks if r.get("severity") == "high"]
        risk_score += len(high_risks) * 3
        
        # Count medium-severity risks
        medium_risks = [r for r in risks if r.get("severity") == "medium"]
        risk_score += len(medium_risks) * 1.5
        
        # Contradictions increase risk
        risk_score += len(contradictions) * 2
        
        # Low confidence increases risk
        if confidence < 0.5:
            risk_score += 2
        elif confidence < 0.7:
            risk_score += 1
        
        if risk_score >= 5:
            return "high"
        elif risk_score >= 2:
            return "medium"
        else:
            return "low"
    
    def _determine_intent(self, signal_strength: float, risk_level: str, confidence: float) -> IntentType:
        """Determine email intent based on signals and risk"""
        if signal_strength >= 0.7 and risk_level == "low" and confidence >= 0.7:
            return IntentType.STRONG_INTEREST
        elif signal_strength >= 0.5 and risk_level in ["low", "medium"]:
            return IntentType.MODERATE_INTEREST
        elif confidence < 0.5 or risk_level == "high":
            return IntentType.NEEDS_CLARIFICATION
        elif signal_strength < 0.3:
            return IntentType.SOFT_DECLINE
        else:
            return IntentType.INITIAL_OUTREACH
    
    def _determine_tone(self, intent: IntentType, risk_level: str, confidence: float) -> Tone:
        """Determine email tone based on intent and context"""
        if intent == IntentType.STRONG_INTEREST:
            return Tone.ENTHUSIASTIC
        elif intent == IntentType.MODERATE_INTEREST:
            return Tone.PROFESSIONAL
        elif intent == IntentType.NEEDS_CLARIFICATION:
            return Tone.CURIOUS
        elif intent == IntentType.SOFT_DECLINE:
            return Tone.CAUTIOUS
        else:
            return Tone.PROFESSIONAL
    
    def _determine_priority(self, intent: IntentType, signal_strength: float, confidence: float) -> str:
        """Determine email priority: high, medium, low"""
        if intent == IntentType.STRONG_INTEREST:
            return "high"
        elif intent == IntentType.MODERATE_INTEREST:
            return "medium" if confidence >= 0.6 else "low"
        elif intent == IntentType.NEEDS_CLARIFICATION:
            return "medium"
        else:
            return "low"
    
    def _generate_reasoning(self, intent: IntentType, tone: Tone, signal_strength: float, risk_level: str) -> str:
        """Generate reasoning for the classification"""
        return f"Intent: {intent.value}, Tone: {tone.value}. Signal strength: {signal_strength:.2f}, Risk level: {risk_level}"


class IntelligentEmailGenerator:
    """Generate context-aware email drafts based on classification"""
    
    def __init__(self):
        self.classifier = EmailIntentClassifier()
        self.anthropic_available = False
        
        try:
            from anthropic import Anthropic
            if os.getenv("ANTHROPIC_API_KEY"):
                self.anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
                self.anthropic_available = True
                print("Claude API available for intelligent email generation")
        except ImportError:
            print("Claude not available for email generation")
    
    def generate_email(
        self,
        company_name: str,
        extraction_data: Dict,
        analysis_markdown: str,
        overall_confidence: float = 0.5
    ) -> Dict:
        """
        Generate intelligent email draft with intent classification
        
        Args:
            company_name: Name of the company
            extraction_data: Structured extraction data
            analysis_markdown: Full analysis markdown
            overall_confidence: Overall confidence score
            
        Returns:
            Dictionary with email draft and metadata
        """
        # Classify intent
        classification = self.classifier.classify(extraction_data, overall_confidence)
        
        # Generate email based on classification
        if self.anthropic_available:
            email_content = self._generate_with_claude(
                company_name, extraction_data, classification, analysis_markdown
            )
        else:
            email_content = self._generate_template_based(
                company_name, extraction_data, classification
            )
        
        return {
            "email_draft": email_content,
            "classification": classification,
            "generated_at": datetime.utcnow().isoformat(),
            "method": "claude" if self.anthropic_available else "template"
        }
    
    def _generate_with_claude(
        self,
        company_name: str,
        extraction_data: Dict,
        classification: Dict,
        analysis_markdown: str
    ) -> str:
        """Generate email using Claude API with context"""
        try:
            # Extract key data points
            financial = extraction_data.get("financial_metrics", {})
            operational = extraction_data.get("operational_metrics", {})
            company_info = extraction_data.get("company_info", {})
            team_info = extraction_data.get("team_info", {})
            
            # Build context
            context = {
                "company": company_name,
                "industry": company_info.get("industry", "Technology"),
                "stage": company_info.get("stage", "Early Stage"),
                "revenue": financial.get("revenue", "Not disclosed"),
                "growth": financial.get("growth_rate", "Not disclosed"),
                "users": operational.get("users", "Not disclosed"),
                "founders": team_info.get("founders", []),
                "intent": classification["intent"],
                "tone": classification["tone"],
                "priority": classification["priority"],
                "signal_strength": classification["signal_strength"],
                "risk_level": classification["risk_level"]
            }
            
            prompt = f"""You are a venture capitalist writing an outreach email.

COMPANY CONTEXT:
```json
{json.dumps(context, indent=2)}
```

ANALYSIS SUMMARY:
{analysis_markdown[:1500]}

STRICT INSTRUCTIONS:
- Intent: {classification['intent']}
- Tone: {classification['tone']}
- Priority: {classification['priority']}

Generate an email that:
1. References 1-2 SPECIFIC data points from the context above
2. Matches the intent and tone specified
3. Is concise (150-200 words)
4. Has a clear call-to-action appropriate to the intent

INTENT-SPECIFIC GUIDELINES:
- strong_interest: Enthusiastic, request meeting, mention specific traction
- moderate_interest: Professional, request call, ask clarifying questions
- needs_clarification: Curious, ask specific questions about missing data
- soft_decline: Cautious, polite decline or request more information
- initial_outreach: Professional introduction, express interest

Output ONLY the email with subject line. No explanations."""

            response = self.anthropic_client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022"),
                max_tokens=800,
                temperature=0.4,
                messages=[{"role": "user", "content": prompt}]
            )
            
            return response.content[0].text
            
        except Exception as e:
            print(f"Claude email generation failed: {e}")
            return self._generate_template_based(company_name, extraction_data, classification)
    
    def _generate_template_based(
        self,
        company_name: str,
        extraction_data: Dict,
        classification: Dict
    ) -> str:
        """Generate email using template-based approach"""
        financial = extraction_data.get("financial_metrics", {})
        operational = extraction_data.get("operational_metrics", {})
        company_info = extraction_data.get("company_info", {})
        team_info = extraction_data.get("team_info", {})
        
        intent = classification["intent"]
        tone = classification["tone"]
        
        # Extract key metrics for personalization
        key_points = []
        if financial.get("revenue"):
            key_points.append(f"revenue of {financial['revenue']}")
        if operational.get("users"):
            key_points.append(f"{operational['users']} users")
        if financial.get("growth_rate"):
            key_points.append(f"{financial['growth_rate']} growth")
        
        key_point_str = " and ".join(key_points[:2]) if key_points else "interesting traction"
        
        # Generate subject line
        if intent == "strong_interest":
            subject = f"Investment Opportunity: {company_name}"
        elif intent == "moderate_interest":
            subject = f"Following up: {company_name}"
        elif intent == "needs_clarification":
            subject = f"Questions about {company_name}"
        elif intent == "soft_decline":
            subject = f"Re: {company_name}"
        else:
            subject = f"Introduction: {company_name}"
        
        # Generate body based on intent
        if intent == "strong_interest":
            body = f"""Hi {company_name} Team,

I came across your pitch deck and was impressed by your {key_point_str}. The {company_info.get('industry', 'technology')} space is one we're actively investing in, and your approach stands out.

Given your {company_info.get('stage', 'early stage')} progress, I'd love to learn more about your plans and see if there's a fit with our investment thesis. Are you available for a 30-minute call next week?

Best regards,
[Your Name]
[Your Firm]"""
        
        elif intent == "moderate_interest":
            body = f"""Hi {company_name} Team,

I've been reviewing your pitch deck and found your work in the {company_info.get('industry', 'technology')} sector interesting. Your {key_point_str} shows promising early traction.

I'd like to better understand your go-to-market strategy and near-term priorities. Would you be open to a brief call to discuss?

Best regards,
[Your Name]
[Your Firm]"""
        
        elif intent == "needs_clarification":
            body = f"""Hi {company_name} Team,

I've reviewed your pitch deck and have a few questions about your business. Could you help me understand:

1. Your current revenue trajectory and unit economics
2. Key milestones for the next 12 months
3. How you're planning to use the funding you're raising

I'd appreciate any additional context you can provide.

Best regards,
[Your Name]
[Your Firm]"""
        
        elif intent == "soft_decline":
            body = f"""Hi {company_name} Team,

Thank you for sharing your pitch deck. While I appreciate the work you're doing in {company_info.get('industry', 'technology')}, our current focus is on companies at a different stage.

I'll keep you on my radar and may reach out in the future if there's a better fit.

Best of luck,
[Your Name]
[Your Firm]"""
        
        else:  # initial_outreach
            body = f"""Hi {company_name} Team,

I hope this email finds you well. I'm a venture capitalist at [Your Firm] and came across your company while researching the {company_info.get('industry', 'technology')} space.

Your approach to addressing market needs caught my attention. I'd love to learn more about what you're building and your vision for the future.

Would you be open to a brief introduction call?

Best regards,
[Your Name]
[Your Firm]"""
        
        return f"Subject: {subject}\n\n{body}"


# Singleton instance
intelligent_email_generator = IntelligentEmailGenerator()
