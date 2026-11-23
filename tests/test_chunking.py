import os
import sys

# Add reader to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'reader'))

import epub_parser
from ai.document_processor import clean_html_to_text, extract_chapter_documents
from ai.chunking import split_japanese_sentences, create_chunks_from_chapter, chunk_entire_book

def test_japanese_sentence_splitting():
    sample = (
        'スバルはコンビニの袋を握りしめた。'
        '「おい、ここはどこだ？」'
        '周囲を見渡すと、見知らぬファンタジー風の街並みが広がっていた！'
        '本当に異世界に来てしまったのか？'
    )
    sentences = split_japanese_sentences(sample)
    assert len(sentences) == 4, f"Previste 4 frasi, ottenute {len(sentences)}: {sentences}"
    assert sentences[0] == 'スバルはコンビニの袋を握りしめた。'
    assert sentences[1] == '「おい、ここはどこだ？」'
    assert sentences[2] == '周囲を見渡すと、見知らぬファンタジー風の街並みが広がっていた！'
    assert sentences[3] == '本当に異世界に来てしまったのか？'
    print("✅ test_japanese_sentence_splitting: superato.")

def test_dialogue_protection():
    # Frase con punto interno alla citazione
    sample = '少女は冷ややかに告げた。「動かないで。怪我をするわよ」そう言って杖を構えた。'
    sentences = split_japanese_sentences(sample)
    # Non deve spezzare "「動かないで。怪我をするわよ」" a metà
    has_broken_dialogue = any(s == '「動かないで。' for s in sentences)
    assert not has_broken_dialogue, "Il dialogo è stato erroneamente spezzato al punto interno!"
    print("✅ test_dialogue_protection: superato.")

def test_clean_html_ruby_stripping():
    html = '<p>スバルは<ruby>異世界<rp>(</rp><rt>いせかい</rt><rp>)</rp></ruby>に<ruby>召喚<rt>しょうかん</rt></ruby>された。</p>'
    paragraphs, full_text = clean_html_to_text(html)
    assert 'いせかい' not in full_text, "Il furigana <rt> non è stato rimosso dal testo base!"
    assert '異世界' in full_text, "Il kanji base è andato perso!"
    assert '召喚' in full_text, "Il kanji base è andato perso!"
    print("✅ test_clean_html_ruby_stripping: superato.")

def test_real_book_chunking():
    books = epub_parser.scan_books()
    if not books:
        print("⚠️ Nessun libro trovato per il test reale, skip.")
        return
        
    first_book = books[0]
    print(f"Test estrazione su volume reale: {first_book['title']} (ID: {first_book['id']})")
    
    doc_data = extract_chapter_documents(first_book['id'])
    assert doc_data is not None, "Estrazione documento fallita!"
    assert len(doc_data['chapters']) > 0, "Nessun capitolo estratto!"
    
    chunks = chunk_entire_book(doc_data, target_chunk_size=350, overlap_size=60)
    assert len(chunks) > 0, "Nessun chunk generato!"
    
    first_chunk = chunks[0]
    assert 'chunk_id' in first_chunk
    assert 'text' in first_chunk
    assert 'volume_num' in first_chunk
    assert 'spine_index' in first_chunk
    assert len(first_chunk['text']) > 20
    
    print(f"✅ test_real_book_chunking: estratti {len(doc_data['chapters'])} capitoli, generati {len(chunks)} chunk.")
    print(f"   Esempio primo chunk [{first_chunk['chunk_id']}]: {first_chunk['text'][:60]}...")

if __name__ == '__main__':
    test_japanese_sentence_splitting()
    test_dialogue_protection()
    test_clean_html_ruby_stripping()
    test_real_book_chunking()
    print("\n🎉 Tutti i test di Document Processing e Chunking sono passati!")
