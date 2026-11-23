"""
reader.ai.hybrid_retrieval
Motore di ricerca ibrida (Hybrid Search) per testi giapponesi.
Combina Information Retrieval lessicale (BM25) e denso (Dense Vector Search)
attraverso l'algoritmo Reciprocal Rank Fusion (RRF).
Supporta re-ranking neurale opzionale con Cross-Encoder.

Formulazione RRF:
RRF_Score(d) = (w_bm25 / (k + rank_bm25(d))) + (w_dense / (k + rank_dense(d)))
con k = 60 (standard accademico Cormack et al.).
"""
import os
from .lexical_search import BM25Index
from .embeddings import DenseVectorIndex

# Cross-Encoder per reranking (lazy loading)
_reranker_model = None

def get_reranker_model(model_name="cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"):
    """Caricamento lazy del Cross-Encoder per il reranking multilingue."""
    global _reranker_model
    if _reranker_model is None:
        try:
            from sentence_transformers import CrossEncoder
            _reranker_model = CrossEncoder(model_name)
        except Exception as e:
            print(f"[Reranker] Impossibile caricare il Cross-Encoder: {e}")
            _reranker_model = False
    return _reranker_model if _reranker_model is not False else None

class HybridRetriever:
    """
    Motore unificato di Retrieval per la tesi:
    Supporta 4 modalità sperimentali confrontabili:
    1. 'bm25': solo ricerca lessicale BM25
    2. 'dense': solo ricerca semantica con Bi-Encoder
    3. 'hybrid': fusione RRF di BM25 + Dense
    4. 'hybrid_rerank': ibrido RRF con reranking neurale Cross-Encoder
    """
    def __init__(self, bm25_index=None, dense_index=None, rrf_k=60):
        self.bm25_index = bm25_index or BM25Index()
        self.dense_index = dense_index or DenseVectorIndex()
        self.rrf_k = rrf_k
        self.chunks_map = {}  # chunk_id -> chunk dict
        
    def index_chunks(self, chunks, build_dense=True, batch_size=32):
        """Indicizza una collezione di chunk sia in BM25 che in Dense."""
        for c in chunks:
            self.chunks_map[c['chunk_id']] = c
            
        print(f"[HybridRetriever] Indicizzazione BM25 di {len(chunks)} chunk...")
        self.bm25_index.add_documents(chunks)
        
        if build_dense:
            print(f"[HybridRetriever] Calcolo embeddings densi ({len(chunks)} chunk)...")
            self.dense_index.build_index(chunks, batch_size=batch_size)
            
    def search(
        self,
        query,
        top_k=5,
        method="hybrid",
        weight_bm25=1.0,
        weight_dense=1.0,
        rerank=False,
        candidate_k=20
    ):
        """
        Esegue la ricerca secondo la strategia selezionata.
        
        Parametri:
        - query: testo della query (in JP, IT o EN)
        - top_k: numero di risultati finali
        - method: 'bm25' | 'dense' | 'hybrid'
        - rerank: se True, applica il Cross-Encoder sui candidati prima del taglio top_k
        """
        method = method.lower()
        
        # 1. Caso BM25 puro (RQ1)
        if method == "bm25":
            results = self.bm25_index.search(query, top_k=candidate_k if rerank else top_k)
            for r in results:
                r['retriever_source'] = 'bm25'
                
        # 2. Caso Dense puro (RQ1)
        elif method == "dense":
            results = self.dense_index.search(query, top_k=candidate_k if rerank else top_k)
            for r in results:
                r['retriever_source'] = 'dense'
                
        # 3. Caso Hybrid RRF (RQ2)
        elif method == "hybrid":
            bm25_hits = self.bm25_index.search(query, top_k=candidate_k)
            dense_hits = self.dense_index.search(query, top_k=candidate_k)
            results = self._reciprocal_rank_fusion(
                bm25_hits=bm25_hits,
                dense_hits=dense_hits,
                w_bm25=weight_bm25,
                w_dense=weight_dense,
                top_k=candidate_k if rerank else top_k
            )
        else:
            raise ValueError(f"Metodo di ricerca non valido: {method}. Usa 'bm25', 'dense', o 'hybrid'.")
            
        # 4. Re-ranking con Cross-Encoder (RQ3)
        if rerank and results:
            results = self._apply_cross_encoder_rerank(query, results, top_k=top_k)
        else:
            results = results[:top_k]
            
        return results
        
    def _reciprocal_rank_fusion(self, bm25_hits, dense_hits, w_bm25=1.0, w_dense=1.0, top_k=10):
        """
        Fusione RRF standard:
        RRF_Score(d) = sum( w_m / (k + rank_m(d)) )
        """
        rrf_scores = {}
        provenance = {}
        
        # Pesi BM25
        for hit in bm25_hits:
            cid = hit['chunk_id']
            rank = hit['rank']
            score_contrib = w_bm25 / (self.rrf_k + rank)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + score_contrib
            provenance[cid] = provenance.get(cid, set()) | {'bm25'}
            
        # Pesi Dense
        for hit in dense_hits:
            cid = hit['chunk_id']
            rank = hit['rank']
            score_contrib = w_dense / (self.rrf_k + rank)
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + score_contrib
            provenance[cid] = provenance.get(cid, set()) | {'dense'}
            
        sorted_docs = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        fused_results = []
        for rank, (cid, score) in enumerate(sorted_docs):
            chunk = self.chunks_map.get(cid) or self.bm25_index.doc_metadata.get(cid)
            fused_results.append({
                'chunk_id': cid,
                'score': round(score, 6),
                'rank': rank + 1,
                'chunk': chunk,
                'retriever_source': "+".join(sorted(list(provenance.get(cid, []))))
            })
            
        return fused_results
        
    def _apply_cross_encoder_rerank(self, query, candidate_results, top_k=5):
        """Riordina i candidati attraverso un modello Cross-Encoder neurale."""
        reranker = get_reranker_model()
        if not reranker:
            return candidate_results[:top_k]
            
        pairs = [[query, r['chunk']['text']] for r in candidate_results]
        try:
            scores = reranker.predict(pairs)
            for r, s in zip(candidate_results, scores):
                r['rerank_score'] = round(float(s), 4)
                
            reranked = sorted(candidate_results, key=lambda x: x['rerank_score'], reverse=True)[:top_k]
            for rank, r in enumerate(reranked):
                r['rank'] = rank + 1
                r['retriever_source'] += "+cross_encoder"
            return reranked
        except Exception as e:
            print(f"[Reranker] Errore durante il reranking: {e}")
            return candidate_results[:top_k]
