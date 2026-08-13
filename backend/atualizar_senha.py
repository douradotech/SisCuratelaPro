import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import UsuarioModel
import bcrypt

db = SessionLocal()

# Busca o seu cadastro que já está preso lá no banco
usuario = db.query(UsuarioModel).filter(UsuarioModel.email == "allandourado@gmail.com").first()

if usuario:
    # Força a atualização para a senha exata com a letra "l" minúscula
    nova_senha = 'U4l5p902'
    usuario.senha_hash = bcrypt.hashpw(nova_senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.commit()
    print(f"✅ Missão cumprida! A senha foi atualizada à força para: {nova_senha}")
else:
    print("❌ Usuário não encontrado.")

db.close()