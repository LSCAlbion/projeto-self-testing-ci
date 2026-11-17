from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from sqlalchemy import (
    Column,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    Enum as SQLEnum,
    Integer,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from src.domain.transaction import TransactionType

Base = declarative_base()


class AccountModel(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_number = Column(String(20), nullable=False)
    holder_name = Column(String(120), nullable=False)
    balance = Column(Numeric(precision=18, scale=2), nullable=False, default=0.0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class TransactionModel(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source_account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False)
    destination_account_id = Column(String(36), ForeignKey("accounts.id"), nullable=False)
    amount = Column(Numeric(precision=18, scale=2), nullable=False)
    type = Column(SQLEnum(TransactionType), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"

    key = Column(String(100), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_body = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


def create_sqlite_in_memory_engine():
    """Cria engine SQLite em memória para isolamento de testes de integração."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine


def get_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)
