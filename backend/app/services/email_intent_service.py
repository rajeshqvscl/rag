"""
Email Intent Classification Service
Analyzes email replies to determine client/investor interest level
Uses both keyword matching and Claude AI for accurate identification
"""
import re
import os
import json
from typing import Dict, List, Tuple
from datetime import datetime

# Import Claude client
from anthropic import Anthropic


class ClaudeIdentifier:
    """Claude-powered identification layer for sophisticated sender type detection"""
    
    def __init__(self):
        self.client = None
        self._init_claude()
    
    def _init_claude(self):
        """Initialize Claude client"""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            try:
                self.client = Anthropic(api_key=api_key)
            except Exception as e:
                print(f"⚠ Could not initialize Claude: {e}")
    
    def identify_sender_type(self, email_subject: str, email_body: str, sender_email: str = None, sender_name: str = None) -> Dict:
        """
        Use Claude to identify if sender is investor, client, or unknown
        Also extracts additional context and reasoning
        """
        if not self.client:
            return {
                "sender_type": "unknown",
                "confidence": 0.0,
                "reasoning": "Claude not available",
                "is_claude_identified": False
            }
        
        # Prepare prompt for Claude
        prompt = f"""You are an expert at identifying the type of sender in business emails, particularly in startup/VC contexts.

Analyze this email and determine if the sender is an INVESTOR, CLIENT/CUSTOMER, or UNKNOWN.

Email Subject: {email_subject}

Email Body:
{email_body[:2000]}

Sender Information:
- Email: {sender_email or "Not provided"}
- Name: {sender_name or "Not provided"}

INVESTOR indicators:
- Mentions investment, funding, valuation, equity, term sheet, due diligence
- Uses terms like "portfolio", "fund", "LP", "GP", "check", "round", "Series X"
- Discusses investment thesis, market size, returns, ROI, exit strategies
- References being a VC, angel investor, or part of an investment firm

CLIENT/CUSTOMER indicators:
- Interested in purchasing, using, or implementing the product/service
- Asks about pricing, features, support, contract terms
- Mentions pilot programs, trials, demos, implementation
- References their company/team using the solution

Respond ONLY with a JSON object in this exact format:
{{
    "sender_type": "investor" or "client" or "unknown",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of why this classification was chosen",
    "key_indicators": ["list", "of", "specific", "indicators", "found"],
    "additional_context": {{
        "investment_stage": "If investor, what stage? (Pre-seed, Seed, Series A, etc.)",
        "client_interest_level": "If client, how interested? (High, Medium, Low)",
        "company_mentioned": "Any company names detected"
    }}
}}
"""
        
        try:
            response = self.client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=1000,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            # Parse Claude's response
            content = response.content[0].text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                result["is_claude_identified"] = True
                return result
            else:
                return {
                    "sender_type": "unknown",
                    "confidence": 0.0,
                    "reasoning": "Could not parse Claude response",
                    "is_claude_identified": False
                }
                
        except Exception as e:
            print(f"Claude identification error: {e}")
            return {
                "sender_type": "unknown",
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
                "is_claude_identified": False
            }
    
    def identify_intent(self, email_subject: str, email_body: str) -> Dict:
        """
        Use Claude to identify interest level and extract nuanced understanding
        """
        if not self.client:
            return {
                "intent_status": "pending",
                "confidence": 0.0,
                "reasoning": "Claude not available",
                "is_claude_identified": False
            }
        
        prompt = f"""You are an expert at analyzing business communication intent, particularly in startup/VC contexts.

Analyze this email reply and determine the sender's interest level.

Email Subject: {email_subject}

Email Body:
{email_body[:2000]}

Classify the intent as:
- INTERESTED: Clear positive signals, wants to proceed, enthusiastic
- NOT_INTERESTED: Clear rejection, pass, not a fit, declined  
- PENDING: Uncertain, needs more info, thinking about it, follow-up needed

Respond ONLY with a JSON object:
{{
    "intent_status": "interested" or "not_interested" or "pending",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation",
    "key_phrases": ["specific", "phrases", "indicating", "intent"],
    "next_steps_suggested": "What should be the next action?",
    "urgency": "High, Medium, or Low"
}}
"""
        
        try:
            response = self.client.messages.create(
                model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                max_tokens=800,
                temperature=0.1,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            content = response.content[0].text.strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
            if json_match:
                result = json.loads(json_match.group())
                result["is_claude_identified"] = True
                return result
            else:
                return {
                    "intent_status": "pending",
                    "confidence": 0.0,
                    "reasoning": "Could not parse Claude response",
                    "is_claude_identified": False
                }
                
        except Exception as e:
            print(f"Claude intent analysis error: {e}")
            return {
                "intent_status": "pending",
                "confidence": 0.0,
                "reasoning": f"Error: {str(e)}",
                "is_claude_identified": False
            }


class EmailIntentService:
    """Service to classify email intent based on content analysis
    Uses a hybrid approach: Keyword matching + Claude AI identification"""
    
    def __init__(self):
        # Initialize Claude identifier layer
        self.claude_identifier = ClaudeIdentifier()
        # Keywords indicating interest
        self.interested_keywords = [
            'interested', 'yes', 'definitely', 'absolutely', 'let\'s proceed',
            'move forward', 'schedule a call', 'meet', 'discuss further',
            'would like to', 'keen', 'excited', 'opportunity', 'potential',
            'willing to', 'ready to', 'onboard', 'partner', 'collaborate',
            'invest', 'funding', 'capital', 'back', 'support', 'growth',
            'next steps', 'send details', 'learn more', 'tell me more',
            'impressive', 'promising', 'strong', 'solid', 'good fit',
            'aligns', 'matches', 'perfect', 'ideal', 'excellent'
        ]
        
        # Keywords indicating NO interest
        self.not_interested_keywords = [
            'not interested', 'not looking', 'pass', 'decline', 'reject',
            'unfortunately', 'sorry', 'regret', 'not a fit', 'not aligned',
            'different focus', 'outside', 'doesn\'t match', 'not the right',
            'not at this time', 'not currently', 'no thanks', 'not for us',
            'skip', 'maybe next time', 'future rounds', 'too early',
            'too late', 'wrong stage', 'different sector', 'competitor',
            'conflict', 'passing', 'not pursuing', 'closing', 'stopped'
        ]
        
        # Keywords indicating PENDING/UNCERTAIN status
        self.pending_keywords = [
            'maybe', 'possibly', 'consider', 'think about it', 'review',
            'get back to you', 'follow up', 'circle back', 'discuss',
            'need time', 'need more info', 'questions', 'concerns',
            'hesitant', 'uncertain', 'undecided', 'weighing', 'evaluating',
            'assessing', 'analyzing', 'comparing', 'waiting',
            'on hold', 'paused', 'delayed', 'postponed', 'revisit'
        ]
    
    def classify_intent(self, email_body: str, email_subject: str = "") -> Dict:
        """
        Classify the intent of an email reply
        
        Returns:
            {
                'intent_status': 'interested' | 'not_interested' | 'pending',
                'intent_keywords': ['keyword1', 'keyword2', ...],
                'intent_confidence': 0.0 to 1.0,
                'sender_type': 'client' | 'investor' | 'unknown'
            }
        """
        if not email_body:
            return {
                'intent_status': 'pending',
                'intent_keywords': [],
                'intent_confidence': 0.0,
                'sender_type': 'unknown'
            }
        
        # Combine subject and body for analysis
        full_text = f"{email_subject} {email_body}".lower()
        
        # Find matching keywords
        interested_matches = self._find_keywords(full_text, self.interested_keywords)
        not_interested_matches = self._find_keywords(full_text, self.not_interested_keywords)
        pending_matches = self._find_keywords(full_text, self.pending_keywords)
        
        # Calculate scores
        interested_score = len(interested_matches) * 2  # Weight interested higher
        not_interested_score = len(not_interested_matches) * 3  # Weight not interested highest
        pending_score = len(pending_matches)
        
        # Determine intent status
        if not_interested_score > interested_score and not_interested_score > 0:
            intent_status = 'not_interested'
            matched_keywords = not_interested_matches
            confidence = min(1.0, not_interested_score / 3)
        elif interested_score > 0:
            intent_status = 'interested'
            matched_keywords = interested_matches
            confidence = min(1.0, interested_score / 4)
        elif pending_score > 0:
            intent_status = 'pending'
            matched_keywords = pending_matches
            confidence = min(1.0, pending_score / 2)
        else:
            intent_status = 'pending'
            matched_keywords = []
            confidence = 0.0
        
        # Detect sender type
        sender_type = self._detect_sender_type(full_text)
        
        return {
            'intent_status': intent_status,
            'intent_keywords': matched_keywords,
            'intent_confidence': round(confidence, 2),
            'sender_type': sender_type
        }
    
    def classify_with_claude(self, email_body: str, email_subject: str = "", 
                            sender_email: str = None, sender_name: str = None,
                            use_claude: bool = True) -> Dict:
        """
        Enhanced classification using both keyword matching AND Claude AI
        
        This hybrid approach provides:
        1. Fast keyword-based classification (always runs)
        2. Accurate Claude AI identification (when enabled)
        3. Combined confidence scoring
        4. Detailed reasoning and context
        
        Args:
            email_body: The email content
            email_subject: Email subject line
            sender_email: Sender's email address
            sender_name: Sender's name
            use_claude: Whether to use Claude AI layer (default True)
        
        Returns:
            Enhanced classification with AI reasoning
        """
        # Step 1: Always get keyword-based classification (baseline)
        keyword_result = self.classify_intent(email_body, email_subject)
        
        # If Claude is disabled or not available, return keyword results
        if not use_claude or not self.claude_identifier.client:
            return {
                **keyword_result,
                'classification_method': 'keyword_only',
                'claude_analysis': None,
                'combined_confidence': keyword_result['intent_confidence'],
                'reasoning': 'Keyword-based classification (Claude unavailable)'
            }
        
        # Step 2: Get Claude AI identification
        claude_sender = self.claude_identifier.identify_sender_type(
            email_subject, email_body, sender_email, sender_name
        )
        
        claude_intent = self.claude_identifier.identify_intent(
            email_subject, email_body
        )
        
        # Step 3: Combine results with weighted confidence
        # If Claude has high confidence, prefer it; otherwise blend with keywords
        
        # Sender type decision
        if claude_sender.get('confidence', 0) > 0.7:
            final_sender_type = claude_sender['sender_type']
            sender_confidence = claude_sender['confidence']
            sender_method = 'claude_high_confidence'
        elif claude_sender.get('confidence', 0) > 0.4:
            # Blend: If both agree, high confidence; if disagree, use keyword
            if claude_sender['sender_type'] == keyword_result['sender_type']:
                final_sender_type = claude_sender['sender_type']
                sender_confidence = (claude_sender['confidence'] + 0.6) / 2
                sender_method = 'blended_agreement'
            else:
                final_sender_type = keyword_result['sender_type']
                sender_confidence = keyword_result['intent_confidence'] * 0.8
                sender_method = 'keyword_override'
        else:
            final_sender_type = keyword_result['sender_type']
            sender_confidence = keyword_result['intent_confidence']
            sender_method = 'keyword_low_claude_confidence'
        
        # Intent decision
        if claude_intent.get('confidence', 0) > 0.7:
            final_intent = claude_intent['intent_status']
            intent_confidence = claude_intent['confidence']
            intent_method = 'claude_high_confidence'
        elif claude_intent.get('confidence', 0) > 0.4:
            if claude_intent['intent_status'] == keyword_result['intent_status']:
                final_intent = claude_intent['intent_status']
                intent_confidence = (claude_intent['confidence'] + keyword_result['intent_confidence']) / 2
                intent_method = 'blended'
            else:
                final_intent = keyword_result['intent_status']
                intent_confidence = keyword_result['intent_confidence']
                intent_method = 'keyword_override'
        else:
            final_intent = keyword_result['intent_status']
            intent_confidence = keyword_result['intent_confidence']
            intent_method = 'keyword_low_claude_confidence'
        
        # Calculate combined confidence
        combined_confidence = (sender_confidence + intent_confidence) / 2
        
        # Build comprehensive result
        return {
            'intent_status': final_intent,
            'intent_keywords': keyword_result['intent_keywords'],
            'intent_confidence': round(intent_confidence, 2),
            'sender_type': final_sender_type,
            'sender_confidence': round(sender_confidence, 2),
            'combined_confidence': round(combined_confidence, 2),
            'classification_method': f"{sender_method}+{intent_method}",
            'keyword_result': {
                'intent_status': keyword_result['intent_status'],
                'sender_type': keyword_result['sender_type'],
                'confidence': keyword_result['intent_confidence']
            },
            'claude_analysis': {
                'sender': {
                    'type': claude_sender.get('sender_type'),
                    'confidence': claude_sender.get('confidence'),
                    'reasoning': claude_sender.get('reasoning'),
                    'key_indicators': claude_sender.get('key_indicators', []),
                    'additional_context': claude_sender.get('additional_context', {})
                },
                'intent': {
                    'status': claude_intent.get('intent_status'),
                    'confidence': claude_intent.get('confidence'),
                    'reasoning': claude_intent.get('reasoning'),
                    'key_phrases': claude_intent.get('key_phrases', []),
                    'next_steps_suggested': claude_intent.get('next_steps_suggested'),
                    'urgency': claude_intent.get('urgency')
                }
            },
            'reasoning': f"Sender: {claude_sender.get('reasoning', 'N/A')} | Intent: {claude_intent.get('reasoning', 'N/A')}",
            'is_claude_identified': claude_sender.get('is_claude_identified', False)
        }
    
    def _find_keywords(self, text: str, keywords: List[str]) -> List[str]:
        """Find all matching keywords in text"""
        matches = []
        for keyword in keywords:
            # Use word boundaries for better matching
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(keyword)
        return matches
    
    def _detect_sender_type(self, text: str) -> str:
        """Detect if sender is client, investor, or unknown"""
        investor_keywords = [
            'investor', 'vc', 'venture capital', 'angel', 'fund', 'lp',
            'general partner', 'check', 'term sheet', 'due diligence',
            'valuation', 'equity', 'stake', 'ownership', 'roi', 'return',
            'portfolio', 'fund', 'capital', 'financing', 'round',
            'seed', 'series a', 'series b', 'pre-seed', 'early stage',
            'growth stage', 'late stage', 'exit', 'acquisition'
        ]
        
        client_keywords = [
            'client', 'customer', 'user', 'pilot', 'trial', 'demo',
            'purchase', 'buy', 'contract', 'agreement', 'license',
            'subscription', 'service', 'product', 'solution',
            'implementation', 'deployment', 'integration', 'api',
            'price', 'pricing', 'cost', 'budget', 'invoice'
        ]
        
        investor_score = sum(1 for kw in investor_keywords if kw in text)
        client_score = sum(1 for kw in client_keywords if kw in text)
        
        if investor_score > client_score and investor_score > 0:
            return 'investor'
        elif client_score > investor_score and client_score > 0:
            return 'client'
        else:
            return 'unknown'
    
    def extract_company_name(self, text: str) -> str:
        """Extract company name from email if possible"""
        # Look for common patterns
        patterns = [
            r'(?:from|at|with)\s+([A-Z][A-Za-z0-9\s]+(?:Inc\.?|LLC|Ltd\.?|Corp\.?|Company|Co\.?)?)',
            r'([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)?)\s+(?:team|company|startup|firm)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def get_intent_summary(self, email_reply: 'EmailReply') -> Dict:
        """Get a summary of intent classification for display"""
        return {
            'status': email_reply.intent_status,
            'status_display': self._get_status_display(email_reply.intent_status),
            'confidence': f"{email_reply.intent_confidence * 100:.0f}%",
            'keywords_found': email_reply.intent_keywords,
            'sender_type': email_reply.sender_type,
            'company': email_reply.company,
            'received': email_reply.received_at.strftime('%Y-%m-%d %H:%M') if email_reply.received_at else 'N/A'
        }
    
    def _get_status_display(self, status: str) -> str:
        """Get human-readable status"""
        status_map = {
            'interested': 'Interested',
            'not_interested': 'Not Interested',
            'pending': 'Pending/Uncertain'
        }
        return status_map.get(status, status.capitalize())


# Singleton instance
email_intent_service = EmailIntentService()
