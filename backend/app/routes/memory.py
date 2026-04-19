"""
Memory routes for conversation history and vector search
"""
from fastapi import APIRouter, Depends, HTTPException
from app.services.security_service import get_api_key
from app.services.memory_service import memory_service
from app.services.claude_service import structure_text
from app.services.embeddings import get_embeddings
import numpy as np
import json
from typing import List, Dict, Any

router = APIRouter()

@router.get("/memory/conversations")
def get_conversations(
    limit: int = 10,
    api_key: str = Depends(get_api_key)
):
    """Get conversation history"""
    try:
        conversations = memory_service.get_conversations(limit)
        return {
            "status": "success",
            "conversations": conversations
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/memory/conversations")
def add_conversation(
    query: str,
    response: str,
    context: str = "",
    api_key: str = Depends(get_api_key)
):
    """Add conversation to memory"""
    try:
        memory_service.add_conversation(query, response, context)
        return {
            "status": "success",
            "message": "Conversation added to memory"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory/search")
def search_memory(
    query: str,
    k: int = 5,
    api_key: str = Depends(get_api_key)
):
    """Search memory by query"""
    try:
        # Get query embedding
        query_embedding = get_embeddings([query])[0]
        
        # Search vectors
        results = memory_service.search_vectors(query_embedding, k)
        
        return {
            "status": "success",
            "results": results,
            "query": query
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/memory/add-vector")
def add_vector(
    text: str,
    api_key: str = Depends(get_api_key)
):
    """Add text vector to memory"""
    try:
        # Get text embedding
        embedding = get_embeddings([text])[0]
        
        # Add to vector index
        memory_service.add_vector(text, embedding)
        
        return {
            "status": "success",
            "message": "Vector added to memory"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/memory/stats")
def get_memory_stats(api_key: str = Depends(get_api_key)):
    """Get memory statistics"""
    try:
        return {
            "status": "success",
            "total_conversations": len(memory_service.conversations),
            "total_vectors": memory_service.vector_index.ntotal if memory_service.vector_index else 0,
            "memory_file": memory_service.memory_file
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
