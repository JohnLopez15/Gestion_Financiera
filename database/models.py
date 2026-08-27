from sqlalchemy import Column, Integer, String, Float, Boolean, Date, Enum, ForeignKey
from sqlalchemy.orm import relationship
from .connection import Base
import enum
import datetime

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

class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    balance = Column(Float, default=0.0)
    updated_at = Column(Date, default=datetime.date.today)
    
    transactions = relationship("Transaction", back_populates="account")

class CreditCard(Base):
    __tablename__ = "credit_cards"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    credit_limit = Column(Float, default=0.0)
    current_debt = Column(Float, default=0.0)
    next_payment_amount = Column(Float, default=0.0)
    statement_day = Column(Integer) # Día de corte (1-31)
    due_day = Column(Integer)       # Día de pago (1-31)

    transactions = relationship("Transaction", back_populates="credit_card")

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

