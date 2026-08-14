from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types
import json
import os

app = FastAPI()

class LoginRequest(BaseModel):
    email: str
    senha: str

@app.post("/auth/login")
async def login(dados: LoginRequest):
    if dados.email == "allandourado@gmail.com":
        return {
            "access_token": "token_seguro_siscuratela_pro",
            "token_type": "bearer",
            "nome": "Allan Dourado",
            "perfil": "CURADOR_ADMIN"
        }
    raise HTTPException(status_code=401, detail="Credenciais inválidas")

def verificar_token():
    return True

# =========================================================================
# ROTA 1: LEITURA INTELIGENTE DE EXTRATOS BANCÁRIOS (PDF)
# =========================================================================
@app.post("/api/extrair-extrato")
@app.post("/api/extrair-extrato/")
async def extrair_extrato(file: UploadFile = File(...)):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY não configurada no servidor.")
    
    conteudo_bytes = await file.read()
    
    try:
        # Correção: Inicialização limpa permitindo que o SDK resolva o endpoint (v1beta)
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

# =========================================================================
# ROTA 2: LEITURA FORENSE DE COMPROVANTES AVULSOS E NOTAS FISCAIS
# =========================================================================
@app.post("/transacoes/extrair-ia")
@app.post("/transacoes/extrair-ia/")
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
                    "Você é um perito em contabilidade forense e direito de família, atuando na prestação de contas de curatela judicial (MPDFT). "
                    "Analise a imagem deste comprovante (NFC-e, NF-e, recibo, boleto). "
                    "Sua missão é extrair os dados e estruturá-los com rigor probatório absoluto para auditoria do juízo. "
                    "Retorne ESTRITAMENTE um objeto JSON válido contendo as seguintes chaves: "
                    "1. 'valor_sugerido': (string) O valor total exato a ser pago. Ex: '1000,00' ou '337,76'. "
                    "2. 'descricao_sugerida': (string) Descrição detalhada forense. Liste o tipo de gasto (ex: Alimentos e Limpeza), datas de atendimento ou serviços prestados. É OBRIGATÓRIO incluir o CPF, CNPJ ou registro profissional (ex: CREFITO/CRM) do emitente para lastro legal. É expressamente proibido usar termos genéricos como 'diversos'. "
                    "3. 'documento_referencia_sugerido': (string) Número da nota, NFC-e, protocolo de autorização ou 'Recibo S/N'. "
                    "4. 'estabelecimento_identificado': (string) Nome fantasia, razão social ou nome do profissional de saúde. "
                    "5. 'categoria_mpdft': (string) Classifique a despesa em uma macrocategoria (ex: Despesas com Saúde, Despesas de Subsistência, Manutenção da Habitação, Custos de Gestão)."
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Falha na Extração Forense: {str(e)}")