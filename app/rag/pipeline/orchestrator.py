"""
Document Intelligence Pipeline - Orchestrator
Coordinates all pipeline stages: extraction → validation → synthesis
"""
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
import io
import concurrent.futures

from app.rag.pipeline.enhanced_loader import EnhancedPDFLoader, load_pdf as enhanced_load_pdf
from app.rag.pipeline.fact_registry import FactRegistry, Fact
from app.rag.pipeline.table_extractor import TableExtractor
from app.rag.pipeline.vision_analyzer import VisionAnalyzer, LayoutAnalyzer
from app.rag.pipeline.validation_engine import ValidationEngine, FactDeduplicator
from app.rag.pipeline.hybrid_retriever import HybridRetriever, FactAwareRetriever


@dataclass
class PipelineConfig:
    """Configuration for pipeline stages"""
    extract_tables: bool = True
    analyze_charts: bool = True
    detect_sections: bool = True
    extract_facts: bool = True
    validate_facts: bool = True
    hybrid_retrieval: bool = True
    min_confidence: float = 0.6


class DocumentIntelligencePipeline:
    """
    Main orchestrator for document intelligence pipeline
    
    Stages:
    1. PDF Loading (page-by-page)
    2. Content Extraction (text, tables, images)
    3. Section Detection
    4. Fact Extraction & Validation
    5. Knowledge Graph Construction
    6. Hybrid Retrieval Setup
    """
    
    def __init__(self, config: PipelineConfig = None):
        self.config = config or PipelineConfig()
        
        self.loader = EnhancedPDFLoader()
        self.table_extractor = TableExtractor()
        self.vision_analyzer = VisionAnalyzer()
        self.layout_analyzer = LayoutAnalyzer()
        self.validation_engine = ValidationEngine()
        self.deduplicator = FactDeduplicator()
        self.hybrid_retriever = HybridRetriever()
        self.fact_aware_retriever = None
        
        self.fact_registry = FactRegistry()
        self.chunks = []
        self.chunk_metadata = []
    
    def process(self, file_content: bytes) -> Dict[str, Any]:
        """
        Run full pipeline on PDF bytes with parallel stage execution

        Returns:
            Dict with:
            - full_text: combined text
            - pages: list of page data
            - facts: fact registry data
            - sections: section breakdown
            - tables: extracted tables
            - chunks: processed chunks for retrieval
        """
        print("\n" + "="*60)
        print("[PIPELINE] Starting Document Intelligence Pipeline")
        print("="*60)

        results = {
            "full_text": "",
            "pages": [],
            "sections": {},
            "tables": [],
            "facts": {},
            "chunks": [],
            "metadata": {}
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}

            if self.config.extract_tables:
                futures['tables'] = executor.submit(self.table_extractor.extract_from_bytes, file_content)

            if self.config.analyze_charts:
                futures['charts'] = executor.submit(self.vision_analyzer.get_all_chart_pages, file_content)

            full_text, pages = enhanced_load_pdf(file_content)
            results["full_text"] = full_text
            results["pages"] = pages
            print(f"[PIPELINE] Stage 1: Loaded {len(pages)} pages")

            if futures:
                concurrent.futures.wait(futures.values())
                if 'tables' in futures:
                    results["tables"] = futures['tables'].result()
                    print(f"[PIPELINE] Stage 2a: Found {len(results['tables'])} tables")
                if 'charts' in futures:
                    chart_page_nums = futures['charts'].result()
                    if chart_page_nums:
                        print(f"[PIPELINE] Stage 2b: Found {len(chart_page_nums)} chart pages")
                    else:
                        print("[PIPELINE] Stage 2b: No chart pages detected")

        if self.config.detect_sections:
            print("[PIPELINE] Stage 3: Analyzing sections...")
            section_counts = self._count_sections(pages)
            results["sections"] = section_counts
            print(f"[PIPELINE] Sections: {section_counts}")

        if self.config.extract_facts:
            print("[PIPELINE] Stage 4: Extracting facts...")
            self._extract_facts_from_pages(pages)
            results["facts"] = self.fact_registry.to_structured_json()
            print(f"[PIPELINE] Extracted {len(self.fact_registry.facts)} facts")

        if self.config.validate_facts:
            print("[PIPELINE] Stage 5: Validating facts...")
            self._validate_and_deduplicate()
            print(f"[PIPELINE] Validated and deduplicated facts")

        print("[PIPELINE] Stage 6: Chunking for retrieval...")
        self._create_chunks(pages)
        results["chunks"] = self.chunks[:50]
        print(f"[PIPELINE] Created {len(self.chunks)} chunks")

        if self.config.hybrid_retrieval:
            print("[PIPELINE] Stage 7: Building hybrid index...")
            self._build_hybrid_index()
            self.fact_aware_retriever = FactAwareRetriever(self.hybrid_retriever)
            print("[PIPELINE] Hybrid index ready")

        print("\n" + "="*60)
        print("[PIPELINE] Pipeline Complete!")
        print("="*60 + "\n")

        return results
    
    def _count_sections(self, pages: List[Dict]) -> Dict[str, int]:
        """Count pages per section"""
        section_counts = {}
        
        for page in pages:
            for section in page.get("sections", []):
                section_counts[section] = section_counts.get(section, 0) + 1
        
        return section_counts
    
    def _extract_facts_from_pages(self, pages: List[Dict]):
        """Extract and validate facts from all pages"""
        from app.rag.pipeline.fact_registry import extract_revenue_facts
        
        for page in pages:
            page_num = page.get("page", 1)
            text = page.get("text", "")
            sections = page.get("sections", [])
            
            primary_section = sections[0] if sections else "general"
            
            facts = extract_revenue_facts(text, page_num, primary_section)
            
            for fact in facts:
                validation = self.validation_engine.validate_fact(fact.to_dict())
                
                if validation.valid:
                    fact.confidence = max(0.5, fact.confidence + validation.confidence_adjustment)
                    fact.validated = True
                    self.fact_registry.add(fact)
    
    def _validate_and_deduplicate(self):
        """Validate and deduplicate all facts"""
        all_facts = self.fact_registry.facts
        fact_dicts = [f.to_dict() for f in all_facts]
        
        validated = self.validation_engine.cross_validate(fact_dicts)
        
        self.fact_registry = FactRegistry()
        for fact_dict in validated:
            if fact_dict.get("cross_validation_notes"):
                fact_dict["confidence"] *= 0.8
            
            fact = Fact(**{k: v for k, v in fact_dict.items() if k != "cross_validation_notes"})
            self.fact_registry.add(fact)
    
    def _create_chunks(self, pages: List[Dict], chunk_size: int = 800, overlap: int = 150):
        """Create chunks with metadata for retrieval"""
        self.chunks = []
        self.chunk_metadata = []
        
        for page in pages:
            text = page.get("text", "")
            page_num = page.get("page", 1)
            sections = page.get("sections", [])
            tables = page.get("tables", [])
            
            table_content = ""
            for table in tables:
                if isinstance(table, dict):
                    table_content += f"\n[TABLE: {table.get('type', 'general')}]\n"
                    for row in table.get("rows", [])[:5]:
                        table_content += " | ".join(str(c) for c in row) + "\n"
            
            start = 0
            while start < len(text):
                end = start + chunk_size
                content = text[start:end].strip()
                
                if content:
                    chunk_with_tables = content + table_content if start == 0 else content
                    
                    self.chunks.append(chunk_with_tables)
                    self.chunk_metadata.append({
                        "page": page_num,
                        "section": sections[0] if sections else "general",
                        "sections": sections[:3],
                        "has_tables": len(tables) > 0,
                        "type": "text"
                    })
                
                start += chunk_size - overlap
    
    def _build_hybrid_index(self):
        """Build hybrid BM25 + embedding index"""
        self.hybrid_retriever.index(self.chunks, self.chunk_metadata)
    
    def query(self, query: str, section: Optional[str] = None, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Query the pipeline with hybrid retrieval
        
        Returns:
            Dict with results, facts, and context
        """
        if self.fact_aware_retriever:
            return self.fact_aware_retriever.retrieve(query, section, doc_id)
        
        return {"results": [], "facts": self.fact_registry.to_structured_json()}
    
    def get_fact(self, key: str) -> Optional[Fact]:
        """Get a specific fact from registry"""
        return self.fact_registry.get_by_key(key)
    
    def get_facts_by_category(self, category: str) -> List[Fact]:
        """Get all facts in a category"""
        return self.fact_registry.get_by_category(category)
    
    def get_structured_analysis(self) -> Dict[str, Any]:
        """
        Get full structured analysis for downstream use
        (scoring, email generation, etc.)
        """
        return {
            "facts": self.fact_registry.to_structured_json(),
            "section_breakdown": self._count_sections(self.loader.pages) if hasattr(self.loader, 'pages') else {},
            "table_count": len(self.table_extractor.extract_from_bytes),
            "validation_status": "complete",
            "confidence_range": (
                min(f.confidence for f in self.fact_registry.facts) if self.fact_registry.facts else 0,
                max(f.confidence for f in self.fact_registry.facts) if self.fact_registry.facts else 0
            )
        }


# Backward compatibility wrapper
def process_document(file_content: bytes, config: PipelineConfig = None) -> Dict[str, Any]:
    """Process document through full pipeline"""
    pipeline = DocumentIntelligencePipeline(config)
    return pipeline.process(file_content)