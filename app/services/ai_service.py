"""AI service for chat-based document querying - LLM integration placeholder."""
import json
import os
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime

from app.config import settings
from app.services.vector_store import VectorStore


logger = logging.getLogger(__name__)


class AIService:
    """Service for AI-powered document querying and chat functionality.
    
    Note: LLM integration has been removed. Implement your own LLM logic here.
    """
    
    def __init__(self, vector_store: VectorStore):
        """Initialize AI service with vector store for document retrieval."""
        self.vector_store = vector_store
        logger.info("AI Service initialized (LLM integration placeholder)")
    
    async def process_query(self, query: str, conversation_history: Optional[List[Dict[str, str]]] = None, model_preference: str = "phi") -> Dict[str, Any]:
        """
        Process a user query and return relevant information from documents.
        
        Args:
            query: User's question or request
            conversation_history: Previous conversation messages (optional)
            model_preference: Model preference (placeholder, not used)
            
        Returns:
            Response with retrieved documents and placeholder for LLM answer
        """
        try:
            logger.info(f"Processing query: {query}")
            
            # Check if query is asking for document list
            query_lower = query.lower()
            if any(phrase in query_lower for phrase in [
                "what documents", "which documents", "list documents", "show documents",
                "documents in memory", "documents uploaded", "what files",
                "which files", "list files", "show files", "all files", "what do you know"
            ]) and "summarize" not in query_lower:
                return await self._list_documents_info()
            
            # Check if query wants summary/info about ALL documents
            wants_all_docs = any(phrase in query_lower for phrase in [
                "summarize all", "summary of all", "all documents", "all the documents",
                "every document", "each document", "summarize everything"
            ])
            
            if wants_all_docs:
                return await self._summarize_all_documents(query)
            
            # Search for relevant documents using vector store
            relevant_docs = self.vector_store.hybrid_search(query, n_results=10)
            
            # Prepare context from relevant documents
            source_documents_dict = {}
            top_docs = relevant_docs[:5]
            
            for doc in top_docs:
                metadata = doc['metadata']
                file_name = metadata.get('file_name', 'Unknown')
                
                # Track source documents for citation
                if file_name not in source_documents_dict or \
                   doc.get('final_score', 0.0) > source_documents_dict[file_name]['similarity_score']:
                    source_documents_dict[file_name] = {
                        'file_name': file_name,
                        'file_path': metadata.get('file_path', 'N/A'),
                        'similarity_score': doc.get('final_score', 0.0),
                        'excerpt': doc['content'][:200] + "..." if len(doc['content']) > 200 else doc['content']
                    }
            
            source_documents = list(source_documents_dict.values())
            
            # Return documents with placeholder for LLM integration
            if relevant_docs:
                preview = "\n\n".join([
                    f"**{doc['metadata'].get('file_name', 'Unknown')}**:\n{doc['content'][:400]}..."
                    for doc in relevant_docs[:3]
                ])
                
                return {
                    "answer": f"🔧 **LLM Integration Needed**\n\nI found {len(relevant_docs)} relevant document excerpts for your query, but LLM integration is not yet implemented.\n\n**Retrieved Context:**\n{preview}\n\n💡 Implement your LLM integration in `app/services/ai_service.py` to generate intelligent responses.",
                    "source_documents": source_documents,
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "llm_integration_status": "pending"
                }
            else:
                return {
                    "answer": f"No relevant documents found for query: '{query}'. Try uploading documents first or rebuild the search index.",
                    "source_documents": [],
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "llm_integration_status": "pending"
                }
            
        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            return {
                "answer": f"An error occurred while processing your query: {str(e)}",
                "source_documents": [],
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def summarize_document(self, file_name: str) -> Dict[str, Any]:
        """
        Summarize a specific document.
        
        Args:
            file_name: Name of the document to summarize
            
        Returns:
            Placeholder response - implement LLM logic here
        """
        try:
            logger.info(f"Summarizing document: {file_name}")
            
            # Retrieve all chunks for this document
            all_docs = self.vector_store.get_all_documents()
            file_docs = [doc for doc in all_docs if doc['metadata'].get('file_name') == file_name]
            
            if not file_docs:
                return {
                    "summary": f"Document '{file_name}' not found in the vector store.",
                    "file_name": file_name,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Combine content
            full_content = "\n\n".join([doc['content'] for doc in file_docs[:10]])  # Limit to first 10 chunks
            
            return {
                "summary": f"🔧 **LLM Integration Needed**\n\nFound {len(file_docs)} chunks for document '{file_name}'.\n\n**Preview:**\n{full_content[:500]}...\n\n💡 Implement LLM summarization logic here.",
                "file_name": file_name,
                "chunk_count": len(file_docs),
                "timestamp": datetime.now().isoformat(),
                "llm_integration_status": "pending"
            }
            
        except Exception as e:
            logger.error(f"Error summarizing document: {e}", exc_info=True)
            return {
                "summary": f"Error summarizing document: {str(e)}",
                "file_name": file_name,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def extract_terms_conditions(self, query_filter: Optional[str] = None) -> Dict[str, Any]:
        """
        Extract terms and conditions from documents.
        
        Args:
            query_filter: Optional filter query
            
        Returns:
            Placeholder response - implement LLM logic here
        """
        try:
            logger.info("Extracting terms and conditions")
            
            # Search for terms-related content
            search_query = query_filter or "terms conditions obligations requirements"
            relevant_docs = self.vector_store.hybrid_search(search_query, n_results=15)
            
            if not relevant_docs:
                return {
                    "terms": "No relevant terms and conditions found.",
                    "timestamp": datetime.now().isoformat()
                }
            
            excerpts = "\n\n".join([
                f"**{doc['metadata'].get('file_name', 'Unknown')}**:\n{doc['content'][:300]}"
                for doc in relevant_docs[:5]
            ])
            
            return {
                "terms": f"🔧 **LLM Integration Needed**\n\nFound {len(relevant_docs)} relevant excerpts.\n\n**Sample Excerpts:**\n{excerpts}\n\n💡 Implement LLM extraction logic to parse and structure terms & conditions.",
                "source_count": len(relevant_docs),
                "timestamp": datetime.now().isoformat(),
                "llm_integration_status": "pending"
            }
            
        except Exception as e:
            logger.error(f"Error extracting terms: {e}", exc_info=True)
            return {
                "terms": f"Error extracting terms: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def get_document_location(self, file_name_query: str) -> Dict[str, Any]:
        """
        Get location information for a document.
        
        Args:
            file_name_query: Query to find the document
            
        Returns:
            Document location information
        """
        try:
            logger.info(f"Getting document location for: {file_name_query}")
            
            # Search for matching documents
            all_docs = self.vector_store.get_all_documents()
            matching_docs = [
                doc for doc in all_docs 
                if file_name_query.lower() in doc['metadata'].get('file_name', '').lower()
            ]
            
            if not matching_docs:
                return {
                    "location": f"No documents found matching '{file_name_query}'",
                    "found": False,
                    "timestamp": datetime.now().isoformat()
                }
            
            locations = []
            for doc in matching_docs[:5]:
                metadata = doc['metadata']
                locations.append({
                    'file_name': metadata.get('file_name', 'Unknown'),
                    'file_path': metadata.get('file_path', 'N/A'),
                    'file_type': metadata.get('file_type', 'Unknown')
                })
            
            return {
                "location": f"Found {len(locations)} matching document(s)",
                "documents": locations,
                "found": True,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting document location: {e}", exc_info=True)
            return {
                "location": f"Error: {str(e)}",
                "found": False,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def _summarize_all_documents(self, query: str) -> Dict[str, Any]:
        """
        Provide an overview of all documents.
        
        Args:
            query: Original query
            
        Returns:
            Overview of all documents with placeholder for LLM summary
        """
        try:
            logger.info("Summarizing all documents")
            
            # Get all unique documents
            all_docs = self.vector_store.get_all_documents()
            
            # Group by file name
            files_dict = {}
            for doc in all_docs:
                file_name = doc['metadata'].get('file_name', 'Unknown')
                if file_name not in files_dict:
                    files_dict[file_name] = {
                        'file_name': file_name,
                        'file_path': doc['metadata'].get('file_path', 'N/A'),
                        'file_type': doc['metadata'].get('file_type', 'Unknown'),
                        'chunk_count': 0,
                        'sample_content': doc['content'][:200]
                    }
                files_dict[file_name]['chunk_count'] += 1
            
            source_documents = list(files_dict.values())
            
            # Create summary
            file_list = "\n".join([
                f"- **{doc['file_name']}** ({doc['file_type']}, {doc['chunk_count']} chunks)"
                for doc in source_documents
            ])
            
            return {
                "answer": f"🔧 **LLM Integration Needed**\n\n**Document Collection Overview:**\n\nTotal documents: {len(source_documents)}\nTotal chunks: {len(all_docs)}\n\n**Files:**\n{file_list}\n\n💡 Implement LLM logic to generate intelligent summaries of all documents.",
                "source_documents": source_documents,
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "llm_integration_status": "pending"
            }
            
        except Exception as e:
            logger.error(f"Error summarizing all documents: {e}", exc_info=True)
            return {
                "answer": f"Error summarizing documents: {str(e)}",
                "source_documents": [],
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
    
    async def _list_documents_info(self) -> Dict[str, Any]:
        """
        List all available documents.
        
        Returns:
            List of documents with metadata
        """
        try:
            logger.info("Listing all documents")
            
            # Get all documents and extract unique files
            all_docs = self.vector_store.get_all_documents()
            
            files_dict = {}
            for doc in all_docs:
                file_name = doc['metadata'].get('file_name', 'Unknown')
                if file_name not in files_dict:
                    files_dict[file_name] = {
                        'file_name': file_name,
                        'file_path': doc['metadata'].get('file_path', 'N/A'),
                        'file_type': doc['metadata'].get('file_type', 'Unknown'),
                        'chunk_count': 0
                    }
                files_dict[file_name]['chunk_count'] += 1
            
            source_documents = list(files_dict.values())
            
            if not source_documents:
                return {
                    "answer": "No documents are currently indexed. Please upload documents using the web interface.",
                    "source_documents": [],
                    "query": "list documents",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Format document list
            file_list = "\n".join([
                f"📄 **{doc['file_name']}** ({doc['file_type']}, {doc['chunk_count']} chunks)"
                for doc in source_documents
            ])
            
            return {
                "answer": f"**Available Documents ({len(source_documents)}):**\n\n{file_list}\n\nYou can ask questions about any of these documents.",
                "source_documents": source_documents,
                "query": "list documents",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error listing documents: {e}", exc_info=True)
            return {
                "answer": f"Error listing documents: {str(e)}",
                "source_documents": [],
                "query": "list documents",
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            }
