from rank_bm25 import BM25Okapi

def build_bm25(chunks):
    tokenized = [c.split() for c in chunks]
    return BM25Okapi(tokenized)

def retrieve(bm25, query, chunks, k=5):
    scores = bm25.get_scores(query.split())
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [chunks[i] for i in top_idx]
