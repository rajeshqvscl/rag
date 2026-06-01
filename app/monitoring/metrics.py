"""
Metrics and Monitoring System
Collects and exposes system metrics for monitoring and debugging
"""
import time
import os
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from functools import wraps
from sqlalchemy import text


@dataclass
class MetricPoint:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime
    tags: Dict[str, str]


METRICS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "data", "metrics_state.json")


class MetricsCollector:
    """Central metrics collection with optional JSON persistence"""

    def __init__(self, persist: bool = True):
        self.counters: Dict[str, float] = defaultdict(float)
        self.histograms: Dict[str, List[float]] = defaultdict(list)
        self.gauges: Dict[str, float] = defaultdict(float)
        self.timestamps: Dict[str, List[tuple]] = defaultdict(list)
        self.persist = persist
        if self.persist:
            self.load()

    def _to_serializable(self):
        return {
            "counters": dict(self.counters),
            "histograms": {k: v for k, v in self.histograms.items()},
            "gauges": dict(self.gauges),
        }

    def save(self):
        if not self.persist:
            return
        try:
            os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
            with open(METRICS_FILE, "w") as f:
                json.dump(self._to_serializable(), f)
        except Exception:
            pass

    def load(self):
        if not self.persist:
            return
        try:
            if os.path.exists(METRICS_FILE):
                with open(METRICS_FILE) as f:
                    data = json.load(f)
                self.counters.update(defaultdict(float, data.get("counters", {})))
                for k, v in data.get("histograms", {}).items():
                    self.histograms[k] = list(v)
                self.gauges.update(defaultdict(float, data.get("gauges", {})))
        except Exception:
            pass

    def increment(self, name: str, value: float = 1, tags: Dict = None):
        """Increment a counter metric"""
        key = self._make_key(name, tags)
        self.counters[key] += value
        self.timestamps[name].append((datetime.now(), value, tags or {}))
        self.save()

    def observe(self, name: str, value: float, tags: Dict = None):
        """Add observation to histogram"""
        key = self._make_key(name, tags)
        self.histograms[key].append(value)
        self.timestamps[name].append((datetime.now(), value, tags or {}))
        self.save()

    def set_gauge(self, name: str, value: float, tags: Dict = None):
        """Set gauge value"""
        key = self._make_key(name, tags)
        self.gauges[key] = value
        self.save()

    def _make_key(self, name: str, tags: Dict = None) -> str:
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}[{tag_str}]"

    def get_counter(self, name: str) -> float:
        return self.counters.get(name, 0)

    def get_histogram_stats(self, name: str) -> Dict[str, float]:
        values = self.histograms.get(name, [])
        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_values = sorted(values)
        n = len(sorted_values)

        return {
            "count": n,
            "sum": sum(values),
            "avg": sum(values) / n,
            "min": sorted_values[0],
            "max": sorted_values[-1],
            "p50": sorted_values[n // 2],
            "p95": sorted_values[int(n * 0.95)] if n > 1 else sorted_values[0],
            "p99": sorted_values[int(n * 0.99)] if n > 1 else sorted_values[0]
        }

    def get_all_metrics(self) -> Dict:
        """Get all metrics in Prometheus-compatible format"""
        output = []

        # Counters
        for name, value in self.counters.items():
            output.append(f"# TYPE {name} counter")
            output.append(f"{name} {value}")

        # Gauges
        for name, value in self.gauges.items():
            output.append(f"# TYPE {name} gauge")
            output.append(f"{name} {value}")

        # Histograms
        for name, values in self.histograms.items():
            if values:
                stats = self.get_histogram_stats(name)
                output.append(f"# TYPE {name} histogram")
                output.append(f"{name}_count {stats['count']}")
                output.append(f"{name}_sum {stats['sum']}")
                output.append(f"{name}_avg {stats['avg']}")

        return {"metrics": output, "raw": {
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "histograms": {k: self.get_histogram_stats(k) for k in self.histograms.keys()}
        }}

    def reset(self):
        """Reset all metrics"""
        self.counters.clear()
        self.histograms.clear()
        self.gauges.clear()
        self.timestamps.clear()
        self.save()


# Global metrics collector
METRICS = MetricsCollector()


def track_time(metric_name: str, tags: Dict = None):
    """
    Decorator to track execution time of functions

    Usage:
        @track_time("pdf_processing_duration")
        async def process_pdf(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                METRICS.observe(f"{metric_name}_ms", duration * 1000, tags)
                METRICS.increment(f"{metric_name}_total", tags=tags)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                METRICS.observe(f"{metric_name}_ms", duration * 1000, tags)
                METRICS.increment(f"{metric_name}_total", tags=tags)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def track_llm_call(model: str, success: bool = True):
    """Track LLM API call"""
    METRICS.increment("llm_calls_total", tags={"model": model, "status": "success" if success else "error"})
    METRICS.set_gauge("llm_last_call", time.time(), tags={"model": model})


def track_retrieval(query_type: str, results_count: int):
    """Track retrieval operation"""
    METRICS.increment("retrieval_calls_total", tags={"type": query_type})
    METRICS.observe("retrieval_results_count", results_count, tags={"type": query_type})


def track_pinecone_query(namespace: str = "default"):
    """Track Pinecone query"""
    METRICS.increment("pinecone_queries_total", tags={"namespace": namespace})


def track_embedding_request(batch_size: int):
    """Track embedding generation"""
    METRICS.increment("embedding_requests_total")
    METRICS.observe("embedding_batch_size", batch_size)


def get_system_health() -> Dict:
    """Get system health status"""
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }

    # Check LLM availability
    try:
        from app.core.llm_client import get_safe_client
        client = get_safe_client()
        health["components"]["llm"] = {"status": "up", "model": getattr(client, 'default_model', 'unknown')}
    except Exception as e:
        health["components"]["llm"] = {"status": "down", "error": str(e)[:100]}
        health["status"] = "degraded"

    # Check Pinecone
    try:
        from app.rag.pinecone_client import index
        stats = index.describe_index_stats()
        namespaces_raw = stats.get("namespaces", {})
        health["components"]["pinecone"] = {
            "status": "up",
            "dimension": stats.get("dimension"),
            "metric": stats.get("metric"),
            "total_vectors": stats.get("total_vector_count", 0),
            "namespaces_count": len(namespaces_raw),
            "namespaces": [
                {"name": ns, "vectors": info.get("vector_count", 0)}
                for ns, info in namespaces_raw.items()
            ]
        }
    except Exception as e:
        health["components"]["pinecone"] = {"status": "down", "error": str(e)[:100]}
        health["status"] = "degraded"

    # Check Database
    try:
        from app.db.session import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["components"]["database"] = {"status": "up"}
    except Exception as e:
        health["components"]["database"] = {"status": "down", "error": str(e)[:100]}
        health["status"] = "degraded"

    return health


def get_metrics_summary() -> Dict:
    """Get summary of key metrics"""
    return {
        "timestamp": datetime.now().isoformat(),
        "llm_calls": METRICS.get_counter("llm_calls_total"),
        "retrieval_calls": METRICS.get_counter("retrieval_calls_total"),
        "pinecone_queries": METRICS.get_counter("pinecone_queries_total"),
        "embedding_requests": METRICS.get_counter("embedding_requests_total"),
        "pdf_processing": METRICS.get_counter("pdf_processing_total"),
        "avg_llm_latency": METRICS.get_histogram_stats("llm_calls_ms")["avg"],
        "avg_retrieval_latency": METRICS.get_histogram_stats("retrieval_calls_ms")["avg"],
        "avg_embedding_latency": METRICS.get_histogram_stats("embedding_requests_ms")["avg"],
    }


def format_prometheus_metrics() -> str:
    """Format metrics in Prometheus exposition format"""
    metrics = METRICS.get_all_metrics()
    output = []

    output.append("# HELP rag_system_info System information")
    output.append("# TYPE rag_system_info gauge")
    output.append('rag_system_info{version="1.0",environment="production"} 1')

    for line in metrics["metrics"]:
        output.append(line)

    return "\n".join(output)


class OperationTimer:
    """Context manager for timing operations"""

    def __init__(self, metric_name: str, tags: Dict = None):
        self.metric_name = metric_name
        self.tags = tags or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000
        METRICS.observe(f"{self.metric_name}_ms", duration, self.tags)
        if exc_type is None:
            METRICS.increment(f"{self.metric_name}_total", tags={**self.tags, "status": "success"})
        else:
            METRICS.increment(f"{self.metric_name}_total", tags={**self.tags, "status": "error"})

    def set_result(self, result_name: str, value: float):
        """Set a result metric"""
        METRICS.observe(f"{self.metric_name}_{result_name}", value, self.tags)