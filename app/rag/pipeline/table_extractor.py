"""
Table Extraction - Structured table parsing
Extracts tables from PDFs with proper structure, not just raw text
"""
import pdfplumber
import re
from typing import List, Dict, Any, Optional
from io import BytesIO


class TableExtractor:
    """
    Extract and parse tables from PDF pages
    """
    
    def extract_from_bytes(self, pdf_bytes: bytes, pages: List[int] = None, max_tables: int = 15) -> List[Dict]:
        """
        Extract tables from specific pages

        Returns:
            List of {"page": int, "tables": List[Dict]} with structured table data
        """
        tables = []

        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                page_range = pages if pages else range(len(pdf.pages))

                for i in page_range:
                    if i >= len(pdf.pages):
                        continue

                    page = pdf.pages[i]
                    page_tables = self._extract_page_tables(page, i + 1, max_tables)

                    if page_tables:
                        tables.append({
                            "page": i + 1,
                            "tables": page_tables
                        })
        except Exception as e:
            print(f"[TABLE EXTRACTOR] Error: {e}")

        return tables
        
        return tables
    
    def _extract_page_tables(self, page, page_num: int, max_tables: int = 15) -> List[Dict]:
        """Extract tables from a single page with filtering"""
        tables = []
        table_count = 0

        try:
            extracted = page.extract_tables()

            if extracted:
                for table in extracted:
                    if table_count >= max_tables:
                        break
                    if table and len(table) > 1:
                        if len(table) < 2 or len(table[0]) < 2:
                            continue
                        if self._is_decorative_table(table):
                            continue
                        structured = self._parse_table_data(table, page_num)
                        if structured:
                            tables.append(structured)
                            table_count += 1
        except Exception as e:
            print(f"[TABLE EXTRACTOR] Page {page_num} error: {e}")

        return tables

    def _is_decorative_table(self, table: List[List]) -> bool:
        """Check if table is decorative (1x1 grids, layout boxes, etc.)"""
        if not table or len(table) < 2:
            return True
        row_count = len(table)
        col_count = len(table[0]) if table[0] else 0

        if row_count < 2 or col_count < 2:
            return True
        if row_count == 1 and col_count == 1:
            return True

        text_density = 0
        for row in table:
            for cell in row:
                if cell and str(cell).strip():
                    text_density += 1
        total_cells = row_count * col_count
        if total_cells > 0 and text_density / total_cells < 0.2:
            return True

        return False
        
        return tables
    
    def _parse_table_data(self, raw_table: List[List], page_num: int) -> Optional[Dict]:
        """Convert raw table to structured format"""
        if not raw_table or len(raw_table) < 2:
            return None
        
        headers = raw_table[0] if raw_table else []
        rows = raw_table[1:] if len(raw_table) > 1 else []
        
        if not headers:
            return None
        
        cleaned_headers = [self._clean_cell(h) for h in headers]
        
        parsed_rows = []
        for row in rows[:20]:  # Limit rows
            if row:
                cleaned_row = [self._clean_cell(cell) for cell in row]
                if any(cleaned_row):
                    parsed_rows.append(cleaned_row)
        
        if not parsed_rows:
            return None
        
        table_type = self._classify_table(cleaned_headers)
        
        return {
            "page": page_num,
            "type": table_type,
            "headers": cleaned_headers,
            "rows": parsed_rows,
            "row_count": len(parsed_rows)
        }
    
    def _clean_cell(self, cell: Any) -> str:
        """Clean individual cell value"""
        if not cell:
            return ""
        text = str(cell).strip()
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def _classify_table(self, headers: List[str]) -> str:
        """Classify table type based on headers"""
        header_str = " ".join(headers).lower()
        
        if any(k in header_str for k in ["revenue", "financial", "income", "profit", "margin"]):
            return "financial"
        if any(k in header_str for k in ["product", "revenue breakdown", "segment"]):
            return "product_revenue"
        if any(k in header_str for k in ["customer", "client", "user", "adoption"]):
            return "customer"
        if any(k in header_str for k in ["founder", "team", "experience", "background"]):
            return "team"
        if any(k in header_str for k in ["market", "tam", "sam", "som", "size"]):
            return "market"
        if any(k in header_str for k in ["milestone", "timeline", "roadmap"]):
            return "milestone"
        
        return "general"
    
    def extract_revenue_table(self, pdf_bytes: bytes, page: int = None) -> Optional[Dict]:
        """Extract revenue breakdown table specifically"""
        if page:
            all_tables = self.extract_from_bytes(pdf_bytes, [page])
        else:
            all_tables = self.extract_from_bytes(pdf_bytes)
        
        for page_data in all_tables:
            for table in page_data.get("tables", []):
                if table.get("type") in ["financial", "product_revenue"]:
                    return table
        
        return None
    
    def table_to_json(self, table: Dict) -> str:
        """Convert structured table to JSON string"""
        import json
        return json.dumps({
            "type": table.get("type"),
            "headers": table.get("headers", []),
            "rows": table.get("rows", []),
            "row_count": table.get("row_count", 0)
        }, indent=2)
    
    def extract_metric_from_table(self, table: Dict, metric_name: str) -> Optional[str]:
        """Extract specific metric from table"""
        headers = [h.lower() for h in table.get("headers", [])]
        
        if metric_name.lower() in headers:
            idx = headers.index(metric_name.lower())
            for row in table.get("rows", []):
                if idx < len(row) and row[idx]:
                    return row[idx]
        
        return None