"""
AI sentiment analysis and risk assessment service
"""
import os
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.database import Draft, Library, Conversation, User
from app.config.database import get_db
import numpy as np

class SentimentService:
    def __init__(self):
        # Sentiment keywords and weights
        self.positive_words = {
            'strong': 0.8, 'excellent': 0.9, 'good': 0.7, 'positive': 0.6, 'growth': 0.7,
            'profitable': 0.8, 'successful': 0.8, 'opportunity': 0.6, 'innovative': 0.7,
            'leading': 0.7, 'market leader': 0.8, 'competitive advantage': 0.8,
            'scalable': 0.7, 'sustainable': 0.7, 'robust': 0.7, 'solid': 0.6,
            'impressive': 0.8, 'outstanding': 0.9, 'favorable': 0.6, 'promising': 0.7
        }
        
        self.negative_words = {
            'weak': -0.8, 'poor': -0.7, 'negative': -0.6, 'decline': -0.7, 'loss': -0.8,
            'risk': -0.6, 'risky': -0.7, 'uncertain': -0.5, 'volatile': -0.6,
            'concern': -0.5, 'problem': -0.6, 'issue': -0.5, 'challenge': -0.4,
            'difficult': -0.5, 'struggling': -0.7, 'failing': -0.9, 'bankruptcy': -0.9,
            'debt': -0.6, 'liability': -0.5, 'burden': -0.5, 'threat': -0.7
        }
        
        # Risk indicators
        self.risk_keywords = {
            'financial': ['debt', 'liability', 'cash flow', 'burn rate', 'runway', 'default'],
            'market': ['competition', 'market share', 'saturation', 'disruption'],
            'operational': ['scalability', 'dependencies', 'single point of failure'],
            'regulatory': ['compliance', 'regulation', 'legal', 'license'],
            'technical': ['technology risk', 'obsolescence', 'security']
        }
        
    def analyze_text_sentiment(self, text: str) -> Dict:
        """Analyze sentiment of text content"""
        try:
            if not text:
                return {"sentiment": "neutral", "score": 0.0, "confidence": 0.0}
            
            # Convert to lowercase for analysis
            text_lower = text.lower()
            
            # Calculate sentiment score
            positive_score = 0
            negative_score = 0
            positive_matches = []
            negative_matches = []
            
            # Check positive words
            for word, weight in self.positive_words.items():
                if word in text_lower:
                    count = text_lower.count(word)
                    positive_score += weight * count
                    positive_matches.append(word)
            
            # Check negative words
            for word, weight in self.negative_words.items():
                if word in text_lower:
                    count = text_lower.count(word)
                    negative_score += weight * count
                    negative_matches.append(word)
            
            # Calculate net sentiment
            total_words = len(text_lower.split())
            net_score = positive_score + negative_score
            
            # Normalize score
            if total_words > 0:
                normalized_score = net_score / (total_words * 0.1)  # Normalize by word count
                normalized_score = max(-1.0, min(1.0, normalized_score))  # Clamp to [-1, 1]
            else:
                normalized_score = 0.0
            
            # Determine sentiment category
            if normalized_score > 0.3:
                sentiment = "positive"
            elif normalized_score < -0.3:
                sentiment = "negative"
            else:
                sentiment = "neutral"
            
            # Calculate confidence based on word matches
            total_matches = len(positive_matches) + len(negative_matches)
            confidence = min(1.0, total_matches / max(total_words * 0.05, 1))
            
            return {
                "sentiment": sentiment,
                "score": round(normalized_score, 3),
                "confidence": round(confidence, 3),
                "positive_matches": positive_matches,
                "negative_matches": negative_matches,
                "word_count": total_words
            }
            
        except Exception as e:
            return {"error": str(e), "sentiment": "neutral", "score": 0.0, "confidence": 0.0}
    
    def assess_financial_risk(self, text: str) -> Dict:
        """Assess financial risk indicators in text"""
        try:
            risk_indicators = {
                'high_risk': [],
                'medium_risk': [],
                'low_risk': [],
                'overall_risk_score': 0.0
            }
            
            if not text:
                return risk_indicators
            
            text_lower = text.lower()
            
            # High risk indicators
            high_risk_patterns = [
                (r'bankruptcy|insolvency|liquidation', 0.9),
                (r'default.*on.*loan|loan.*default', 0.8),
                (r'negative.*cash.*flow|cash.*flow.*negative', 0.8),
                (r'burn.*rate.*high|high.*burn.*rate', 0.7),
                (r'debt.*to.*equity.*high|high.*debt.*ratio', 0.7)
            ]
            
            for pattern, score in high_risk_patterns:
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    risk_indicators['high_risk'].append({
                        'indicator': match,
                        'score': score,
                        'context': self._extract_context(text_lower, match)
                    })
            
            # Medium risk indicators
            medium_risk_patterns = [
                (r'decline|decreasing|falling', 0.5),
                (r'challenge|difficulty|problem', 0.4),
                (r'uncertain|uncertainty', 0.4),
                (r'concern|worry', 0.3),
                (r'volatile|volatility', 0.5)
            ]
            
            for pattern, score in medium_risk_patterns:
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    risk_indicators['medium_risk'].append({
                        'indicator': match,
                        'score': score,
                        'context': self._extract_context(text_lower, match)
                    })
            
            # Low risk indicators
            low_risk_patterns = [
                (r'stable|steady', 0.2),
                (r'manageable|controlled', 0.2),
                (r'moderate|reasonable', 0.1)
            ]
            
            for pattern, score in low_risk_patterns:
                matches = re.findall(pattern, text_lower)
                for match in matches:
                    risk_indicators['low_risk'].append({
                        'indicator': match,
                        'score': score,
                        'context': self._extract_context(text_lower, match)
                    })
            
            # Calculate overall risk score
            total_score = 0
            total_weight = 0
            
            for indicator in risk_indicators['high_risk']:
                total_score += indicator['score'] * 3
                total_weight += 3
            
            for indicator in risk_indicators['medium_risk']:
                total_score += indicator['score'] * 2
                total_weight += 2
            
            for indicator in risk_indicators['low_risk']:
                total_score += indicator['score'] * 1
                total_weight += 1
            
            if total_weight > 0:
                risk_indicators['overall_risk_score'] = min(1.0, total_score / total_weight)
            else:
                risk_indicators['overall_risk_score'] = 0.0
            
            return risk_indicators
            
        except Exception as e:
            return {"error": str(e), "overall_risk_score": 0.0}
    
    def _extract_context(self, text: str, keyword: str, context_length: int = 50) -> str:
        """Extract context around a keyword"""
        try:
            index = text.find(keyword)
            if index == -1:
                return ""
            
            start = max(0, index - context_length)
            end = min(len(text), index + len(keyword) + context_length)
            
            return text[start:end].strip()
        except:
            return ""
    
    def analyze_company_sentiment(self, company: str, user_id: int = 1) -> Dict:
        """Analyze sentiment across all data for a company"""
        try:
            db = next(get_db())
            
            # Get all data for the company
            drafts = db.query(Draft).filter(Draft.company == company, Draft.user_id == user_id).all()
            library = db.query(Library).filter(Library.company == company, Library.user_id == user_id).all()
            conversations = db.query(Conversation).filter(Conversation.user_id == user_id).all()
            
            # Filter conversations that mention the company
            company_conversations = []
            for conv in conversations:
                if company.lower() in conv.query.lower() or company.lower() in conv.response.lower():
                    company_conversations.append(conv)
            
            # Analyze sentiment for each data type
            sentiment_analysis = {
                "company": company,
                "overall_sentiment": "neutral",
                "overall_score": 0.0,
                "data_sources": {
                    "drafts": {"count": len(drafts), "sentiments": []},
                    "library": {"count": len(library), "sentiments": []},
                    "conversations": {"count": len(company_conversations), "sentiments": []}
                },
                "risk_assessment": {},
                "recommendations": []
            }
            
            all_scores = []
            all_risk_scores = []
            
            # Analyze drafts
            for draft in drafts:
                text_content = f"{draft.company} {draft.analysis or ''} {draft.email_draft or ''}"
                sentiment = self.analyze_text_sentiment(text_content)
                risk = self.assess_financial_risk(text_content)
                
                sentiment_analysis["data_sources"]["drafts"]["sentiments"].append({
                    "id": draft.id,
                    "sentiment": sentiment,
                    "risk": risk
                })
                
                if "score" in sentiment:
                    all_scores.append(sentiment["score"])
                
                if "overall_risk_score" in risk:
                    all_risk_scores.append(risk["overall_risk_score"])
            
            # Analyze library items (metadata and file names)
            for item in library:
                text_content = f"{item.company} {item.file_name} {item.tags or ''}"
                sentiment = self.analyze_text_sentiment(text_content)
                risk = self.assess_financial_risk(text_content)
                
                sentiment_analysis["data_sources"]["library"]["sentiments"].append({
                    "id": item.id,
                    "sentiment": sentiment,
                    "risk": risk
                })
                
                if "score" in sentiment:
                    all_scores.append(sentiment["score"])
                
                if "overall_risk_score" in risk:
                    all_risk_scores.append(risk["overall_risk_score"])
            
            # Analyze conversations
            for conv in company_conversations:
                text_content = f"{conv.query} {conv.response}"
                sentiment = self.analyze_text_sentiment(text_content)
                risk = self.assess_financial_risk(text_content)
                
                sentiment_analysis["data_sources"]["conversations"]["sentiments"].append({
                    "id": conv.id,
                    "sentiment": sentiment,
                    "risk": risk
                })
                
                if "score" in sentiment:
                    all_scores.append(sentiment["score"])
                
                if "overall_risk_score" in risk:
                    all_risk_scores.append(risk["overall_risk_score"])
            
            # Calculate overall sentiment
            if all_scores:
                overall_score = np.mean(all_scores)
                sentiment_analysis["overall_score"] = round(overall_score, 3)
                
                if overall_score > 0.3:
                    sentiment_analysis["overall_sentiment"] = "positive"
                elif overall_score < -0.3:
                    sentiment_analysis["overall_sentiment"] = "negative"
                else:
                    sentiment_analysis["overall_sentiment"] = "neutral"
            
            # Calculate overall risk
            if all_risk_scores:
                avg_risk = np.mean(all_risk_scores)
                
                if avg_risk > 0.7:
                    risk_level = "high"
                elif avg_risk > 0.4:
                    risk_level = "medium"
                else:
                    risk_level = "low"
                
                sentiment_analysis["risk_assessment"] = {
                    "overall_risk_score": round(avg_risk, 3),
                    "risk_level": risk_level,
                    "risk_factors": self._identify_risk_factors(sentiment_analysis)
                }
            
            # Generate recommendations
            sentiment_analysis["recommendations"] = self._generate_recommendations(
                sentiment_analysis["overall_sentiment"],
                sentiment_analysis["risk_assessment"].get("risk_level", "low")
            )
            
            return sentiment_analysis
            
        except Exception as e:
            return {"error": str(e)}
        finally:
            db.close()
    
    def _identify_risk_factors(self, sentiment_analysis: Dict) -> List[str]:
        """Identify key risk factors"""
        risk_factors = []
        
        # Analyze all risk indicators
        for source_type, source_data in sentiment_analysis["data_sources"].items():
            for item in source_data.get("sentiments", []):
                risk = item.get("risk", {})
                
                # High risk factors
                for indicator in risk.get("high_risk", []):
                    if indicator["score"] > 0.7:
                        risk_factors.append(f"High: {indicator['indicator']}")
                
                # Medium risk factors
                for indicator in risk.get("medium_risk", []):
                    if indicator["score"] > 0.5:
                        risk_factors.append(f"Medium: {indicator['indicator']}")
        
        # Remove duplicates and limit to top 10
        risk_factors = list(set(risk_factors))[:10]
        
        return risk_factors
    
    def _generate_recommendations(self, sentiment: str, risk_level: str) -> List[str]:
        """Generate recommendations based on sentiment and risk"""
        recommendations = []
        
        if sentiment == "positive" and risk_level == "low":
            recommendations.append("Company shows positive indicators with low risk - good investment candidate")
            recommendations.append("Consider increasing exposure based on strong performance")
        
        elif sentiment == "positive" and risk_level == "medium":
            recommendations.append("Positive sentiment but moderate risk - monitor closely")
            recommendations.append("Consider diversification to mitigate risks")
        
        elif sentiment == "positive" and risk_level == "high":
            recommendations.append("Positive outlook but high risk factors present")
            recommendations.append("Conduct detailed due diligence before investment")
        
        elif sentiment == "negative" and risk_level == "low":
            recommendations.append("Negative sentiment but low structural risk")
            recommendations.append("Investigate causes of negative sentiment")
        
        elif sentiment == "negative" and risk_level == "medium":
            recommendations.append("Negative sentiment with moderate risk - caution advised")
            recommendations.append("Wait for improvement in sentiment before considering")
        
        elif sentiment == "negative" and risk_level == "high":
            recommendations.append("High risk company with negative indicators - avoid investment")
            recommendations.append("Monitor for turnaround signals")
        
        else:  # neutral
            recommendations.append("Neutral sentiment - gather more information")
            recommendations.append("Look for catalysts that could change sentiment")
        
        return recommendations
    
    def batch_sentiment_analysis(self, companies: List[str], user_id: int = 1) -> Dict:
        """Perform sentiment analysis for multiple companies"""
        try:
            results = {
                "companies_analyzed": len(companies),
                "sentiment_summary": {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0
                },
                "risk_summary": {
                    "high": 0,
                    "medium": 0,
                    "low": 0
                },
                "company_analyses": {}
            }
            
            for company in companies:
                analysis = self.analyze_company_sentiment(company, user_id)
                
                if "error" not in analysis:
                    results["company_analyses"][company] = analysis
                    
                    # Update summaries
                    sentiment = analysis.get("overall_sentiment", "neutral")
                    results["sentiment_summary"][sentiment] += 1
                    
                    risk_level = analysis.get("risk_assessment", {}).get("risk_level", "low")
                    results["risk_summary"][risk_level] += 1
            
            return results
            
        except Exception as e:
            return {"error": str(e)}

# Global sentiment service instance
sentiment_service = SentimentService()
