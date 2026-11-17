import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, call
from uuid import uuid4

from src.domain.exceptions import (
    AccountNotFoundError,
    InsufficientFundsError,
    KycValidationError,
    SelfTransferNotAllowedError,
)
from src.domain.transaction import TransactionType
from src.repositories.models import (
    Base,
    create_sqlite_in_memory_engine,
    get_session_factory,
)
from src.services.wallet_service import WalletService
from src.services.anti_fraud_client import AntiFraudClient
from src.services.external_clients import KycValidationClient


@pytest.fixture
def db_session():
    """Fixture que fornece uma sessão limpa em banco de dados SQLite em memória."""
    engine = create_sqlite_in_memory_engine()
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ==============================================================================
# 1. TESTES COM STUB (Validação Cadastral - Dados de Entrada Controlados)
# ==============================================================================

def test_should_create_account_when_kyc_stub_approves_document(db_session):
    """
    STUB: Substitui a chamada de rede externa por um stub que fornece
    uma resposta fixa de aprovação cadastral controlada.
    """
    # Arrange: Configuração do STUB
    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.return_value = {
        "is_valid": True,
        "score": 950,
        "status": "APPROVED",
    }

    wallet_service = WalletService(session=db_session, kyc_client=kyc_stub)

    # Act
    account = wallet_service.create_account(
        document_number="123.456.789-00",
        holder_name="Lucas Stub Test",
        initial_balance=Decimal("250.00"),
    )

    # Assert
    assert account.id is not None
    assert account.balance == Decimal("250.00")
    # Verifica que o serviço foi acionado com o documento esperado
    kyc_stub.validate_document.assert_called_once_with("123.456.789-00")


def test_should_reject_account_creation_when_kyc_stub_rejects_document(db_session):
    """
    STUB: Configura o stub para forçar uma exceção de recusa cadastral,
    garantindo que a conta não seja salva no banco de dados.
    """
    # Arrange: STUB lançando erro
    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.side_effect = KycValidationError("Documento bloqueado por compliance")

    wallet_service = WalletService(session=db_session, kyc_client=kyc_stub)

    # Act & Assert
    with pytest.raises(KycValidationError, match="Documento bloqueado por compliance"):
        wallet_service.create_account(
            document_number="999.999.999-99",
            holder_name="Fraude Fraudulenta",
            initial_balance=Decimal("100.00"),
        )


# ==============================================================================
# 2. TESTES COM MOCK (Gateway Anti-Fraude - Verificação de Saída e Parâmetros)
# ==============================================================================

def test_should_verify_mock_interactions_on_successful_transfer(db_session):
    """
    MOCK: Uso mandatório para verificar chamadas, contagem e parâmetros
    enviados para o serviço externo de anti-fraude.
    """
    # Arrange
    anti_fraud_mock = Mock(spec=AntiFraudClient)
    anti_fraud_mock.notify_transfer.return_value = {"status": "APPROVED", "risk_level": "LOW"}

    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.return_value = {"is_valid": True}

    wallet_service = WalletService(
        session=db_session,
        anti_fraud_client=anti_fraud_mock,
        kyc_client=kyc_stub,
    )

    acc1 = wallet_service.create_account("111.111.111-11", "Conta 1", Decimal("500.00"))
    acc2 = wallet_service.create_account("222.222.222-22", "Conta 2", Decimal("100.00"))

    transfer_amount = Decimal("150.00")
    key = str(uuid4())

    # Act
    result = wallet_service.transfer(
        source_account_id=acc1.id,
        destination_account_id=acc2.id,
        amount=transfer_amount,
        idempotency_key=key,
    )

    # Assert - Saldos atualizados no banco de dados
    updated_acc1 = wallet_service.get_account(acc1.id)
    updated_acc2 = wallet_service.get_account(acc2.id)
    assert updated_acc1.balance == Decimal("350.00")
    assert updated_acc2.balance == Decimal("250.00")

    # Assert do MOCK:
    # 1. Verificar se foi chamado
    assert anti_fraud_mock.notify_transfer.called is True
    # 2. Verificar contagem exata de chamadas
    assert anti_fraud_mock.notify_transfer.call_count == 1
    # 3. Verificar os parâmetros exatos enviados
    args, kwargs = anti_fraud_mock.notify_transfer.call_args
    assert kwargs["source_account_id"] == acc1.id
    assert kwargs["destination_account_id"] == acc2.id
    assert kwargs["amount"] == transfer_amount
    assert kwargs["transaction_id"] is not None


def test_should_not_notify_anti_fraud_when_transfer_fails_due_to_insufficient_funds(db_session):
    """
    MOCK: Garante que o serviço de anti-fraude NUNCA seja notificado
    se a transferência falhar antes da transação ser efetivada.
    """
    # Arrange
    anti_fraud_mock = Mock(spec=AntiFraudClient)
    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.return_value = {"is_valid": True}

    wallet_service = WalletService(
        session=db_session,
        anti_fraud_client=anti_fraud_mock,
        kyc_client=kyc_stub,
    )

    acc1 = wallet_service.create_account("111.111.111-11", "Conta 1", Decimal("50.00"))
    acc2 = wallet_service.create_account("222.222.222-22", "Conta 2", Decimal("100.00"))

    # Act & Assert
    with pytest.raises(InsufficientFundsError):
        wallet_service.transfer(
            source_account_id=acc1.id,
            destination_account_id=acc2.id,
            amount=Decimal("200.00"),
        )

    # O mock do anti-fraude NÃO deve ter sido chamado nenhuma vez
    assert anti_fraud_mock.notify_transfer.call_count == 0


# ==============================================================================
# 3. TESTES DE IDEMPOTÊNCIA
# ==============================================================================

def test_should_ensure_idempotency_when_repeating_same_key(db_session):
    """
    IDEMPOTÊNCIA: Se a requisição com a mesma chave for repetida,
    não debita novamente e retorna a mesma resposta com cache flag.
    """
    # Arrange
    anti_fraud_mock = Mock(spec=AntiFraudClient)
    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.return_value = {"is_valid": True}

    wallet_service = WalletService(
        session=db_session,
        anti_fraud_client=anti_fraud_mock,
        kyc_client=kyc_stub,
    )

    acc1 = wallet_service.create_account("111.111.111-11", "Conta 1", Decimal("300.00"))
    acc2 = wallet_service.create_account("222.222.222-22", "Conta 2", Decimal("50.00"))
    idempotency_key = "idemp-test-unique-key-12345"

    # Primeira execução
    res1 = wallet_service.transfer(
        source_account_id=acc1.id,
        destination_account_id=acc2.id,
        amount=Decimal("100.00"),
        idempotency_key=idempotency_key,
    )
    assert res1["idempotent_replay"] is False
    assert anti_fraud_mock.notify_transfer.call_count == 1

    # Segunda execução com a MESMA chave
    res2 = wallet_service.transfer(
        source_account_id=acc1.id,
        destination_account_id=acc2.id,
        amount=Decimal("100.00"),
        idempotency_key=idempotency_key,
    )

    # Assert
    assert res2["idempotent_replay"] is True
    assert res2["transaction_id"] == res1["transaction_id"]
    # Saldos não devem sofrer novo débito/crédito
    updated_acc1 = wallet_service.get_account(acc1.id)
    updated_acc2 = wallet_service.get_account(acc2.id)
    assert updated_acc1.balance == Decimal("200.00")
    assert updated_acc2.balance == Decimal("150.00")
    # Anti-fraude NÃO deve ser chamado novamente
    assert anti_fraud_mock.notify_transfer.call_count == 1


# ==============================================================================
# 4. TESTES DE EXTRATO COM FILTROS
# ==============================================================================

def test_should_filter_statement_by_type_and_date(db_session):
    kyc_stub = Mock(spec=KycValidationClient)
    kyc_stub.validate_document.return_value = {"is_valid": True}
    anti_fraud_mock = Mock(spec=AntiFraudClient)

    wallet_service = WalletService(
        session=db_session,
        anti_fraud_client=anti_fraud_mock,
        kyc_client=kyc_stub,
    )

    acc1 = wallet_service.create_account("111.111.111-11", "Conta 1", Decimal("1000.00"))
    acc2 = wallet_service.create_account("222.222.222-22", "Conta 2", Decimal("500.00"))

    # Realiza duas transferências
    wallet_service.transfer(acc1.id, acc2.id, Decimal("50.00"))
    wallet_service.transfer(acc2.id, acc1.id, Decimal("30.00"))

    # Extrato completo da conta 1 (1 débito de 50 e 1 crédito de 30)
    full_stmt = wallet_service.get_statement(acc1.id)
    assert len(full_stmt) == 2

    # Filtro apenas por DEBIT
    debit_only = wallet_service.get_statement(acc1.id, transaction_type=TransactionType.DEBIT)
    assert len(debit_only) == 1
    assert debit_only[0].amount == Decimal("50.00")

    # Filtro apenas por CREDIT
    credit_only = wallet_service.get_statement(acc1.id, transaction_type=TransactionType.CREDIT)
    assert len(credit_only) == 1
    assert credit_only[0].amount == Decimal("30.00")
