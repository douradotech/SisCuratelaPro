import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import UsuarioModel
import bcrypt
import uuid

db = SessionLocal()

# Criptografa a sua senha oficial para o navegador (U4l5p902)
senha_hash = bcrypt.hashpw('U4l5p902'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

novo_admin = UsuarioModel(
    id_usuario=str(uuid.uuid4()),
    nome="Allan Francisco Dourado",
    email="allandourado@gmail.com",
    senha_hash=senha_hash,
    perfil="CURADOR_ADMIN",
    ativo=True
)

try:
    db.add(novo_admin)
    db.commit()
    print("✅ Conta cadastrada com sucesso no Supabase! Senha web: U4l5p902")
except Exception as e:
    print(f"Erro ao cadastrar: {e}")
finally:
    db.close()