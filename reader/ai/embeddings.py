"""
reader.ai.embeddings
Generazione di rappresentazioni vettoriali dense (Dense Retrieval)
tramite Sentence-Transformers multilingue.
Caratteristiche:
- Modello pre-addestrato multilingue ottimizzato per similarità semantica (supporta JP, IT, EN)
- Normalizzazione L2 dei vettori per calcolo immediato della Cosine Similarity via dot product
- Memorizzazione persistente compressa (.npz) per massima velocità di caricamento e scalabilità
"""
import os
import json
import numpy as np

# Modello predefinito: leggero, rapido su CPU, eccellente per task multilingue
DEFAULT_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

_model = None

def get_embedding_model(model_name=DEFAULT_MODEL_NAME):
    """Caricamento lazy del modello SentenceTransformer."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
    return _model

class DenseVectorIndex:
    """
    Indice vettoriale denso per ricerca semantica su chunk di testo.
    """
    def __init__(self, model_name=DEFAULT_MODEL_NAME):
        self.model_name = model_name
        self.chunks = []           # Lista di dict con metadati chunk
        self.chunk_ids = []        # Lista parallela di ID
        self.embeddings = None     # Matrice numpy float32 normalizzata (N, D)
        
    def build_index(self, chunks, batch_size=32, show_progress=False):
        """
        Calcola gli embeddings per una lista di chunk e popola la matrice vettoriale.
        """
        if not chunks:
            return
            
        model = get_embedding_model(self.model_name)
        texts = [c['text'] for c in chunks]
        
        # Genera vettori con normalizzazione L2 (norma = 1)
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            normalize_embeddings=True,
            convert_to_numpy=True
        )
        
        self.chunks = list(chunks)
        self.chunk_ids = [c['chunk_id'] for c in chunks]
        self.embeddings = vectors.astype(np.float32)
        
    def add_chunks(self, new_chunks, batch_size=32):
        """Aggiunge incrementalmente nuovi chunk all'indice esistente."""
        if not new_chunks:
            return
            
        model = get_embedding_model(self.model_name)
        texts = [c['text'] for c in new_chunks]
        new_vectors = model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True
        ).astype(np.float32)
        
        if self.embeddings is None or len(self.embeddings) == 0:
            self.embeddings = new_vectors
            self.chunks = list(new_chunks)
            self.chunk_ids = [c['chunk_id'] for c in new_chunks]
        else:
            self.embeddings = np.vstack([self.embeddings, new_vectors])
            self.chunks.extend(new_chunks)
            self.chunk_ids.extend([c['chunk_id'] for c in new_chunks])
            
    def search(self, query, top_k=10):
        """
        Esegue la ricerca semantica densa.
        Poiché i vettori sono normalizzati, il prodotto scalare (dot product) equivale alla cosine similarity.
        Restituisce:
        [{ 'chunk_id', 'score', 'rank', 'chunk' }, ...]
        """
        if self.embeddings is None or len(self.embeddings) == 0:
            return []
            
        model = get_embedding_model(self.model_name)
        query_vec = model.encode(
            [query],
            normalize_embeddings=True,
            convert_to_numpy=True
        ).astype(np.float32)[0]
        
        # Similarità del coseno: dot product tra matrice (N, D) e vettore query (D,) -> (N,)
        similarities = np.dot(self.embeddings, query_vec)
        
        # Indici dei top-k punteggi
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for rank, idx in enumerate(top_indices):
            results.append({
                'chunk_id': self.chunk_ids[idx],
                'score': round(float(similarities[idx]), 4),
                'rank': rank + 1,
                'chunk': self.chunks[idx]
            })
            
        return results
        
    def save(self, filepath):
        """Salva vettori e metadati in formato compresso .npz."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        chunks_json = json.dumps(self.chunks, ensure_ascii=False)
        np.savez_compressed(
            filepath,
            embeddings=self.embeddings,
            chunk_ids=np.array(self.chunk_ids),
            chunks_json=chunks_json,
            model_name=self.model_name
        )
        
    @classmethod
    def load(cls, filepath):
        """Carica l'indice vettoriale da file .npz."""
        if not os.path.exists(filepath):
            return None
        data = np.load(filepath, allow_pickle=True)
        model_name = str(data['model_name'])
        idx = cls(model_name=model_name)
        idx.embeddings = data['embeddings']
        idx.chunk_ids = list(data['chunk_ids'])
        idx.chunks = json.loads(str(data['chunks_json']))
        return idx
