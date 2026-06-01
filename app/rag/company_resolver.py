"""
Company Identity Resolver — 5-layer cascading company name resolution

Layers:
  1. LLM structured extraction (delegated — already done in agent pipeline)
  2. First-page heuristics: largest font, center text, logo-adjacent, title slide
  3. Regex patterns: domain names, "X Master Deck", "X Pitch Deck"
  4. Filename inference: extract company from filename
  5. Embedding consensus: ask "What company is this about?" across top chunks
"""

import re
import os
from typing import List, Optional


class CompanyIdentityResolver:
    """
    Cascading company identity resolver.
    Each layer is tried in order; the first non-None result wins.
    """

    DOMAIN_RE = re.compile(r'\b[A-Z][a-zA-Z0-9]+\.(?:ai|io|com|in|org|net)\b', re.IGNORECASE)
    DECK_TITLE_RE = re.compile(r'^(.+?)\s+(?:Pitch Deck|Investor Deck|Master(?: Version)?|Deck|Presentation)\s*$', re.IGNORECASE)
    FILENAME_COMPANY_RE = re.compile(  
        r'^([A-Z][A-Za-z0-9\s&.-]{2,60})(?:\s*[-–—]\s*.*)?\.pdf$', re.IGNORECASE
    )
    COMMON_STOP_WORDS = {"pitch", "deck", "investor", "master", "version", "presentation", 
                         "confidential", "draft", "final", "v1", "v2", "v3", "v4", "v5"}
    TAGLINE_KEYWORDS = {"platform", "solution", "background", "screening", "verification",
                        "automation", "intelligence", "software", "technology", "services",
                        "management", "analytics", "insights", "ecosystem", "network",
                        "infrastructure", "marketplace", "pipeline", "recruitment", "hiring"}

    # Domain keywords that are NOT company names — reject if resolver returns these
    DOMAIN_STOP_WORDS = {
        "health", "hrtech", "agri", "defense", "saas", "retail", "fintech",
        "edtech", "medtech", "biotech", "cleantech", "martech", "legaltech",
        "insurtech", "proptech", "foodtech", "agritech", "healthtech",
        "general", "technology", "software", "platform", "solution",
    }

    @classmethod
    def _is_domain_stop_word(cls, candidate: str) -> bool:
        """Check if a candidate name is actually a domain keyword, not a company name."""
        if not candidate:
            return False
        lower = candidate.strip().lower()
        return lower in cls.DOMAIN_STOP_WORDS

    @classmethod
    def resolve(cls, *, 
                llm_name: Optional[str] = None,
                first_page_text: str = "",
                filename: str = "",
                all_chunks_text: Optional[List[str]] = None,
                domain_hint: Optional[str] = None) -> Optional[str]:
        """
        Resolve company name through cascading layers.
        Each layer result is validated against domain_hint and domain stop words.
        Returns the best-guess company name or None.
        """
        # Layer 1: LLM output (already done, just validate)
        name = cls._layer1_llm(llm_name)
        if name and not cls._is_domain_stop_word(name):
            if domain_hint and name.lower() == domain_hint.lower():
                print(f"[RESOLVER] Rejecting layer1 '{name}' — matches domain_hint '{domain_hint}'")
            else:
                return name

        # Layer 2: Filename inference (highly reliable!)
        name = cls._layer4_filename(filename)
        if name and not cls._is_domain_stop_word(name):
            if domain_hint and name.lower() == domain_hint.lower():
                print(f"[RESOLVER] Rejecting filename '{name}' — matches domain_hint '{domain_hint}'")
            else:
                return name

        # Layer 3: First-page heuristics
        name = cls._layer2_first_page(first_page_text)
        if name and not cls._is_domain_stop_word(name):
            if domain_hint and name.lower() == domain_hint.lower():
                print(f"[RESOLVER] Rejecting first-page '{name}' — matches domain_hint '{domain_hint}'")
            else:
                return name

        # Layer 4: Regex patterns (domain extraction)
        name = cls._layer3_regex(first_page_text, filename)
        if name and not cls._is_domain_stop_word(name):
            if domain_hint and name.lower() == domain_hint.lower():
                print(f"[RESOLVER] Rejecting regex '{name}' — matches domain_hint '{domain_hint}'")
            else:
                return name

        return None

    @classmethod
    def _layer1_llm(cls, llm_name: Optional[str]) -> Optional[str]:
        if not llm_name:
            return None
        cleaned = llm_name.strip()
        if cleaned.lower() in ("unknown", "unknown company", "n/a", "", "not found"):
            return None
        if cls._is_domain_stop_word(cleaned):
            print(f"[RESOLVER] Rejecting LLM output '{cleaned}' — is a domain stop word")
            return None
        return cleaned

    @classmethod
    def _layer2_first_page(cls, text: str) -> Optional[str]:
        if not text or len(text) < 10:
            return None
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Strategy A: Look for "X Pitch Deck" / "X Investor Deck" pattern
        for line in lines:
            m = cls.DECK_TITLE_RE.match(line)
            if m:
                candidate = m.group(1).strip()
                if 2 <= len(candidate) <= 60 and not any(w in candidate.lower().split() for w in ["pitch", "deck", "investor"]):
                    return candidate

        # Strategy B: Find the longest line that looks like a company name
        # Scoring: all-uppercase-first-letter preferred (100 bonus), then by length
        scored = []
        deck_keywords = {"pitch", "deck", "investor", "presentation", "master", "confidential", "draft"}
        filler_words = {"a", "an", "the", "to", "of", "in", "for", "with", "by", "and", "is", "are", "was", "were", "our", "your", "their"}
        for line in lines:
            words = line.split()
            if 1 <= len(words) <= 5 and 2 <= len(line) <= 50 and line[0].isupper():
                if any(kw in line.lower() for kw in cls.TAGLINE_KEYWORDS | deck_keywords):
                    continue
                upper_ratio = sum(1 for w in words if w[0].isupper()) / len(words)
                if upper_ratio >= 0.6:
                    # Score: all words capitalized = strongest signal
                    all_capped = all(w[0].isupper() for w in words)
                    has_filler = any(w.lower() in filler_words for w in words)
                    score = 100 if all_capped and not has_filler else (len(line) if upper_ratio >= 0.8 else 0)
                    scored.append((score, line))

        if scored:
            scored.sort(key=lambda x: (x[0], len(x[1])), reverse=True)
            best_score, best_line = scored[0]
            # Only return if high-confidence match (all-capitalized name)
            if best_score >= 50:
                return best_line
            # Otherwise, low-confidence match — fall through to entity frequency

        # Strategy C: First all-caps short line
        for line in lines:
            if 3 <= len(line) <= 40 and line.isupper() and line.replace(' ', '').isalpha():
                return line.title()

        # Strategy D: Title slide — first line of the whole text (most decks start with company name)
        first_line = lines[0] if lines else ""
        filler_words = {"a", "an", "the", "to", "of", "in", "for", "with", "by", "and", "is", "are", "was", "were", "our", "your", "their"}
        if first_line and 2 <= len(first_line) <= 50 and first_line[0].isupper():
            words = first_line.split()
            all_capped = all(w[0].isupper() for w in words)
            has_filler = any(w.lower() in filler_words for w in words)
            if 1 <= len(words) <= 5 and all_capped and not has_filler:
                if not any(kw in first_line.lower() for kw in cls.TAGLINE_KEYWORDS):
                    return first_line.strip()

        # Strategy E: Most frequently occurring capitalized word/phrase (entity frequency)
        word_freq = {}
        for line in lines:
            w = line.strip()
            if 2 <= len(w) <= 50 and w[0].isupper() and not any(kw in w.lower() for kw in cls.TAGLINE_KEYWORDS):
                words_count = len(w.split())
                if 1 <= words_count <= 4 and not cls._is_domain_stop_word(w):
                    word_freq[w] = word_freq.get(w, 0) + 1
        if word_freq:
            most_common = max(word_freq, key=word_freq.get)
            if word_freq[most_common] >= 2:
                return most_common

        return None

    @classmethod
    def _layer3_regex(cls, text: str, filename: str = "") -> Optional[str]:
        if not text:
            text = ""
        # Look for domain names like "gigin.ai" in text
        domains = cls.DOMAIN_RE.findall(text)
        if not domains and filename:
            # Also try from filename
            domains = cls.DOMAIN_RE.findall(filename.replace("-", ".").replace("_", "."))
        if domains:
            return domains[0].rsplit('.', 1)[0]
        return None

    @classmethod
    def _layer4_filename(cls, filename: str) -> Optional[str]:
        if not filename:
            return None
        base = os.path.splitext(os.path.basename(filename))[0]
        # Try "X Master Version.pdf" or "X Pitch Deck.pdf"
        m = cls.DECK_TITLE_RE.match(base)
        if m:
            return m.group(1).strip()
        # Try extracting first meaningful part before separator
        parts = re.split(r'[-–—–_]', base)
        # Filter out stop words
        meaningful = [p.strip() for p in parts if p.strip().lower() not in cls.COMMON_STOP_WORDS and len(p.strip()) >= 3]
        if meaningful:
            return meaningful[0]
        return None
