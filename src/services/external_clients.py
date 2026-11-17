import os
from typing import Dict, Any
import httpx
from src.domain.exceptions import KycValidationError


class KycValidationClient:
    """Cliente para serviço externo de validação cadastral (KYC)."""

    def __init__(self, base_url: str = "https://api.kyc-service.local"):
        self.base_url = base_url

    def validate_document(self, document_number: str) -> Dict[str, Any]:
        """
        Consulta serviço externo cadastral.
        Em ambiente de teste/carga (MOCK_EXTERNAL_SERVICES=true), responde localmente.
        """
        if os.getenv("MOCK_EXTERNAL_SERVICES", "false").lower() == "true":
            return {"is_valid": True, "score": 950}

        url = f"{self.base_url}/v1/validate"
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.post(url, json={"document": document_number})
                data = resp.json()
                if not data.get("is_valid", False):
                    raise KycValidationError(f"Documento {document_number} reprovado na verificação cadastral")
                return data
        except httpx.RequestError:
            raise KycValidationError("Serviço de validação cadastral indisponível")


class ExchangeRateClient:
    """Cliente para serviço externo de taxas de câmbio."""

    def __init__(self, base_url: str = "https://api.cambio-service.local"):
        self.base_url = base_url

    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """
        Obtém cotação entre moedas.
        Nos testes, este método é substituído por um STUB com valores fixos pré-programados.
        """
        url = f"{self.base_url}/v1/rates?from={from_currency}&to={to_currency}"
        try:
            with httpx.Client(timeout=3.0) as client:
                resp = client.get(url)
                return float(resp.json().get("rate", 1.0))
        except httpx.RequestError:
            return 1.0
