# backend/models.py
from sqlalchemy import Column, String, Boolean, Date, DateTime, Numeric, Integer
from sqlalchemy.sql import func
from database import Base

class TransacaoModel(Base):
    __tablename__ = "transacoes"

    id_transacao = Column(String, primary_key=True, index=True)
    id_conta = Column(String)
    id_usuario = Column(String)
    id_micro = Column(String)
    data_transacao = Column(Date)
    valor = Column(Numeric(15, 2))
    descricao = Column(String)
    documento_referencia = Column(String, nullable=True)
    exige_alvara = Column(Boolean, default=False)
    comprovante_path = Column(String, nullable=True)  # <-- NOVO CAMPO PARA O COMPROVANTE
    criado_em = Column(DateTime, server_default=func.now())
    atualizado_em = Column(DateTime, server_default=func.now(), onupdate=func.now())

# NOVO MODELO DE AUDITORIA PERSISTENTE
class AuditoriaModel(Base):
    __tablename__ = "logs_auditoria"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, server_default=func.now())
    email = Column(String, nullable=False)
    acao = Column(String, nullable=False)
    status = Column(String, nullable=False)