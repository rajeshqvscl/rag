# 🚀 RAG Intelligence Engine (Production-Ready)

A lightweight, production-ready Retrieval-Augmented Generation (RAG) system designed to extract structured business intelligence from documents.

This system is built to power applications like **LeadStream AI**, enabling automated analysis of pitch decks, reports, and business documents.

---

## 🧠 Overview

This project implements a full RAG pipeline:

1. **Document Ingestion** → PDF parsing & cleaning
2. **Chunking & Embedding** → Semantic representation
3. **Vector Search (FAISS)** → Context retrieval
4. **LLM Generation (Groq)** → Structured intelligence output

---

## ⚙️ Tech Stack

### Backend

* FastAPI (API layer)
* Python 3.10+

### AI / ML

* Embeddings: `all-MiniLM-L6-v2`
* LLM: Groq (`llama-3.1-8b-instant`)

### Storage

* Vector DB: FAISS (local, persisted)
* Database (planned): Neon (Postgres)

---

## 📂 Project Structure

```
rag_system/
│
├── app/
│   ├── main.py              # FastAPI entrypoint
│   ├── rag/
│   │   ├── loader.py        # PDF processing
│   │   ├── embedder.py      # Embeddings
│   │   ├── vector_store.py  # FAISS index
│   │   ├── retriever.py     # Context retrieval
│   │   └── generator.py     # LLM response
│
├── data/
│   ├── documents/           # Uploaded PDFs
│   └── faiss_index/         # Saved vector index
│
├── index.html               # Test UI
├── requirements.txt
└── README.md
```

---

## 🔄 System Flow

```
PDF → Clean → Chunk → Embed → Store (FAISS)
                                ↓
User Query → Embed → Retrieve Top Chunks → LLM → Structured Output
```

---

## 🧩 API Endpoints

### 1. Health Check

```
GET /
```

### 2. Ingest Document

```
POST /ingest
```

### 3. Query System

```
GET /query?q=your_question
```

---

## 📊 Output Format

The system returns structured business insights:

```
Business Model:

Core Model:
...

Revenue Streams:
...

Distribution Strategy:
...
```

---

## 🚀 Deployment

### Render Deployment

1. Push code to GitHub
2. Create new Web Service on Render
3. Configure:

```
Build Command: pip install -r requirements.txt
Start Command: uvicorn app.main:app --host 0.0.0.0 --port 10000
```

4. Add environment variable:

```
GROQ_API_KEY=your_api_key
```

---

## 🔐 Environment Variables

```
GROQ_API_KEY=your_groq_api_key
```

---

## ⚡ Usage

1. Upload PDF via `/ingest`
2. Query insights via `/query`
3. Integrate into applications like LeadStream AI

---

## 🔥 Key Features

* Structured intelligence extraction (not just Q&A)
* Zero hallucination (strict context grounding)
* Clean classification (business model, revenue, distribution)
* Lightweight & scalable
* Production-ready architecture

---

## 📌 Future Enhancements

* Insight Layer (risks, strengths, red flags)
* Multi-user support
* Dashboard (Next.js)
* Vector DB upgrade (Pinecone)
* Email automation integration

---

## 🧠 Use Case: LeadStream AI

This system acts as the **intelligence engine** behind LeadStream AI:

* Analyze investor replies
* Understand business context
* Generate smart responses
* Assist deal evaluation

---

## 📜 License

MIT License

---

## ✨ Author

Built as part of an AI-driven investment intelligence system.

---
