import pysbd

segmenter = pysbd.Segmenter(language="en", clean=False)

def fast_sentence_chunker(text, max_chars=1800, overlap_chars=320):
    sentences = segmenter.segment(text)
    
    chunks = []
    current_chunk = []
    current_len = 0
    
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
            
        if current_len + len(sent) > max_chars and current_chunk:
            chunks.append(" ".join(current_chunk))
            
            # Build overlap from end
            overlap = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) < overlap_chars:
                    overlap.insert(0, s)
                    overlap_len += len(s) + 1
                else:
                    break
            current_chunk = overlap
            current_len = overlap_len
        
        current_chunk.append(sent)
        current_len += len(sent) + 1
    
    if current_chunk:
        chunks.append(" ".join(current_chunk))
    
    return chunks