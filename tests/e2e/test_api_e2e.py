import pytest
from decimal import Decimal
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import Mock

from src.controllers.api import app, get_db, get_anti_fraud_client, get_kyc_client
from src.repositories.models import Base, create_sqlite_in_memory_engine, get_session_factory
from src.services.anti_fraud_client import AntiFraudClient
from src.services.external_clients import KycValidationClient
from src.domain.exceptions import KycValidationError


@pytest.fixture
def client_e2e():
    """
    Fixture E2E: Configura banco SQLite em memória isolado e cliente HTTP
    para disparar requisições REST reais contra o app FastAPI.
    """
    engine = create_sqlite_in_memory_engine()
    TestingSessionFactory = get_session_factory(engine)

    def override_get_db():
        db = TestingSessionFactory()
        try:
            yield db
        finally:
            db.close()

    mock_kyc = Mock(spec=KycValidationClient)
    def validate_doc(doc):
        if "000.000" in doc:
            raise KycValidationError("Documento reprovado no KYC")
        return {"is_valid": True, "score": 900}
    mock_kyc.validate_document.side_effect = validate_doc

    mock_anti_fraud = Mock(spec=AntiFraudClient)
    mock_anti_fraud.notify_transfer.return_value = {"status": "APPROVED"}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_kyc_client] = lambda: mock_kyc
    app.dependency_overrides[get_anti_fraud_client] = lambda: mock_anti_fraud

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def test_complete_e2e_wallet_lifecycle(client_e2e):
    """
    Teste E2E Completo:
    1. Criação de duas contas com saldo inicial via HTTP POST /accounts.
    2. Consulta das contas via HTTP GET /accounts/{id}.
    3. Transferência atômica via HTTP POST /transfers com cabeçalho Idempotency-Key.
    4. Replay com mesma Idempotency-Key (garantindo ausência de duplicidade).
    5. Tentativa de transferência com saldo insuficiente (validando HTTP 422).
    6. Consulta de extrato com filtros por tipo e conferência de saldos finais.
    """
    # 1. Cria Conta Origem
    resp_acc1 = client_e2e.post(
        "/accounts",
        json={
            "document_number": "111.222.333-44",
            "holder_name": "Alice Origem",
            "initial_balance": "1000.00",
        },
    )
    assert resp_acc1.status_code == 201
    acc1_data = resp_acc1.json()
    acc1_id = acc1_data["id"]
    assert acc1_data["balance"] == "1000.00"

    # 1b. Cria Conta Destino
    resp_acc2 = client_e2e.post(
        "/accounts",
        json={
            "document_number": "555.666.777-88",
            "holder_name": "Bob Destino",
            "initial_balance": "200.00",
        },
    )
    assert resp_acc2.status_code == 201
    acc2_data = resp_acc2.json()
    acc2_id = acc2_data["id"]
    assert acc2_data["balance"] == "200.00"

    # 2. Consulta Conta Origem
    get_acc1 = client_e2e.get(f"/accounts/{acc1_id}")
    assert get_acc1.status_code == 200
    assert get_acc1.json()["holder_name"] == "Alice Origem"

    # 3. Executa Transferência de 350.00 de Alice para Bob
    idempotency_key = str(uuid4())
    transfer_payload = {
        "source_account_id": acc1_id,
        "destination_account_id": acc2_id,
        "amount": "350.00",
    }
    resp_transfer = client_e2e.post(
        "/transfers",
        json=transfer_payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    assert resp_transfer.status_code == 200
    tx_data = resp_transfer.json()
    assert tx_data["amount"] == "350.00"
    assert tx_data["source_balance"] == "650.00"
    assert tx_data["destination_balance"] == "550.00"
    assert tx_data["idempotent_replay"] is False

    # 4. Replay com a mesma Idempotency-Key
    resp_replay = client_e2e.post(
        "/transfers",
        json=transfer_payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    assert resp_replay.status_code == 200
    replay_data = resp_replay.json()
    assert replay_data["transaction_id"] == tx_data["transaction_id"]
    assert replay_data["idempotent_replay"] is True

    # 5. Tentativa com Saldo Insuficiente (tentando transferir 800.00 tendo apenas 650.00)
    resp_insufficient = client_e2e.post(
        "/transfers",
        json={
            "source_account_id": acc1_id,
            "destination_account_id": acc2_id,
            "amount": "800.00",
        },
    )
    assert resp_insufficient.status_code == 422
    assert "Saldo insuficiente" in resp_insufficient.json()["detail"]

    # 6. Extrato da Conta de Alice (deve registrar o débito de 350.00)
    resp_stmt = client_e2e.get(f"/accounts/{acc1_id}/statement?type=DEBIT")
    assert resp_stmt.status_code == 200
    stmt_data = resp_stmt.json()
    assert stmt_data["current_balance"] == "650.00"
    assert len(stmt_data["transactions"]) == 1
    assert stmt_data["transactions"][0]["amount"] == "350.00"
    assert stmt_data["transactions"][0]["type"] == "DEBIT"

    # Extrato da Conta de Bob (deve registrar o crédito de 350.00)
    resp_stmt_bob = client_e2e.get(f"/accounts/{acc2_id}/statement?type=CREDIT")
    assert resp_stmt_bob.status_code == 200
    stmt_bob = resp_stmt_bob.json()
    assert stmt_bob["current_balance"] == "550.00"
    assert len(stmt_bob["transactions"]) == 1
    assert stmt_bob["transactions"][0]["amount"] == "350.00"
    assert stmt_bob["transactions"][0]["type"] == "CREDIT"


def test_e2e_error_scenarios(client_e2e):
    """Valida cenários de erro e status HTTP 404, 400 e 422."""
    # Conta inexistente
    non_existent = str(uuid4())
    resp_404 = client_e2e.get(f"/accounts/{non_existent}")
    assert resp_404.status_code == 404

    # Auto-transferência (mesma conta de origem e destino)
    acc = client_e2e.post(
        "/accounts",
        json={"document_number": "123.456.789-10", "holder_name": "Carl", "initial_balance": "100.00"},
    ).json()
    resp_self = client_e2e.post(
        "/transfers",
        json={"source_account_id": acc["id"], "destination_account_id": acc["id"], "amount": "10.00"},
    )
    assert resp_self.status_code == 400
    assert "mesma conta" in resp_self.json()["detail"]

    # Validação de KYC com reprovação
    resp_kyc_fail = client_e2e.post(
        "/accounts",
        json={"document_number": "000.000.000-00", "holder_name": "Reprovado", "initial_balance": "100.00"},
    )
    assert resp_kyc_fail.status_code == 422
