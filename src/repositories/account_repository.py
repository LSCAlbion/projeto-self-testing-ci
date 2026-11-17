from decimal import Decimal
from typing import Optional, List
from uuid import UUID
from sqlalchemy.orm import Session
from src.domain.account import Account, quantize_amount
from src.domain.exceptions import AccountNotFoundError
from src.repositories.models import AccountModel


class AccountRepository:
    def __init__(self, session: Session):
        self.session = session

    def save(self, account: Account) -> Account:
        model = self.session.query(AccountModel).filter(AccountModel.id == str(account.id)).first()
        if not model:
            model = AccountModel(
                id=str(account.id),
                document_number=account.document_number,
                holder_name=account.holder_name,
                balance=account.balance,
                created_at=account.created_at,
            )
            self.session.add(model)
        else:
            model.balance = account.balance
        self.session.flush()
        return account

    def get_by_id(self, account_id: UUID, for_update: bool = False) -> Optional[Account]:
        query = self.session.query(AccountModel).filter(AccountModel.id == str(account_id))
        if for_update:
            # SQLite ignora com no-op gracioso, bancos relacionais como PostgreSQL aplicam lock de linha
            query = query.with_for_update()
        model = query.first()
        if not model:
            return None

        acc = Account(
            document_number=model.document_number,
            holder_name=model.holder_name,
            initial_balance=Decimal(str(model.balance)),
            id=UUID(model.id),
        )
        acc.created_at = model.created_at
        return acc

    def get_by_id_or_fail(self, account_id: UUID, for_update: bool = False) -> Account:
        acc = self.get_by_id(account_id, for_update=for_update)
        if not acc:
            raise AccountNotFoundError(f"Conta com ID {account_id} não encontrada")
        return acc

    def list_all(self) -> List[Account]:
        models = self.session.query(AccountModel).all()
        accounts = []
        for m in models:
            acc = Account(
                document_number=m.document_number,
                holder_name=m.holder_name,
                initial_balance=Decimal(str(m.balance)),
                id=UUID(m.id),
            )
            acc.created_at = m.created_at
            accounts.append(acc)
        return accounts
