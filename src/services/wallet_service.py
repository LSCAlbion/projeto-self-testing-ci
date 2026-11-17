import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session

from src.domain.account import Account, quantize_amount
from src.domain.transaction import Transaction, TransactionType, execute_transfer
from src.domain.exceptions import (
    AccountNotFoundError,
    InsufficientFundsError,
    SelfTransferNotAllowedError,
    InvalidAmountError,
)
from src.repositories.account_repository import AccountRepository
from src.repositories.transaction_repository import TransactionRepository
from src.repositories.idempotency_repository import IdempotencyRepository
from src.services.anti_fraud_client import AntiFraudClient
from src.services.external_clients import KycValidationClient


class WalletService:
    def __init__(
        self,
        session: Session,
        anti_fraud_client: Optional[AntiFraudClient] = None,
        kyc_client: Optional[KycValidationClient] = None,
    ):
        self.session = session
        self.account_repo = AccountRepository(session)
        self.transaction_repo = TransactionRepository(session)
        self.idempotency_repo = IdempotencyRepository(session)
        self.anti_fraud_client = anti_fraud_client or AntiFraudClient()
        self.kyc_client = kyc_client or KycValidationClient()

    def create_account(
        self,
        document_number: str,
        holder_name: str,
        initial_balance: Decimal = Decimal("0.00"),
    ) -> Account:
        """Cria nova conta bancária após validação cadastral (KYC)."""
        # Validação cadastral externa (alimentada por STUB nos testes)
        self.kyc_client.validate_document(document_number)

        account = Account(
            document_number=document_number,
            holder_name=holder_name,
            initial_balance=initial_balance,
        )
        self.account_repo.save(account)
        self.session.commit()
        return account

    def get_account(self, account_id: UUID) -> Account:
        """Consulta dados e saldo da conta."""
        return self.account_repo.get_by_id_or_fail(account_id)

    def transfer(
        self,
        source_account_id: UUID,
        destination_account_id: UUID,
        amount: Decimal,
        idempotency_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executa transferência atômica com concorrência segura, idempotência e anti-fraude.
        """
        amount = quantize_amount(amount)

        # 1. Tratamento de Idempotência
        request_hash = ""
        if idempotency_key:
            raw_hash_data = f"{source_account_id}:{destination_account_id}:{amount}"
            request_hash = hashlib.sha256(raw_hash_data.encode()).hexdigest()
            existing_record = self.idempotency_repo.get(idempotency_key)
            if existing_record:
                data = json.loads(existing_record.response_body)
                data["idempotent_replay"] = True
                return data

        # 2. Concorrência: ordenamento de IDs para travar linhas na mesma sequência e prevenir deadlocks
        ordered_ids = sorted([source_account_id, destination_account_id])
        first_id, second_id = ordered_ids[0], ordered_ids[1]

        # Inicia bloco transacional
        try:
            # Trava as duas contas
            self.account_repo.get_by_id_or_fail(first_id, for_update=True)
            self.account_repo.get_by_id_or_fail(second_id, for_update=True)

            source_acc = self.account_repo.get_by_id_or_fail(source_account_id)
            dest_acc = self.account_repo.get_by_id_or_fail(destination_account_id)

            # 3. Execução das regras de negócio no domínio
            debit_tx, credit_tx = execute_transfer(
                source_account=source_acc,
                destination_account=dest_acc,
                amount=amount,
            )

            # 4. Atualização de saldos no banco de dados
            self.account_repo.save(source_acc)
            self.account_repo.save(dest_acc)

            # 5. Persistência dos registros de transação
            self.transaction_repo.save(debit_tx)
            self.transaction_repo.save(credit_tx)

            # 6. Notificação do gateway de anti-fraude (verificado via MOCK nos testes)
            self.anti_fraud_client.notify_transfer(
                transaction_id=debit_tx.id,
                source_account_id=source_acc.id,
                destination_account_id=dest_acc.id,
                amount=amount,
            )

            response_data = {
                "transaction_id": str(debit_tx.id),
                "source_account_id": str(source_acc.id),
                "destination_account_id": str(dest_acc.id),
                "amount": str(amount),
                "source_balance": str(source_acc.balance),
                "destination_balance": str(dest_acc.balance),
                "created_at": debit_tx.created_at.isoformat(),
                "idempotent_replay": False,
            }

            # 7. Salva registro de idempotência se chave fornecida
            if idempotency_key:
                self.idempotency_repo.save(
                    key=idempotency_key,
                    request_hash=request_hash,
                    status_code=200,
                    response_body=json.dumps(response_data),
                )

            self.session.commit()
            return response_data

        except Exception:
            self.session.rollback()
            raise

    def get_statement(
        self,
        account_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transaction_type: Optional[TransactionType] = None,
    ) -> List[Transaction]:
        """Consulta o extrato financeiro da conta com filtros."""
        # Garante que a conta existe
        self.account_repo.get_by_id_or_fail(account_id)

        return self.transaction_repo.get_statement(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
        )
