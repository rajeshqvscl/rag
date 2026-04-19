from fastapi import APIRouter, UploadFile, File, Form, Depends
import os
from app.tasks import process_file_task
from app.services.claude_service import analyze_documents, generate_draft_email
from app.services.projection_service import projection_service
from app.services.cache_service_lru import cache_service
from datetime import datetime
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.models.database import Draft, Library, User

router = APIRouter()

def get_or_create_default_user(db: Session):
    """Get or create default user for saving drafts and library"""
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

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/email-webhook")
async def receive_email(
    company: str = Form("Unknown"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    try:
        print(f"--- Received Deal Processing Request for: {company} ---")
        print(f"Number of files received: {len(files)}")
        results = []
        contents = []

        for file in files:
            file_path = os.path.join(UPLOAD_DIR, file.filename)

            # Read file content once
            file_content = await file.read()
            
            # Save to uploads directory
            with open(file_path, "wb") as f:
                f.write(file_content)

            result = process_file_task(
                file_path=file_path,
                file_name=file.filename,
                company=company
            )
            
            # Save PDF to library if it's a pitch deck
            if file.filename.lower().endswith('.pdf'):
                try:
                    print(f"Attempting to save PDF {file.filename} to library for {company}")
                    # Create library directory if it doesn't exist
                    library_dir = "data/library_files"
                    os.makedirs(library_dir, exist_ok=True)
                    
                    # Save file to library directory
                    library_file_path = os.path.join(library_dir, file.filename)
                    with open(library_file_path, "wb") as f:
                        f.write(file_content)
                    print(f"File saved to {library_file_path}")
                    
                    # Add to library database (SQLAlchemy)
                    user = get_or_create_default_user(db)
                    new_library_entry = Library(
                        user_id=user.id,
                        company=company,
                        file_name=file.filename,
                        file_path=library_file_path,
                        file_size=os.path.getsize(library_file_path),
                        file_type="pdf",
                        date_uploaded=datetime.utcnow(),
                        confidence="High",
                        tags=["pitch_deck"],
                        file_metadata={"source": "email_webhook", "original_upload": True}
                    )
                    db.add(new_library_entry)
                    db.commit()
                    
                    # Invalidate library cache
                    cache_service.invalidate_library(user.id)
                    print(f"Saved {file.filename} to library database successfully for {company}")
                    print(f"Library cache invalidated for user {user.id}")
                except Exception as e:
                    print(f"Failed to save to library: {e}")
                    import traceback
                    traceback.print_exc()

            if result.get("status") == "success":
                contents.append(f"FILE: {file.filename}\nTYPE: {result.get('type')}\nCONTENT: {result.get('content')}")

            results.append({
                "file": file.filename,
                "result": result
            })

        # Logic for analysis and drafting
        analysis_text = "No content extracted to analyze."
        revenue_data = []
        draft_email = "No email drafted."

        print(f"Starting analysis with {len(contents)} document chunks...")
        if contents:
            print(f"Analyzing {len(contents)} document chunks...")
            try:
                analysis_data = analyze_documents(contents) or {}
                print(f"Analysis completed, got data type: {type(analysis_data)}")
                
                # Handle different response formats
                if isinstance(analysis_data, dict) and 'analysis_markdown' in analysis_data:
                    analysis_text = analysis_data.get("analysis_markdown", "No summary could be generated.")
                    revenue_data = analysis_data.get("revenue_data", [])
                    
                    # If analysis_markdown contains JSON string, parse it
                    if analysis_text.startswith('{') or analysis_text.startswith('```json'):
                        try:
                            import json
                            # Remove markdown code blocks if present
                            clean_json = analysis_text.replace('```json', '').replace('```', '').strip()
                            parsed_json = json.loads(clean_json)
                            if 'analysis_markdown' in parsed_json:
                                analysis_text = parsed_json['analysis_markdown']
                            if 'revenue_data' in parsed_json and not revenue_data:
                                revenue_data = parsed_json['revenue_data']
                        except:
                            # If parsing fails, use as-is
                            pass
                elif isinstance(analysis_data, dict) and 'full_report' in analysis_data:
                    # Fallback analysis format
                    analysis_text = analysis_data.get('full_report', 'No analysis available')
                    revenue_data = []
                else:
                    analysis_text = str(analysis_data) if analysis_data else "No summary could be generated."
                    revenue_data = []
                
                if revenue_data:
                    formatted_proj = [
                        {"metric": "Revenue", "value": str(r.get("revenue")), "period": str(r.get("year")), "source_context": "Extracted from uploaded documents."}
                        for r in revenue_data
                    ]
                    projection_service.save_projections(company, formatted_proj)
                    
                draft_email = generate_draft_email(analysis_text, company, revenue_data)
                print(f"Generated draft email for {company}")
                
                # Save draft to drafts section (database)
                try:
                    print(f"Attempting to save draft for {company}")
                    user = get_or_create_default_user(db)
                    
                    new_draft = Draft(
                        user_id=user.id,
                        company=company,
                        date=datetime.utcnow(),
                        status="Completed",
                        confidence="High" if revenue_data else "Medium",
                        analysis=analysis_text,
                        email_draft=draft_email,
                        revenue_data=revenue_data,
                        files=[{"name": file.filename, "type": "uploaded"} for file in files],
                        tags=["auto_generated"]
                    )
                    db.add(new_draft)
                    db.commit()
                    
                    # Invalidate cache so new draft appears immediately
                    cache_service.invalidate_drafts(user.id)
                    print(f"Draft saved successfully for {company} (ID: {new_draft.id})")
                    print(f"Cache invalidated for user {user.id}")
                except Exception as e:
                    print(f"Failed to save draft: {e}")
                    import traceback
                    traceback.print_exc()
                    
            except Exception as e:
                print(f"Analysis/Drafting Failed: {e}")
                # Fallback analysis when Claude is unavailable
                if contents:
                    analysis_text = f"Document Analysis for {company}:\n\n"
                    analysis_text += f"Processed {len(contents)} document chunks.\n"
                    analysis_text += "Key findings:\n"
                    for i, content in enumerate(contents[:3]):
                        analysis_text += f"{i+1}. {content[:200]}...\n"
                    analysis_text += "\nNote: AI analysis temporarily unavailable due to API limitations. Manual review recommended."
                    draft_email = f"Subject: Document Review - {company}\n\nDear Team,\n\nWe have received and processed the documents for {company}. Due to current system limitations, we recommend manual review of the materials.\n\nBest regards,\nFinRAG System"
                else:
                    analysis_text = "No content extracted from uploaded documents. Please check file formats and try again."
                    draft_email = "Unable to generate draft - no content extracted."

        return {
            "status": "processed",
            "results": results,
            "analysis": analysis_text,
            "revenue_data": revenue_data,
            "draft_email": draft_email
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"GLOBAL WEBHOOK ERROR: {e}\n{error_details}")
        return {
            "status": "error",
            "message": str(e),
            "analysis": f"Internal Server Error: {str(e)}",
            "draft_email": "Error processing your request."
        }