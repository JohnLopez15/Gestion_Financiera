from sqlalchemy import Column, Integer, String, Float, Boolean, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from flask_login import UserMixin
from .connection import Base
import enum
import datetime


# ──────────────────────────────────────────────
# ENUMERACIONES
# ──────────────────────────────────────────────

class PeriodicityEnum(str, enum.Enum):
    unique = "Única"
    weekly = "Semanal"
    biweekly = "Quincenal"
    monthly = "Mensual"
    bimonthly = "Bimestral"
    semiannual = "Semestral"
    annual = "Anual"

class TransactionTypeEnum(str, enum.Enum):
    income = "Ingreso"
    expense = "Gasto"


# ──────────────────────────────────────────────
# MODELO DE USUARIO (Autenticación)
# ──────────────────────────────────────────────

class User(UserMixin, Base):
    """
    Modelo de usuario para autenticación.
    - UserMixin provee los métodos requeridos por Flask-Login.
    - La contraseña NUNCA se guarda en texto plano; se almacena su hash.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(Date, default=datetime.date.today)

    def __repr__(self):
        return f"<User {self.username}>"


# ──────────────────────────────────────────────
# MODELOS FINANCIEROS
# ──────────────────────────────────────────────

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    balance = Column(Float, default=0.0)
    updated_at = Column(Date, default=datetime.date.today)

    transactions = relationship("Transaction", back_populates="account")
    # Historial de saldos reales registrados manualmente
    balance_history = relationship(
        "AccountBalanceHistory",
        back_populates="account",
        order_by="AccountBalanceHistory.recorded_at",
        cascade="all, delete-orphan"
    )


class AccountBalanceHistory(Base):
    """
    Registro histórico de saldos reales de una Cuenta de Ahorro/Corriente.
    Cada vez que el usuario actualiza el saldo actual de una cuenta,
    se guarda un snapshot con la fecha y el valor real para análisis histórico.
    """
    __tablename__ = "account_balance_history"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    balance = Column(Float, nullable=False)
    recorded_at = Column(Date, default=datetime.date.today, nullable=False)
    note = Column(String, nullable=True)  # Observación opcional del usuario

    account = relationship("Account", back_populates="balance_history")

    def __repr__(self):
        return f"<AccountBalanceHistory account={self.account_id} balance={self.balance} date={self.recorded_at}>"


class CreditCard(Base):
    __tablename__ = "credit_cards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    credit_limit = Column(Float, default=0.0)
    current_debt = Column(Float, default=0.0)
    next_payment_amount = Column(Float, default=0.0)
    statement_day = Column(Integer)   # Día de corte (1-31)
    due_day = Column(Integer)         # Día de pago (1-31)

    transactions = relationship("Transaction", back_populates="credit_card")
    # Historial de deuda real registrada manualmente
    debt_history = relationship(
        "CreditCardDebtHistory",
        back_populates="credit_card",
        order_by="CreditCardDebtHistory.recorded_at",
        cascade="all, delete-orphan"
    )


class CreditCardDebtHistory(Base):
    """
    Registro histórico de la deuda real de una Tarjeta de Crédito.
    Cada vez que el usuario actualiza la deuda actual de una TC,
    se guarda un snapshot con la fecha y el valor real para análisis histórico.
    """
    __tablename__ = "credit_card_debt_history"

    id = Column(Integer, primary_key=True, index=True)
    credit_card_id = Column(Integer, ForeignKey("credit_cards.id"), nullable=False)
    current_debt = Column(Float, nullable=False)
    next_payment_amount = Column(Float, nullable=True)
    recorded_at = Column(Date, default=datetime.date.today, nullable=False)
    note = Column(String, nullable=True)  # Observación opcional del usuario

    credit_card = relationship("CreditCard", back_populates="debt_history")

    def __repr__(self):
        return f"<CreditCardDebtHistory card={self.credit_card_id} debt={self.current_debt} date={self.recorded_at}>"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    description = Column(String)
    amount = Column(Float)
    start_date = Column(Date)

    is_recurring = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    periodicity = Column(Enum(PeriodicityEnum), default=PeriodicityEnum.unique)
    type = Column(Enum(TransactionTypeEnum))

    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    credit_card_id = Column(Integer, ForeignKey("credit_cards.id"), nullable=True)

    account = relationship("Account", back_populates="transactions")
    credit_card = relationship("CreditCard", back_populates="transactions")
