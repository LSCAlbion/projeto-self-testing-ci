from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from src.domain.transaction import TransactionType


class CreateAccountRequest(BaseModel):
    document_number: str = Field(..., min_length=3, max_length=20, description="CPF ou CNPJ do titular")
    holder_name: str = Field(..., min_length=2, max_length=120, description="Nome completo do titular")
    initial_balance: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Saldo inicial da conta")


class AccountResponse(BaseModel):
    id: UUID
    document_number: str
    holder_name: str
    balance: Decimal
    created_at: datetime


class TransferRequest(BaseModel):
    source_account_id: UUID = Field(..., description="ID da conta debitada")
    destination_account_id: UUID = Field(..., description="ID da conta creditada")
    amount: Decimal = Field(..., gt=Decimal("0.00"), description="Valor financeiro a transferir")


class TransferResponse(BaseModel):
    transaction_id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    source_balance: Decimal
    destination_balance: Decimal
    created_at: str
    idempotent_replay: bool


class TransactionItemResponse(BaseModel):
    id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    type: TransactionType
    created_at: datetime


class StatementResponse(BaseModel):
    account_id: UUID
    current_balance: Decimal
    transactions: List[TransactionItemResponse]
