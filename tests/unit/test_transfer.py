import pytest
from decimal import Decimal
from uuid import uuid4
from src.domain.account import Account
from src.domain.transaction import (
    Transaction,
    TransactionType,
    execute_transfer,
)
from src.domain.exceptions import (
    InsufficientFundsError,
    InvalidAmountError,
    SelfTransferNotAllowedError,
)


def test_should_execute_successful_transfer_between_two_accounts():
    # Arrange
    source = Account("111.111.111-11", "Origem", Decimal("100.00"))
    dest = Account("222.222.222-22", "Destino", Decimal("50.00"))
    transfer_amount = Decimal("30.00")

    # Act
    debit_tx, credit_tx = execute_transfer(
        source_account=source,
        destination_account=dest,
        amount=transfer_amount
    )

    # Assert
    assert source.balance == Decimal("70.00")
    assert dest.balance == Decimal("80.00")

    assert debit_tx.source_account_id == source.id
    assert debit_tx.destination_account_id == dest.id
    assert debit_tx.amount == transfer_amount
    assert debit_tx.type == TransactionType.DEBIT

    assert credit_tx.source_account_id == source.id
    assert credit_tx.destination_account_id == dest.id
    assert credit_tx.amount == transfer_amount
    assert credit_tx.type == TransactionType.CREDIT


def test_should_fail_transfer_when_source_has_insufficient_funds():
    source = Account("111.111.111-11", "Origem", Decimal("20.00"))
    dest = Account("222.222.222-22", "Destino", Decimal("50.00"))

    with pytest.raises(InsufficientFundsError, match="Saldo insuficiente para a operação"):
        execute_transfer(source, dest, Decimal("30.00"))

    # Saldos devem permanecer inalterados
    assert source.balance == Decimal("20.00")
    assert dest.balance == Decimal("50.00")


def test_should_fail_transfer_when_source_and_destination_are_the_same():
    account = Account("111.111.111-11", "Mesma Conta", Decimal("100.00"))

    with pytest.raises(SelfTransferNotAllowedError, match="Transferência para a mesma conta não permitida"):
        execute_transfer(account, account, Decimal("10.00"))

    assert account.balance == Decimal("100.00")


def test_should_fail_transfer_when_amount_is_zero_or_negative():
    source = Account("111.111.111-11", "Origem", Decimal("100.00"))
    dest = Account("222.222.222-22", "Destino", Decimal("50.00"))

    with pytest.raises(InvalidAmountError, match="Valor de transferência deve ser positivo"):
        execute_transfer(source, dest, Decimal("0.00"))

    with pytest.raises(InvalidAmountError, match="Valor de transferência deve ser positivo"):
        execute_transfer(source, dest, Decimal("-10.00"))

    assert source.balance == Decimal("100.00")
    assert dest.balance == Decimal("50.00")
