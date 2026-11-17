from datetime import datetime
from decimal import Decimal
from typing import Generator, Optional
from uuid import UUID
import os

from fastapi import FastAPI, Depends, HTTPException, Header, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.controllers.schemas import (
    CreateAccountRequest,
    AccountResponse,
    TransferRequest,
    TransferResponse,
    StatementResponse,
    TransactionItemResponse,
)
from src.domain.exceptions import (
    AccountNotFoundError,
    AntiFraudRejectedError,
    InsufficientFundsError,
    InvalidAmountError,
    InvalidDocumentError,
    KycValidationError,
    SelfTransferNotAllowedError,
)
from src.domain.transaction import TransactionType
from src.repositories.models import Base
from src.services.wallet_service import WalletService
from src.services.anti_fraud_client import AntiFraudClient
from src.services.external_clients import KycValidationClient

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./wallet.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_anti_fraud_client() -> AntiFraudClient:
    return AntiFraudClient()


def get_kyc_client() -> KycValidationClient:
    return KycValidationClient()


def get_wallet_service(
    db: Session = Depends(get_db),
    anti_fraud: AntiFraudClient = Depends(get_anti_fraud_client),
    kyc: KycValidationClient = Depends(get_kyc_client),
) -> WalletService:
    return WalletService(session=db, anti_fraud_client=anti_fraud, kyc_client=kyc)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wallet API - Microsserviço Financeiro",
        description="API REST de Carteira Digital, Conciliação e Transferências com Alta Resiliência",
        version="1.0.0",
    )

    # Handlers para tradução de exceções de domínio em códigos de status HTTP apropriados
    @app.exception_handler(AccountNotFoundError)
    async def account_not_found_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(InsufficientFundsError)
    async def insufficient_funds_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)})

    @app.exception_handler(SelfTransferNotAllowedError)
    async def self_transfer_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(InvalidAmountError)
    async def invalid_amount_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(InvalidDocumentError)
    async def invalid_document_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_400_BAD_REQUEST, content={"detail": str(exc)})

    @app.exception_handler(AntiFraudRejectedError)
    async def anti_fraud_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)})

    @app.exception_handler(KycValidationError)
    async def kyc_validation_handler(request, exc):
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(exc)})

    @app.post("/accounts", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
    def create_account(
        payload: CreateAccountRequest,
        service: WalletService = Depends(get_wallet_service),
    ):
        account = service.create_account(
            document_number=payload.document_number,
            holder_name=payload.holder_name,
            initial_balance=payload.initial_balance,
        )
        return AccountResponse(
            id=account.id,
            document_number=account.document_number,
            holder_name=account.holder_name,
            balance=account.balance,
            created_at=account.created_at,
        )

    @app.get("/accounts/{account_id}", response_model=AccountResponse)
    def get_account(
        account_id: UUID,
        service: WalletService = Depends(get_wallet_service),
    ):
        account = service.get_account(account_id)
        return AccountResponse(
            id=account.id,
            document_number=account.document_number,
            holder_name=account.holder_name,
            balance=account.balance,
            created_at=account.created_at,
        )

    @app.post("/transfers", response_model=TransferResponse, status_code=status.HTTP_200_OK)
    def transfer(
        payload: TransferRequest,
        idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
        service: WalletService = Depends(get_wallet_service),
    ):
        result = service.transfer(
            source_account_id=payload.source_account_id,
            destination_account_id=payload.destination_account_id,
            amount=payload.amount,
            idempotency_key=idempotency_key,
        )
        return TransferResponse(
            transaction_id=UUID(result["transaction_id"]),
            source_account_id=UUID(result["source_account_id"]),
            destination_account_id=UUID(result["destination_account_id"]),
            amount=Decimal(result["amount"]),
            source_balance=Decimal(result["source_balance"]),
            destination_balance=Decimal(result["destination_balance"]),
            created_at=result["created_at"],
            idempotent_replay=result["idempotent_replay"],
        )

    @app.get("/accounts/{account_id}/statement", response_model=StatementResponse)
    def get_statement(
        account_id: UUID,
        start_date: Optional[datetime] = Query(None),
        end_date: Optional[datetime] = Query(None),
        type: Optional[TransactionType] = Query(None),
        service: WalletService = Depends(get_wallet_service),
    ):
        account = service.get_account(account_id)
        transactions = service.get_statement(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=type,
        )
        items = [
            TransactionItemResponse(
                id=tx.id,
                source_account_id=tx.source_account_id,
                destination_account_id=tx.destination_account_id,
                amount=tx.amount,
                type=tx.type,
                created_at=tx.created_at,
            )
            for tx in transactions
        ]
        return StatementResponse(
            account_id=account.id,
            current_balance=account.balance,
            transactions=items,
        )

    return app


app = create_app()
