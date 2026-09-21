from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from src.ingestion.resume_text_store import load_resume_texts


VECTOR_STORE_PATH = "data/vector_store/resumes"


def create_resume_documents(resumes):

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=150,
        separators=[
            "\n\n",
            "\n",
            ". ",
            " ",
            ""
        ]
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

        chunks = text_splitter.split_documents(
            [whole_resume]
        )

        for chunk_id, chunk in enumerate(chunks):

            chunk.metadata["document_type"] = "resume_chunk"
            chunk.metadata["chunk_id"] = chunk_id

        documents.extend(chunks)

    return documents


def create_embedding_model():

    return HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-mpnet-base-v2"
    )

def get_or_create_vector_store(
    filepath,
    embeddings,
    documents=None
):

    path = Path(filepath)

    faiss_file = path / "index.faiss"
    pickle_file = path / "index.pkl"

    # --------------------------------------------------
    # Existing store
    # --------------------------------------------------

    if faiss_file.exists() and pickle_file.exists():

        print(
            f"Loading existing vector store: {filepath}"
        )

        return FAISS.load_local(
            filepath,
            embeddings,
            allow_dangerous_deserialization=True
        )

    # --------------------------------------------------
    # New store
    # --------------------------------------------------

    if documents is None:

        raise ValueError(
            "Documents are required when creating "
            "a new vector store."
        )

    print(
        "No existing vector store found."
    )

    print(
        "Creating new vector store..."
    )

    vector_store = FAISS.from_documents(
        documents,
        embeddings
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    vector_store.save_local(
        filepath
    )

    print(
        f"Vector store saved to: {filepath}"
    )

    return vector_store


if __name__ == "__main__":

    resumes = load_resume_texts()

    documents = create_resume_documents(
        resumes
    )

    print(f"Total documents: {len(documents)}")

    whole_resumes = sum(
        doc.metadata["document_type"] == "whole_resume"
        for doc in documents
    )

    chunks = sum(
        doc.metadata["document_type"] == "resume_chunk"
        for doc in documents
    )

    print(f"Whole resumes: {whole_resumes}")
    print(f"Resume chunks: {chunks}")

    embeddings = create_embedding_model()

    vector_store = get_or_create_vector_store(
        filepath=VECTOR_STORE_PATH,
        embeddings=embeddings,
        documents=documents
    )

    # Test retrieval
    query = """
    Python developer with experience in Django,
    REST APIs, PostgreSQL and backend development.
    """

    results = vector_store.similarity_search(
        query,
        k=10
    )

    print("\n" + "=" * 100)
    print("TEST RETRIEVAL")
    print("=" * 100)

    for i, document in enumerate(results, start=1):

        print(f"\nResult {i}")
        print("-" * 80)

        print("Name:", document.metadata.get("name"))
        print(
            "Type:",
            document.metadata.get("document_type")
        )
        print(
            "Chunk:",
            document.metadata.get("chunk_id")
        )
        print("\nText:")
        print(document.page_content[:500])