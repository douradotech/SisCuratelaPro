# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import urllib.parse

# Codifica a senha de forma segura para evitar erros com caracteres especiais
senha_segura = urllib.parse.quote_plus("U415p902Allan")

SQLALCHEMY_DATABASE_URL = "postgresql://postgres.vakotodqgzxolhdvwevw:U4l5p902Allan@aws-0-sa-east-1.pooler.supabase.com:5432/postgres?sslmode=require"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
# ... (mantenha o restante do código get_db igual)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()