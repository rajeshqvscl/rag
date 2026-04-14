"""
Team collaboration service for shared workspaces and communication
"""
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.database import User, Draft, Library, Conversation, Analytics
from app.config.database import get_db
from pydantic import BaseModel
import uuid

class CollaborationService:
    def __init__(self):
        self.workspaces = {}
        self.shared_resources = {}
        
    def create_workspace(self, name: str, description: str, creator_id: int, db: Session) -> Dict:
        """Create a new collaboration workspace"""
        try:
            workspace_id = str(uuid.uuid4())
            
            workspace = {
                "id": workspace_id,
                "name": name,
                "description": description,
                "creator_id": creator_id,
                "created_at": datetime.utcnow().isoformat(),
                "members": [creator_id],
                "shared_drafts": [],
                "shared_library": [],
                "shared_conversations": [],
                "permissions": {
                    str(creator_id): "admin"
                },
                "activity_log": []
            }
            
            # Store workspace (in production, this would be in database)
            self.workspaces[workspace_id] = workspace
            
            # Log activity
            self.log_activity(workspace_id, creator_id, "workspace_created", {"name": name})
            
            return workspace
            
        except Exception as e:
            return {"error": str(e)}
    
    def invite_member(self, workspace_id: str, user_id: int, invited_by: int, db: Session) -> Dict:
        """Invite a user to join a workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if inviter has permission
            inviter_permission = workspace["permissions"].get(str(invited_by))
            if inviter_permission not in ["admin", "editor"]:
                return {"error": "Insufficient permissions to invite members"}
            
            # Check if user is already a member
            if user_id in workspace["members"]:
                return {"error": "User is already a member"}
            
            # Add user to workspace
            workspace["members"].append(user_id)
            workspace["permissions"][str(user_id)] = "member"
            
            # Log activity
            self.log_activity(workspace_id, invited_by, "member_invited", {"user_id": user_id})
            
            return {"status": "success", "message": "Member invited successfully"}
            
        except Exception as e:
            return {"error": str(e)}
    
    def share_resource(self, workspace_id: str, resource_type: str, resource_id: int, shared_by: int, db: Session) -> Dict:
        """Share a resource (draft, library item, etc.) with a workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if user has permission to share
            permission = workspace["permissions"].get(str(shared_by))
            if permission not in ["admin", "editor"]:
                return {"error": "Insufficient permissions to share resources"}
            
            # Add resource to shared list
            resource_entry = {
                "id": resource_id,
                "shared_by": shared_by,
                "shared_at": datetime.utcnow().isoformat(),
                "access_count": 0
            }
            
            if resource_type == "draft":
                workspace["shared_drafts"].append(resource_entry)
            elif resource_type == "library":
                workspace["shared_library"].append(resource_entry)
            elif resource_type == "conversation":
                workspace["shared_conversations"].append(resource_entry)
            else:
                return {"error": "Invalid resource type"}
            
            # Log activity
            self.log_activity(workspace_id, shared_by, "resource_shared", {
                "resource_type": resource_type,
                "resource_id": resource_id
            })
            
            return {"status": "success", "message": f"{resource_type} shared successfully"}
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_workspace_resources(self, workspace_id: str, user_id: int, db: Session) -> Dict:
        """Get all shared resources in a workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if user is a member
            if user_id not in workspace["members"]:
                return {"error": "Access denied"}
            
            resources = {
                "drafts": [],
                "library": [],
                "conversations": []
            }
            
            # Get shared drafts
            for draft_entry in workspace["shared_drafts"]:
                draft = db.query(Draft).filter(Draft.id == draft_entry["id"]).first()
                if draft:
                    resources["drafts"].append({
                        "id": draft.id,
                        "company": draft.company,
                        "status": draft.status,
                        "confidence": draft.confidence,
                        "shared_by": draft_entry["shared_by"],
                        "shared_at": draft_entry["shared_at"],
                        "access_count": draft_entry["access_count"]
                    })
            
            # Get shared library items
            for library_entry in workspace["shared_library"]:
                item = db.query(Library).filter(Library.id == library_entry["id"]).first()
                if item:
                    resources["library"].append({
                        "id": item.id,
                        "company": item.company,
                        "file_name": item.file_name,
                        "confidence": item.confidence,
                        "shared_by": library_entry["shared_by"],
                        "shared_at": library_entry["shared_at"],
                        "access_count": library_entry["access_count"]
                    })
            
            # Get shared conversations
            for conv_entry in workspace["shared_conversations"]:
                conv = db.query(Conversation).filter(Conversation.id == conv_entry["id"]).first()
                if conv:
                    resources["conversations"].append({
                        "id": conv.id,
                        "query": conv.query[:100] + "..." if len(conv.query) > 100 else conv.query,
                        "timestamp": conv.timestamp.isoformat(),
                        "shared_by": conv_entry["shared_by"],
                        "shared_at": conv_entry["shared_at"],
                        "access_count": conv_entry["access_count"]
                    })
            
            return {
                "status": "success",
                "workspace": {
                    "id": workspace["id"],
                    "name": workspace["name"],
                    "description": workspace["description"],
                    "created_at": workspace["created_at"],
                    "member_count": len(workspace["members"])
                },
                "resources": resources
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def log_activity(self, workspace_id: str, user_id: int, activity_type: str, details: Dict):
        """Log activity in workspace"""
        try:
            if workspace_id in self.workspaces:
                activity = {
                    "user_id": user_id,
                    "activity_type": activity_type,
                    "details": details,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                self.workspaces[workspace_id]["activity_log"].append(activity)
                
                # Keep only last 100 activities
                if len(self.workspaces[workspace_id]["activity_log"]) > 100:
                    self.workspaces[workspace_id]["activity_log"] = self.workspaces[workspace_id]["activity_log"][-100:]
                    
        except Exception as e:
            print(f"Error logging activity: {e}")
    
    def get_activity_log(self, workspace_id: str, user_id: int, limit: int = 20) -> Dict:
        """Get activity log for a workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if user is a member
            if user_id not in workspace["members"]:
                return {"error": "Access denied"}
            
            # Get recent activities
            activities = workspace["activity_log"][-limit:]
            activities.reverse()  # Most recent first
            
            return {
                "status": "success",
                "activities": activities
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def update_permissions(self, workspace_id: str, user_id: int, target_user_id: int, new_permission: str, updated_by: int) -> Dict:
        """Update user permissions in workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if updater has admin permission
            updater_permission = workspace["permissions"].get(str(updated_by))
            if updater_permission != "admin":
                return {"error": "Only admins can update permissions"}
            
            # Check if target user is a member
            if target_user_id not in workspace["members"]:
                return {"error": "User is not a member of this workspace"}
            
            # Update permission
            workspace["permissions"][str(target_user_id)] = new_permission
            
            # Log activity
            self.log_activity(workspace_id, updated_by, "permission_updated", {
                "target_user_id": target_user_id,
                "new_permission": new_permission
            })
            
            return {"status": "success", "message": "Permissions updated successfully"}
            
        except Exception as e:
            return {"error": str(e)}
    
    def remove_member(self, workspace_id: str, user_id: int, removed_by: int) -> Dict:
        """Remove a member from workspace"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if remover has admin permission
            remover_permission = workspace["permissions"].get(str(removed_by))
            if remover_permission != "admin":
                return {"error": "Only admins can remove members"}
            
            # Cannot remove the creator
            if user_id == workspace["creator_id"]:
                return {"error": "Cannot remove workspace creator"}
            
            # Remove user from workspace
            if user_id in workspace["members"]:
                workspace["members"].remove(user_id)
                del workspace["permissions"][str(user_id)]
                
                # Log activity
                self.log_activity(workspace_id, removed_by, "member_removed", {
                    "user_id": user_id
                })
                
                return {"status": "success", "message": "Member removed successfully"}
            else:
                return {"error": "User is not a member of this workspace"}
                
        except Exception as e:
            return {"error": str(e)}
    
    def get_user_workspaces(self, user_id: int) -> Dict:
        """Get all workspaces for a user"""
        try:
            user_workspaces = []
            
            for workspace_id, workspace in self.workspaces.items():
                if user_id in workspace["members"]:
                    user_workspaces.append({
                        "id": workspace["id"],
                        "name": workspace["name"],
                        "description": workspace["description"],
                        "created_at": workspace["created_at"],
                        "member_count": len(workspace["members"]),
                        "permission": workspace["permissions"].get(str(user_id), "member"),
                        "is_creator": user_id == workspace["creator_id"]
                    })
            
            return {
                "status": "success",
                "workspaces": user_workspaces
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def create_comment(self, workspace_id: str, resource_type: str, resource_id: int, comment: str, user_id: int) -> Dict:
        """Add a comment to a shared resource"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if user is a member
            if user_id not in workspace["members"]:
                return {"error": "Access denied"}
            
            # Create comment
            comment_data = {
                "id": str(uuid.uuid4()),
                "resource_type": resource_type,
                "resource_id": resource_id,
                "user_id": user_id,
                "comment": comment,
                "created_at": datetime.utcnow().isoformat(),
                "replies": []
            }
            
            # Initialize comments if not exists
            if "comments" not in workspace:
                workspace["comments"] = []
            
            workspace["comments"].append(comment_data)
            
            # Log activity
            self.log_activity(workspace_id, user_id, "comment_added", {
                "resource_type": resource_type,
                "resource_id": resource_id
            })
            
            return {"status": "success", "comment": comment_data}
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_comments(self, workspace_id: str, resource_type: str, resource_id: int, user_id: int) -> Dict:
        """Get comments for a shared resource"""
        try:
            if workspace_id not in self.workspaces:
                return {"error": "Workspace not found"}
            
            workspace = self.workspaces[workspace_id]
            
            # Check if user is a member
            if user_id not in workspace["members"]:
                return {"error": "Access denied"}
            
            # Get comments for the resource
            comments = []
            if "comments" in workspace:
                for comment in workspace["comments"]:
                    if comment["resource_type"] == resource_type and comment["resource_id"] == resource_id:
                        comments.append(comment)
            
            return {
                "status": "success",
                "comments": comments
            }
            
        except Exception as e:
            return {"error": str(e)}

# Global collaboration service instance
collaboration_service = CollaborationService()
