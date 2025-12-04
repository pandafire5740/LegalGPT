"""Application configuration management."""
import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings."""
    
    # Sharepoint Configuration (Optional for basic startup)
    sharepoint_site_url: str = Field(
        default="https://yourcompany.sharepoint.com/sites/yoursite",
        description="Sharepoint site URL"
    )
    sharepoint_client_id: str = Field(
        default="your-client-id",
        description="Sharepoint app client ID"
    )
    sharepoint_client_secret: str = Field(
        default="your-client-secret",
        description="Sharepoint app client secret"
    )
    sharepoint_tenant_id: str = Field(
        default="your-tenant-id",
        description="Azure tenant ID"
    )
    sharepoint_folder_path: str = Field(
        default="/Shared Documents/Legal Documents",
        description="Path to legal documents folder in Sharepoint"
    )
    
    # OpenAI Configuration (Optional for basic startup)
    openai_api_key: str = Field(
        default="your-openai-api-key",
        description="OpenAI API key"
    )
    
    # Vector Database Configuration
    chroma_persist_directory: str = Field(
        default="./chroma_db",
        description="Directory for ChromaDB persistence"
    )
    
    # File Upload Configuration
    uploads_directory: str = Field(
        default="./uploads",
        description="Directory for storing uploaded files"
    )
    
    # Redis Configuration
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for background tasks"
    )
    
    # Application Configuration
    debug: bool = Field(default=True, description="Debug mode")
    host: str = Field(default="0.0.0.0", description="Host address")
    port: int = Field(default=8000, description="Port number")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    
    # Security
    allowed_origins: List[str] = Field(
        default=["http://localhost:8000", "http://127.0.0.1:8000"],
        description="List of allowed origins for CORS"
    )
    
    # Search Configuration
    search_similarity_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score (0.0-1.0) for files to appear in search results. Default: 0.3 (30%)"
    )
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
