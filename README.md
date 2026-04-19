---
title: FinRAG Investor Portal
emoji: 🚀
colorFrom: indigo
colorTo: indigo
sdk: docker
pinned: false
license: mit
app_port: 7860
---

# FinRAG: AI-Powered Investor Intelligence

Deployment of the FinRAG Hybrid RAG system. This portal allows VCs and Investors to parse pitch decks, perform semantic hybrid search, and generate automated "Revert" reports.

## Features
- **Hybrid RAG**: FastEmbed semantic search + Keyword matching.
- **Investment Analysis**: VC-Grade synthesis using Claude 3.5 Sonnet.
- **Zero-Trust Backend**: Pure Python implementation with local vector persistence.

## Deployment Info
This Space runs via Docker on Port 7860.
Make sure to set the following Secret in your Space Settings:
- `ANTHROPIC_API_KEY`: Your Claude API Key
- `X_API_KEY`: finrag_at_2026 (For frontend-backend communication)
