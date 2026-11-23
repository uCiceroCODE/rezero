# 🎓 Proposta & Mappa della Tesi Triennale in Ingegneria Informatica (UniSalento)

> **Titolo Ufficiale Proposto:**  
> *«Progettazione e valutazione sperimentale di un sistema RAG per la consultazione intelligente di libri digitali multilingua con focus sulla lingua giapponese»*

---

## 📌 1. Quadro Scientifico & Motivazioni Accademiche

### 🎯 Perché è una vera tesi di Ingegneria Informatica?
La tesi unisce due pilastri fondamentali:
1. **Contributo Ingegneristico:** Architettura software modulare, robusta e scalabile per la gestione di testi digitali (EPUB), elaborazione NLP specializzata per lingue senza spaziatori (giapponese con kanji/kana/furigana), e pipeline di indicizzazione.
2. **Contributo Scientifico-Sperimentale:** Formulazione di ipotesi di ricerca, disegno di esperimenti controllati su un dataset prefissato, confronto quantitativo tra algoritmi di Information Retrieval (lessicale vs denso vs ibrido vs reranking) e misurazione della fedeltà delle risposte RAG.

---

## 🔬 2. Domande di Ricerca (Research Questions - RQ)

Ogni capitolo sperimentale della tesi risponderà formalmente a queste 5 domande:

| Codice | Domanda di Ricerca | Ipotesi di Lavoro |
|---|---|---|
| **RQ1** | *La ricerca semantica (Dense Retrieval) recupera passaggi più pertinenti rispetto alla ricerca lessicale (BM25) su testi narrativi?* | Dense cattura concetti parafrasati; BM25 eccelle su nomi propri e termini specifici. |
| **RQ2** | *La ricerca ibrida (Hybrid Search) migliora l'accuratezza complessiva rispetto alle due tecniche usate singolarmente?* | La fusione con Reciprocal Rank Fusion (RRF) compensa i punti ciechi di entrambi. |
| **RQ3** | *L'introduzione di un Reranker neurale (Cross-Encoder) sui top-$k$ passaggi incrementa significativamente la precisione?* | Il Cross-Encoder migliora il ranking finale a fronte di un costo computazionale aggiuntivo. |
| **RQ4** | *Quanto sono fedeli le risposte RAG al testo sorgente, e qual è il tasso di allucinazione?* | La presenza di citazioni esatte con offset riduce drasticamente l'allucinazione rispetto a prompt aperti. |
| **RQ5** | *Qual è l'impatto delle differenti strategie sui tempi di risposta (latenza) e sul consumo di risorse (RAM/CPU)?* | Compromesso ingegneristico: Trade-off tra qualità IR (NDCG) e latenza al 95° percentile ($P_{95}$). |

---

## 🏗️ 3. Architettura Modulare del Sistema

```
reader/
├── server.py                  # API Flask (core reader + endpoint AI per interrogazioni)
├── epub_parser.py             # Estrazione, parsing capitoli e navigazione spine
├── database.py                # Persistenza dati utente e sessioni (SQLite WAL)
├── dictionary_manager.py      # EDICT2 locale + Jisho online fallback
├── furigana_manager.py        # pykakasi furigana injection & token analysis
├── translator_manager.py      # Google gtx translation engine con caching SQLite
│
├── ai/                        # 🧠 MODULO RAG & INFORMATION RETRIEVAL
│   ├── __init__.py
│   ├── document_processor.py  # Estrazione capitoli puliti con riferimenti (vol/cap/offset)
│   ├── chunking.py            # Segmentazione intelligente (rispetto frasi JP: 。「」 e windowing)
│   ├── embeddings.py          # Dense bi-encoder (es. multilingual-e5-small / paraphrase-multilingual)
│   ├── lexical_search.py      # BM25 con tokenizzazione morfologica (SudachiPy / MeCab / pykakasi)
│   ├── hybrid_retrieval.py    # Reciprocal Rank Fusion (RRF) combinando BM25 + Vettori
│   ├── reranker.py            # Cross-Encoder (riordino top-10 passaggi)
│   ├── rag_engine.py          # Assemblaggio prompt, iniezione contesto e chiamata LLM (API/locale)
│   └── prompts.py             # Prompt bilingue (contesto in giapponese, risposta strutturata in italiano)
│
├── evaluation/                # 📊 SUITE SPERIMENTALE & BENCHMARK
│   ├── dataset.py             # Collezione di 200-500 query annotate con passaggi ground-truth
│   ├── metrics.py             # Precision@k, Recall@k, MRR (Mean Reciprocal Rank), NDCG@k, Faithfulness
│   ├── benchmark.py           # Esecutore automatico di test per confrontare i 4 sistemi
│   └── reports.py             # Generazione automatica di tabelle e grafici di benchmark
│
└── tests/                     # Test unitari per robustezza ingegneristica
    ├── test_epub_parser.py
    ├── test_chunking.py
    ├── test_retrieval.py
    └── test_rag.py
```

---

## 🧪 4. Matrice degli Esperimenti

### Esperimento A: Confronto Information Retrieval (Stesso Dataset di Query)
Si confrontano 4 configurazioni sul medesimo dataset di query annotate:
1. **Sistema 1 (Baseline Lessicale):** BM25 (adattato per giapponese).
2. **Sistema 2 (Dense Retrieval):** Bi-Encoder Sentence-Transformers multilingue.
3. **Sistema 3 (Hybrid Search):** RRF combinando BM25 e Bi-Encoder ($RRF\_score = \sum \frac{1}{60 + rank_i}$).
4. **Sistema 4 (Hybrid + Reranker):** Top-20 passaggi dell'ibrido riordinati con Cross-Encoder neurale.

**Metriche calcolate:**
- $\text{Precision}@3$, $\text{Precision}@5$
- $\text{Recall}@5$
- $\text{MRR}$ (Mean Reciprocal Rank)
- $\text{nDCG}@5$ (Normalized Discounted Cumulative Gain)
- **Latenza media e $P_{95}$ (ms)**

### Esperimento B: Valutazione Qualitativa RAG
Per ciascun sistema di recupero, il contesto viene passato all'LLM per generare la risposta:
- **Fedeltà alle fonti (Faithfulness):** % di affermazioni verificabili nei passaggi citati.
- **Tasso di Allucinazione:** % di risposte con fatti non presenti nel libro.
- **Riferimento verificabile:** Accuratezza del link capitolo/paragrafo restituito all'utente.

### Esperimento C: Prestazioni Ingegneristiche
- Tempo di indicizzazione per volume (secondi).
- Dimensione dell'indice su disco/RAM.
- Throughput (query al secondo).

---

## 📖 5. Struttura della Tesi Scritta (Indice Capitoli)

1. **Capitolo 1 — Introduzione**
   - Problema della consultazione intelligente nei testi digitali lunghi.
   - Obiettivi della tesi e Research Questions.
2. **Capitolo 2 — Stato dell'Arte**
   - Evoluzione dell'Information Retrieval: da TF-IDF/BM25 ai Dense Embeddings.
   - Architetture RAG (Retrieval-Augmented Generation).
   - Problematiche specifiche del NLP in lingua giapponese (tokenizzazione, kanji/kana, segmentazione).
3. **Capitolo 3 — Tecnologie e Strumenti**
   - Python, Flask/FastAPI, SQLite/pgvector.
   - Sentence-Transformers, SudachiPy/pykakasi, Cross-Encoder.
4. **Capitolo 4 — Progettazione e Architettura del Sistema**
   - Requisiti funzionali e non funzionali.
   - Pipeline di Document Processing, Chunking e Indicizzazione.
   - Architettura dell'Hybrid Retriever e del RAG Engine.
5. **Capitolo 5 — Implementazione del Prototipo**
   - Dettagli implementativi del lettore e dei moduli AI.
   - Gestione delle citazioni interattive e della sicurezza.
6. **Capitolo 6 — Metodologia Sperimentale**
   - Costruzione del dataset di valutazione e annotazione ground-truth.
   - Definizione formale delle metriche adottate (MRR, NDCG, Faithfulness).
7. **Capitolo 7 — Risultati Sperimentali e Discussione**
   - Risposta analitica a ciascuna RQ (tabelle e grafici comparativi).
   - Analisi degli errori e casi di studio specifici.
8. **Capitolo 8 — Conclusioni e Sviluppi Futuri**
   - Sintesi dei risultati ottenuti e limiti del sistema.
   - Possibili estensioni a corpora multilingue più ampi.

---

## 🗓️ 6. Cronoprogramma di Sviluppo (14 Settimane)

| Periodo | Macro-Attività | Deliverable |
|---|---|---|
| **Settimane 1–2** | Studio bibliografico e definizione formale del dataset di test | Note bibliografiche e 5-10 paper di riferimento |
| **Settimane 3–4** | Pipeline di preprocessing EPUB, pulizia testo e chunking con metadati | `reader/ai/document_processor.py` e `chunking.py` |
| **Settimane 5–6** | Implementazione BM25 lessicale e Dense Bi-Encoder | `lexical_search.py` e `embeddings.py` |
| **Settimane 7–8** | Implementazione Hybrid Search (RRF) e Cross-Encoder Reranker | `hybrid_retrieval.py` e `reranker.py` |
| **Settimane 9–10** | Integrazione RAG Engine e interfaccia chat con citazioni verificabili | `rag_engine.py` e UI reader |
| **Settimane 11–12** | Esecuzione benchmark sperimentale, calcolo metriche IR e fedeltà | Tabelle dati, log e grafici prestazionali |
| **Settimane 13–14** | Analisi critica dei risultati, stesura finale tesi e revisione | Documento di tesi completo pronto per la discussione |

---

## ✉️ 7. Modello di Proposta per Docente di UniSalento

Da inviare via email a un professore dell'area Ingegneria Informatica (Sistemi di Elaborazione delle Informazioni / AI / Basi di Dati / NLP):

```text
Oggetto: Proposta di Tesi Triennale in Ingegneria Informatica – [Tuo Nome e Cognome, Matricola]

Gentile Prof. [Cognome],

Sono uno studente del corso di Laurea Triennale in Ingegneria Informatica (matricola [Numero]) e Le scrivo per sottoporre alla Sua attenzione una proposta per la tesi di laurea, nell'ambito dell'Information Retrieval e dell'Intelligenza Artificiale applicata.

Titolo provvisorio:
«Progettazione e valutazione sperimentale di un sistema RAG per la consultazione intelligente di libri digitali multilingua»

Descrizione sintetica del progetto:
L'obiettivo del lavoro è progettare, sviluppare e valutare sperimentalmente un sistema software per la consultazione intelligente di documenti digitali in formato EPUB, integrando tecniche di Information Retrieval (IR) e modelli linguistici generativi (RAG - Retrieval-Augmented Generation).

Il sistema affronta in particolare le sfide legate al recupero di informazioni da testi narrativi e multilingua, con un approfondimento sulla lingua giapponese (caratterizzata dall'assenza di spaziatori inter-parola e da complessità morfologiche kanji/kana).

Contributo sperimentale della tesi:
Il nucleo accademico del lavoro consisterà nel confronto quantitativo e controllato tra diverse strategie di reperimento delle informazioni su un dataset annotato:
1. Ricerca lessicale (BM25 adattato con tokenizzazione morfologica);
2. Ricerca semantica densa (Bi-Encoder con Sentence-Transformers multilingue);
3. Ricerca ibrida (Reciprocal Rank Fusion);
4. Ricerca ibrida con re-ranking neurale (Cross-Encoder).

I passaggi recuperati alimenteranno una pipeline RAG per la generazione di risposte corredate da citazioni puntuali e verificabili al testo originale (volume, capitolo, offset). Le prestazioni saranno valutate attraverso metriche standard di IR (Precision@K, Recall@K, MRR, nDCG, latenza) e metriche di fedeltà della risposta (assenza di allucinazioni).

Ho già sviluppato un prototipo funzionante del motore di lettura e parsing EPUB, che costituirà la base ingegneristica per integrare i moduli di retrieval e valutazione sperimentale.

Sarei molto grato se potesse dedicarmi un breve colloquio (anche online su Teams) per valutare l'idoneità del tema e ricevere Sue indicazioni su perimetro ed eventuali approfondimenti bibliografici.

In allegato trasmetto un abstract più dettagliato del progetto.

Cordiali saluti,
[Nome e Cognome]
Matricola: [Numero]
Corso di Laurea in Ingegneria Informatica – Università del Salento
```
