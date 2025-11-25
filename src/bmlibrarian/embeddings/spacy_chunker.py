import spacy

nlp = spacy.load("en_core_sci_sm")  # or en_core_web_sm

def sentence_aware_chunker(text, max_chars=1800, overlap_chars=320):
    """
    Split text into chunks that respect sentence boundaries.
    Why using spacy models? - https://github.com/allenai/scispacy :
    "scispacy models are trained on biomedical text and are better at 
    handling abbreviations, acronyms, and other domain-specific language
    that simpler approaches might not understand and interprete as 
    sentence boundary (e.g. 'Fig. 8')"
    """
    doc = nlp(text)
    sentences = [sent.text.strip() for sent in doc.sents]
    
    chunks = []
    current_chunk = []
    current_len = 0
    
    for sent in sentences:
        if current_len + len(sent) > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            # Keep last N chars worth of sentences for overlap
            overlap_text = ""
            for s in reversed(current_chunk):
                if len(overlap_text) + len(s) < overlap_chars:
                    overlap_text = s + " " + overlap_text
                else:
                    break
            current_chunk = [overlap_text.strip()] if overlap_text.strip() else []
            current_len = len(overlap_text)
        
        current_chunk.append(sent)
        current_len += len(sent) + 1
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks