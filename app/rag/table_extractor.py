import pdfplumber
import io
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    camelot = None


@dataclass
class ExtractedTable:
    page_num: int
    table_idx: int
    headers: List[str]
    rows: List[List[str]]
    confidence: float
    extraction_method: str
    cleaned_data: List[List[str]]


class TableExtractor:
    def __init__(self):
        self.min_rows = 2
        self.min_cols = 2
        self.max_rows_per_table = 100
    
    def extract_from_bytes(self, file_content: bytes, pages: str = "all") -> List[ExtractedTable]:
        tables = []
        
        if CAMELOT_AVAILABLE:
            try:
                tables.extend(self._extract_with_camelot(file_content, pages))
            except Exception as e:
                print(f"[TABLE_EXTRACTOR] Camelot failed: {e}")
        
        if not tables:
            tables.extend(self._extract_with_pdfplumber(file_content, pages))
        
        return tables
    
    def _extract_with_camelot(self, file_content: bytes, pages: str) -> List[ExtractedTable]:
        tables = []
        
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(file_content)
                tmp_path = tmp.name
            
            if pages == "all":
                camelot_tables = camelot.read_pdf(tmp_path, pages="all", flavor="stream")
            else:
                camelot_tables = camelot.read_pdf(tmp_path, pages=pages, flavor="stream")
            
            for idx, table in enumerate(camelot_tables):
                if table.df is not None and len(table.df) >= self.min_rows:
                    extracted = self._process_camelot_table(table.df, idx)
                    if extracted:
                        tables.append(extracted)
            
            import os
            os.unlink(tmp_path)
            
        except Exception as e:
            print(f"[TABLE_EXTRACTOR] Camelot error: {e}")
        
        return tables
    
    def _extract_with_pdfplumber(self, file_content: bytes, pages: str) -> List[ExtractedTable]:
        tables = []
        
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                page_range = range(len(pdf.pages)) if pages == "all" else self._parse_pages(pages)
                
                for page_idx in page_range:
                    if page_idx >= len(pdf.pages):
                        break
                    
                    page = pdf.pages[page_idx]
                    try:
                        extracted_tables = page.extract_tables()
                        if extracted_tables:
                            for table_idx, table in enumerate(extracted_tables):
                                if table and len(table) >= self.min_rows:
                                    extracted = self._process_table_data(table, page_idx + 1, table_idx)
                                    if extracted:
                                        tables.append(extracted)
                    except Exception as e:
                        print(f"[TABLE_EXTRACTOR] pdfplumber page {page_idx} error: {e}")
                        
        except Exception as e:
            print(f"[TABLE_EXTRACTOR] pdfplumber error: {e}")
        
        return tables
    
    def _is_valid_data_table(self, headers: List[str], rows: List[List[str]]) -> bool:
        """Filter out layout grids, decorative tables, and low-density visual noise."""
        if not rows or len(rows) < self.min_rows:
            return False
            
        max_cols = max(len(row) for row in rows) if rows else 0
        if max_cols < self.min_cols:
            return False
            
        total_cells = len(rows) * max_cols
        if total_cells == 0:
            return False
            
        filled_cells = sum(1 for row in rows for cell in row if str(cell).strip())
        fill_rate = filled_cells / total_cells
        
        # Grid/layout pre-filter: skip decorative boxes (under 15% fill rate)
        if fill_rate < 0.15:
            return False
            
        # Skip decorative elements containing only whitespace or single punctuation
        total_char_len = sum(len(str(cell).strip()) for row in rows for cell in row if cell)
        avg_char_len = total_char_len / filled_cells if filled_cells > 0 else 0
        if avg_char_len < 1.0:
            return False
            
        return True

    def _process_camelot_table(self, df, table_idx: int) -> Optional[ExtractedTable]:
        if df.empty:
            return None
        
        headers = df.columns.tolist() if hasattr(df, 'columns') else []
        rows = df.fillna("").values.tolist()
        
        if not rows or len(rows) < self.min_rows:
            return None
        
        cleaned_headers = self._clean_row(headers)
        cleaned_rows = [self._clean_row(row) for row in rows[:self.max_rows_per_table]]
        
        if not self._is_valid_data_table(cleaned_headers, cleaned_rows):
            return None

        confidence = self._calculate_confidence(cleaned_headers, cleaned_rows)
        
        return ExtractedTable(
            page_num=0,
            table_idx=table_idx,
            headers=cleaned_headers,
            rows=cleaned_rows,
            confidence=confidence,
            extraction_method="camelot",
            cleaned_data=cleaned_rows
        )
    
    def _process_table_data(self, table: List[List], page_num: int, table_idx: int) -> Optional[ExtractedTable]:
        if not table or len(table) < self.min_rows:
            return None
        
        cleaned_rows = [self._clean_row(row) for row in table[:self.max_rows_per_table]]
        headers = cleaned_rows[0] if cleaned_rows else []
        data_rows = cleaned_rows[1:] if len(cleaned_rows) > 1 else []
        
        if not self._is_valid_data_table(headers, data_rows):
            return None

        confidence = self._calculate_confidence(headers, data_rows)
        
        return ExtractedTable(
            page_num=page_num,
            table_idx=table_idx,
            headers=headers,
            rows=data_rows,
            confidence=confidence,
            extraction_method="pdfplumber",
            cleaned_data=cleaned_rows
        )
    
    def _clean_row(self, row: List) -> List[str]:
        return [str(cell).strip().replace("\n", " ").replace("\r", "") if cell else "" for cell in row]
    
    def _calculate_confidence(self, headers: List[str], rows: List[List[str]]) -> float:
        if not rows:
            return 0.0
        
        base_confidence = 0.8
        
        if headers and all(h for h in headers[:3]):
            base_confidence += 0.1
        
        filled_cells = sum(1 for row in rows for cell in row if cell)
        total_cells = len(rows) * max(len(row) for row in rows) if rows else 1
        fill_rate = filled_cells / total_cells if total_cells > 0 else 0
        
        if fill_rate > 0.8:
            base_confidence += 0.05
        
        return min(base_confidence, 0.98)
    
    def _parse_pages(self, pages: str) -> range:
        if pages == "all":
            return range(1000)
        
        try:
            if "-" in pages:
                start, end = pages.split("-")
                return range(int(start) - 1, int(end))
            else:
                return range(int(pages) - 1, int(pages))
        except:
            return range(0)
    
    def tables_to_json(self, tables: List[ExtractedTable]) -> List[Dict]:
        return [
            {
                "page": t.page_num,
                "index": t.table_idx,
                "headers": t.headers,
                "rows": t.rows,
                "row_count": len(t.rows),
                "confidence": round(t.confidence, 2),
                "method": t.extraction_method
            }
            for t in tables
        ]
    
    def find_table_by_content(self, tables: List[ExtractedTable], keywords: List[str]) -> List[ExtractedTable]:
        matching = []
        for table in tables:
            all_text = " ".join(table.headers) + " " + " ".join([" ".join(row) for row in table.rows])
            all_text_lower = all_text.lower()
            
            if all(keyword.lower() in all_text_lower for keyword in keywords):
                matching.append(table)
        
        return matching
    
    def extract_financial_metrics(self, tables: List[ExtractedTable]) -> Dict[str, Any]:
        metrics = {
            "revenue_tables": [],
            "growth_tables": [],
            "customer_tables": [],
            "unit_economics_tables": []
        }
        
        for table in tables:
            all_text = " ".join(table.headers).lower()
            
            if any(kw in all_text for kw in ["revenue", "sales", "invoice"]):
                metrics["revenue_tables"].append(table.table_idx)
            
            if any(kw in all_text for kw in ["growth", "yoy", "increase"]):
                metrics["growth_tables"].append(table.table_idx)
            
            if any(kw in all_text for kw in ["customer", "user", "client"]):
                metrics["customer_tables"].append(table.table_idx)
            
            if any(kw in all_text for kw in ["unit economics", "cac", "ltv", "margin"]):
                metrics["unit_economics_tables"].append(table.table_idx)
        
        return metrics


def extract_all_tables(file_path: str = None, file_content: bytes = None, pages: str = "all") -> List[Dict]:
    extractor = TableExtractor()
    
    if file_content is None and file_path:
        with open(file_path, "rb") as f:
            file_content = f.read()
    
    if file_content is None:
        return []
    
    tables = extractor.extract_from_bytes(file_content, pages)
    return extractor.tables_to_json(tables)


def get_table_summary(tables: List[Dict]) -> str:
    if not tables:
        return "No tables found"
    
    summary = f"Found {len(tables)} tables\n"
    
    for i, table in enumerate(tables[:5]):
        row_count = table.get("row_count", 0)
        headers = table.get("headers", [])[:3]
        summary += f"  Table {i+1}: {row_count} rows, headers: {headers}\n"
    
    if len(tables) > 5:
        summary += f"  ... and {len(tables) - 5} more tables\n"
    
    return summary