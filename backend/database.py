# backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Cole a URL direta do Supabase aqui, substituindo SUA_SENHA_AQUI pela senha real do banco
SQLALCHEMY_DATABASE_URL = "postgresql://postgres.vakotodqgzxolhdvwevw:SUA_SENHA_AQUI@aws-0-sa-east-1.pooler.supabase.com:5432/postgres"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()