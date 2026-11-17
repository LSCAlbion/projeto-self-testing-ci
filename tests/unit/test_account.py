import pytest
from decimal import Decimal
from uuid import uuid4
from src.domain.account import Account
from src.domain.exceptions import (
    InsufficientFundsError,
    InvalidAmountError,
    InvalidDocumentError,
)


def test_should_create_account_with_valid_initial_balance():
    # Arrange
    doc = "123.456.789-00"
    holder = "Lucas Dev"
    initial_balance = Decimal("100.00")

    # Act
    account = Account(
        document_number=doc,
        holder_name=holder,
        initial_balance=initial_balance
    )

    # Assert
    assert account.id is not None
    assert account.document_number == doc
    assert account.holder_name == holder
    assert account.balance == initial_balance
    assert account.created_at is not None


def test_should_not_create_account_with_negative_initial_balance():
    with pytest.raises(InvalidAmountError, match="Saldo inicial não pode ser negativo"):
        Account(
            document_number="123.456.789-00",
            holder_name="Lucas Dev",
            initial_balance=Decimal("-10.00")
        )


def test_should_not_create_account_without_document():
    with pytest.raises(InvalidDocumentError, match="Documento do titular é obrigatório"):
        Account(
            document_number="",
            holder_name="Lucas Dev",
            initial_balance=Decimal("0.00")
        )


def test_should_deposit_positive_amount():
    account = Account(
        document_number="123.456.789-00",
        holder_name="Lucas Dev",
        initial_balance=Decimal("50.00")
    )
    account.deposit(Decimal("25.50"))
    assert account.balance == Decimal("75.50")


def test_should_not_deposit_zero_or_negative_amount():
    account = Account(
        document_number="123.456.789-00",
        holder_name="Lucas Dev",
        initial_balance=Decimal("50.00")
    )
    with pytest.raises(InvalidAmountError, match="Valor de depósito deve ser positivo"):
        account.deposit(Decimal("0.00"))

    with pytest.raises(InvalidAmountError, match="Valor de depósito deve ser positivo"):
        account.deposit(Decimal("-10.00"))


def test_should_withdraw_when_balance_is_sufficient():
    account = Account(
        document_number="123.456.789-00",
        holder_name="Lucas Dev",
        initial_balance=Decimal("100.00")
    )
    account.withdraw(Decimal("40.00"))
    assert account.balance == Decimal("60.00")


def test_should_not_withdraw_when_balance_is_insufficient():
    account = Account(
        document_number="123.456.789-00",
        holder_name="Lucas Dev",
        initial_balance=Decimal("30.00")
    )
    with pytest.raises(InsufficientFundsError, match="Saldo insuficiente para a operação"):
        account.withdraw(Decimal("50.00"))


def test_should_not_withdraw_zero_or_negative_amount():
    account = Account(
        document_number="123.456.789-00",
        holder_name="Lucas Dev",
        initial_balance=Decimal("100.00")
    )
    with pytest.raises(InvalidAmountError, match="Valor de saque deve ser positivo"):
        account.withdraw(Decimal("0.00"))

    with pytest.raises(InvalidAmountError, match="Valor de saque deve ser positivo"):
        account.withdraw(Decimal("-5.00"))
