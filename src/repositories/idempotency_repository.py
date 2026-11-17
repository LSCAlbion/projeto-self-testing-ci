from typing import Optional
from sqlalchemy.orm import Session
from src.repositories.models import IdempotencyRecordModel


class IdempotencyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, key: str) -> Optional[IdempotencyRecordModel]:
        return self.session.query(IdempotencyRecordModel).filter(IdempotencyRecordModel.key == key).first()

    def save(self, key: str, request_hash: str, status_code: int, response_body: str) -> IdempotencyRecordModel:
        record = IdempotencyRecordModel(
            key=key,
            request_hash=request_hash,
            status_code=status_code,
            response_body=response_body,
        )
        self.session.add(record)
        self.session.flush()
        return record
