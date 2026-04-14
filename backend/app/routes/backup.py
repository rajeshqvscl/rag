"""
Backup and restore routes for data management
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.backup_service import backup_service
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class BackupRequest(BaseModel):
    backup_name: Optional[str] = None
    user_id: Optional[int] = None

class RestoreRequest(BaseModel):
    backup_name: str
    user_id: Optional[int] = None

@router.post("/backup/create")
def create_backup(
    request: BackupRequest,
    api_key: str = Depends(get_api_key)
):
    """Create a backup of all data"""
    try:
        result = backup_service.create_backup(request.backup_name, request.user_id)
        
        if result["status"] == "success":
            return {
                "status": "success",
                "message": f"Backup '{result['backup_name']}' created successfully",
                "backup_info": {
                    "name": result["backup_name"],
                    "path": result["backup_path"],
                    "size": result["backup_size"],
                    "created_at": result["created_at"]
                }
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backup/restore")
def restore_backup(
    request: RestoreRequest,
    api_key: str = Depends(get_api_key)
):
    """Restore data from backup"""
    try:
        backup_path = f"backups/{request.backup_name}.zip"
        result = backup_service.restore_backup(backup_path, request.user_id)
        
        if result["status"] == "success":
            return {
                "status": "success",
                "message": "Backup restored successfully",
                "restore_log": result["restore_log"]
            }
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup/list")
def list_backups(api_key: str = Depends(get_api_key)):
    """List all available backups"""
    try:
        backups = backup_service.list_backups()
        
        return {
            "status": "success",
            "backups": backups,
            "total_backups": len(backups)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/backup/{backup_name}")
def delete_backup(
    backup_name: str,
    api_key: str = Depends(get_api_key)
):
    """Delete a backup"""
    try:
        result = backup_service.delete_backup(backup_name)
        
        if result["status"] == "success":
            return {
                "status": "success",
                "message": result["message"]
            }
        else:
            raise HTTPException(status_code=404, detail=result["message"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backup/upload")
async def upload_backup(
    file: UploadFile = File(...),
    api_key: str = Depends(get_api_key)
):
    """Upload a backup file"""
    try:
        # Create backup directory if it doesn't exist
        import os
        backup_dir = "backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # Save uploaded file
        backup_path = os.path.join(backup_dir, file.filename)
        
        with open(backup_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Validate backup file
        try:
            import zipfile
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                if "backup_metadata.json" not in zip_file.namelist():
                    os.remove(backup_path)
                    raise HTTPException(status_code=400, detail="Invalid backup file format")
        except:
            os.remove(backup_path)
            raise HTTPException(status_code=400, detail="Invalid backup file")
        
        return {
            "status": "success",
            "message": f"Backup file '{file.filename}' uploaded successfully",
            "backup_name": file.filename.replace(".zip", "")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup/download/{backup_name}")
def download_backup(
    backup_name: str,
    api_key: str = Depends(get_api_key)
):
    """Download a backup file"""
    try:
        from fastapi.responses import FileResponse
        import os
        
        backup_path = f"backups/{backup_name}.zip"
        
        if not os.path.exists(backup_path):
            raise HTTPException(status_code=404, detail="Backup not found")
        
        return FileResponse(
            backup_path,
            media_type="application/zip",
            filename=f"{backup_name}.zip"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/backup/export/csv")
def export_data_csv(
    user_id: Optional[int] = None,
    api_key: str = Depends(get_api_key)
):
    """Export data to CSV format"""
    try:
        result = backup_service.export_data_csv(user_id)
        
        if result["status"] == "success":
            from fastapi.responses import FileResponse
            
            return FileResponse(
                result["export_path"],
                media_type="application/zip",
                filename=f"{result['export_name']}.zip"
            )
        else:
            raise HTTPException(status_code=500, detail=result["message"])
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/backup/status")
def get_backup_status(api_key: str = Depends(get_api_key)):
    """Get backup system status"""
    try:
        import os
        
        backup_dir = "backups"
        
        # Check if backup directory exists
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        
        # Get directory info
        backups = backup_service.list_backups()
        total_size = sum(backup["size"] for backup in backups)
        
        return {
            "status": "success",
            "backup_directory": backup_dir,
            "total_backups": len(backups),
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "latest_backup": backups[0] if backups else None,
            "system_status": "healthy"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
