"""
CRM integration service for customer relationship management
"""
import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.database import Draft, Library, User
from app.config.database import get_db

class CRMService:
    def __init__(self):
        self.crm_config = {
            "salesforce": {
                "base_url": os.getenv("SALESFORCE_URL", ""),
                "client_id": os.getenv("SALESFORCE_CLIENT_ID", ""),
                "client_secret": os.getenv("SALESFORCE_CLIENT_SECRET", ""),
                "username": os.getenv("SALESFORCE_USERNAME", ""),
                "password": os.getenv("SALESFORCE_PASSWORD", "")
            },
            "hubspot": {
                "api_key": os.getenv("HUBSPOT_API_KEY", ""),
                "base_url": "https://api.hubapi.com"
            },
            "zoho": {
                "client_id": os.getenv("ZOHO_CLIENT_ID", ""),
                "client_secret": os.getenv("ZOHO_CLIENT_SECRET", ""),
                "refresh_token": os.getenv("ZOHO_REFRESH_TOKEN", ""),
                "base_url": "https://www.zohoapis.com"
            }
        }
        
    def sync_companies_to_crm(self, crm_type: str, user_id: int = 1) -> Dict:
        """Sync companies from FinRAG to CRM system"""
        try:
            db = next(get_db())
            
            # Get all unique companies
            drafts = db.query(Draft).filter(Draft.user_id == user_id).all()
            library = db.query(Library).filter(Library.user_id == user_id).all()
            
            companies = set()
            company_data = {}
            
            # Collect company information
            for draft in drafts:
                if draft.company not in companies:
                    companies.add(draft.company)
                    company_data[draft.company] = {
                        "name": draft.company,
                        "description": draft.analysis[:200] if draft.analysis else "",
                        "status": draft.status,
                        "confidence": draft.confidence,
                        "last_updated": draft.updated_at.isoformat(),
                        "source": "draft",
                        "interactions": 1
                    }
                else:
                    company_data[draft.company]["interactions"] += 1
            
            for item in library:
                if item.company not in companies:
                    companies.add(item.company)
                    company_data[item.company] = {
                        "name": item.company,
                        "description": f"Library item: {item.file_name}",
                        "status": "active",
                        "confidence": item.confidence,
                        "last_updated": item.date_uploaded.isoformat(),
                        "source": "library",
                        "interactions": 1
                    }
                else:
                    company_data[item.company]["interactions"] += 1
            
            # Sync to specific CRM
            if crm_type.lower() == "salesforce":
                return self._sync_to_salesforce(list(company_data.values()))
            elif crm_type.lower() == "hubspot":
                return self._sync_to_hubspot(list(company_data.values()))
            elif crm_type.lower() == "zoho":
                return self._sync_to_zoho(list(company_data.values()))
            else:
                return {"error": f"Unsupported CRM type: {crm_type}"}
                
        except Exception as e:
            return {"error": str(e)}
        finally:
            db.close()
    
    def _sync_to_salesforce(self, companies: List[Dict]) -> Dict:
        """Sync companies to Salesforce"""
        try:
            config = self.crm_config["salesforce"]
            
            if not all([config["base_url"], config["client_id"], config["client_secret"]]):
                return {"error": "Salesforce configuration incomplete"}
            
            # Get access token
            token_response = self._get_salesforce_token()
            
            if "error" in token_response:
                return token_response
            
            access_token = token_response["access_token"]
            
            # Sync companies
            synced_companies = []
            errors = []
            
            for company in companies:
                try:
                    # Create or update company in Salesforce
                    company_data = {
                        "Name": company["name"],
                        "Description": company["description"],
                        "Industry": "Financial Services",
                        "AnnualRevenue": None,
                        "NumberOfEmployees": None,
                        "FinRAG__Confidence__c": company["confidence"],
                        "FinRAG__Status__c": company["status"],
                        "FinRAG__Source__c": company["source"],
                        "FinRAG__Interactions__c": company["interactions"],
                        "FinRAG__Last_Sync__c": datetime.utcnow().isoformat()
                    }
                    
                    # Check if company exists
                    existing = self._find_salesforce_company(company["name"], access_token)
                    
                    if existing:
                        # Update existing company
                        response = requests.patch(
                            f"{config['base_url']}/services/data/v52.0/sobjects/Account/{existing['id']}",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json"
                            },
                            json=company_data
                        )
                    else:
                        # Create new company
                        response = requests.post(
                            f"{config['base_url']}/services/data/v52.0/sobjects/Account",
                            headers={
                                "Authorization": f"Bearer {access_token}",
                                "Content-Type": "application/json"
                            },
                            json=company_data
                        )
                    
                    if response.status_code in [200, 201, 204]:
                        synced_companies.append(company["name"])
                    else:
                        errors.append(f"Failed to sync {company['name']}: {response.text}")
                        
                except Exception as e:
                    errors.append(f"Error syncing {company['name']}: {str(e)}")
            
            return {
                "status": "success",
                "synced_companies": synced_companies,
                "total_companies": len(companies),
                "errors": errors,
                "crm_type": "Salesforce"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _sync_to_hubspot(self, companies: List[Dict]) -> Dict:
        """Sync companies to HubSpot"""
        try:
            config = self.crm_config["hubspot"]
            
            if not config["api_key"]:
                return {"error": "HubSpot API key not configured"}
            
            synced_companies = []
            errors = []
            
            for company in companies:
                try:
                    # Prepare company data for HubSpot
                    company_data = {
                        "properties": {
                            "name": company["name"],
                            "description": company["description"],
                            "industry": "Financial Services",
                            "lifecyclestage": "opportunity",
                            "finrag_confidence": company["confidence"],
                            "finrag_status": company["status"],
                            "finrag_source": company["source"],
                            "finrag_interactions": str(company["interactions"]),
                            "finrag_last_sync": datetime.utcnow().isoformat()
                        }
                    }
                    
                    # Check if company exists
                    existing = self._find_hubspot_company(company["name"])
                    
                    if existing:
                        # Update existing company
                        response = requests.patch(
                            f"{config['base_url']}/crm/v3/objects/companies/{existing['id']}",
                            headers={
                                "Authorization": f"Bearer {config['api_key']}",
                                "Content-Type": "application/json"
                            },
                            json=company_data
                        )
                    else:
                        # Create new company
                        response = requests.post(
                            f"{config['base_url']}/crm/v3/objects/companies",
                            headers={
                                "Authorization": f"Bearer {config['api_key']}",
                                "Content-Type": "application/json"
                            },
                            json=company_data
                        )
                    
                    if response.status_code in [200, 201]:
                        synced_companies.append(company["name"])
                    else:
                        errors.append(f"Failed to sync {company['name']}: {response.text}")
                        
                except Exception as e:
                    errors.append(f"Error syncing {company['name']}: {str(e)}")
            
            return {
                "status": "success",
                "synced_companies": synced_companies,
                "total_companies": len(companies),
                "errors": errors,
                "crm_type": "HubSpot"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _sync_to_zoho(self, companies: List[Dict]) -> Dict:
        """Sync companies to Zoho CRM"""
        try:
            config = self.crm_config["zoho"]
            
            if not all([config["client_id"], config["client_secret"], config["refresh_token"]]):
                return {"error": "Zoho CRM configuration incomplete"}
            
            # Get access token
            token_response = self._get_zoho_token()
            
            if "error" in token_response:
                return token_response
            
            access_token = token_response["access_token"]
            
            synced_companies = []
            errors = []
            
            for company in companies:
                try:
                    # Prepare company data for Zoho
                    company_data = {
                        "Account_Name": company["name"],
                        "Description": company["description"],
                        "Industry": "Financial Services",
                        "Account_Type": "Prospect",
                        "FinRAG_Confidence": company["confidence"],
                        "FinRAG_Status": company["status"],
                        "FinRAG_Source": company["source"],
                        "FinRAG_Interactions": company["interactions"],
                        "FinRAG_Last_Sync": datetime.utcnow().isoformat()
                    }
                    
                    # Check if company exists
                    existing = self._find_zoho_company(company["name"], access_token)
                    
                    if existing:
                        # Update existing company
                        response = requests.put(
                            f"{config['base_url']}/crm/v2/Accounts/{existing['id']}",
                            headers={
                                "Authorization": f"Zoho-oauthtoken {access_token}",
                                "Content-Type": "application/json"
                            },
                            json={"data": [company_data]}
                        )
                    else:
                        # Create new company
                        response = requests.post(
                            f"{config['base_url']}/crm/v2/Accounts",
                            headers={
                                "Authorization": f"Zoho-oauthtoken {access_token}",
                                "Content-Type": "application/json"
                            },
                            json={"data": [company_data]}
                        )
                    
                    if response.status_code in [200, 201, 202]:
                        synced_companies.append(company["name"])
                    else:
                        errors.append(f"Failed to sync {company['name']}: {response.text}")
                        
                except Exception as e:
                    errors.append(f"Error syncing {company['name']}: {str(e)}")
            
            return {
                "status": "success",
                "synced_companies": synced_companies,
                "total_companies": len(companies),
                "errors": errors,
                "crm_type": "Zoho CRM"
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _get_salesforce_token(self) -> Dict:
        """Get Salesforce access token"""
        try:
            config = self.crm_config["salesforce"]
            
            response = requests.post(
                f"{config['base_url']}/services/oauth2/token",
                data={
                    "grant_type": "password",
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "username": config["username"],
                    "password": config["password"]
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Failed to get Salesforce token: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def _get_zoho_token(self) -> Dict:
        """Get Zoho CRM access token"""
        try:
            config = self.crm_config["zoho"]
            
            response = requests.post(
                f"{config['base_url']}/oauth/v2/token",
                data={
                    "refresh_token": config["refresh_token"],
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "grant_type": "refresh_token"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"error": f"Failed to get Zoho token: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def _find_salesforce_company(self, company_name: str, access_token: str) -> Optional[Dict]:
        """Find existing company in Salesforce"""
        try:
            config = self.crm_config["salesforce"]
            
            response = requests.get(
                f"{config['base_url']}/services/data/v52.0/query?q=SELECT+Id+FROM+Account+WHERE+Name='{company_name}'",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("records"):
                    return {"id": data["records"][0]["Id"]}
            
            return None
            
        except:
            return None
    
    def _find_hubspot_company(self, company_name: str) -> Optional[Dict]:
        """Find existing company in HubSpot"""
        try:
            config = self.crm_config["hubspot"]
            
            response = requests.get(
                f"{config['base_url']}/crm/v3/objects/companies/search",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                params={
                    "q": company_name,
                    "limit": 1
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("results"):
                    return {"id": data["results"][0]["id"]}
            
            return None
            
        except:
            return None
    
    def _find_zoho_company(self, company_name: str, access_token: str) -> Optional[Dict]:
        """Find existing company in Zoho CRM"""
        try:
            config = self.crm_config["zoho"]
            
            response = requests.get(
                f"{config['base_url']}/crm/v2/Accounts/search",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params={"word": company_name}
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    return {"id": data["data"][0]["id"]}
            
            return None
            
        except:
            return None
    
    def get_crm_status(self, crm_type: str) -> Dict:
        """Get CRM connection status"""
        try:
            config = self.crm_config.get(crm_type.lower(), {})
            
            if crm_type.lower() == "salesforce":
                if all([config.get("base_url"), config.get("client_id"), config.get("client_secret")]):
                    # Test connection
                    token_result = self._get_salesforce_token()
                    if "error" not in token_result:
                        return {"status": "connected", "crm_type": crm_type}
                    else:
                        return {"status": "error", "error": token_result["error"]}
                else:
                    return {"status": "not_configured", "missing_fields": ["base_url", "client_id", "client_secret"]}
            
            elif crm_type.lower() == "hubspot":
                if config.get("api_key"):
                    return {"status": "connected", "crm_type": crm_type}
                else:
                    return {"status": "not_configured", "missing_fields": ["api_key"]}
            
            elif crm_type.lower() == "zoho":
                if all([config.get("client_id"), config.get("client_secret"), config.get("refresh_token")]):
                    token_result = self._get_zoho_token()
                    if "error" not in token_result:
                        return {"status": "connected", "crm_type": crm_type}
                    else:
                        return {"status": "error", "error": token_result["error"]}
                else:
                    return {"status": "not_configured", "missing_fields": ["client_id", "client_secret", "refresh_token"]}
            
            else:
                return {"status": "unsupported", "crm_type": crm_type}
                
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def export_crm_data(self, crm_type: str, user_id: int = 1) -> Dict:
        """Export data from CRM to FinRAG format"""
        try:
            if crm_type.lower() == "salesforce":
                return self._export_from_salesforce()
            elif crm_type.lower() == "hubspot":
                return self._export_from_hubspot()
            elif crm_type.lower() == "zoho":
                return self._export_from_zoho()
            else:
                return {"error": f"Unsupported CRM type: {crm_type}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def _export_from_salesforce(self) -> Dict:
        """Export companies from Salesforce"""
        try:
            config = self.crm_config["salesforce"]
            token_result = self._get_salesforce_token()
            
            if "error" in token_result:
                return token_result
            
            access_token = token_result["access_token"]
            
            # Get companies with FinRAG fields
            response = requests.get(
                f"{config['base_url']}/services/data/v52.0/query?q=SELECT+Name,Description,FinRAG__Confidence__c,FinRAG__Status__c,FinRAG__Source__c+FROM+Account+WHERE+FinRAG__Confidence__c+!=+null",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                companies = []
                
                for record in data.get("records", []):
                    companies.append({
                        "name": record.get("Name"),
                        "description": record.get("Description"),
                        "confidence": record.get("FinRAG__Confidence__c"),
                        "status": record.get("FinRAG__Status__c"),
                        "source": record.get("FinRAG__Source__c")
                    })
                
                return {
                    "status": "success",
                    "companies": companies,
                    "total_count": len(companies),
                    "crm_type": "Salesforce"
                }
            else:
                return {"error": f"Failed to export from Salesforce: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def _export_from_hubspot(self) -> Dict:
        """Export companies from HubSpot"""
        try:
            config = self.crm_config["hubspot"]
            
            response = requests.get(
                f"{config['base_url']}/crm/v3/objects/companies",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                params={
                    "properties": "name,description,finrag_confidence,finrag_status,finrag_source",
                    "limit": 100
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                companies = []
                
                for result in data.get("results", []):
                    properties = result.get("properties", {})
                    companies.append({
                        "name": properties.get("name"),
                        "description": properties.get("description"),
                        "confidence": properties.get("finrag_confidence"),
                        "status": properties.get("finrag_status"),
                        "source": properties.get("finrag_source")
                    })
                
                return {
                    "status": "success",
                    "companies": companies,
                    "total_count": len(companies),
                    "crm_type": "HubSpot"
                }
            else:
                return {"error": f"Failed to export from HubSpot: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def _export_from_zoho(self) -> Dict:
        """Export companies from Zoho CRM"""
        try:
            config = self.crm_config["zoho"]
            token_result = self._get_zoho_token()
            
            if "error" in token_result:
                return token_result
            
            access_token = token_result["access_token"]
            
            response = requests.get(
                f"{config['base_url']}/crm/v2/Accounts",
                headers={"Authorization": f"Zoho-oauthtoken {access_token}"},
                params={
                    "fields": "Account_Name,Description,FinRAG_Confidence,FinRAG_Status,FinRAG_Source"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                companies = []
                
                for record in data.get("data", []):
                    companies.append({
                        "name": record.get("Account_Name"),
                        "description": record.get("Description"),
                        "confidence": record.get("FinRAG_Confidence"),
                        "status": record.get("FinRAG_Status"),
                        "source": record.get("FinRAG_Source")
                    })
                
                return {
                    "status": "success",
                    "companies": companies,
                    "total_count": len(companies),
                    "crm_type": "Zoho CRM"
                }
            else:
                return {"error": f"Failed to export from Zoho: {response.text}"}
                
        except Exception as e:
            return {"error": str(e)}

# Global CRM service instance
crm_service = CRMService()
