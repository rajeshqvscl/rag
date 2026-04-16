"""
SQLAlchemy custom type for pgvector
Enables vector storage and operations in PostgreSQL
"""
import json
from typing import List, Optional
from sqlalchemy.types import UserDefinedType, String
from sqlalchemy import func


class Vector(UserDefinedType):
    """
    SQLAlchemy type for PostgreSQL pgvector extension.
    Stores and retrieves vector embeddings efficiently.
    """
    
    def __init__(self, dimensions: int = 384):
        """
        Initialize Vector type with specified dimensions.
        
        Args:
            dimensions: Number of dimensions in the vector (default 384 for all-MiniLM-L6-v2)
        """
        self.dimensions = dimensions
    
    def get_colspec(self, **kw):
        """Return column specification for CREATE TABLE"""
        return f"vector({self.dimensions})"
    
    def bind_processor(self, dialect):
        """Convert Python list to PostgreSQL vector string format"""
        def process(value):
            if value is None:
                return None
            if isinstance(value, list):
                # Convert list to PostgreSQL vector format: [1.0, 2.0, 3.0]
                return f"[{','.join(str(float(x)) for x in value)}]"
            return value
        return process
    
    def result_processor(self, dialect, coltype):
        """Convert PostgreSQL vector to Python list"""
        def process(value):
            if value is None:
                return None
            if isinstance(value, str):
                # Parse vector string format: [1.0, 2.0, 3.0]
                try:
                    # Remove brackets and split
                    value = value.strip('[]')
                    if value:
                        return [float(x) for x in value.split(',')]
                    return []
                except (ValueError, TypeError):
                    return None
            elif isinstance(value, list):
                return [float(x) for x in value]
            return value
        return process
    
    def literal_processor(self, dialect):
        """Process literal values in SQL expressions"""
        def process(value):
            if value is None:
                return 'NULL'
            if isinstance(value, list):
                return f"'[{','.join(str(float(x)) for x in value)}]'::vector({self.dimensions})"
            return str(value)
        return process
    
    class comparator_factory(UserDefinedType.Comparator):
        """Custom comparator for vector operations"""
        
        def cosine_distance(self, other):
            """Calculate cosine distance: 1 - cosine_similarity"""
            return func.cosine_distance(self.expr, other)
        
        def l2_distance(self, other):
            """Calculate L2/Euclidean distance"""
            return func.l2_distance(self.expr, other)
        
        def inner_product(self, other):
            """Calculate inner/dot product"""
            return func.inner_product(self.expr, other)
        
        def cosine_similarity(self, other):
            """Calculate cosine similarity: 1 - cosine_distance"""
            return 1 - func.cosine_distance(self.expr, other)
        
        def max_inner_product(self, other):
            """Calculate max inner product (for MIPS)"""
            return func.max_inner_product(self.expr, other)
        
        def nearest_neighbors(self, other, k: int = 5):
            """Get k nearest neighbors using cosine distance"""
            return func.cosine_distance(self.expr, other).asc().limit(k)


def to_pgvector(embedding: List[float], dimensions: int = 384) -> str:
    """
    Convert Python list to PostgreSQL vector string format.
    
    Args:
        embedding: List of float values
        dimensions: Expected dimensions (for validation)
    
    Returns:
        PostgreSQL vector string format
    """
    if embedding is None:
        return None
    
    if len(embedding) != dimensions:
        # Pad or truncate to match dimensions
        if len(embedding) < dimensions:
            embedding = embedding + [0.0] * (dimensions - len(embedding))
        else:
            embedding = embedding[:dimensions]
    
    return f"[{','.join(str(float(x)) for x in embedding)}]"


def from_pgvector(vector_str: str) -> Optional[List[float]]:
    """
    Convert PostgreSQL vector string to Python list.
    
    Args:
        vector_str: PostgreSQL vector string format
    
    Returns:
        List of float values or None
    """
    if vector_str is None:
        return None
    
    if isinstance(vector_str, list):
        return [float(x) for x in vector_str]
    
    try:
        vector_str = vector_str.strip('[]')
        if vector_str:
            return [float(x) for x in vector_str.split(',')]
    except (ValueError, TypeError):
        pass
    
    return None


# SQLAlchemy expression operators for vectors
def vector_distance(column, vector, metric='cosine'):
    """
    Create a SQL expression for vector distance.
    
    Args:
        column: SQLAlchemy column expression
        vector: Vector to compare against
        metric: Distance metric ('cosine', 'l2', 'inner_product')
    
    Returns:
        SQL expression for distance
    """
    vector_str = to_pgvector(vector) if isinstance(vector, list) else vector
    
    if metric == 'cosine':
        return func.cosine_distance(column, vector_str)
    elif metric == 'l2':
        return func.l2_distance(column, vector_str)
    elif metric == 'inner_product':
        return func.inner_product(column, vector_str)
    elif metric == 'max_inner_product':
        return func.max_inner_product(column, vector_str)
    else:
        raise ValueError(f"Unknown metric: {metric}")


def vector_similarity(column, vector, metric='cosine'):
    """
    Create a SQL expression for vector similarity (1 - distance for cosine).
    
    Args:
        column: SQLAlchemy column expression
        vector: Vector to compare against
        metric: Similarity metric ('cosine', 'inner_product')
    
    Returns:
        SQL expression for similarity
    """
    if metric == 'cosine':
        return 1 - func.cosine_distance(column, to_pgvector(vector))
    elif metric == 'inner_product':
        return func.inner_product(column, to_pgvector(vector))
    else:
        raise ValueError(f"Unknown metric: {metric}")
