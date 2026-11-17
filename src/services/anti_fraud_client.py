import os
from decimal import Decimal
from typing import Dict, Any
from uuid import UUID
import httpx
from src.domain.exceptions import AntiFraudRejectedError


class AntiFraudClient:
    """Cliente HTTP responsável por integrar com o serviço fictício de anti-fraude."""

    def __init__(self, base_url: str = "https://api.gateway-antifraude-ficticio.local"):
        self.base_url = base_url

    def notify_transfer(
        self,
        transaction_id: UUID,
        source_account_id: UUID,
        destination_account_id: UUID,
        amount: Decimal,
    ) -> Dict[str, Any]:
        """
        Notifica o gateway externo de anti-fraude via webhook/HTTP POST.
        Em ambiente de teste/carga (MOCK_EXTERNAL_SERVICES=true), responde localmente com sucesso.
        """
        if os.getenv("MOCK_EXTERNAL_SERVICES", "false").lower() == "true":
            return {"status": "APPROVED", "risk_level": "LOW", "transaction_id": str(transaction_id)}

        payload = {
            "transaction_id": str(transaction_id),
            "source_account_id": str(source_account_id),
            "destination_account_id": str(destination_account_id),
            "amount": float(amount),
        }
        url = f"{self.base_url}/v1/notify"
        
        try:
            with httpx.Client(timeout=3.0) as client:
                response = client.post(url, json=payload)
                if response.status_code == 403:
                    raise AntiFraudRejectedError("Transferência bloqueada por suspeita de fraude")
                return response.json()
        except httpx.RequestError as exc:
            # Fallback seguro ou registro de log para o gateway fictício
            return {"status": "ACK_OFFLINE", "transaction_id": str(transaction_id)}
