from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from src.common.config import (
    EMBEDDING_MODEL_NAME,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_SEPARATORS,
)


def create_resume_documents(resumes):
    """
    Split extracted candidate resume texts into whole resume documents
    and overlapping paragraph-level chunk documents with metadata.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=CHUNK_SEPARATORS,
    )

    documents = []

    for resume in resumes:
        if resume["status"] != "text_extracted":
            continue

        if not resume["text"]:
            continue

        metadata = {
            "source_row": resume["source_row"],
            "name": resume["name"],
            "resume_url": resume["resume_url"],
            "local_path": resume["local_path"]
        }

        whole_resume = Document(
            page_content=resume["text"],
            metadata={
                **metadata,
                "document_type": "whole_resume"
            }
        )

        documents.append(whole_resume)

        chunks = text_splitter.split_documents([whole_resume])

        for chunk_id, chunk in enumerate(chunks):
            chunk.metadata["document_type"] = "resume_chunk"
            chunk.metadata["chunk_id"] = chunk_id

        documents.extend(chunks)

    return documents


def create_embedding_model():
    """
    Initialize the shared SentenceTransformer embedding model.
    Loaded once at application startup.
    """
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME
    )


def create_vector_store(documents, embeddings):
    """
    Build an in-memory, request-scoped FAISS vector store from candidate documents.
    """
    if not documents:
        raise ValueError("Documents are required to create a vector store.")

    return FAISS.from_documents(
        documents,
        embeddings
    )
