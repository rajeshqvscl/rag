"""
PageData Adapter - Unified access to page data regardless of source format
Handles both dict and dataclass PageData objects
"""


class PageAdapter:
    """Adapter for unified page data access."""

    @staticmethod
    def text(page_data) -> str:
        """Get text content from page data."""
        if isinstance(page_data, dict):
            return page_data.get("text", page_data.get("content", ""))
        return getattr(page_data, "content", getattr(page_data, "text", ""))

    @staticmethod
    def raw_text(page_data) -> str:
        """Get raw text from page data."""
        if isinstance(page_data, dict):
            return page_data.get("raw_text", "")
        return getattr(page_data, "raw_text", "")

    @staticmethod
    def page_num(page_data) -> int:
        """Get page number."""
        if isinstance(page_data, dict):
            return page_data.get("page", 1)
        return getattr(page_data, "page", 1)

    @staticmethod
    def sections(page_data) -> list:
        """Get sections from page data."""
        if isinstance(page_data, dict):
            return page_data.get("sections", [])
        return getattr(page_data, "sections", [])

    @staticmethod
    def tables(page_data) -> list:
        """Get tables from page data."""
        if isinstance(page_data, dict):
            return page_data.get("tables", [])
        return getattr(page_data, "tables", [])

    @staticmethod
    def layout(page_data) -> dict:
        """Get layout from page data."""
        if isinstance(page_data, dict):
            return page_data.get("layout", {})
        return getattr(page_data, "layout", {})

    @staticmethod
    def title(page_data) -> str:
        """Get title from page data."""
        if isinstance(page_data, dict):
            return page_data.get("title", "")
        return getattr(page_data, "title", "")

    @staticmethod
    def layout_blocks(page_data) -> list:
        """Get layout blocks from page data (for visual parsing)."""
        if isinstance(page_data, dict):
            layout = page_data.get("layout", {})
            return layout.get("blocks", [])
        return getattr(page_data, "layout", {}).get("blocks", [])

    @staticmethod
    def cleaned_text(page_data) -> str:
        """Get cleaned text - prefer cleaned over raw."""
        if isinstance(page_data, dict):
            return page_data.get("text", page_data.get("cleaned_text", page_data.get("raw_text", "")))
        return (
            getattr(page_data, "content", "") or
            getattr(page_data, "text", "") or
            getattr(page_data, "cleaned_text", "") or
            getattr(page_data, "raw_text", "")
        )

    @staticmethod
    def get(page_data, key: str, default=None):
        """Generic get method for any field."""
        if isinstance(page_data, dict):
            return page_data.get(key, default)
        return getattr(page_data, key, default)

    @staticmethod
    def to_dict(page_data) -> dict:
        """Convert any page data to dict format."""
        if isinstance(page_data, dict):
            return page_data

        if hasattr(page_data, "__dataclass_fields__"):
            return {
                "page": getattr(page_data, "page", 1),
                "title": getattr(page_data, "title", ""),
                "text": getattr(page_data, "content", getattr(page_data, "text", "")),
                "raw_text": getattr(page_data, "raw_text", ""),
                "tables": getattr(page_data, "tables", []),
                "sections": getattr(page_data, "sections", []),
                "layout": getattr(page_data, "layout", {}),
            }

        return {"text": str(page_data)}