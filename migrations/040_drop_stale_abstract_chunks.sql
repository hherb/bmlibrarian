-- Migration 040: an abstract change drops the document's abstract chunks (#475).
--
-- When an importer rewrites document.abstract (a newer medRxiv version, a
-- PubMed update file's upsert, any other UPDATE), the abstract chunks in
-- public.chunks and their embeddings still hold the old text, so semantic
-- search matches an abstract the UI no longer shows. This trigger removes them
-- in the same transaction as the UPDATE, for every importer at once:
--
-- * every embedding of the document's abstract chunks (embedding_base, which
--   includes its inherited emb_768 / emb_1024 tables; those carry no foreign
--   key, so a chunk delete would not cascade to them);
-- * the abstract chunks themselves, except one an evaluation still references
--   (public.evaluations.chunk_id has no ON DELETE CASCADE; that chunk keeps its
--   row for the evaluation's history, without embeddings).
--
-- The document then has no abstract embedding, so the embedder
-- (embed_documents_cli.py embed) picks it up again on its next run. Full-text
-- chunks (semantic.chunks) are re-queued by trg_queue_chunking (migration 015).
--
-- Idempotent: safe to run repeatedly.

CREATE OR REPLACE FUNCTION public.drop_stale_abstract_chunks()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM public.embedding_base eb
    USING public.chunks c, public.chunktypes ct
    WHERE eb.chunk_id = c.id
      AND c.chunktype_id = ct.id
      AND ct.chunktype = 'abstract'
      AND c.document_id = NEW.id;

    DELETE FROM public.chunks c
    USING public.chunktypes ct
    WHERE c.chunktype_id = ct.id
      AND ct.chunktype = 'abstract'
      AND c.document_id = NEW.id
      AND NOT EXISTS (SELECT 1 FROM public.evaluations e WHERE e.chunk_id = c.id);

    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION public.drop_stale_abstract_chunks() IS
'Trigger function: when document.abstract changes, delete the embeddings of the
document''s abstract chunks and the chunks no evaluation references, so the
embedder re-embeds the new abstract (#475).';

DROP TRIGGER IF EXISTS trg_drop_stale_abstract_chunks ON public.document;

CREATE TRIGGER trg_drop_stale_abstract_chunks
AFTER UPDATE OF abstract ON public.document
FOR EACH ROW
WHEN (OLD.abstract IS DISTINCT FROM NEW.abstract)
EXECUTE FUNCTION public.drop_stale_abstract_chunks();
