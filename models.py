import os
import uuid
from datetime import datetime
from sqlalchemy import Column, String, BigInteger, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker

# 1. Initialize Base for Declarative Mapping
Base = declarative_base()

# 2. Define Document relational schema
class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(512), nullable=False)
    s3_key = Column(String(1024), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=True)
    
    # State Machine: PENDING_UPLOAD -> QUEUING_FAILED -> QUEUED -> PROCESSING -> COMPLETED -> FAILED
    status = Column(String(20), nullable=False, default="PENDING_UPLOAD")
    
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        """Converts model attributes to a clean dictionary representation."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "s3_key": self.s3_key,
            "file_size_bytes": self.file_size_bytes,
            "status": self.status,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

from config import settings

# 3. Database Engine & Session Maker Setup
# Create Async Engine for scalable, non-blocking PostgreSQL operations
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set to True if you want to see raw SQL logs in the terminal
    pool_pre_ping=True,  # Automatically tests connections before querying (prevents disconnected errors)
)

# Create Async Session maker
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False  # Prevents SQLAlchemy from reloading attributes after commits (better performance)
)

# 4. Dependency Injection Helper for FastAPI Endpoints
async def get_db():
    """Dependency helper to yield async database sessions to FastAPI routes."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
