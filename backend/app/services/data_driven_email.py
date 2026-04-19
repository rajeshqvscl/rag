"""
Data-Driven Email Generator
Generates specific questions based on missing data
"""
from typing import Dict, List, Optional


class DataDrivenEmailGenerator:
    """Generate emails with specific questions for missing data"""
    
    def generate(self, company_name: str, key_metrics: Dict) -> str:
        """
        Generate HONEST data-driven email draft
        
        Args:
            company_name: Name of the company
            key_metrics: Dictionary with revenue, growth, users, tam, etc.
            
        Returns:
            Email draft - HONEST about missing data, NO generic fluff
        """
        # Check if we have ANY real data
        has_revenue = bool(key_metrics.get('revenue'))
        has_growth = bool(key_metrics.get('growth'))
        has_users = bool(key_metrics.get('users'))
        has_tam = bool(key_metrics.get('tam'))
        has_raising = bool(key_metrics.get('raising'))
        
        has_any_data = has_revenue or has_growth or has_users or has_tam
        
        # Build email
        subject = f"Follow-up: {company_name} Investment Opportunity"
        
        # HONEST OPENING - no fake enthusiasm
        if not has_any_data:
            # NO DATA EXTRACTED - be honest
            body = f"""Hi {company_name} Team,

I reviewed your pitch deck, but I wasn't able to extract clear financial metrics from the document.

To better evaluate the investment opportunity, I'd like to understand:

1. **Current Revenue**: What is your current ARR or revenue run-rate?
2. **Growth Rate**: What is your YoY revenue growth?
3. **Customer Base**: How many paying customers or active users do you have?
4. **Funding Needs**: How much are you currently raising, and what's the intended use of funds?

Would you be available for a brief call to discuss these details?

Best regards,
[Your Name]
"""
        elif has_revenue and has_growth:
            # HAVE KEY METRICS - reference them
            body = f"""Hi {company_name} Team,

I reviewed your pitch deck and noted the following metrics:

- Revenue: {key_metrics.get('revenue', 'Not specified')}
- Growth: {key_metrics.get('growth', 'Not specified')}
"""
            if has_users:
                body += f"- Users: {key_metrics.get('users')}\n"
            
            body += "\nTo complete my evaluation, I'd appreciate clarification on:\n\n"
            
            questions = []
            if not has_tam:
                questions.append("1. **Market Size**: What is your estimated TAM/SAM/SOM?")
            if not has_raising:
                questions.append(f"{len(questions)+1}. **Funding**: How much are you raising, and at what valuation?")
            
            body += "\n".join(questions) if questions else "General questions about your business model and competitive positioning."
            
            body += "\n\nWould you be available for a brief call?\n\nBest regards,\n[Your Name]\n"
        else:
            # PARTIAL DATA
            body = f"""Hi {company_name} Team,

I reviewed your pitch deck. I was able to extract some information, but key financial metrics appear to be missing or unclear.

What I found:
"""
            if has_revenue:
                body += f"- Revenue: {key_metrics.get('revenue')}\n"
            if has_growth:
                body += f"- Growth: {key_metrics.get('growth')}\n"
            if has_users:
                body += f"- Users: {key_metrics.get('users')}\n"
            
            body += "\nWhat's missing:\n"
            if not has_revenue:
                body += "- Current revenue or ARR\n"
            if not has_growth:
                body += "- Growth rate\n"
            if not has_tam:
                body += "- Market size (TAM)\n"
            
            body += "\nCould you provide these details? A brief call would be helpful.\n\nBest regards,\n[Your Name]\n"
        
        return f"Subject: {subject}\n\n{body}"


# Singleton
data_driven_email_generator = DataDrivenEmailGenerator()
