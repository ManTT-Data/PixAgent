from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Text, LargeBinary, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .postgresql import Base
import datetime

class FAQItem(Base):
    __tablename__ = "faq_item"
    
    id = Column(Integer, primary_key=True, index=True)
    question = Column(String, nullable=False)
    answer = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class EmergencyItem(Base):
    __tablename__ = "emergency_item"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    description = Column(String, nullable=True)
    address = Column(String, nullable=True)
    location = Column(String, nullable=True)  # Will be converted to/from PostGIS POINT type
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class EventItem(Base):
    __tablename__ = "event_item"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    address = Column(String, nullable=False)
    location = Column(String, nullable=True)  # Will be converted to/from PostGIS POINT type
    date_start = Column(DateTime, nullable=False)
    date_end = Column(DateTime, nullable=True)
    price = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    featured = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class VectorDatabase(Base):
    __tablename__ = "vector_database"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    pinecone_index = Column(String, nullable=False)
    api_key = Column(String, nullable=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="vector_database")
    vector_statuses = relationship("VectorStatus", back_populates="vector_database")
    engine_associations = relationship("EngineVectorDb", back_populates="vector_database")

class Document(Base):
    __tablename__ = "document"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    file_content = Column(LargeBinary, nullable=True)
    file_type = Column(String, nullable=True)
    size = Column(Integer, nullable=True)
    content_type = Column(String, nullable=True)
    is_embedded = Column(Boolean, default=False)
    file_metadata = Column(JSON, nullable=True)
    vector_database_id = Column(Integer, ForeignKey("vector_database.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    vector_database = relationship("VectorDatabase", back_populates="documents")
    vector_statuses = relationship("VectorStatus", back_populates="document")

class VectorStatus(Base):
    __tablename__ = "vector_status"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("document.id"), nullable=False)
    vector_database_id = Column(Integer, ForeignKey("vector_database.id"), nullable=False)
    vector_id = Column(String, nullable=True)
    status = Column(String, default="pending")
    error_message = Column(String, nullable=True)
    embedded_at = Column(DateTime, nullable=True)
    
    # Relationships
    document = relationship("Document", back_populates="vector_statuses")
    vector_database = relationship("VectorDatabase", back_populates="vector_statuses")

class TelegramBot(Base):
    __tablename__ = "telegram_bot"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    username = Column(String, nullable=False, unique=True)
    token = Column(String, nullable=False)
    status = Column(String, default="inactive")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    bot_engines = relationship("BotEngine", back_populates="bot")

class ChatEngine(Base):
    __tablename__ = "chat_engine"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    answer_model = Column(String, nullable=False)
    system_prompt = Column(Text, nullable=True)
    empty_response = Column(String, nullable=True)
    similarity_top_k = Column(Integer, default=3)
    vector_distance_threshold = Column(Float, default=0.75)
    grounding_threshold = Column(Float, default=0.2)
    use_public_information = Column(Boolean, default=False)
    status = Column(String, default="active")
    created_at = Column(DateTime, server_default=func.now())
    last_modified = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relationships
    bot_engines = relationship("BotEngine", back_populates="engine")
    engine_vector_dbs = relationship("EngineVectorDb", back_populates="engine")

class BotEngine(Base):
    __tablename__ = "bot_engine"
    
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(Integer, ForeignKey("telegram_bot.id"), nullable=False)
    engine_id = Column(Integer, ForeignKey("chat_engine.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    
    # Relationships
    bot = relationship("TelegramBot", back_populates="bot_engines")
    engine = relationship("ChatEngine", back_populates="bot_engines")

class EngineVectorDb(Base):
    __tablename__ = "engine_vector_db"
    
    id = Column(Integer, primary_key=True, index=True)
    engine_id = Column(Integer, ForeignKey("chat_engine.id"), nullable=False)
    vector_database_id = Column(Integer, ForeignKey("vector_database.id"), nullable=False)
    priority = Column(Integer, default=0)
    
    # Relationships
    engine = relationship("ChatEngine", back_populates="engine_vector_dbs")
    vector_database = relationship("VectorDatabase", back_populates="engine_associations")

class ApiKey(Base):
    __tablename__ = "api_key"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    last_used = Column(DateTime, nullable=True) 