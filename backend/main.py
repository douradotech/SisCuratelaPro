from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, field_validator
from decimal import Decimal
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import uuid
import bcrypt
import jwt
import shutil
import os
import json
import base64
import requests

from database import get_db
from models import TransacaoModel, AuditoriaModel, UsuarioModel

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
            raise ValueError("Rejeitado: O sistema não permite mais de duas casas decimais.")
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
    email_digitado = request.email.lower().strip()
    usuario = db.query(UsuarioModel).filter(UsuarioModel.email == email_digitado).first()
    
    if not usuario:
        registrar_audit_log_db(email_digitado, "LOGIN FALHA", "Credenciais inválidas", db)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    senha_valida = bcrypt.checkpw(request.senha.encode('utf-8'), usuario.senha_hash.encode('utf-8'))
    
    if not senha_valida:
        registrar_audit_log_db(email_digitado, "LOGIN FALHA", "Credenciais inválidas", db)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    access_token = criar_token_jwt({"sub": usuario.email, "perfil": usuario.perfil})
    registrar_audit_log_db(email_digitado, "LOGIN SUCESSO", "Acesso liberado", db)
    
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
    return {"status": "sucesso", "mensagem": "Lançamento gravado com sucesso.", "id_transacao": nova_transacao.id_transacao}

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
        raise HTTPException(status_code=404, detail="Transação não encontrada.")
    
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


# =========================================================================
# ROTAS DE INTELIGÊNCIA ARTIFICIAL (REST API DIRETA - À PROVA DE FALHAS)
# =========================================================================
@app.post("/api/extrair-extrato")
@app.post("/api/extrair-extrato/")
async def extrair_extrato(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY ausente no Render.")
    
    conteudo_bytes = await file.read()
    base64_pdf = base64.b64encode(conteudo_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = """
    Atue como um assistente especialista em direito de família e contabilidade forense, focado em prestação de contas de curatela judicial no Brasil. 
    Analise este extrato financeiro do Banco do Brasil e retorne ESTRITAMENTE um arquivo JSON válido. Não inclua blocos de formatação Markdown como ```json. 
    O JSON DEVE conter APENAS as seguintes chaves: 
    1. 'mes_referencia' (string) 
    2. 'saldo_conta_corrente' (float) 
    3. 'saldo_aplicacoes' (float) 
    4. 'recebimentos' (lista de objetos com 'data', 'descricao', 'valor'). 
    Colete apenas os saldos finais e os recebimentos autorizados.
    """
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "application/pdf", "data": base64_pdf}}
            ]
        }],
        "generationConfig": {"temperature": 0.1}
    }
    
    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Erro da API Google: {response.text}")
            
        texto_resposta = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        
        if texto_resposta.startswith("```json"):
            texto_resposta = texto_resposta[7:]
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta[3:]
        if texto_resposta.endswith("```"):
            texto_resposta = texto_resposta[:-3]
            
        return json.loads(texto_resposta.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no processamento: {str(e)}")


@app.post("/transacoes/extrair-ia")
@app.post("/transacoes/extrair-ia/")
async def extrair_dados_documento_ia(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY ausente no Render.")
    
    conteudo_bytes = await file.read()
    mime_type = file.content_type if file.content_type else "image/jpeg"
    if mime_type not in ["image/jpeg", "image/png", "image/webp", "application/pdf"]:
        mime_type = "image/jpeg"
        
    base64_img = base64.b64encode(conteudo_bytes).decode('utf-8')
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    prompt = """
    Atue como um assistente especialista em direito de família e contabilidade forense, focado em prestação de contas de curatela judicial (MPDFT). 
    Analise esta imagem e extraia os dados ESTRITAMENTE em um arquivo JSON válido. Não inclua blocos Markdown como ```json. 
    As chaves são: 'valor_sugerido' (string), 'descricao_sugerida' (string), 'documento_referencia_sugerido' (string), 'estabelecimento_identificado' (string), 'categoria_sugerida' (string).
    """
    
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64_img}}
            ]
        }],
        "generationConfig": {"temperature": 0.1}
    }
    
    try:
        response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'})
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Erro da API Google: {response.text}")
            
        texto_resposta = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        
        if texto_resposta.startswith("```json"):
            texto_resposta = texto_resposta[7:]
        if texto_resposta.startswith("```"):
            texto_resposta = texto_resposta[3:]
        if texto_resposta.endswith("```"):
            texto_resposta = texto_resposta[:-3]
            
        return json.loads(texto_resposta.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha na Extração: {str(e)}")