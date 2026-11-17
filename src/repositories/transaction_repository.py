from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from src.domain.transaction import Transaction, TransactionType
from src.repositories.models import TransactionModel


class TransactionRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, transaction: Transaction) -> Transaction:
        model = TransactionModel(
            id=str(transaction.id),
            source_account_id=str(transaction.source_account_id),
            destination_account_id=str(transaction.destination_account_id),
            amount=transaction.amount,
            type=transaction.type,
            created_at=transaction.created_at,
        )
        self.session.add(model)
        self.session.flush()
        return transaction

    def get_statement(
        self,
        account_id: UUID,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        transaction_type: Optional[TransactionType] = None,
    ) -> List[Transaction]:
        str_id = str(account_id)

        # A transação pertence à conta se ela for a origem (DEBIT) ou destino (CREDIT)
        conditions = [
            or_(
                and_(TransactionModel.source_account_id == str_id, TransactionModel.type == TransactionType.DEBIT),
                and_(TransactionModel.destination_account_id == str_id, TransactionModel.type == TransactionType.CREDIT),
            )
        ]

        if start_date:
            conditions.append(TransactionModel.created_at >= start_date)
        if end_date:
            conditions.append(TransactionModel.created_at <= end_date)
        if transaction_type:
            conditions.append(TransactionModel.type == transaction_type)

        query = (
            self.session.query(TransactionModel)
            .filter(*conditions)
            .order_by(TransactionModel.created_at.desc())
        )

        results = []
        for m in query.all():
            tx = Transaction(
                source_account_id=UUID(m.source_account_id),
                destination_account_id=UUID(m.destination_account_id),
                amount=Decimal(str(m.amount)),
                type=m.type,
                id=UUID(m.id),
                created_at=m.created_at,
            )
            results.append(tx)
        return results
