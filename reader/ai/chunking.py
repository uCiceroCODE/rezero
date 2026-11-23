"""
reader.ai.chunking
Segmentazione semantica del testo giapponese per Information Retrieval e RAG.
Caratteristiche:
- Rilevamento dei confini di frase giapponesi (。！？)
- Rispetto delle citazioni e dei dialoghi (「...」, 『...』) per evitare troncamenti a metà battuta
- Finestra scorrevole con overlap configurabile
- Tracciamento metadati puntuali (Volume, Capitolo, Offset) per citazioni verificabili
"""
import re

def split_japanese_sentences(text):
    """
    Divide un testo giapponese in frasi logiche rispettando le virgolette di dialogo.
    Non divide su '。' se si trova all'interno di virgolette 「...」 o 『...』.
    """
    sentences = []
    current = []
    in_single_quote = False  # 「...」
    in_double_quote = False  # 『...』
    
    delimiters = {'。', '！', '？', '\n'}
    
    for char in text:
        current.append(char)
        if char == '「':
            in_single_quote = True
        elif char == '」':
            in_single_quote = False
            # La fine di una battuta di dialogo è spesso un buon confine
            sentences.append("".join(current).strip())
            current = []
            continue
        elif char == '『':
            in_double_quote = True
        elif char == '』':
            in_double_quote = False
            sentences.append("".join(current).strip())
            current = []
            continue
            
        # Confine normale: fine frase NON all'interno di dialogo
        if not in_single_quote and not in_double_quote:
            if char in delimiters:
                s = "".join(current).strip()
                if s:
                    sentences.append(s)
                current = []
                
    if current:
        s = "".join(current).strip()
        if s:
            sentences.append(s)
            
    return [s for s in sentences if s]

def create_chunks_from_chapter(
    book_id,
    volume_num,
    spine_index,
    chapter_title,
    full_text,
    target_chunk_size=400,
    overlap_size=80
):
    """
    Genera chunk da un capitolo con finestra scorrevole basata su frasi logiche.
    
    Parametri:
    - target_chunk_size: dimensione obiettivo in caratteri (default ~400 char, ideale per bi-encoder)
    - overlap_size: sovrapposizione in caratteri tra chunk consecutivi (~80 char)
    
    Restituisce:
    - Lista di dizionari con chunk_id, testo, metadati di posizionamento e coordinate.
    """
    if not full_text or len(full_text.strip()) < 10:
        return []
        
    sentences = split_japanese_sentences(full_text)
    if not sentences:
        return []
        
    chunks = []
    chunk_index = 0
    current_sentences = []
    current_len = 0
    
    for sentence in sentences:
        s_len = len(sentence)
        
        # Se una singola frase supera il target_chunk_size (raro), la aggiungiamo comunque
        if current_len + s_len > target_chunk_size and current_sentences:
            # Crea chunk corrente
            chunk_text = "".join(current_sentences).strip()
            
            # Calcola coordinate di offset approssimate nel capitolo
            char_start = full_text.find(current_sentences[0]) if current_sentences else 0
            if char_start < 0:
                char_start = 0
            char_end = char_start + len(chunk_text)
            
            # Statistiche linguistiche
            cjk_chars = len(re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', chunk_text))
            cjk_ratio = round(cjk_chars / max(len(chunk_text), 1), 2)
            
            chunk_id = f"{book_id}_sp{spine_index}_c{chunk_index}"
            chunks.append({
                'chunk_id': chunk_id,
                'book_id': book_id,
                'volume_num': volume_num,
                'spine_index': spine_index,
                'chapter_title': chapter_title,
                'chunk_index': chunk_index,
                'text': chunk_text,
                'char_count': len(chunk_text),
                'char_start': char_start,
                'char_end': char_end,
                'cjk_ratio': cjk_ratio
            })
            chunk_index += 1
            
            # Gestione overlap: teniamo le ultime frasi fino a raggiungere overlap_size
            overlap_sentences = []
            overlap_len = 0
            for prev_s in reversed(current_sentences):
                if overlap_len + len(prev_s) <= overlap_size:
                    overlap_sentences.insert(0, prev_s)
                    overlap_len += len(prev_s)
                else:
                    break
                    
            current_sentences = overlap_sentences
            current_len = overlap_len
            
        current_sentences.append(sentence)
        current_len += s_len
        
    # Ultimo chunk residuo
    if current_sentences:
        chunk_text = "".join(current_sentences).strip()
        if len(chunk_text) >= 20:  # Ignora frammenti insignificanti a fine capitolo
            char_start = full_text.find(current_sentences[0]) if current_sentences else 0
            if char_start < 0:
                char_start = 0
            char_end = char_start + len(chunk_text)
            
            cjk_chars = len(re.findall(r'[\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff]', chunk_text))
            cjk_ratio = round(cjk_chars / max(len(chunk_text), 1), 2)
            
            chunk_id = f"{book_id}_sp{spine_index}_c{chunk_index}"
            chunks.append({
                'chunk_id': chunk_id,
                'book_id': book_id,
                'volume_num': volume_num,
                'spine_index': spine_index,
                'chapter_title': chapter_title,
                'chunk_index': chunk_index,
                'text': chunk_text,
                'char_count': len(chunk_text),
                'char_start': char_start,
                'char_end': char_end,
                'cjk_ratio': cjk_ratio
            })
            
    return chunks

def chunk_entire_book(doc_data, target_chunk_size=400, overlap_size=80):
    """
    Applica il chunking all'intero libro restituito da document_processor.extract_chapter_documents.
    """
    all_chunks = []
    book_id = doc_data['book_id']
    vol_num = doc_data['volume_num']
    
    for ch in doc_data['chapters']:
        if not ch['is_text_heavy']:
            continue
        ch_chunks = create_chunks_from_chapter(
            book_id=book_id,
            volume_num=vol_num,
            spine_index=ch['spine_index'],
            chapter_title=ch['chapter_title'],
            full_text=ch['full_text'],
            target_chunk_size=target_chunk_size,
            overlap_size=overlap_size
        )
        all_chunks.extend(ch_chunks)
        
    return all_chunks
