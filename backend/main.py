from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from decimal import Decimal
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import uuid
import bcrypt
import jwt
import shutil
import os
import re
from database import get_db
from models import TransacaoModel, AuditoriaModel, UsuarioModel

# Correção da declaração da API
app = FastAPI(title="API SisCuratela Pro - Backend de Produção")

SECRET_KEY = "ChaveSuperSecreta_MudarEmProducao_MPDFT"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

security = HTTPBearer()

def gerar_hash(senha: str) -> str:
    return bcrypt.hashpw(senha.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def obter_usuario_atual(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise HTTPException(status_code=401, detail="Token inválido: Usuário não identificado.")
        return usuario_id
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Token de acesso inválido ou expirado.")

class LoginRequest(BaseModel):
    email: str
    senha: str

class LoginResponse(BaseModel):
    access_token: str
    nome: str
    perfil: str

class LancamentoRequest(BaseModel):
    id_conta: str
    id_micro: str
    data_transacao: str
    valor: Decimal
    descricao: str
    documento_referencia: str = None

    @field_validator('descricao')
    def validar_descricao(cls, v):
        termos_proibidos = ['diversos', 'outros', 'vários', 'gastos', 'despesas', 'compra']
        if any(termo in v.lower() for termo in termos_proibidos):
            raise ValueError("Rejeitado: A descrição contém termos genéricos não aceitos pelo MPDFT.")
        if len(v.strip()) < 10:
            raise ValueError("Rejeitado: A descrição é muito curta. Detalhe melhor o lançamento.")
        return v

    @field_validator('valor')
    def validar_valor(cls, v):
        if v <= 0:
            raise ValueError("Rejeitado: O valor do lançamento deve ser maior que zero.")
        if v.as_tuple().exponent < -2:
            raise ValueError("Rejeitado: O sistema financeiro não permite mais de duas casas decimais.")
        return v

def registrar_audit_log_db(email: str, acao: str, status: str, db: Session):
    try:
        novo_log = AuditoriaModel(email=email, acao=acao, status=status)
        db.add(novo_log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[ERRO AUDIT] {str(e)}")

def criar_token_jwt(dados: dict):
    dados_para_codificar = dados.copy()
    expiracao = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    dados_para_codificar.update({"exp": expiracao})
    return jwt.encode(dados_para_codificar, SECRET_KEY, algorithm=ALGORITHM)

@app.post("/auth/login", response_model=LoginResponse)
def login_oficial(request: LoginRequest, db: Session = Depends(get_db)):
    print(f"\n[RADAR] Iniciando tentativa de login para: {request.email}")
    email_digitado = request.email.lower().strip()
    print("[RADAR] Conectando ao Supabase para buscar usuário...")
    usuario = db.query(UsuarioModel).filter(UsuarioModel.email == email_digitado).first()
    
    if not usuario:
        print("[RADAR] Usuário não encontrado no banco.")
        registrar_audit_log_db(email_digitado, "LOGIN FALHA", "Credenciais inválidas", db)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    print("[RADAR] Usuário encontrado! Validando a criptografia da senha...")
    senha_valida = bcrypt.checkpw(request.senha.encode('utf-8'), usuario.senha_hash.encode('utf-8'))
    
    if not senha_valida:
        print("[RADAR] Senha rejeitada.")
        registrar_audit_log_db(email_digitado, "LOGIN FALHA", "Credenciais inválidas", db)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
        
    print("[RADAR] Senha aprovada! Gerando Token de Acesso...")
    access_token = criar_token_jwt({"sub": usuario.email, "perfil": usuario.perfil})
    registrar_audit_log_db(email_digitado, "LOGIN SUCESSO", "Acesso liberado", db)
    print("[RADAR] Login concluído com sucesso!")
    
    return {
        "nome": usuario.nome,
        "perfil": usuario.perfil,
        "access_token": access_token
    }

@app.post("/transacoes/novo")
def registrar_nova_transacao(dados: LancamentoRequest, db: Session = Depends(get_db), usuario_id_autenticado: str = Depends(obter_usuario_atual)):
    nova_transacao = TransacaoModel(
        id_transacao=str(uuid.uuid4()),
        id_conta=dados.id_conta,
        id_usuario=usuario_id_autenticado,
        id_micro=dados.id_micro,
        data_transacao=dados.data_transacao,
        valor=dados.valor,
        descricao=dados.descricao,
        documento_referencia=dados.documento_referencia,
        exige_alvara=True if dados.valor > 5000.00 else False
    )
    try:
        db.add(nova_transacao)
        db.commit()
        db.refresh(nova_transacao)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao gravar transação: {str(e)}")
        
    return {"status": "sucesso", "mensagem": "Lançamento financeiro gravado com sucesso no banco de dados.", "id_transacao": nova_transacao.id_transacao}

@app.get("/transacoes/listar")
def listar_transacoes(db: Session = Depends(get_db), usuario_id_autenticado: str = Depends(obter_usuario_atual)):
    transacoes = db.query(TransacaoModel).filter(TransacaoModel.id_usuario == usuario_id_autenticado).all()
    return transacoes

PASTA_UPLOADS = "uploads_comprovantes"
os.makedirs(PASTA_UPLOADS, exist_ok=True)

@app.post("/transacoes/{id_transacao}/anexar")
def anexar_comprovante(id_transacao: str, file: UploadFile = File(...), db: Session = Depends(get_db), usuario_id_autenticado: str = Depends(obter_usuario_atual)):
    transacao = db.query(TransacaoModel).filter(TransacaoModel.id_transacao == id_transacao).first()
    if not transacao:
        raise HTTPException(status_code=404, detail="Transação financeira não encontrada.")
        
    extensoes_permitidas = [".pdf", ".png", ".jpg", ".jpeg"]
    extensao = os.path.splitext(file.filename)[1].lower()
    if extensao not in extensoes_permitidas:
        raise HTTPException(status_code=400, detail="Formato inválido.")
        
    nome_arquivo_seguro = f"{uuid.uuid4()}{extensao}"
    caminho_completo = os.path.join(PASTA_UPLOADS, nome_arquivo_seguro)
    
    try:
        with open(caminho_completo, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        transacao.comprovante_path = caminho_completo
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")
        
    return {"status": "sucesso", "mensagem": "Anexado com sucesso", "arquivo": nome_arquivo_seguro}

@app.post("/transacoes/extrair-ia")
def extrair_dados_documento_ia(file: UploadFile = File(...)):
    import os
    import json
    import google.generativeai as genai
    
    # FORÇA TOTAL DE AUTENTICAÇÃO: Injeta a chave diretamente no ambiente do sistema operacional
    genai.configure(api_key="AQ.Ab8RN6KSnBtt8QyaD8oDU77KDA0TAwql9Qm6ZgsJP7pXZgItmg", transport="rest")
    
    try:
        conteudo_bytes = file.file.read()
        mime_type = file.content_type if file.content_type else "image/jpeg"
        
        if mime_type not in ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"]:
            mime_type = "image/jpeg"
            
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = """
        Você é um assistente financeiro especialista em auditoria. 
        Analise esta imagem de comprovante fiscal/recibo.
        Extraia os dados solicitados e retorne APENAS um JSON válido.
        Não use markdown, crases ou blocos de código. Retorne ESTRITAMENTE o texto do JSON.
        
        Modelo esperado:
        {
            "valor_sugerido": "valor numérico com duas casas decimais separado por vírgula (ex: 367,02)",
            "estabelecimento_identificado": "Nome do local impresso no topo (ex: DROGARIA ROSARIO)",
            "descricao_sugerida": "Breve resumo dos itens",
            "documento_referencia_sugerido": "Numero do cupom (NFC-e, CCF, etc) ou S/N"
        }
        """
        
        resposta = model.generate_content([
            prompt,
            {"mime_type": mime_type, "data": conteudo_bytes}
        ])
        
        texto_limpo = resposta.text.strip()
        if texto_limpo.startswith("```json"):
            texto_limpo = texto_limpo[7:-3].strip()
        elif texto_limpo.startswith("```"):
            texto_limpo = texto_limpo[3:-3].strip()
            
        dados = json.loads(texto_limpo)
        
        return {
            "status": "sucesso",
            "valor_sugerido": dados.get("valor_sugerido", ""),
            "descricao_sugerida": dados.get("descricao_sugerida", ""),
            "documento_referencia_sugerido": dados.get("documento_referencia_sugerido", "S/N"),
            "estabelecimento_identificado": dados.get("estabelecimento_identificado", ""),
            "mensagem": "Inteligência Artificial processou o documento com sucesso!"
        }
        
    except Exception as e:
        print(f"[ERRO CRÍTICO IA]: {str(e)}")
        return {
            "status": "erro",
            "valor_sugerido": "",
            "descricao_sugerida": f"Falha na Extração: {str(e)}",
            "documento_referencia_sugerido": "",
            "estabelecimento_identificado": "Erro no Processamento Visual",
            "mensagem": "A IA não conseguiu ler o documento."
        }
