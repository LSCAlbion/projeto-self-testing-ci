class DomainException(Exception):
    """Exceção base para erros de regras de negócio."""
    pass


class InvalidAmountError(DomainException):
    """Lançada quando um valor financeiro for inválido ou negativo."""
    pass


class InsufficientFundsError(DomainException):
    """Lançada quando a conta não possui saldo suficiente para débito."""
    pass


class InvalidDocumentError(DomainException):
    """Lançada quando o documento fornecido for inválido."""
    pass


class AccountNotFoundError(DomainException):
    """Lançada quando uma conta informada não for localizada."""
    pass


class SelfTransferNotAllowedError(DomainException):
    """Lançada quando origem e destino da transferência forem a mesma conta."""
    pass


class AntiFraudRejectedError(DomainException):
    """Lançada quando a operação for rejeitada pelo serviço anti-fraude."""
    pass


class KycValidationError(DomainException):
    """Lançada quando a validação cadastral (KYC) falhar."""
    pass
