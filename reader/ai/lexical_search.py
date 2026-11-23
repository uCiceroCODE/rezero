"""
reader.ai.lexical_search
Implementazione dell'algoritmo di Information Retrieval BM25 (Okapi BM25)
ottimizzato per testi in lingua giapponese.
Caratteristiche:
- Tokenizzazione morfologica via pykakasi combinata con bi-grammi di caratteri
- Calcolo esatto di TF-IDF saturato con parametri k1=1.5 e b=0.75
- Indice invertito persistente e serializzabile
- Restituisce i passaggi più rilevanti con punteggio BM25 e metadati completi
"""
import math
import os
import json
import re
import pykakasi

# Inizializzazione converter pykakasi (singleton lazy)
_kks = None
def get_kks():
    global _kks
    if _kks is None:
        _kks = pykakasi.kakasi()
    return _kks

def tokenize_japanese(text):
    """
    Tokenizza testo giapponese combinando analisi morfologica e bi-grammi.
    Garantisce alta recall su nomi propri in katakana e composti kanji.
    """
    text = text.strip()
    if not text:
        return []
        
    kks = get_kks()
    conv = kks.convert(text)
    
    tokens = []
    clean_chars = []
    
    for item in conv:
        orig = item['orig'].strip()
        hira = item['hira'].strip()
        if orig:
            tokens.append(orig.lower())
            clean_chars.extend(list(orig))
        if hira and hira != orig:
            tokens.append(hira)
            
    # Aggiungi bi-grammi sui caratteri CJK/Katakana per catturare sottoparole e nomi composti
    raw_cjk = "".join(re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff\w]', text))
    if len(raw_cjk) >= 2:
        for i in range(len(raw_cjk) - 1):
            tokens.append(raw_cjk[i:i+2].lower())
            
    return tokens

class BM25Index:
    """
    Indice lessicale Okapi BM25 per documenti di testo giapponesi.
    """
    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_doc_len = 0.0
        self.doc_lens = {}          # doc_id -> int
        self.doc_metadata = {}      # doc_id -> dict
        self.inverted_index = {}    # token -> dict(doc_id -> freq)
        self.idf_cache = {}         # token -> float
        
    def add_documents(self, chunks):
        """
        Aggiunge una lista di chunk all'indice BM25.
        Ogni chunk deve essere un dict con almeno 'chunk_id' e 'text'.
        """
        for chunk in chunks:
            doc_id = chunk['chunk_id']
            text = chunk['text']
            tokens = tokenize_japanese(text)
            doc_len = len(tokens)
            
            self.doc_lens[doc_id] = doc_len
            self.doc_metadata[doc_id] = chunk
            
            # Calcola frequenze dei termini nel documento
            term_freqs = {}
            for t in tokens:
                term_freqs[t] = term_freqs.get(t, 0) + 1
                
            for t, freq in term_freqs.items():
                if t not in self.inverted_index:
                    self.inverted_index[t] = {}
                self.inverted_index[t][doc_id] = freq
                
        self.doc_count = len(self.doc_lens)
        total_len = sum(self.doc_lens.values())
        self.avg_doc_len = (total_len / self.doc_count) if self.doc_count > 0 else 0.0
        self._compute_all_idfs()
        
    def _compute_all_idfs(self):
        """Precalcola i pesi IDF per tutti i termini dell'indice."""
        self.idf_cache = {}
        for token, postings in self.inverted_index.items():
            df = len(postings)
            # Formula IDF standard Lucene/Okapi: ln(1 + (N - df + 0.5) / (df + 0.5))
            idf = math.log(1.0 + (self.doc_count - df + 0.5) / (df + 0.5))
            self.idf_cache[token] = max(idf, 0.0)
            
    def search(self, query, top_k=10):
        """
        Esegue la ricerca BM25 per la query data.
        Restituisce una lista di risultati ordinati per punteggio decrescente:
        [{ 'chunk_id', 'score', 'chunk' }, ...]
        """
        if self.doc_count == 0:
            return []
            
        query_tokens = tokenize_japanese(query)
        if not query_tokens:
            return []
            
        scores = {}
        for q_token in set(query_tokens):
            if q_token not in self.inverted_index:
                continue
                
            idf = self.idf_cache.get(q_token, 0.0)
            if idf <= 0.0:
                continue
                
            postings = self.inverted_index[q_token]
            for doc_id, freq in postings.items():
                doc_len = self.doc_lens[doc_id]
                numerator = freq * (self.k1 + 1.0)
                denominator = freq + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                term_score = idf * (numerator / denominator)
                scores[doc_id] = scores.get(doc_id, 0.0) + term_score
                
        if not scores:
            return []
            
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        
        results = []
        for rank, (doc_id, score) in enumerate(ranked):
            results.append({
                'chunk_id': doc_id,
                'score': round(score, 4),
                'rank': rank + 1,
                'chunk': self.doc_metadata.get(doc_id, {})
            })
            
        return results
        
    def save(self, filepath):
        """Salva l'indice BM25 su file JSON compresso."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        data = {
            'k1': self.k1,
            'b': self.b,
            'doc_count': self.doc_count,
            'avg_doc_len': self.avg_doc_len,
            'doc_lens': self.doc_lens,
            'doc_metadata': self.doc_metadata,
            'inverted_index': self.inverted_index,
            'idf_cache': self.idf_cache
        }
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
            
    @classmethod
    def load(cls, filepath):
        """Carica l'indice BM25 da file JSON."""
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        idx = cls(k1=data['k1'], b=data['b'])
        idx.doc_count = data['doc_count']
        idx.avg_doc_len = data['avg_doc_len']
        idx.doc_lens = data['doc_lens']
        idx.doc_metadata = data['doc_metadata']
        idx.inverted_index = data['inverted_index']
        idx.idf_cache = data['idf_cache']
        return idx
