import os
import sys

# Add reader to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reader'))

from ai.lexical_search import BM25Index, tokenize_japanese
from ai.embeddings import DenseVectorIndex
from ai.hybrid_retrieval import HybridRetriever

# Sample test chunks based on Re:Zero themes
SAMPLE_CHUNKS = [
    {
        'chunk_id': 'c_01',
        'book_id': 'vol1',
        'volume_num': 1,
        'spine_index': 1,
        'chapter_title': 'プロローグ',
        'text': 'ナツキ・スバルは突如として異世界へと召喚された。何の能力も持たない無力な高校生。'
    },
    {
        'chunk_id': 'c_02',
        'book_id': 'vol1',
        'volume_num': 1,
        'spine_index': 2,
        'chapter_title': '第一章',
        'text': '銀髪のハーフエルフの美少女、エミリアと出会い、スバルは彼女に命を救われる。'
    },
    {
        'chunk_id': 'c_03',
        'book_id': 'vol1',
        'volume_num': 1,
        'spine_index': 3,
        'chapter_title': '第二章',
        'text': '死んでも時間を巻き戻してやり直す能力『死に戻り』。過酷な運命に抗う唯一の力。'
    },
    {
        'chunk_id': 'c_04',
        'book_id': 'vol2',
        'volume_num': 2,
        'spine_index': 4,
        'chapter_title': 'ロズワール邸',
        'text': 'ロズワール邸で働く双子のメイド、レムとラム。鬼の血を引く姉妹との共同生活が始まる。'
    },
    {
        'chunk_id': 'c_05',
        'book_id': 'vol3',
        'volume_num': 3,
        'spine_index': 5,
        'chapter_title': '王選開始',
        'text': 'ルグニカ王国の次期国王を決める王位継承戦が幕を開ける。五人の候補者たちが集う。'
    }
]

def test_japanese_tokenizer():
    tokens = tokenize_japanese("ナツキ・スバルは死に戻りの能力を得た。")
    assert len(tokens) > 0, "Nessun token generato!"
    assert any('スバル' in t for t in tokens), "Nome スバル mancante nei token!"
    print("✅ test_japanese_tokenizer: superato.")

def test_bm25_search():
    bm25 = BM25Index()
    bm25.add_documents(SAMPLE_CHUNKS)
    
    # Query lessicale su "死に戻り" (deve trovare il chunk c_03 al primo posto)
    hits = bm25.search("死に戻り", top_k=3)
    assert len(hits) > 0, "Nessun risultato BM25 trovato!"
    assert hits[0]['chunk_id'] == 'c_03', f"Atteso c_03 in cima, trovato {hits[0]['chunk_id']}"
    assert hits[0]['score'] > 0
    
    # Query su "エミリア" (deve trovare c_02)
    hits_emilia = bm25.search("エミリア", top_k=1)
    assert hits_emilia[0]['chunk_id'] == 'c_02'
    print("✅ test_bm25_search: superato (matching esatto e ranking corretto).")

def test_dense_search():
    print("Avvio test DenseVectorIndex (download o caricamento modello SentenceTransformers)...")
    dense = DenseVectorIndex()
    dense.build_index(SAMPLE_CHUNKS)
    
    # Query semantica: "capacità di tornare in vita dopo la morte"
    # Deve agganciare c_03 ('死に戻り') anche se la query è in italiano o parafrasi!
    hits = dense.search("capacità di tornare in vita dopo la morte e ricominciare", top_k=2)
    assert len(hits) > 0
    top_hit = hits[0]
    print(f"   Query semantica IT -> Miglior chunk recuperato: [{top_hit['chunk_id']}] con score {top_hit['score']}")
    print(f"   Testo: {top_hit['chunk']['text']}")
    assert top_hit['chunk_id'] == 'c_03', f"Atteso c_03 per la semantica di ritorno dalla morte, ottenuto {top_hit['chunk_id']}"
    print("✅ test_dense_search: superato (ricerca semantica multilingue funzionante).")

def test_hybrid_retrieval():
    retriever = HybridRetriever()
    retriever.index_chunks(SAMPLE_CHUNKS, build_dense=True)
    
    # Test modalità ibrida (RRF)
    hybrid_hits = retriever.search("スバルとエミリアの出会い", top_k=3, method="hybrid")
    assert len(hybrid_hits) > 0
    print(f"   Query Hybrid -> Top 1: [{hybrid_hits[0]['chunk_id']}] sorgente: {hybrid_hits[0]['retriever_source']}")
    assert hybrid_hits[0]['chunk_id'] in ('c_01', 'c_02')
    
    # Test modalità singole via retriever unificato
    bm25_hits = retriever.search("レムとラム", top_k=1, method="bm25")
    assert bm25_hits[0]['chunk_id'] == 'c_04'
    
    dense_hits = retriever.search("le due gemelle cameriere", top_k=1, method="dense")
    assert dense_hits[0]['chunk_id'] == 'c_04'
    
    print("✅ test_hybrid_retrieval: superato (confronto BM25 vs Dense vs Hybrid verificato).")

if __name__ == '__main__':
    test_japanese_tokenizer()
    test_bm25_search()
    test_dense_search()
    test_hybrid_retrieval()
    print("\n🎉 Tutti i test dei Motori di Ricerca (BM25, Dense, Hybrid RRF) sono passati!")
