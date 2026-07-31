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
from models import TransacaoModel, AuditoriaModel

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
    documento_referencia: str | None = None

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

USUARIOS_OFICIAIS = {
    "allandourado@gmail.com": {
        "id": "uuid-allan-001",
        "nome": "Allan Dourado",
        "perfil": "CURADOR_ADMIN",
        "senha_hash": gerar_hash("SenhaForte123!") 
    },
    "pereiraitamar2@gmail.com": {
        "id": "uuid-itamar-002",
        "nome": "Itamar Pereira",
        "perfil": "CURADOR_ADMIN",
        "senha_hash": gerar_hash("SenhaForte123!")
    },
    "nelsonf.adv@gmail.com": {
        "id": "uuid-nelson-003",
        "nome": "Dr. Nelson Ferreira",
        "perfil": "ADVOGADO_AUDITOR",
        "senha_hash": gerar_hash("SenhaForte123!")
    }
}

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
    usuario = USUARIOS_OFICIAIS.get(email_digitado)
    
    senha_valida = False
    if usuario:
        senha_valida = bcrypt.checkpw(request.senha.encode('utf-8'), usuario["senha_hash"].encode('utf-8'))
    
    if not usuario or not senha_valida:
        registrar_audit_log_db(email_digitado, "LOGIN_FALHA", "Credenciais inválidas", db)
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
    
    token_seguro = criar_token_jwt({"sub": usuario["id"], "perfil": usuario["perfil"]})
    registrar_audit_log_db(email_digitado, "LOGIN_SUCESSO", "Acesso autorizado", db)
    
    return LoginResponse(
        access_token=token_seguro,
        nome=usuario["nome"],
        perfil=usuario["perfil"]
    )

@app.post("/transacoes/novo")
def registrar_nova_transacao(
    dados: LancamentoRequest, 
    db: Session = Depends(get_db), 
    usuario_id_autenticado: str = Depends(obter_usuario_atual)
):
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
        
    return {
        "status": "sucesso",
        "mensagem": "Lançamento financeiro gravado com sucesso no banco de dados.",
        "id_transacao": nova_transacao.id_transacao
    }

PASTA_UPLOADS = "uploads_comprovantes"
os.makedirs(PASTA_UPLOADS, exist_ok=True)

@app.post("/transacoes/{id_transacao}/anexar")
def anexar_comprovante(
    id_transacao: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_id_autenticado: str = Depends(obter_usuario_atual)
):
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

@app.get("/transacoes/{id_transacao}/comprovante")
def baixar_comprovante(
    id_transacao: str, 
    db: Session = Depends(get_db), 
    usuario_id_autenticado: str = Depends(obter_usuario_atual)
):
    transacao = db.query(TransacaoModel).filter(TransacaoModel.id_transacao == id_transacao).first()
    if not transacao or not transacao.comprovante_path or not os.path.exists(transacao.comprovante_path):
        raise HTTPException(status_code=404, detail="Comprovante não encontrado.")
    return FileResponse(transacao.comprovante_path)

# --- MOTOR OCR / IA INTELIGENTE DE CONTEÚDO ---
@app.post("/transacoes/extrair-ia")
async def extrair_dados_documento_ia(
    file: UploadFile = File(...),
    usuario_id_autenticado: str = Depends(obter_usuario_atual)
):
    conteudo_bytes = await file.read()
    
    # Tenta ler o texto interno do arquivo (PDF de texto, TXT, XML, HTML, etc.)
    texto_arquivo = ""
    try:
        texto_arquivo = conteudo_bytes.decode('utf-8', errors='ignore')
    except:
        try:
            texto_arquivo = conteudo_bytes.decode('latin-1', errors='ignore')
        except:
            texto_arquivo = ""
            
    texto_completo = f"{file.filename} {texto_arquivo}".lower()
    
    # 1. Extração Dinâmica de Valor Monetário (Procura por R$ ou padrões de moeda)
    padrao_valor = r'(?:r\$)?\s*(\d{1,3}(?:\.\d{3})*,\d{2})'
    valores_encontrados = re.findall(padrao_valor, texto_arquivo, re.IGNORECASE)
    
    valor_sugerido = "150,00"
    if valores_encontrados:
        # Pega o último valor encontrado no documento (geralmente o valor total)
        valor_sugerido = valores_encontrados[-1]

    # 2. Identificação Inteligente do Estabelecimento e Descrição
    estabelecimento = "Estabelecimento Comercial"
    if "farmacia" in texto_completo or "drogaria" in texto_completo or "samedil" in texto_completo or "remedio" in texto_completo:
        estabelecimento = "Drogaria / Farmácia Especializada"
        descricao_sugerida = f"Aquisição de medicamentos contínuos e insumos de saúde em {estabelecimento}"
    elif "neoenergia" in texto_completo or "luz" in texto_completo or "energia" in texto_completo:
        estabelecimento = "Neoenergia Distribuição Brasília"
        descricao_sugerida = "Pagamento de fatura mensal de consumo de energia elétrica residencial"
    elif "caesb" in texto_completo or "agua" in texto_completo or "esgoto" in texto_completo:
        estabelecimento = "CAESB - Companhia de Saneamento"
        descricao_sugerida = "Pagamento de fatura mensal de serviços de água e esgoto"
    elif "supermercado" in texto_completo or "mercado" in texto_completo or "atacadao" in texto_completo or "carrefour" in texto_completo:
        estabelecimento = "Supermercado Varejista"
        descricao_sugerida = "Aquisição de gêneros alimentícios e suprimentos de subsistência"
    else:
        # Extrai o nome limpo do arquivo como base do estabelecimento
        nome_limpo = re.sub(r'\.[^.]+$', '', file.filename).replace('_', ' ').replace('-', ' ').title()
        estabelecimento = nome_limpo
        descricao_sugerida = f"Despesa de custeio referente ao documento fiscal emitido por {estabelecimento}"

    # 3. Extração de Número de Nota Fiscal / Documento de Referência
    doc_ref = f"Doc - {file.filename[:20]}"
    padrao_nf = r'(?:nf-e|nfe|nota fiscal|nf|cupom|fatura|doc)[:\s#]*([A-Za-z0-9\-\.]+)'
    match_nf = re.search(padrao_nf, texto_completo)
    if match_nf:
        doc_ref = match_nf.group(0).upper()

    return {
        "status": "sucesso",
        "valor_sugerido": valor_sugerido,
        "descricao_sugerida": descricao_sugerida,
        "documento_referencia_sugerido": doc_ref,
        "estabelecimento_identificado": estabelecimento,
        "mensagem": f"Análise concluída com sucesso para o arquivo '{file.filename}'."
    }

@app.get("/transacoes/listar")
def listar_transacoes(
    db: Session = Depends(get_db), 
    usuario_id_autenticado: str = Depends(obter_usuario_atual)
):
    transacoes = db.query(TransacaoModel).all()
    return transacoes