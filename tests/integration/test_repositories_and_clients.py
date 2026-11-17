import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4
import httpx

from src.domain.account import Account
from src.domain.exceptions import (
    AccountNotFoundError,
    AntiFraudRejectedError,
    KycValidationError,
)
from src.domain.transaction import Transaction, TransactionType
from src.repositories.models import (
    Base,
    create_sqlite_in_memory_engine,
    get_session_factory,
)
from src.repositories.account_repository import AccountRepository
from src.repositories.transaction_repository import TransactionRepository
from src.services.anti_fraud_client import AntiFraudClient
from src.services.external_clients import KycValidationClient, ExchangeRateClient


@pytest.fixture
def repo_session():
    engine = create_sqlite_in_memory_engine()
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_account_repository_list_and_not_found(repo_session):
    repo = AccountRepository(repo_session)
    acc1 = Account("111", "Lucas", Decimal("100.00"))
    acc2 = Account("222", "Carlos", Decimal("200.00"))
    repo.save(acc1)
    repo.save(acc2)
    repo_session.commit()

    all_accounts = repo.list_all()
    assert len(all_accounts) == 2

    # Busca inexistente
    non_existent_id = uuid4()
    assert repo.get_by_id(non_existent_id) is None
    with pytest.raises(AccountNotFoundError):
        repo.get_by_id_or_fail(non_existent_id)


def test_transaction_repository_date_range_filters(repo_session):
    acc_repo = AccountRepository(repo_session)
    tx_repo = TransactionRepository(repo_session)

    acc1 = Account("111", "Lucas", Decimal("500.00"))
    acc2 = Account("222", "Carlos", Decimal("100.00"))
    acc_repo.save(acc1)
    acc_repo.save(acc2)
    repo_session.commit()

    now = datetime.now(timezone.utc)
    past = now - timedelta(days=2)
    future = now + timedelta(days=2)

    tx1 = Transaction(acc1.id, acc2.id, Decimal("50.00"), TransactionType.DEBIT, created_at=now)
    tx_repo.save(tx1)
    repo_session.commit()

    # Com filtro de data que inclui a transação
    res1 = tx_repo.get_statement(acc1.id, start_date=past, end_date=future)
    assert len(res1) == 1

    # Com filtro de data no futuro que exclui a transação
    res2 = tx_repo.get_statement(acc1.id, start_date=future)
    assert len(res2) == 0


def test_anti_fraud_client_transport_mock(monkeypatch):
    """Testa os fluxos internos do AntiFraudClient simulando respostas HTTP."""
    client = AntiFraudClient(base_url="https://mock-anti-fraud.local")

    # Caso 1: Sucesso HTTP
    def mock_post_success(*args, **kwargs):
        class MockResponse:
            status_code = 200
            def json(self):
                return {"status": "SUCCESS", "id": "123"}
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post_success)
    resp = client.notify_transfer(uuid4(), uuid4(), uuid4(), Decimal("100.00"))
    assert resp["status"] == "SUCCESS"

    # Caso 2: 403 Fraude
    def mock_post_fraud(*args, **kwargs):
        class MockResponse:
            status_code = 403
            def json(self):
                return {"error": "fraud"}
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post_fraud)
    with pytest.raises(AntiFraudRejectedError):
        client.notify_transfer(uuid4(), uuid4(), uuid4(), Decimal("50000.00"))

    # Caso 3: RequestError (fallback offline)
    def mock_post_error(*args, **kwargs):
        raise httpx.RequestError("Network error", request=Mock())

    monkeypatch.setattr(httpx.Client, "post", mock_post_error)
    fallback = client.notify_transfer(uuid4(), uuid4(), uuid4(), Decimal("10.00"))
    assert fallback["status"] == "ACK_OFFLINE"


def test_external_clients_transport_mock(monkeypatch):
    """Testa KycValidationClient e ExchangeRateClient com simulação de HTTP."""
    kyc = KycValidationClient("https://mock-kyc.local")
    exchange = ExchangeRateClient("https://mock-exchange.local")

    # KYC Sucesso
    def mock_kyc_success(*args, **kwargs):
        class MockResponse:
            def json(self):
                return {"is_valid": True}
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_kyc_success)
    assert kyc.validate_document("12345678900")["is_valid"] is True

    # KYC Falha
    def mock_kyc_fail(*args, **kwargs):
        class MockResponse:
            def json(self):
                return {"is_valid": False}
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_kyc_fail)
    with pytest.raises(KycValidationError):
        kyc.validate_document("00000000000")

    # KYC Network Error
    def mock_network_error(*args, **kwargs):
        raise httpx.RequestError("offline", request=Mock())

    monkeypatch.setattr(httpx.Client, "post", mock_network_error)
    with pytest.raises(KycValidationError, match="indisponível"):
        kyc.validate_document("11111111111")

    # Câmbio Sucesso
    def mock_exchange_success(*args, **kwargs):
        class MockResponse:
            def json(self):
                return {"rate": 5.25}
        return MockResponse()

    monkeypatch.setattr(httpx.Client, "get", mock_exchange_success)
    assert exchange.get_rate("USD", "BRL") == 5.25

    # Câmbio Network Error
    monkeypatch.setattr(httpx.Client, "get", mock_network_error)
    assert exchange.get_rate("USD", "BRL") == 1.0
