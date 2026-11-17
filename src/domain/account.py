from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from typing import Optional
from uuid import UUID, uuid4
from src.domain.exceptions import (
    InsufficientFundsError,
    InvalidAmountError,
    InvalidDocumentError,
)

TWO_PLACES = Decimal("0.01")


def quantize_amount(value: Decimal) -> Decimal:
    """Padroniza valores monetários com precisão de duas casas decimais."""
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_EVEN)


@dataclass
class Account:
    """Entidade de domínio representativa de uma conta bancária digital."""
    document_number: str
    holder_name: str
    initial_balance: Decimal = Decimal("0.00")
    id: UUID = field(default_factory=uuid4)
    balance: Decimal = field(init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        self._validate_and_sanitize()
        self.balance = quantize_amount(self.initial_balance)

    def _validate_and_sanitize(self) -> None:
        if not self.document_number or not self.document_number.strip():
            raise InvalidDocumentError("Documento do titular é obrigatório")

        # Hotfix: normaliza removendo caracteres não numéricos (pontos, traços, etc.)
        cleaned_doc = "".join(filter(str.isdigit, self.document_number))
        self.document_number = cleaned_doc if cleaned_doc else self.document_number.strip()
        self.holder_name = self.holder_name.strip() if self.holder_name else ""

        if self.initial_balance < Decimal("0.00"):
            raise InvalidAmountError("Saldo inicial não pode ser negativo")

    def deposit(self, amount: Decimal) -> None:
        """Adiciona saldo à conta com validação de valor estritamente positivo."""
        if amount <= Decimal("0.00"):
            raise InvalidAmountError("Valor de depósito deve ser positivo")
        self.balance = quantize_amount(self.balance + amount)

    def withdraw(self, amount: Decimal) -> None:
        """Debita saldo da conta garantindo ausência de saldo negativo."""
        if amount <= Decimal("0.00"):
            raise InvalidAmountError("Valor de saque deve ser positivo")
        normalized_amount = quantize_amount(amount)
        if self.balance < normalized_amount:
            raise InsufficientFundsError("Saldo insuficiente para a operação")
        self.balance -= normalized_amount
