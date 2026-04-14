"""
Team collaboration routes for shared workspaces and communication
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.services.security_service import get_api_key
from app.services.collaboration_service import collaboration_service
from app.models.database import User
from app.config.database import get_db
from typing import List, Dict, Optional
from pydantic import BaseModel

router = APIRouter()

class WorkspaceCreate(BaseModel):
    name: str
    description: str

class MemberInvite(BaseModel):
    workspace_id: str
    user_id: int

class ResourceShare(BaseModel):
    workspace_id: str
    resource_type: str
    resource_id: int

class CommentCreate(BaseModel):
    workspace_id: str
    resource_type: str
    resource_id: int
    comment: str

class PermissionUpdate(BaseModel):
    workspace_id: str
    user_id: int
    new_permission: str

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

@router.post("/collaboration/workspace/create")
def create_workspace(
    request: WorkspaceCreate,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Create a new collaboration workspace"""
    try:
        user = get_or_create_default_user(db)
        
        workspace = collaboration_service.create_workspace(
            request.name,
            request.description,
            user_id,
            db
        )
        
        if "error" in workspace:
            raise HTTPException(status_code=500, detail=workspace["error"])
        
        return {
            "status": "success",
            "message": "Workspace created successfully",
            "workspace": workspace
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/workspace/invite")
def invite_member(
    request: MemberInvite,
    invited_by: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Invite a user to join a workspace"""
    try:
        result = collaboration_service.invite_member(
            request.workspace_id,
            request.user_id,
            invited_by,
            db
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/workspace/share")
def share_resource(
    request: ResourceShare,
    shared_by: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Share a resource with a workspace"""
    try:
        result = collaboration_service.share_resource(
            request.workspace_id,
            request.resource_type,
            request.resource_id,
            shared_by,
            db
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/workspace/{workspace_id}/resources")
def get_workspace_resources(
    workspace_id: str,
    user_id: int = 1,
    db: Session = Depends(get_db),
    api_key: str = Depends(get_api_key)
):
    """Get all shared resources in a workspace"""
    try:
        result = collaboration_service.get_workspace_resources(workspace_id, user_id, db)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/workspace/{workspace_id}/activity")
def get_activity_log(
    workspace_id: str,
    user_id: int = 1,
    limit: int = 20,
    api_key: str = Depends(get_api_key)
):
    """Get activity log for a workspace"""
    try:
        result = collaboration_service.get_activity_log(workspace_id, user_id, limit)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/collaboration/workspace/permissions")
def update_permissions(
    request: PermissionUpdate,
    updated_by: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Update user permissions in workspace"""
    try:
        result = collaboration_service.update_permissions(
            request.workspace_id,
            request.user_id,
            request.new_permission,
            updated_by
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collaboration/workspace/{workspace_id}/members/{user_id}")
def remove_member(
    workspace_id: str,
    user_id: int,
    removed_by: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Remove a member from workspace"""
    try:
        result = collaboration_service.remove_member(workspace_id, user_id, removed_by)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/workspaces")
def get_user_workspaces(
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get all workspaces for a user"""
    try:
        result = collaboration_service.get_user_workspaces(user_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collaboration/comment")
def create_comment(
    request: CommentCreate,
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Add a comment to a shared resource"""
    try:
        result = collaboration_service.create_comment(
            request.workspace_id,
            request.resource_type,
            request.resource_id,
            request.comment,
            user_id
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/comments/{workspace_id}/{resource_type}/{resource_id}")
def get_comments(
    workspace_id: str,
    resource_type: str,
    resource_id: int,
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get comments for a shared resource"""
    try:
        result = collaboration_service.get_comments(
            workspace_id,
            resource_type,
            resource_id,
            user_id
        )
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/summary")
def get_collaboration_summary(
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get collaboration summary for a user"""
    try:
        # Get user workspaces
        workspaces_result = collaboration_service.get_user_workspaces(user_id)
        
        if "error" in workspaces_result:
            raise HTTPException(status_code=500, detail=workspaces_result["error"])
        
        workspaces = workspaces_result["workspaces"]
        
        # Calculate summary statistics
        summary = {
            "total_workspaces": len(workspaces),
            "owned_workspaces": len([w for w in workspaces if w["is_creator"]]),
            "admin_workspaces": len([w for w in workspaces if w["permission"] == "admin"]),
            "editor_workspaces": len([w for w in workspaces if w["permission"] == "editor"]),
            "member_workspaces": len([w for w in workspaces if w["permission"] == "member"]),
            "total_shared_resources": 0,
            "recent_activity": []
        }
        
        # Get activity from all workspaces
        for workspace in workspaces:
            try:
                activity_result = collaboration_service.get_activity_log(workspace["id"], user_id, 5)
                if "activities" in activity_result:
                    summary["recent_activity"].extend(activity_result["activities"])
            except:
                continue
        
        # Sort recent activity
        summary["recent_activity"].sort(key=lambda x: x["timestamp"], reverse=True)
        summary["recent_activity"] = summary["recent_activity"][:10]  # Keep only 10 most recent
        
        return {
            "status": "success",
            "collaboration_summary": summary
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collaboration/workspace/{workspace_id}/members")
def get_workspace_members(
    workspace_id: str,
    user_id: int = 1,
    api_key: str = Depends(get_api_key)
):
    """Get all members of a workspace"""
    try:
        # Check if workspace exists and user is a member
        workspaces_result = collaboration_service.get_user_workspaces(user_id)
        
        if "error" in workspaces_result:
            raise HTTPException(status_code=500, detail=workspaces_result["error"])
        
        user_workspaces = [w for w in workspaces_result["workspaces"] if w["id"] == workspace_id]
        
        if not user_workspaces:
            raise HTTPException(status_code=404, detail="Workspace not found or access denied")
        
        workspace = user_workspaces[0]
        
        # Get member details (in production, this would query the database)
        members = []
        for member_id in collaboration_service.workspaces.get(workspace_id, {}).get("members", []):
            permissions = collaboration_service.workspaces.get(workspace_id, {}).get("permissions", {}).get(str(member_id), "member")
            
            members.append({
                "user_id": member_id,
                "permission": permissions,
                "joined_at": "N/A"  # In production, this would be tracked
            })
        
        return {
            "status": "success",
            "workspace_id": workspace_id,
            "members": members,
            "total_members": len(members)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
