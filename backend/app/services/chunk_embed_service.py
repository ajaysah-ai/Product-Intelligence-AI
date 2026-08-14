import os

from sqlalchemy.orm import Session

from app.chunking.chunker import chunk_text
from app.embeddings.embedder import embed_texts
from app.models import TempChunk, TempDocument, TempEmbedding, TempRequest


def process_request_chunks_and_embeddings(db: Session, temp_request: TempRequest) -> dict:
    eligible_docs = [
        d
        for d in temp_request.documents
        if d.extraction_status == "success" and d.extracted_text and not d.chunks
    ]

    chunk_objects: list[TempChunk] = []
    for doc in eligible_docs:
        pieces = chunk_text(doc.extracted_text)
        for idx, piece in enumerate(pieces):
            chunk = TempChunk(temp_document_id=doc.id, chunk_index=idx, text=piece)
            db.add(chunk)
            chunk_objects.append(chunk)

    if not chunk_objects:
        return {"documents_processed": len(eligible_docs), "chunks_created": 0, "embeddings_created": 0}

    db.flush()  # assign DB-generated ids before embedding, so we can link embeddings to them

    # One batched call across every chunk in the request, not one call per document —
    # far fewer, larger forward passes through the embedding model.
    texts = [c.text for c in chunk_objects]
    vectors = embed_texts(texts)

    model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
    for chunk, vector in zip(chunk_objects, vectors):
        db.add(TempEmbedding(temp_chunk_id=chunk.id, vector=vector, model_name=model_name))

    db.commit()

    return {
        "documents_processed": len(eligible_docs),
        "chunks_created": len(chunk_objects),
        "embeddings_created": len(chunk_objects),
    }
