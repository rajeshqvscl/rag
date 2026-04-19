"""
CRM integration routes for customer relationship management
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.crm_service import crm_service
from app.models.database import User
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class CRMSyncRequest(BaseModel):
    crm_type: str
    user_id: Optional[int] = 1

class CRMExportRequest(BaseModel):
    crm_type: str
    user_id: Optional[int] = 1

def get_or_create_default_user(db: Session) -> User:
    """Get or create default user"""
    user = db.query(User).filter_by(username="default").first()
    if not user:
        user = User(
            username="default",
            email="default@finrag.com",
            hashed_password="default",
            full_name="Default User"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

@router.post("/crm/sync")
def sync_to_crm(
    request: CRMSyncRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Sync companies from FinRAG to CRM system"""
    try:
        user = get_or_create_default_user(db)
        
        result = crm_service.sync_companies_to_crm(request.crm_type, request.user_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "status": "success",
            "sync_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/sync/{crm_type}")
def sync_to_crm_get(
    crm_type: str,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Sync companies to CRM (GET endpoint)"""
    try:
        user = get_or_create_default_user(db)
        
        result = crm_service.sync_companies_to_crm(crm_type, user_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "status": "success",
            "sync_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/status/{crm_type}")
def get_crm_status(
    crm_type: str,
    api_key: str = Depends(get_api_key)
):
    """Get CRM connection status"""
    try:
        status = crm_service.get_crm_status(crm_type)
        
        return {
            "status": "success",
            "crm_status": status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/status")
def get_all_crm_status(api_key: str = Depends(get_api_key)):
    """Get status of all CRM systems"""
    try:
        crm_types = ["salesforce", "hubspot", "zoho"]
        all_status = {}
        
        for crm_type in crm_types:
            all_status[crm_type] = crm_service.get_crm_status(crm_type)
        
        return {
            "status": "success",
            "crm_statuses": all_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/crm/export")
def export_from_crm(
    request: CRMExportRequest,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Export data from CRM to FinRAG format"""
    try:
        user = get_or_create_default_user(db)
        
        result = crm_service.export_crm_data(request.crm_type, request.user_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "status": "success",
            "export_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/export/{crm_type}")
def export_from_crm_get(
    crm_type: str,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Export data from CRM (GET endpoint)"""
    try:
        user = get_or_create_default_user(db)
        
        result = crm_service.export_crm_data(crm_type, user_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "status": "success",
            "export_result": result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/config")
def get_crm_config(api_key: str = Depends(get_api_key)):
    """Get CRM configuration status"""
    try:
        config_status = {
            "supported_crms": ["salesforce", "hubspot", "zoho"],
            "configuration_status": {},
            "required_fields": {
                "salesforce": ["base_url", "client_id", "client_secret", "username", "password"],
                "hubspot": ["api_key"],
                "zoho": ["client_id", "client_secret", "refresh_token"]
            },
            "environment_variables": {
                "salesforce": {
                    "SALESFORCE_URL": "Salesforce instance URL",
                    "SALESFORCE_CLIENT_ID": "OAuth client ID",
                    "SALESFORCE_CLIENT_SECRET": "OAuth client secret",
                    "SALESFORCE_USERNAME": "Salesforce username",
                    "SALESFORCE_PASSWORD": "Salesforce password"
                },
                "hubspot": {
                    "HUBSPOT_API_KEY": "HubSpot API key"
                },
                "zoho": {
                    "ZOHO_CLIENT_ID": "Zoho client ID",
                    "ZOHO_CLIENT_SECRET": "Zoho client secret",
                    "ZOHO_REFRESH_TOKEN": "Zoho refresh token"
                }
            }
        }
        
        # Check configuration status for each CRM
        for crm_type in config_status["supported_crms"]:
            status = crm_service.get_crm_status(crm_type)
            config_status["configuration_status"][crm_type] = status
        
        return {
            "status": "success",
            "crm_config": config_status
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/sync-history")
def get_sync_history(
    crm_type: Optional[str] = None,
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get sync history (mock implementation)"""
    try:
        # In a real implementation, this would query a sync history table
        sync_history = [
            {
                "id": 1,
                "crm_type": "salesforce",
                "sync_type": "export",
                "companies_synced": 15,
                "status": "success",
                "synced_at": "2024-01-15T10:30:00Z",
                "errors": []
            },
            {
                "id": 2,
                "crm_type": "hubspot",
                "sync_type": "export",
                "companies_synced": 12,
                "status": "success",
                "synced_at": "2024-01-14T15:45:00Z",
                "errors": []
            },
            {
                "id": 3,
                "crm_type": "salesforce",
                "sync_type": "import",
                "companies_imported": 8,
                "status": "partial_success",
                "synced_at": "2024-01-13T09:20:00Z",
                "errors": ["Failed to import 2 companies due to missing fields"]
            }
        ]
        
        # Filter by CRM type if specified
        if crm_type:
            sync_history = [sync for sync in sync_history if sync["crm_type"] == crm_type.lower()]
        
        return {
            "status": "success",
            "sync_history": sync_history,
            "total_syncs": len(sync_history)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/mapping")
def get_field_mapping(
    crm_type: str,
    api_key: str = Depends(get_api_key)
):
    """Get field mapping between FinRAG and CRM"""
    try:
        field_mappings = {
            "salesforce": {
                "finrag_fields": {
                    "company": "Name",
                    "description": "Description",
                    "confidence": "FinRAG__Confidence__c",
                    "status": "FinRAG__Status__c",
                    "source": "FinRAG__Source__c",
                    "interactions": "FinRAG__Interactions__c",
                    "last_updated": "FinRAG__Last_Sync__c"
                },
                "crm_fields": {
                    "Name": "company",
                    "Description": "description",
                    "Industry": "Financial Services",
                    "AccountSource": "FinRAG"
                }
            },
            "hubspot": {
                "finrag_fields": {
                    "company": "name",
                    "description": "description",
                    "confidence": "finrag_confidence",
                    "status": "finrag_status",
                    "source": "finrag_source",
                    "interactions": "finrag_interactions",
                    "last_updated": "finrag_last_sync"
                },
                "crm_fields": {
                    "name": "company",
                    "description": "description",
                    "industry": "Financial Services",
                    "lifecyclestage": "opportunity"
                }
            },
            "zoho": {
                "finrag_fields": {
                    "company": "Account_Name",
                    "description": "Description",
                    "confidence": "FinRAG_Confidence",
                    "status": "FinRAG_Status",
                    "source": "FinRAG_Source",
                    "interactions": "FinRAG_Interactions",
                    "last_updated": "FinRAG_Last_Sync"
                },
                "crm_fields": {
                    "Account_Name": "company",
                    "Description": "description",
                    "Industry": "Financial Services",
                    "Account_Type": "Prospect"
                }
            }
        }
        
        if crm_type.lower() not in field_mappings:
            raise HTTPException(status_code=404, detail=f"CRM type '{crm_type}' not supported")
        
        return {
            "status": "success",
            "crm_type": crm_type,
            "field_mapping": field_mappings[crm_type.lower()]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/crm/bi-directional-sync")
def bi_directional_sync(
    crm_type: str,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Perform bi-directional sync between FinRAG and CRM"""
    try:
        user = get_or_create_default_user(db)
        
        # Export from CRM to FinRAG
        export_result = crm_service.export_crm_data(crm_type, user_id)
        
        # Import from FinRAG to CRM
        sync_result = crm_service.sync_companies_to_crm(crm_type, user_id)
        
        # Combine results
        bi_directional_result = {
            "crm_type": crm_type,
            "export_result": export_result,
            "sync_result": sync_result,
            "timestamp": "2024-01-16T12:00:00Z"  # In production, use actual timestamp
        }
        
        if "error" in export_result or "error" in sync_result:
            return {
                "status": "partial_success",
                "bi_directional_sync": bi_directional_result,
                "errors": [
                    export_result.get("error"),
                    sync_result.get("error")
                ]
            }
        
        return {
            "status": "success",
            "bi_directional_sync": bi_directional_result
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/crm/statistics")
def get_crm_statistics(
    crm_type: Optional[str] = None,
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get CRM integration statistics"""
    try:
        statistics = {
            "total_syncs": 45,
            "successful_syncs": 42,
            "failed_syncs": 3,
            "last_sync": "2024-01-15T10:30:00Z",
            "crm_statistics": {
                "salesforce": {
                    "total_companies": 25,
                    "last_sync": "2024-01-15T10:30:00Z",
                    "sync_status": "connected",
                    "companies_synced": 23
                },
                "hubspot": {
                    "total_companies": 18,
                    "last_sync": "2024-01-14T15:45:00Z",
                    "sync_status": "connected",
                    "companies_synced": 18
                },
                "zoho": {
                    "total_companies": 12,
                    "last_sync": "2024-01-13T09:20:00Z",
                    "sync_status": "not_configured",
                    "companies_synced": 0
                }
            }
        }
        
        # Filter by CRM type if specified
        if crm_type:
            if crm_type.lower() in statistics["crm_statistics"]:
                statistics["crm_statistics"] = {crm_type.lower(): statistics["crm_statistics"][crm_type.lower()]}
            else:
                raise HTTPException(status_code=404, detail=f"CRM type '{crm_type}' not found")
        
        return {
            "status": "success",
            "crm_statistics": statistics
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
