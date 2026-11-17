from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4
from src.domain.exceptions import (
    InsufficientFundsError,
    InvalidAmountError,
    InvalidDocumentError,
)


@dataclass
class Account:
    document_number: str
    holder_name: str
    initial_balance: Decimal = Decimal("0.00")
    id: UUID = field(default_factory=uuid4)
    balance: Decimal = field(init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.document_number or not self.document_number.strip():
            raise InvalidDocumentError("Documento do titular é obrigatório")

        if self.initial_balance < Decimal("0.00"):
            raise InvalidAmountError("Saldo inicial não pode ser negativo")

        self.balance = self.initial_balance

    def deposit(self, amount: Decimal) -> None:
        if amount <= Decimal("0.00"):
            raise InvalidAmountError("Valor de depósito deve ser positivo")
        self.balance += amount

    def withdraw(self, amount: Decimal) -> None:
        if amount <= Decimal("0.00"):
            raise InvalidAmountError("Valor de saque deve ser positivo")
        if self.balance < amount:
            raise InsufficientFundsError("Saldo insuficiente para a operação")
        self.balance -= amount
