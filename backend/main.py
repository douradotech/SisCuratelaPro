from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types
import json
import os

# 1. INSTANCIAÇÃO DO FASTAPI (DEVE FICAR NO TOPO)
app = FastAPI()

# 2. MODELOS E AUTENTICAÇÃO
class LoginRequest(BaseModel):
    email: str
    senha: str

@app.post("/auth/login")
async def login(dados: LoginRequest):
    if dados.email == "allandourado@gmail.com":
        return {
            "access_token": "token_seguro_siscuratela_pro",
            "token_type": "bearer",
            "usuario": "Allan Dourado"
        }
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

def verificar_token():
    return True

# 3. ROTA 1: LEITURA INTELIGENTE DE EXTRATOS BANCÁRIOS (PDF)
@app.post("/api/extrair-extrato")
async def extrair_extrato(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY não configurada no servidor.")
    
    conteudo_bytes = await file.read()
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=conteudo_bytes,
                    mime_type="application/pdf",
                ),
                (
                    "Você é um auditor financeiro especialista em extratos bancários do Banco do Brasil. "
                    "Analise este extrato em PDF e retorne estritamente um JSON válido contendo: "
                    "1. 'mes_referencia' (string, ex: 'Agosto/2026'), "
                    "2. 'saldo_conta_corrente' (float), "
                    "3. 'saldo_aplicacoes' (float), "
                    "4. 'recebimentos' (lista de objetos com 'data', 'descricao', 'valor'). "
                    "Atenção: Ignore totalmente os débitos e saídas. Colete apenas os saldos finais e os recebimentos de entradas (como aposentadorias, aluguéis e rendimentos)."
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar extrato com IA: {str(e)}")

# 4. ROTA 2: LEITURA DE COMPROVANTES AVULSOS E NOTAS FISCAIS
@app.post("/transacoes/extrair-ia")
async def extrair_dados_documento_ia(file: UploadFile = File(...), token: str = Depends(verificar_token)):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY não configurada no servidor.")
    
    conteudo_bytes = await file.read()
    mime_type = file.content_type if file.content_type else "image/jpeg"
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=conteudo_bytes,
                    mime_type=mime_type,
                ),
                (
                    "Você é um assistente financeiro especialista em auditoria. Analise esta imagem de comprovante fiscal/recibo. "
                    "Extraia os dados solicitados e retorne APENAS um JSON válido com as chaves: "
                    "'valor_sugerido' (string com ponto ou vírgula), 'descricao_sugerida' (string detalhada), "
                    "'documento_referencia_sugerido' (string), 'estabelecimento_identificado' (string)."
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha na Extração: {str(e)}")