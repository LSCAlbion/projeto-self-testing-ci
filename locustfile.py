from decimal import Decimal
from uuid import uuid4
from locust import HttpUser, task, between


class WalletTransferUser(HttpUser):
    """
    Simula usuários concorrentes realizando transferências financeiras simultâneas.
    """
    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Inicializa duas contas para o fluxo de transferências se necessário."""
        # Cria Conta Origem
        doc_src = str(uuid4().int)[:11]
        resp_src = self.client.post(
            "/accounts",
            json={
                "document_number": doc_src,
                "holder_name": f"User {doc_src}",
                "initial_balance": "50000.00",
            },
        )
        if resp_src.status_code == 201:
            self.source_id = resp_src.json()["id"]
        else:
            self.source_id = None

        # Cria Conta Destino
        doc_dst = str(uuid4().int)[:11]
        resp_dst = self.client.post(
            "/accounts",
            json={
                "document_number": doc_dst,
                "holder_name": f"User {doc_dst}",
                "initial_balance": "1000.00",
            },
        )
        if resp_dst.status_code == 201:
            self.dest_id = resp_dst.json()["id"]
        else:
            self.dest_id = None

    @task(3)
    def transfer_funds(self):
        """Dispara transferência financeira com concorrência e chave de idempotência."""
        if not self.source_id or not self.dest_id:
            return

        idempotency_key = str(uuid4())
        payload = {
            "source_account_id": self.source_id,
            "destination_account_id": self.dest_id,
            "amount": "10.00",
        }
        headers = {"Idempotency-Key": idempotency_key}

        with self.client.post(
            "/transfers",
            json=payload,
            headers=headers,
            catch_response=True,
        ) as response:
            # Respostas válidas são 200 (transferência ok ou replay) e 422 (saldo insuficiente)
            if response.status_code in [200, 422]:
                response.success()
            else:
                response.failure(f"Erro inesperado no servidor: {response.status_code}")

    @task(1)
    def check_statement(self):
        """Consulta extrato da conta de origem concorrentemente."""
        if not self.source_id:
            return
        self.client.get(f"/accounts/{self.source_id}/statement")
