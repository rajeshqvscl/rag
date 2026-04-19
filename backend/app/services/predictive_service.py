"""
Predictive analytics service for financial forecasting and insights
"""
import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.database import Draft, Library, Conversation, Analytics, User
from app.config.database import get_db
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

class PredictiveService:
    def __init__(self):
        self.models = {
            'linear': LinearRegression(),
            'random_forest': RandomForestRegressor(n_estimators=100, random_state=42)
        }
        self.scaler = StandardScaler()
        
    def get_historical_data(self, user_id: int = 1) -> Dict:
        """Get historical data for predictive analysis"""
        db = next(get_db())
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {}
            
            # Get drafts data
            drafts = db.query(Draft).filter(Draft.user_id == user_id).all()
            drafts_data = []
            
            for draft in drafts:
                drafts_data.append({
                    'date': draft.created_at,
                    'company': draft.company,
                    'confidence': draft.confidence,
                    'status': draft.status,
                    'revenue_data': draft.revenue_data or []
                })
            
            # Get library data
            library = db.query(Library).filter(Library.user_id == user_id).all()
            library_data = []
            
            for item in library:
                library_data.append({
                    'date': item.date_uploaded,
                    'company': item.company,
                    'confidence': item.confidence,
                    'file_type': item.file_type
                })
            
            # Get analytics data
            analytics = db.query(Analytics).filter(Analytics.user_id == user_id).all()
            analytics_data = []
            
            for analytic in analytics:
                analytics_data.append({
                    'date': analytic.timestamp,
                    'event_type': analytic.event_type,
                    'event_data': analytic.event_data
                })
            
            return {
                'drafts': drafts_data,
                'library': library_data,
                'analytics': analytics_data
            }
            
        finally:
            db.close()
    
    def prepare_time_series_data(self, data: List[Dict], date_field: str) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare time series data for modeling"""
        if not data:
            return np.array([]), np.array([])
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        df[date_field] = pd.to_datetime(df[date_field])
        
        # Sort by date
        df = df.sort_values(date_field)
        
        # Create time series features
        df['day_of_week'] = df[date_field].dt.dayofweek
        df['month'] = df[date_field].dt.month
        df['quarter'] = df[date_field].dt.quarter
        df['day_of_year'] = df[date_field].dt.dayofyear
        
        # Create lag features
        df['count_lag_1'] = df.groupby([df[date_field].dt.date]).cumcount().shift(1)
        df['count_lag_7'] = df.groupby([df[date_field].dt.date]).cumcount().shift(7)
        
        # Fill NaN values
        df = df.fillna(0)
        
        # Prepare features and target
        feature_columns = ['day_of_week', 'month', 'quarter', 'day_of_year', 'count_lag_1', 'count_lag_7']
        
        if len(df) < 2:
            return np.array([]), np.array([])
        
        X = df[feature_columns].values
        y = np.arange(len(df))  # Simple trend as target
        
        return X, y
    
    def predict_activity_trends(self, user_id: int = 1, days_ahead: int = 30) -> Dict:
        """Predict activity trends for the next N days"""
        try:
            historical_data = self.get_historical_data(user_id)
            
            predictions = {
                'drafts_trend': [],
                'library_trend': [],
                'overall_trend': [],
                'confidence_scores': [],
                'model_accuracy': {}
            }
            
            # Predict drafts trend
            if historical_data['drafts']:
                X, y = self.prepare_time_series_data(historical_data['drafts'], 'created_at')
                
                if len(X) > 0:
                    # Train model
                    model = self.models['linear']
                    model.fit(X, y)
                    
                    # Generate future dates
                    last_date = max(item['created_at'] for item in historical_data['drafts'])
                    future_dates = [last_date + timedelta(days=i) for i in range(1, days_ahead + 1)]
                    
                    # Predict for each future date
                    for future_date in future_dates:
                        features = np.array([
                            future_date.weekday(),
                            future_date.month,
                            (future_date.month - 1) // 3 + 1,
                            future_date.timetuple().tm_yday,
                            len(historical_data['drafts']),  # Simple lag
                            len(historical_data['drafts'])   # Simple lag
                        ]).reshape(1, -1)
                        
                        prediction = model.predict(features)[0]
                        predictions['drafts_trend'].append({
                            'date': future_date.isoformat(),
                            'predicted_activity': max(0, prediction),
                            'confidence': 0.75  # Default confidence
                        })
                    
                    # Calculate model accuracy
                    train_score = model.score(X, y)
                    predictions['model_accuracy']['drafts'] = train_score
            
            # Predict library trend
            if historical_data['library']:
                X, y = self.prepare_time_series_data(historical_data['library'], 'date_uploaded')
                
                if len(X) > 0:
                    model = self.models['linear']
                    model.fit(X, y)
                    
                    last_date = max(item['date'] for item in historical_data['library'])
                    future_dates = [last_date + timedelta(days=i) for i in range(1, days_ahead + 1)]
                    
                    for future_date in future_dates:
                        features = np.array([
                            future_date.weekday(),
                            future_date.month,
                            (future_date.month - 1) // 3 + 1,
                            future_date.timetuple().tm_yday,
                            len(historical_data['library']),
                            len(historical_data['library'])
                        ]).reshape(1, -1)
                        
                        prediction = model.predict(features)[0]
                        predictions['library_trend'].append({
                            'date': future_date.isoformat(),
                            'predicted_activity': max(0, prediction),
                            'confidence': 0.75
                        })
                    
                    train_score = model.score(X, y)
                    predictions['model_accuracy']['library'] = train_score
            
            # Generate overall trend
            if predictions['drafts_trend'] and predictions['library_trend']:
                for i in range(days_ahead):
                    draft_pred = predictions['drafts_trend'][i]['predicted_activity'] if i < len(predictions['drafts_trend']) else 0
                    library_pred = predictions['library_trend'][i]['predicted_activity'] if i < len(predictions['library_trend']) else 0
                    
                    predictions['overall_trend'].append({
                        'date': predictions['drafts_trend'][i]['date'] if i < len(predictions['drafts_trend']) else (datetime.utcnow() + timedelta(days=i+1)).isoformat(),
                        'predicted_activity': draft_pred + library_pred,
                        'confidence': 0.70
                    })
            
            return predictions
            
        except Exception as e:
            return {'error': str(e)}
    
    def predict_company_performance(self, company: str, user_id: int = 1) -> Dict:
        """Predict company performance based on historical data"""
        try:
            historical_data = self.get_historical_data(user_id)
            
            # Filter data for specific company
            company_drafts = [d for d in historical_data['drafts'] if d['company'] == company]
            company_library = [l for l in historical_data['library'] if l['company'] == company]
            
            if not company_drafts and not company_library:
                return {'error': 'No historical data found for this company'}
            
            performance_predictions = {
                'company': company,
                'data_points': len(company_drafts) + len(company_library),
                'confidence_score': 0,
                'predictions': {}
            }
            
            # Analyze confidence trends
            if company_drafts:
                confidence_scores = []
                for draft in company_drafts:
                    if draft['confidence'] == 'High':
                        confidence_scores.append(3)
                    elif draft['confidence'] == 'Medium':
                        confidence_scores.append(2)
                    else:
                        confidence_scores.append(1)
                
                if confidence_scores:
                    avg_confidence = np.mean(confidence_scores)
                    performance_predictions['confidence_score'] = avg_confidence / 3.0
                    
                    # Predict future confidence
                    if len(confidence_scores) > 1:
                        # Simple trend analysis
                        trend = np.polyfit(range(len(confidence_scores)), confidence_scores, 1)[0]
                        
                        if trend > 0.1:
                            performance_predictions['predictions']['confidence_trend'] = 'improving'
                        elif trend < -0.1:
                            performance_predictions['predictions']['confidence_trend'] = 'declining'
                        else:
                            performance_predictions['predictions']['confidence_trend'] = 'stable'
            
            # Analyze activity frequency
            all_dates = []
            for draft in company_drafts:
                all_dates.append(draft['created_at'])
            for item in company_library:
                all_dates.append(item['date'])
            
            if all_dates:
                # Calculate activity frequency
                date_range = max(all_dates) - min(all_dates)
                activity_frequency = len(all_dates) / max(date_range.days, 1)
                
                performance_predictions['predictions']['activity_frequency'] = activity_frequency
                
                # Predict future activity
                if activity_frequency > 0.5:
                    performance_predictions['predictions']['future_activity'] = 'high'
                elif activity_frequency > 0.1:
                    performance_predictions['predictions']['future_activity'] = 'medium'
                else:
                    performance_predictions['predictions']['future_activity'] = 'low'
            
            # Generate recommendations
            recommendations = []
            
            if performance_predictions['confidence_score'] > 0.7:
                recommendations.append("Strong confidence scores indicate reliable data quality")
            elif performance_predictions['confidence_score'] < 0.4:
                recommendations.append("Consider improving data quality for better predictions")
            
            if performance_predictions['predictions'].get('confidence_trend') == 'improving':
                recommendations.append("Company shows positive performance trend")
            elif performance_predictions['predictions'].get('confidence_trend') == 'declining':
                recommendations.append("Monitor company performance closely")
            
            performance_predictions['recommendations'] = recommendations
            
            return performance_predictions
            
        except Exception as e:
            return {'error': str(e)}
    
    def predict_revenue_growth(self, company: str, user_id: int = 1) -> Dict:
        """Predict revenue growth based on pitch deck data"""
        try:
            historical_data = self.get_historical_data(user_id)
            
            # Find drafts with revenue data for the company
            company_drafts = [d for d in historical_data['drafts'] if d['company'] == company]
            revenue_data_points = []
            
            for draft in company_drafts:
                if draft['revenue_data']:
                    for revenue_point in draft['revenue_data']:
                        if isinstance(revenue_point, dict) and 'amount' in revenue_point:
                            revenue_data_points.append({
                                'date': draft['created_at'],
                                'amount': float(revenue_point['amount']),
                                'period': revenue_point.get('period', 'unknown')
                            })
            
            if len(revenue_data_points) < 2:
                return {'error': 'Insufficient revenue data for prediction'}
            
            # Sort by date
            revenue_data_points.sort(key=lambda x: x['date'])
            
            # Prepare data for modeling
            amounts = [point['amount'] for point in revenue_data_points]
            time_indices = np.arange(len(amounts)).reshape(-1, 1)
            
            # Train model
            model = self.models['linear']
            model.fit(time_indices, amounts)
            
            # Predict future revenue
            future_periods = len(amounts) + 5  # Predict 5 periods ahead
            future_indices = np.arange(len(amounts), future_periods).reshape(-1, 1)
            predicted_revenue = model.predict(future_indices)
            
            # Calculate growth rate
            if len(amounts) > 1:
                growth_rate = (amounts[-1] - amounts[0]) / amounts[0] * 100
            else:
                growth_rate = 0
            
            # Calculate model accuracy
            model_score = model.score(time_indices, amounts)
            
            predictions = {
                'company': company,
                'historical_data_points': len(revenue_data_points),
                'current_revenue': amounts[-1] if amounts else 0,
                'predicted_revenue': predicted_revenue.tolist(),
                'growth_rate': growth_rate,
                'model_accuracy': model_score,
                'confidence': min(model_score, 0.9),
                'insights': []
            }
            
            # Generate insights
            if growth_rate > 20:
                predictions['insights'].append("Strong positive growth trend detected")
            elif growth_rate < -10:
                predictions['insights'].append("Declining revenue trend - requires attention")
            else:
                predictions['insights'].append("Stable revenue performance")
            
            if model_score > 0.8:
                predictions['insights'].append("High prediction accuracy - reliable forecasts")
            elif model_score < 0.5:
                predictions['insights'].append("Low prediction accuracy - more data needed")
            
            return predictions
            
        except Exception as e:
            return {'error': str(e)}
    
    def generate_market_insights(self, user_id: int = 1) -> Dict:
        """Generate market insights based on portfolio analysis"""
        try:
            historical_data = self.get_historical_data(user_id)
            
            insights = {
                'total_companies': 0,
                'top_performers': [],
                'risk_assessment': {},
                'market_trends': [],
                'recommendations': []
            }
            
            # Analyze companies
            companies = set()
            company_performance = {}
            
            for draft in historical_data['drafts']:
                companies.add(draft['company'])
                if draft['company'] not in company_performance:
                    company_performance[draft['company']] = {
                        'drafts': 0,
                        'high_confidence': 0,
                        'medium_confidence': 0,
                        'low_confidence': 0
                    }
                
                company_performance[draft['company']]['drafts'] += 1
                if draft['confidence'] == 'High':
                    company_performance[draft['company']]['high_confidence'] += 1
                elif draft['confidence'] == 'Medium':
                    company_performance[draft['company']]['medium_confidence'] += 1
                else:
                    company_performance[draft['company']]['low_confidence'] += 1
            
            for item in historical_data['library']:
                companies.add(item['company'])
            
            insights['total_companies'] = len(companies)
            
            # Identify top performers
            for company, performance in company_performance.items():
                total_drafts = performance['drafts']
                if total_drafts > 0:
                    confidence_ratio = performance['high_confidence'] / total_drafts
                    company_performance[company]['confidence_ratio'] = confidence_ratio
            
            # Sort by confidence ratio
            sorted_companies = sorted(
                company_performance.items(),
                key=lambda x: x[1].get('confidence_ratio', 0),
                reverse=True
            )
            
            insights['top_performers'] = [
                {
                    'company': company,
                    'confidence_ratio': performance.get('confidence_ratio', 0),
                    'total_drafts': performance['drafts'],
                    'performance_score': performance.get('confidence_ratio', 0) * 100
                }
                for company, performance in sorted_companies[:5]
            ]
            
            # Risk assessment
            high_risk_companies = []
            medium_risk_companies = []
            low_risk_companies = []
            
            for company, performance in company_performance.items():
                confidence_ratio = performance.get('confidence_ratio', 0)
                
                if confidence_ratio < 0.3:
                    high_risk_companies.append(company)
                elif confidence_ratio < 0.6:
                    medium_risk_companies.append(company)
                else:
                    low_risk_companies.append(company)
            
            insights['risk_assessment'] = {
                'high_risk': high_risk_companies,
                'medium_risk': medium_risk_companies,
                'low_risk': low_risk_companies,
                'risk_distribution': {
                    'high': len(high_risk_companies),
                    'medium': len(medium_risk_companies),
                    'low': len(low_risk_companies)
                }
            }
            
            # Generate recommendations
            if len(high_risk_companies) > len(low_risk_companies):
                insights['recommendations'].append("Portfolio shows high risk - consider diversification")
            
            if len(insights['top_performers']) > 0:
                top_performer = insights['top_performers'][0]
                if top_performer['confidence_ratio'] > 0.8:
                    insights['recommendations'].append(f"Consider increasing exposure to {top_performer['company']} - strong performance")
            
            insights['recommendations'].append("Regular monitoring recommended for all portfolio companies")
            
            return insights
            
        except Exception as e:
            return {'error': str(e)}

# Global predictive service instance
predictive_service = PredictiveService()
