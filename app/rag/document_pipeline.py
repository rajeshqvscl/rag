"""
Unified Document Intelligence Pipeline
Orchestrates: PDF extraction → Fact extraction → Validation → Storage → Retrieval
"""

import io
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from .pdf_intelligence import PDFIntelligence, load_pdf_intelligent
from .table_extractor import TableExtractor, extract_all_tables
from .vision_analyzer import VisionAnalyzer, extract_page_as_image
from .fact_registry import FactRegistry, ExtractedFact, FactSource, extract_facts_from_text
from .validator import FactValidator, validate_page_data, validate_table_data
from .hybrid_retriever import HybridRetriever
from .embedder import embed_text
from .vector_store import store_embeddings


@dataclass
class PipelineConfig:
    enable_vision: bool = True
    enable_table_extraction: bool = True
    enable_validation: bool = True
    enable_fact_registry: bool = True
    max_pages: int = 100
    chunk_size: int = 800
    vision_max_charts: int = 10


class DocumentIntelligencePipeline:
    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        self.pdf_intel = PDFIntelligence()
        self.table_extractor = TableExtractor()
        self.vision_analyzer = VisionAnalyzer()
        self.validator = FactValidator()
        self.fact_registry = FactRegistry()
        self.hybrid_retriever = HybridRetriever()
    
    def process(self, file_content: bytes, doc_id: str = None, 
                metadata: Dict = None) -> Dict[str, Any]:
        """
        Main pipeline execution
        
        Returns:
            {
                "full_text": str,
                "pages": List[Dict],
                "tables": List[Dict],
                "facts": Dict,
                "charts": List[Dict],
                "validation": Dict,
                "chunks": List[Dict],
                "stats": Dict
            }
        """
        start_time = time.time()
        results = {
            "doc_id": doc_id,
            "metadata": metadata or {},
            "processing_time": 0,
            "pages_processed": 0,
            "tables_found": 0,
            "facts_extracted": 0,
            "charts_analyzed": 0,
            "errors": []
        }
        
        try:
            print(f"[PIPELINE] Starting document intelligence pipeline")
            
            full_text, pages = self._extract_text_and_structure(file_content)
            results["full_text"] = full_text
            results["pages"] = pages
            results["pages_processed"] = len(pages)
            
            tables = self._extract_tables(file_content)
            results["tables"] = tables
            results["tables_found"] = len(tables)
            
            facts = self._extract_facts(full_text, pages, tables)
            results["facts"] = facts.to_structured_json() if hasattr(facts, 'to_structured_json') else facts
            results["facts_extracted"] = len(facts.get_all_facts()) if hasattr(facts, 'get_all_facts') else 0
            self.fact_registry = facts
            
            if self.config.enable_vision:
                charts = self._analyze_charts(file_content)
                results["charts"] = charts
                results["charts_analyzed"] = len(charts)
            else:
                results["charts"] = []
            
            page_validations = self._validate_pages(pages)
            table_validations = self._validate_tables(tables)
            results["validation"] = {
                "pages": page_validations,
                "tables": table_validations
            }
            
            chunks = self._create_chunks(pages, tables)
            results["chunks"] = chunks
            
            results["processing_time"] = round(time.time() - start_time, 2)
            
            print(f"[PIPELINE] Completed in {results['processing_time']}s")
            print(f"[PIPELINE] Pages: {results['pages_processed']}, Tables: {results['tables_found']}, "
                  f"Facts: {results['facts_extracted']}, Charts: {results['charts_analyzed']}")
            
        except Exception as e:
            results["errors"].append(str(e))
            print(f"[PIPELINE] Error: {e}")
        
        return results
    
    def _extract_text_and_structure(self, file_content: bytes) -> Tuple[str, List[Dict]]:
        print("[PIPELINE] Extracting text and structure...")
        return load_pdf_intelligent(file_content)
    
    def _extract_tables(self, file_content: bytes) -> List[Dict]:
        if not self.config.enable_table_extraction:
            return []
        
        print("[PIPELINE] Extracting tables...")
        tables = extract_all_tables(file_content=file_content, pages="all")
        return tables
    
    def _extract_facts(self, full_text: str, pages: List[Dict], tables: List[Dict]) -> FactRegistry:
        if not self.config.enable_fact_registry:
            return FactRegistry()
        
        print("[PIPELINE] Extracting and validating facts...")
        registry = FactRegistry()
        
        for page in pages:
            page_num = page.get("page", 0)
            text = page.get("text", "")
            sections = page.get("sections", ["general"])
            section = sections[0] if sections else "general"
            
            facts = extract_facts_from_text(text, page_num, section)
            for fact in facts:
                validation = self.validator.validate_metric(fact.name, fact.value)
                if validation.passed:
                    fact.validated = True
                else:
                    fact.confidence = max(fact.confidence - 20, 40)
                registry.add(fact)
        
        for table in tables:
            page_num = table.get("page", 0)
            for row in table.get("rows", []):
                row_text = " ".join([str(cell) for cell in row])
                facts = extract_facts_from_text(row_text, page_num, "table_data")
                for fact in facts:
                    fact.source_type = FactSource.TABLE
                    validation = self.validator.validate_metric(fact.name, fact.value)
                    if validation.passed:
                        fact.validated = True
                    registry.add(fact)
        
        return registry
    
    def _analyze_charts(self, file_content: bytes) -> List[Dict]:
        print("[PIPELINE] Analyzing charts with vision...")
        charts_data = self.vision_analyzer.extract_charts_from_pdf(file_content)
        
        if not charts_data:
            return []
        
        analyses = self.vision_analyzer.batch_analyze_charts(
            charts_data, 
            max_charts=self.config.vision_max_charts
        )
        
        results = []
        for analysis in analyses:
            results.append({
                "page": analysis["page"],
                "chart_type": analysis.get("analysis", {}).get("chart_type", "unknown"),
                "title": analysis.get("analysis", {}).get("title", ""),
                "metrics": analysis.get("analysis", {}).get("metrics", []),
                "confidence": analysis.get("analysis", {}).get("confidence", 0)
            })
        
        return results
    
    def _validate_pages(self, pages: List[Dict]) -> List[Dict]:
        if not self.config.enable_validation:
            return []
        
        validations = []
        for page in pages:
            validation = validate_page_data(page)
            validations.append(validation)
        
        return validations
    
    def _validate_tables(self, tables: List[Dict]) -> List[Dict]:
        if not self.config.enable_validation:
            return []
        
        return validate_table_data(tables)
    
    def _prioritize_and_cap_chunks(self, chunks: List[Dict], max_chunks: int = 25) -> List[Dict]:
        """Rank chunks by presence of financial terms and keep top N chunks before embedding."""
        if len(chunks) <= max_chunks:
            return chunks

        import re
        financial_keywords = [
            "revenue", "arr", "growth", "margin", "ebitda", "pipeline", "funding", 
            "valuation", "tam", "sam", "som", "customer", "cohort", "churn",
            "profit", "sales", "cac", "ltv", "forecast", "projection", "cap table"
        ]

        scored_chunks = []
        for idx, chunk in enumerate(chunks):
            content_lower = chunk.get("content", "").lower()
            score = 0.0
            
            # Check for financial keywords
            for kw in financial_keywords:
                if kw in content_lower:
                    score += 1.5
                    
            # Check for currency symbols and numeric indicators
            has_currency = any(sym in chunk.get("content", "") for sym in ["₹", "$", "€", "£"])
            if has_currency:
                score += 2.0
                
            # Check for percentage figures
            has_percent = "%" in content_lower
            if has_percent:
                score += 1.0
                
            # Check for generic numbers (evidence density)
            number_count = len(re.findall(r'\b\d+\b', content_lower))
            score += min(number_count * 0.2, 3.0)
            
            # Preserve original layout ordering slightly by adding a tiny position bias
            score -= (idx / len(chunks)) * 0.1

            scored_chunks.append((score, chunk))

        # Sort by priority score descending
        scored_chunks.sort(key=lambda x: -x[0])
        
        # Take the top N chunks
        selected_chunks = [item[1] for item in scored_chunks[:max_chunks]]
        print(f"[CHUNKER] Prioritized and selected top {len(selected_chunks)} chunks out of {len(chunks)} total.")
        return selected_chunks

    def _create_chunks(self, pages: List[Dict], tables: List[Dict]) -> List[Dict]:
        chunks = []
        
        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page", 1)
            sections = page.get("sections", [])
            
            start = 0
            while start < len(text):
                end = start + self.config.chunk_size
                chunk_text = text[start:end].strip()
                
                if chunk_text:
                    chunks.append({
                        "content": chunk_text,
                        "metadata": {
                            "page": page_num,
                            "sections": sections[:2],
                            "section": sections[0] if sections else "general",
                            "has_tables": False
                        }
                    })
                
                start += self.config.chunk_size - 150
        
        return self._prioritize_and_cap_chunks(chunks, max_chunks=25)
    
    def index_to_vector_store(self, results: Dict, namespace: str = None) -> Dict:
        """Index processed results to vector store"""
        chunks = results.get("chunks", [])
        
        if not chunks:
            return {"status": "no_chunks", "count": 0}
        
        print(f"[PIPELINE] Indexing {len(chunks)} chunks to vector store")
        
        texts = [c["content"] for c in chunks]
        embeddings = embed_text(texts, namespace=namespace or results.get("doc_id", "default"))
        
        store_embeddings(
            chunks=chunks,
            embeddings=embeddings,
            namespace=namespace or results.get("doc_id", "default"),
            doc_id=results.get("doc_id"),
            domain=results.get("metadata", {}).get("domain", "General")
        )
        
        return {"status": "indexed", "count": len(chunks)}
    
    def get_fact_report(self) -> Dict:
        """Generate a fact extraction report"""
        if not hasattr(self.fact_registry, 'get_stats'):
            return {"error": "No fact registry available"}
        
        stats = self.fact_registry.get_stats()
        structured = self.fact_registry.to_structured_json()
        
        return {
            "stats": stats,
            "sections": structured
        }


def quick_process(file_content: bytes, doc_id: str = None) -> Dict:
    """Quick processing with sensible defaults"""
    config = PipelineConfig(
        enable_vision=True,
        enable_table_extraction=True,
        enable_validation=True,
        enable_fact_registry=True
    )
    
    pipeline = DocumentIntelligencePipeline(config)
    return pipeline.process(file_content, doc_id)


def process_and_index(file_content: bytes, doc_id: str, namespace: str = None) -> Dict:
    """Process document and index to vector store"""
    config = PipelineConfig()
    pipeline = DocumentIntelligencePipeline(config)
    
    results = pipeline.process(file_content, doc_id)
    
    if namespace:
        pipeline.index_to_vector_store(results, namespace)
    
    return results