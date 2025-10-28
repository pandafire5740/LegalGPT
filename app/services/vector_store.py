"""Vector database service for document embeddings and similarity search.
Uses OpenAI embeddings (text-embedding-3-small) for all vector operations.
"""
from typing import List, Dict, Any, Optional, Tuple
import logging
import os
import chromadb
from chromadb.config import Settings
from openai import OpenAI

from app.config import settings


logger = logging.getLogger(__name__)

# Global cached instances (singleton pattern)
_chroma_client = None
_openai_client = None


def _get_chroma_client():
    """Get or create the ChromaDB client (singleton)."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=settings.chroma_persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )
        logger.info("Initialized ChromaDB client")
    return _chroma_client


def _get_openai_client():
    """Get or create the OpenAI client (singleton)."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.info("✅ OpenAI embeddings client initialized (text-embedding-3-small)")
    return _openai_client


class VectorStore:
    """Service for managing document embeddings and similarity search."""
    
    def __init__(self):
        """Initialize ChromaDB and embedding model."""
        # Use cached instances
        self.client = _get_chroma_client()
        
        # Get or create collection for legal documents
        self.collection = self.client.get_or_create_collection(
            name="legal_documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Use OpenAI for embeddings
        self.openai_client = _get_openai_client()
        
        logger.info("VectorStore ready (using OpenAI embeddings)")
    
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> None:
        """
        Add a document chunk to the vector store.
        
        Args:
            doc_id: Unique identifier for the document chunk
            text: Text content to embed
            metadata: Document metadata
        """
        try:
            # Generate embedding via OpenAI
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            embedding = response.data[0].embedding
            
            # Store in ChromaDB
            self.collection.add(
                embeddings=[embedding],
                documents=[text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
            logger.debug(f"Added document to vector store, doc_id: {doc_id}, text_length: {len(text)}")
            
        except Exception as e:
            logger.error(f"Failed to add document to vector store, doc_id: {doc_id}, error: {str(e)}")
            raise
    
    def search_similar(self, query: str, n_results: int = 10, where: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Search for similar documents using vector similarity.
        
        Args:
            query: Search query text
            n_results: Number of results to return
            where: Optional metadata filters
            
        Returns:
            List of similar documents with metadata and scores
        """
        try:
            # Generate query embedding via OpenAI
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query
            )
            query_embedding = response.data[0].embedding
            
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                include=['metadatas', 'documents', 'distances']
            )
            
            # Format results
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    result = {
                        'id': results['ids'][0][i] if results['ids'] else f"result_{i}",
                        'content': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'similarity_score': 1 - results['distances'][0][i] if results['distances'] else 0.0  # Convert distance to similarity
                    }
                    formatted_results.append(result)
            
            logger.info(f"Vector search completed, query: {query}, results: {len(formatted_results)}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search vector store, query: {query}, error: {str(e)}")
            raise
    
    def search_by_file(self, file_name: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific file.
        
        Args:
            file_name: Name of the file to search for
            
        Returns:
            List of document chunks for the file
        """
        try:
            results = self.collection.get(
                where={"file_name": file_name},
                include=['metadatas', 'documents']
            )
            
            formatted_results = []
            if results['documents']:
                for i, doc in enumerate(results['documents']):
                    result = {
                        'id': results['ids'][i],
                        'content': doc,
                        'metadata': results['metadatas'][i] if results['metadatas'] else {}
                    }
                    formatted_results.append(result)
            
            logger.info(f"File search completed, file_name: {file_name}, chunks: {len(formatted_results)}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search by file, file_name: {file_name}, error: {str(e)}")
            raise
    
    def search_by_metadata(self, metadata_filter: Dict[str, Any], n_results: int = 50) -> List[Dict[str, Any]]:
        """
        Search documents by metadata filters.
        
        Args:
            metadata_filter: Dictionary of metadata key-value pairs to filter by
            n_results: Maximum number of results to return
            
        Returns:
            List of matching documents
        """
        try:
            results = self.collection.get(
                where=metadata_filter,
                limit=n_results,
                include=['metadatas', 'documents']
            )
            
            formatted_results = []
            if results['documents']:
                for i, doc in enumerate(results['documents']):
                    result = {
                        'id': results['ids'][i],
                        'content': doc,
                        'metadata': results['metadatas'][i] if results['metadatas'] else {}
                    }
                    formatted_results.append(result)
            
            logger.info(f"Metadata search completed, filter: {metadata_filter}, results: {len(formatted_results)}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to search by metadata, filter: {metadata_filter}, error: {str(e)}")
            raise
    
    def delete_document_chunks(self, file_name: str) -> int:
        """
        Delete all chunks for a specific document.
        
        Args:
            file_name: Name of the file to delete chunks for
            
        Returns:
            Number of chunks deleted
        """
        try:
            # Get all chunk IDs for the file
            results = self.collection.get(
                where={"file_name": file_name},
                include=['ids']
            )
            
            if results['ids']:
                self.collection.delete(ids=results['ids'])
                deleted_count = len(results['ids'])
                logger.info(f"Deleted document chunks, file_name: {file_name}, count: {deleted_count}")
                return deleted_count
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to delete document chunks, file_name: {file_name}, error: {str(e)}")
            raise
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the document collection.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            count_result = self.collection.count()
            total_documents = count_result
            
            # Get sample of metadata to analyze
            sample_results = self.collection.get(
                limit=100,
                include=['metadatas']
            )
            
            # Analyze file types
            file_types = {}
            unique_files = set()
            
            if sample_results['metadatas']:
                for metadata in sample_results['metadatas']:
                    file_name = metadata.get('file_name', '')
                    unique_files.add(file_name)
                    
                    if '.' in file_name:
                        ext = file_name.split('.')[-1].lower()
                        file_types[ext] = file_types.get(ext, 0) + 1
            
            stats = {
                'total_chunks': total_documents,
                'unique_files': len(unique_files),
                'file_types': file_types,
                'collection_name': self.collection.name
            }
            
            logger.info(f"Retrieved collection stats: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get collection stats, error: {str(e)}")
            raise
    
    def get_all_documents(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get all documents from the collection.
        
        Args:
            limit: Maximum number of documents to return
            
        Returns:
            List of documents with content and metadata
        """
        try:
            results = self.collection.get(
                limit=limit,
                include=['documents', 'metadatas']
            )
            
            documents = []
            for i, doc_id in enumerate(results['ids']):
                documents.append({
                    'id': doc_id,
                    'content': results['documents'][i],
                    'metadata': results['metadatas'][i]
                })
            
            logger.debug(f"Retrieved {len(documents)} documents from collection")
            return documents
            
        except Exception as e:
            logger.error(f"Failed to get all documents, error: {str(e)}")
            raise
    
    def reset_store(self) -> Dict[str, Any]:
        """Delete all data in the collection and recreate it fresh."""
        try:
            # Delete the collection entirely for a clean reset
            self.client.delete_collection("legal_documents")
            # Recreate collection
            self.collection = self.client.get_or_create_collection(
                name="legal_documents",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info("Vector store reset: collection recreated with zero documents")
            return {"status": "success", "total_chunks": 0, "unique_files": 0}
        except Exception as e:
            logger.error(f"Failed to reset vector store, error: {str(e)}")
            raise
    
    def hybrid_search(self, query: str, metadata_filter: Optional[Dict[str, Any]] = None, n_results: int = 10, require_keyword: bool = True) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining vector similarity and keyword matching.
        
        Args:
            query: Search query text
            metadata_filter: Optional metadata filters
            n_results: Number of results to return
            require_keyword: If True, only return results containing at least one query keyword
            
        Returns:
            List of relevant documents with scores
        """
        try:
            # Perform vector search with metadata filter (get more results to filter later)
            vector_results = self.search_similar(query, n_results * 4, metadata_filter)
            
            query_lower = query.lower()
            # Extract meaningful words (2+ characters, excluding common stopwords)
            stopwords = {'the', 'is', 'at', 'which', 'on', 'in', 'to', 'of', 'and', 'or', 'for', 'by', 'a', 'an'}
            query_words = [
                word.strip('.,!?;:()[]{}') 
                for word in query_lower.split() 
                if len(word.strip('.,!?;:()[]{}')) >= 2 and word.strip('.,!?;:()[]{}') not in stopwords
            ]
            
            # If no valid query words after filtering, return empty
            if require_keyword and not query_words:
                logger.warning(f"No valid query words after filtering: {query}")
                return []
            
            # For multi-word queries, check if it's a phrase query (words should appear together)
            is_phrase_query = len(query_words) >= 2
            
            filtered_results = []
            
            # Score and filter documents
            for result in vector_results:
                content_lower = result['content'].lower()
                metadata_lower = str(result.get('metadata', {})).lower()
                
                # Check if document contains query keywords
                contains_content_keyword = False  # Keywords in actual content
                contains_metadata_keyword = False  # Keywords in filename/metadata
                keyword_score = 0.0
                matched_words = set()
                
                for word in query_words:
                    # Check content (primary match)
                    if word in content_lower:
                        contains_content_keyword = True
                        matched_words.add(word)
                        # Count occurrences for scoring
                        occurrences = content_lower.count(word)
                        keyword_score += 0.2 * min(occurrences, 3)  # Cap at 3 occurrences per word
                    
                    # Also check filename for matches (useful for single-word queries like "NDA")
                    elif word in metadata_lower:
                        contains_metadata_keyword = True
                        matched_words.add(word)
                        keyword_score += 0.1
                
                # Require keywords based on query complexity:
                # - For single-word queries: allow metadata matches (e.g., "NDA" in filename)
                # - For 2-word queries: require ALL words in content (phrase matching)
                # - For 3+ word queries: require at least 2 words in content
                if require_keyword:
                    if len(query_words) == 1:
                        # Single word: content OR metadata match is OK
                        if not (contains_content_keyword or contains_metadata_keyword):
                            continue
                    elif len(query_words) == 2:
                        # 2-word phrase: require BOTH words in content for strict matching
                        if len(matched_words) < 2:
                            continue
                    else:
                        # 3+ words: require at least 2 words in content
                        if len(matched_words) < 2:
                            continue
                
                # Boost score if multiple query words match
                if len(matched_words) > 1:
                    keyword_score += 0.15 * (len(matched_words) - 1)
                
                # For phrase queries, check if words appear close together (within 50 chars)
                phrase_bonus = 0.0
                if is_phrase_query and len(query_words) >= 2:
                    # Check if all query words appear in a window
                    for i in range(len(content_lower) - 50):
                        window = content_lower[i:i+50]
                        if all(word in window for word in query_words):
                            phrase_bonus = 0.5  # Big boost for phrase matches
                            break
                
                # Calculate final score: semantic similarity + keyword matching + phrase bonus
                semantic_score = result['similarity_score']
                final_score = semantic_score + keyword_score + phrase_bonus
                
                result['final_score'] = final_score
                result['keyword_matches'] = contains_content_keyword or contains_metadata_keyword
                result['content_match'] = contains_content_keyword
                filtered_results.append(result)
            
            # Sort by final score and return top results
            filtered_results.sort(key=lambda x: x['final_score'], reverse=True)
            
            logger.info(f"Hybrid search completed, query: {query}, results: {len(filtered_results[:n_results])} (filtered from {len(vector_results)})")
            return filtered_results[:n_results]
            
        except Exception as e:
            logger.error(f"Failed to perform hybrid search, query: {query}, error: {str(e)}")
            raise
