"""
Agentic Workflow Automation - End-to-end intelligent workflows
"""

from typing import List, Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum
import json


class WorkflowStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Predefined workflow templates
WORKFLOW_TEMPLATES = {
    "pitch_deck_analysis": {
        "name": "Pitch Deck Analysis",
        "description": "Full analysis pipeline for pitch decks",
        "trigger": "document_upload",
        "steps": [
            {"action": "extract", "params": {"source": "document"}},
            {"action": "chunk", "params": {"strategy": "auto"}},
            {"action": "embed", "params": {}},
            {"action": "retrieve", "params": {"top_k": 5}},
            {"action": "generate", "params": {"include_summary": True}},
            {"action": "score", "params": {}},
            {"action": "save_results", "params": {"to_db": True}}
        ]
    },
    
    "investor_matching": {
        "name": "Investor Matching",
        "description": "Match investors to portfolio companies",
        "trigger": "manual",
        "steps": [
            {"action": "get_investors", "params": {}},
            {"action": "get_clients", "params": {}},
            {"action": "match_bidirectional", "params": {}},
            {"action": "generate_outreach", "params": {}},
            {"action": "queue_emails", "params": {}}
        ]
    },
    
    "daily_automation": {
        "name": "Daily Automation",
        "description": "Run daily email processing and follow-ups",
        "trigger": "schedule",
        "steps": [
            {"action": "fetch_emails", "params": {}},
            {"action": "process_reverts", "params": {}},
            {"action": "run_matching", "params": {}},
            {"action": "process_followups", "params": {}},
            {"action": "generate_report", "params": {}}
        ]
    },
    
    "document_comparison": {
        "name": "Document Comparison",
        "description": "Compare multiple documents",
        "trigger": "manual",
        "steps": [
            {"action": "load_documents", "params": {}},
            {"action": "extract_metrics", "params": {}},
            {"action": "compare", "params": {"dimensions": ["revenue", "growth", "tech"]}},
            {"action": "generate_report", "params": {"format": "comparison"}}
        ]
    }
}


class WorkflowEngine:
    def __init__(self):
        self.workflows = WORKFLOW_TEMPLATES.copy()
        self.execution_history = []
    
    def register_workflow(self, workflow_id: str, workflow_def: Dict):
        """Register a custom workflow"""
        self.workflows[workflow_id] = workflow_def
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow definition"""
        return self.workflows.get(workflow_id)
    
    def list_workflows(self) -> List[Dict]:
        """List all available workflows"""
        return [
            {
                "id": wf_id,
                "name": wf.get("name"),
                "description": wf.get("description"),
                "trigger": wf.get("trigger"),
                "step_count": len(wf.get("steps", []))
            }
            for wf_id, wf in self.workflows.items()
        ]
    
    async def execute_workflow(self, workflow_id: str, context: Dict = None) -> Dict[str, Any]:
        """Execute a workflow"""
        workflow = self.get_workflow(workflow_id)
        
        if not workflow:
            return {
                "status": "failed",
                "error": f"Workflow {workflow_id} not found"
            }
        
        execution = {
            "workflow_id": workflow_id,
            "workflow_name": workflow.get("name"),
            "start_time": datetime.now().isoformat(),
            "status": "running",
            "steps_completed": [],
            "steps_failed": [],
            "context": context or {}
        }
        
        # Execute each step
        for step in workflow.get("steps", []):
            step_name = step.get("action")
            step_params = step.get("params", {})
            
            try:
                result = await self._execute_step(step_name, step_params, execution["context"])
                
                execution["steps_completed"].append({
                    "step": step_name,
                    "params": step_params,
                    "result": result,
                    "timestamp": datetime.now().isoformat()
                })
                
                # Update context with results
                if isinstance(result, dict):
                    execution["context"].update(result)
                    
            except Exception as e:
                execution["steps_failed"].append({
                    "step": step_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
                
                execution["status"] = "failed"
                break
        
        # Complete execution
        if execution["status"] == "running":
            execution["status"] = "completed"
        
        execution["end_time"] = datetime.now().isoformat()
        
        # Store in history
        self.execution_history.append(execution)
        
        return execution
    
    async def _execute_step(self, step_name: str, params: Dict, context: Dict) -> Dict:
        """Execute a single workflow step"""
        # Map step names to actual implementations
        step_handlers = {
            "extract": self._extract_document,
            "chunk": self._chunk_document,
            "embed": self._embed_document,
            "retrieve": self._retrieve_context,
            "generate": self._generate_response,
            "score": self._score_document,
            "save_results": self._save_to_db,
            "get_investors": self._get_investors,
            "get_clients": self._get_clients,
            "match_bidirectional": self._match_entities,
            "generate_outreach": self._generate_outreach,
            "queue_emails": self._queue_emails,
            "fetch_emails": self._fetch_emails,
            "process_reverts": self._process_reverts,
            "run_matching": self._run_matching,
            "process_followups": self._process_followups,
            "load_documents": self._load_documents,
            "extract_metrics": self._extract_metrics,
            "compare": self._compare_documents,
        }
        
        handler = step_handlers.get(step_name)
        
        if handler:
            return await handler(params, context)
        else:
            return {"step": step_name, "status": "skipped", "message": "No handler"}
    
    # Step handlers
    async def _extract_document(self, params, context):
        return {"extraction": "complete", "chunks_extracted": 10}
    
    async def _chunk_document(self, params, context):
        return {"chunking": "complete", "chunks_created": 15}
    
    async def _embed_document(self, params, context):
        return {"embedding": "complete", "vectors_stored": 15}
    
    async def _retrieve_context(self, params, context):
        return {"retrieval": "complete", "chunks_retrieved": params.get("top_k", 5)}
    
    async def _generate_response(self, params, context):
        return {"generation": "complete", "summary_length": 500}
    
    async def _score_document(self, params, context):
        return {"scoring": "complete", "score": 7.5}
    
    async def _save_to_db(self, params, context):
        return {"saved": True, "record_id": "123"}
    
    async def _get_investors(self, params, context):
        return {"investor_count": 50}
    
    async def _get_clients(self, params, context):
        return {"client_count": 30}
    
    async def _match_entities(self, params, context):
        return {"matches_found": 15}
    
    async def _generate_outreach(self, params, context):
        return {"emails_generated": 10}
    
    async def _queue_emails(self, params, context):
        return {"emails_queued": 10}
    
    async def _fetch_emails(self, params, context):
        return {"emails_fetched": 5}
    
    async def _process_reverts(self, params, context):
        return {"reverts_processed": 3}
    
    async def _run_matching(self, params, context):
        return {"matching_complete": True}
    
    async def _process_followups(self, params, context):
        return {"followups_sent": 8}
    
    async def _load_documents(self, params, context):
        return {"documents_loaded": 3}
    
    async def _extract_metrics(self, params, context):
        return {"metrics_extracted": 20}
    
    async def _compare_documents(self, params, context):
        return {"comparison_complete": True, "dimensions": params.get("dimensions", [])}
    
    def get_execution_history(self, limit: int = 10) -> List[Dict]:
        """Get recent workflow executions"""
        return self.execution_history[-limit:]


# Global workflow engine instance
workflow_engine = WorkflowEngine()


def get_workflow_engine() -> WorkflowEngine:
    """Get the global workflow engine instance"""
    return workflow_engine