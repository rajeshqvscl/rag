"""
Backup and restore service for data management
"""
import os
import json
import shutil
import zipfile
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from app.models.database import Draft, Library, Conversation, Memory, User, Analytics
from app.config.database import get_db
import csv
import io

class BackupService:
    def __init__(self):
        self.backup_dir = "backups"
        os.makedirs(self.backup_dir, exist_ok=True)
        
    def create_backup(self, backup_name: str = None, user_id: int = None) -> Dict:
        """Create comprehensive backup of all data"""
        try:
            if not backup_name:
                backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            backup_path = os.path.join(self.backup_dir, f"{backup_name}.zip")
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as backup_zip:
                db = next(get_db())
                try:
                    # Backup users
                    users = db.query(User).all()
                    if user_id:
                        users = [u for u in users if u.id == user_id]
                    
                    if users:
                        users_data = []
                        for user in users:
                            users_data.append({
                                "id": user.id,
                                "username": user.username,
                                "email": user.email,
                                "full_name": user.full_name,
                                "is_active": user.is_active,
                                "is_admin": user.is_admin,
                                "created_at": user.created_at.isoformat(),
                                "updated_at": user.updated_at.isoformat()
                            })
                        
                        backup_zip.writestr("users.json", json.dumps(users_data, indent=2))
                    
                    # Backup drafts
                    for user in users:
                        drafts = db.query(Draft).filter(Draft.user_id == user.id).all()
                        if drafts:
                            drafts_data = []
                            for draft in drafts:
                                drafts_data.append({
                                    "id": draft.id,
                                    "user_id": draft.user_id,
                                    "company": draft.company,
                                    "date": draft.date.isoformat() if draft.date else None,
                                    "status": draft.status,
                                    "confidence": draft.confidence,
                                    "analysis": draft.analysis,
                                    "email_draft": draft.email_draft,
                                    "revenue_data": draft.revenue_data,
                                    "files": draft.files,
                                    "tags": draft.tags,
                                    "created_at": draft.created_at.isoformat(),
                                    "updated_at": draft.updated_at.isoformat()
                                })
                            
                            backup_zip.writestr(f"drafts_user_{user.id}.json", json.dumps(drafts_data, indent=2))
                    
                    # Backup library
                    for user in users:
                        library = db.query(Library).filter(Library.user_id == user.id).all()
                        if library:
                            library_data = []
                            for item in library:
                                library_data.append({
                                    "id": item.id,
                                    "user_id": item.user_id,
                                    "company": item.company,
                                    "file_name": item.file_name,
                                    "file_path": item.file_path,
                                    "file_size": item.file_size,
                                    "file_type": item.file_type,
                                    "date_uploaded": item.date_uploaded.isoformat(),
                                    "confidence": item.confidence,
                                    "tags": item.tags,
                                    "metadata": item.metadata,
                                    "created_at": item.created_at.isoformat()
                                })
                            
                            backup_zip.writestr(f"library_user_{user.id}.json", json.dumps(library_data, indent=2))
                            
                            # Also backup actual files
                            for item in library:
                                if item.file_path and os.path.exists(item.file_path):
                                    backup_zip.write(item.file_path, f"files/{item.file_name}")
                    
                    # Backup conversations
                    for user in users:
                        conversations = db.query(Conversation).filter(Conversation.user_id == user.id).all()
                        if conversations:
                            conv_data = []
                            for conv in conversations:
                                conv_data.append({
                                    "id": conv.id,
                                    "user_id": conv.user_id,
                                    "query": conv.query,
                                    "response": conv.response,
                                    "context": conv.context,
                                    "tags": conv.tags,
                                    "timestamp": conv.timestamp.isoformat(),
                                    "session_id": conv.session_id
                                })
                            
                            backup_zip.writestr(f"conversations_user_{user.id}.json", json.dumps(conv_data, indent=2))
                    
                    # Backup memory vectors
                    for user in users:
                        memories = db.query(Memory).filter(Memory.user_id == user.id).all()
                        if memories:
                            memory_data = []
                            for memory in memories:
                                memory_data.append({
                                    "id": memory.id,
                                    "user_id": memory.user_id,
                                    "conversation_id": memory.conversation_id,
                                    "text": memory.text,
                                    "embedding": memory.embedding,
                                    "vector_id": memory.vector_id,
                                    "tags": memory.tags,
                                    "created_at": memory.created_at.isoformat()
                                })
                            
                            backup_zip.writestr(f"memory_user_{user.id}.json", json.dumps(memory_data, indent=2))
                    
                    # Backup analytics
                    for user in users:
                        analytics = db.query(Analytics).filter(Analytics.user_id == user.id).all()
                        if analytics:
                            analytics_data = []
                            for analytic in analytics:
                                analytics_data.append({
                                    "id": analytic.id,
                                    "user_id": analytic.user_id,
                                    "event_type": analytic.event_type,
                                    "event_data": analytic.event_data,
                                    "timestamp": analytic.timestamp.isoformat(),
                                    "session_id": analytic.session_id
                                })
                            
                            backup_zip.writestr(f"analytics_user_{user.id}.json", json.dumps(analytics_data, indent=2))
                    
                    # Add backup metadata
                    backup_metadata = {
                        "backup_name": backup_name,
                        "created_at": datetime.utcnow().isoformat(),
                        "version": "1.0",
                        "user_id": user_id,
                        "total_users": len(users),
                        "backup_type": "full" if not user_id else "user_specific"
                    }
                    
                    backup_zip.writestr("backup_metadata.json", json.dumps(backup_metadata, indent=2))
                    
                finally:
                    db.close()
            
            # Get backup size
            backup_size = os.path.getsize(backup_path)
            
            return {
                "status": "success",
                "backup_name": backup_name,
                "backup_path": backup_path,
                "backup_size": backup_size,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Backup failed: {str(e)}"
            }
    
    def restore_backup(self, backup_path: str, user_id: int = None) -> Dict:
        """Restore data from backup file"""
        try:
            if not os.path.exists(backup_path):
                return {
                    "status": "error",
                    "message": "Backup file not found"
                }
            
            restore_log = []
            
            with zipfile.ZipFile(backup_path, 'r') as backup_zip:
                # Read backup metadata
                if "backup_metadata.json" in backup_zip.namelist():
                    metadata = json.loads(backup_zip.read("backup_metadata.json").decode())
                    restore_log.append(f"Restoring backup: {metadata.get('backup_name', 'unknown')}")
                    restore_log.append(f"Backup created: {metadata.get('created_at', 'unknown')}")
                else:
                    restore_log.append("No backup metadata found")
                
                db = next(get_db())
                try:
                    # Restore users
                    if "users.json" in backup_zip.namelist():
                        users_data = json.loads(backup_zip.read("users.json").decode())
                        
                        for user_data in users_data:
                            if user_id and user_data["id"] != user_id:
                                continue
                            
                            existing_user = db.query(User).filter(User.id == user_data["id"]).first()
                            
                            if not existing_user:
                                # Create new user
                                new_user = User(
                                    id=user_data["id"],
                                    username=user_data["username"],
                                    email=user_data["email"],
                                    hashed_password=user_data.get("hashed_password", "default"),
                                    full_name=user_data["full_name"],
                                    is_active=user_data["is_active"],
                                    is_admin=user_data["is_admin"],
                                    created_at=datetime.fromisoformat(user_data["created_at"]),
                                    updated_at=datetime.fromisoformat(user_data["updated_at"])
                                )
                                db.add(new_user)
                                restore_log.append(f"Restored user: {user_data['username']}")
                            else:
                                # Update existing user
                                existing_user.username = user_data["username"]
                                existing_user.email = user_data["email"]
                                existing_user.full_name = user_data["full_name"]
                                existing_user.is_active = user_data["is_active"]
                                existing_user.is_admin = user_data["is_admin"]
                                existing_user.updated_at = datetime.fromisoformat(user_data["updated_at"])
                                restore_log.append(f"Updated user: {user_data['username']}")
                    
                    db.commit()
                    
                    # Restore other data types
                    data_types = [
                        ("drafts", Draft),
                        ("library", Library),
                        ("conversations", Conversation),
                        ("memory", Memory),
                        ("analytics", Analytics)
                    ]
                    
                    for data_type, model_class in data_types:
                        for filename in backup_zip.namelist():
                            if filename.startswith(f"{data_type}_user_") and filename.endswith(".json"):
                                user_id_match = filename.split("_")[2].split(".")[0]
                                
                                if user_id and user_id_match != str(user_id):
                                    continue
                                
                                data = json.loads(backup_zip.read(filename).decode())
                                
                                for item_data in data:
                                    existing_item = db.query(model_class).filter(model_class.id == item_data["id"]).first()
                                    
                                    if not existing_item:
                                        # Create new item
                                        new_item = model_class()
                                        
                                        for key, value in item_data.items():
                                            if key in ["created_at", "updated_at", "date", "date_uploaded", "timestamp"]:
                                                if value:
                                                    setattr(new_item, key, datetime.fromisoformat(value))
                                            elif key != "id":
                                                setattr(new_item, key, value)
                                        
                                        db.add(new_item)
                                        restore_log.append(f"Restored {data_type[:-1]}: {item_data.get('id', 'unknown')}")
                                    else:
                                        # Update existing item
                                        for key, value in item_data.items():
                                            if key in ["created_at", "updated_at", "date", "date_uploaded", "timestamp"]:
                                                if value:
                                                    setattr(existing_item, key, datetime.fromisoformat(value))
                                            elif key != "id":
                                                setattr(existing_item, key, value)
                                        restore_log.append(f"Updated {data_type[:-1]}: {item_data.get('id', 'unknown')}")
                    
                    db.commit()
                    
                    # Restore files
                    for filename in backup_zip.namelist():
                        if filename.startswith("files/"):
                            file_path = os.path.join("data/library_files", os.path.basename(filename))
                            
                            # Create directory if it doesn't exist
                            os.makedirs(os.path.dirname(file_path), exist_ok=True)
                            
                            # Extract file
                            with backup_zip.open(filename) as source_file:
                                with open(file_path, "wb") as target_file:
                                    shutil.copyfileobj(source_file, target_file)
                            
                            restore_log.append(f"Restored file: {filename}")
                    
                finally:
                    db.close()
            
            return {
                "status": "success",
                "message": "Backup restored successfully",
                "restore_log": restore_log
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Restore failed: {str(e)}"
            }
    
    def list_backups(self) -> List[Dict]:
        """List all available backups"""
        try:
            backups = []
            
            for filename in os.listdir(self.backup_dir):
                if filename.endswith(".zip"):
                    file_path = os.path.join(self.backup_dir, filename)
                    file_stat = os.stat(file_path)
                    
                    # Try to read metadata
                    metadata = {}
                    try:
                        with zipfile.ZipFile(file_path, 'r') as backup_zip:
                            if "backup_metadata.json" in backup_zip.namelist():
                                metadata = json.loads(backup_zip.read("backup_metadata.json").decode())
                    except:
                        pass
                    
                    backups.append({
                        "filename": filename,
                        "path": file_path,
                        "size": file_stat.st_size,
                        "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        "metadata": metadata
                    })
            
            # Sort by creation date (newest first)
            backups.sort(key=lambda x: x["created_at"], reverse=True)
            
            return backups
            
        except Exception as e:
            return []
    
    def delete_backup(self, backup_name: str) -> Dict:
        """Delete a backup file"""
        try:
            backup_path = os.path.join(self.backup_dir, f"{backup_name}.zip")
            
            if not os.path.exists(backup_path):
                return {
                    "status": "error",
                    "message": "Backup file not found"
                }
            
            os.remove(backup_path)
            
            return {
                "status": "success",
                "message": f"Backup {backup_name} deleted successfully"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Delete failed: {str(e)}"
            }
    
    def export_data_csv(self, user_id: int = None) -> Dict:
        """Export data to CSV format"""
        try:
            export_dir = "exports"
            os.makedirs(export_dir, exist_ok=True)
            
            export_name = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            export_path = os.path.join(export_dir, f"{export_name}.zip")
            
            with zipfile.ZipFile(export_path, 'w', zipfile.ZIP_DEFLATED) as export_zip:
                db = next(get_db())
                try:
                    # Export users
                    users = db.query(User).all()
                    if user_id:
                        users = [u for u in users if u.id == user_id]
                    
                    if users:
                        users_csv = io.StringIO()
                        writer = csv.writer(users_csv)
                        writer.writerow(["id", "username", "email", "full_name", "is_active", "is_admin", "created_at", "updated_at"])
                        
                        for user in users:
                            writer.writerow([
                                user.id, user.username, user.email, user.full_name,
                                user.is_active, user.is_admin,
                                user.created_at.isoformat(), user.updated_at.isoformat()
                            ])
                        
                        export_zip.writestr("users.csv", users_csv.getvalue())
                    
                    # Export other data types similarly...
                    # (Drafts, Library, Conversations, etc.)
                    
                finally:
                    db.close()
            
            return {
                "status": "success",
                "export_name": export_name,
                "export_path": export_path,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Export failed: {str(e)}"
            }

# Global backup service instance
backup_service = BackupService()
