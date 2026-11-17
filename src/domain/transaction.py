from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Tuple
from uuid import UUID, uuid4
from src.domain.account import Account, quantize_amount
from src.domain.exceptions import (
    InvalidAmountError,
    SelfTransferNotAllowedError,
)


class TransactionType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


@dataclass
class Transaction:
    source_account_id: UUID
    destination_account_id: UUID
    amount: Decimal
    type: TransactionType
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        self.amount = quantize_amount(self.amount)


def execute_transfer(
    source_account: Account,
    destination_account: Account,
    amount: Decimal,
) -> Tuple[Transaction, Transaction]:
    """
    Executa a transferência entre duas contas no domínio com atomicidade lógica.
    Retorna a tupla (transação_de_débito, transação_de_crédito).
    """
    if source_account.id == destination_account.id:
        raise SelfTransferNotAllowedError("Transferência para a mesma conta não permitida")

    if amount <= Decimal("0.00"):
        raise InvalidAmountError("Valor de transferência deve ser positivo")

    normalized_amount = quantize_amount(amount)

    # Débito da origem (lançará InsufficientFundsError se saldo insuficiente)
    source_account.withdraw(normalized_amount)
    # Crédito no destino
    destination_account.deposit(normalized_amount)

    debit_tx = Transaction(
        source_account_id=source_account.id,
        destination_account_id=destination_account.id,
        amount=normalized_amount,
        type=TransactionType.DEBIT,
    )

    credit_tx = Transaction(
        source_account_id=source_account.id,
        destination_account_id=destination_account.id,
        amount=normalized_amount,
        type=TransactionType.CREDIT,
    )

    return debit_tx, credit_tx
