# frontend/app.py
import streamlit as st
import requests
import datetime
import pandas as pd
import re

st.set_page_config(page_title="SisCuratela Pro Gestão e Compliance", page_icon="🛡️", layout="wide")

if "logado" not in st.session_state:
    st.session_state.update({
        "logado": False,
        "token": None,
        "nome_usuario": None,
        "perfil_usuario": None,
        "msg_sucesso": None,
        "ocr_valor": "",
        "ocr_desc": "",
        "ocr_ref": "",
        "ocr_estab": "",
        "ocr_data": None,
        "form_counter": 0
    })

def login_backend(email, senha):
    url_api = "https://siscuratelapro.onrender.com/auth/login"
    try:
        resposta = requests.post(url_api, json={"email": email, "senha": senha}, timeout=30)
        if resposta.status_code == 200:
            dados = resposta.json()
            return True, dados["nome"], dados["perfil"], dados["access_token"]
        elif resposta.status_code == 401:
            return False, "E-mail ou senha incorretos.", None, None
        else:
            return False, f"Erro no servidor: {resposta.text}", None, None
    except requests.exceptions.Timeout:
        return False, "O servidor demorou para responder (Timeout). Tente novamente.", None, None
    except requests.exceptions.ConnectionError:
        return False, "Erro Crítico: Backend desligado.", None, None

def enviar_lancamento(dados_transacao, token):
    url_api = "http://127.0.0.1:8000/transacoes/novo"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resposta = requests.post(url_api, json=dados_transacao, headers=headers, timeout=30)
        if resposta.status_code == 200:
            resultado = resposta.json()
            return True, resultado.get("mensagem", "Sucesso"), resultado.get("id_transacao")
        else:
            erro_detalhe = resposta.json().get("detail", "Erro desconhecido.")
            return False, erro_detalhe, None
    except requests.exceptions.ConnectionError:
        return False, "Falha de conexão com o Backend.", None

# === TELA DE LOGIN SEGURA ===
if not st.session_state["logado"]:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<h1 style='text-align: center; color: #2E7D32;'>SisCuratela Pro</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: gray;'>Sistema de Gestão e Prestação de Contas (MPDFT)</h3>", unsafe_allow_html=True)
        st.write("---")
        with st.form("form_login"):
            email = st.text_input("E-mail de Acesso")
            senha = st.text_input("Senha de Acesso", type="password")
            submit = st.form_submit_button("Autenticar via Servidor Seguro")
            if submit:
                sucesso, nome_ou_erro, perfil, token = login_backend(email.strip(), senha)
                if sucesso:
                    st.session_state.update({"logado": True, "nome_usuario": nome_ou_erro, "perfil_usuario": perfil, "token": token})
                    st.rerun()
                else:
                    st.error(f"Falha na autenticação: {nome_ou_erro}")

# === PAINEL LOGADO ===
else:
    st.sidebar.title("Painel de Controle")
    st.sidebar.markdown(f"**Operador:** {st.session_state['nome_usuario']}")
    st.sidebar.markdown(f"**Perfil:** {st.session_state['perfil_usuario']}")
    st.sidebar.write("---")
    menu = st.sidebar.radio("Navegação", ["Painel Central", "Novo Lançamento Financeiro", "Extratos e Relatórios"])
    
    if st.sidebar.button("Encerrar Sessão (Logout)"):
        st.session_state.clear()
        st.rerun()
        
    if menu == "Painel Central":
        st.title("Painel Executivo e Compliance")
        st.success("Conexão estabelecida com segurança entre Frontend, Backend e PostgreSQL!")
        
    elif menu == "Novo Lançamento Financeiro":
        st.title("Novo Lançamento e Leitura Inteligente (OCR/IA)")
        
        if st.session_state.get("msg_sucesso"):
            st.success(st.session_state["msg_sucesso"])
            st.session_state["msg_sucesso"] = None
            
        with st.expander("Assistente de Captura e Leitura IA", expanded=True):
            arquivo_capturado = st.file_uploader("Selecione o documento fiscal", type=["pdf", "png", "jpg", "jpeg"])
            if arquivo_capturado is not None:
                if st.button("Processar Documento com IA"):
                    # Agora ele verifica direto a variável da tela, sem usar session_state
                    if arquivo_capturado is not None:
                        with st.spinner("Analisando documento e estruturando dados..."):
                            try:
                                # Extrai o nome e os bytes do arquivo diretamente do componente
                                files = {'file': (arquivo_capturado.name, arquivo_capturado.getvalue(), getattr(arquivo_capturado, 'type', 'image/jpeg'))}
                                headers = {'Authorization': f"Bearer {st.session_state.get('token')}"}
                                
                                resp_ocr = requests.post("https://siscuratelapro.onrender.com/transacoes/extrair-ia", files=files, headers=headers)
                                
                                if resp_ocr.status_code == 200:
                                    res_json = resp_ocr.json()
                                    
                                    # Salva os dados nas variáveis oficiais do sistema atual
                                    st.session_state["ocr_valor"] = res_json.get("valor_sugerido", "")
                                    st.session_state["ocr_desc"] = res_json.get("descricao_sugerida", "")
                                    st.session_state["ocr_ref"] = res_json.get("documento_referencia_sugerido", "")
                                    st.session_state["ocr_estab"] = res_json.get("estabelecimento_identificado", "")
                                    
                                    # CORREÇÃO TÁTICA: Força o Streamlit a preencher a chave visual do valor
                                    counter = st.session_state.get("form_counter", 0)
                                    st.session_state[f"valor_dinamico_{counter}"] = res_json.get("valor_sugerido", "")
                                    
                                    st.success(f"✨ Sucesso! Estabelecimento: **{st.session_state['ocr_estab']}** | Valor Sugerido: **R$ {st.session_state['ocr_valor']}**")
                                    st.rerun()
                                else:
                                    st.error(f"Erro no servidor: {resp_ocr.status_code}")
                            except Exception as e:
                                st.error(f"Falha de comunicação: {str(e)}")
                    else:
                        st.warning("Nenhum documento selecionado para processamento.")
                            
        with st.form("form_transacao"):
            id_conta = st.selectbox("Conta Bancária", ["conta-bb-corrente"])
            valor_digitado = st.text_input("Valor (R$)", value=st.session_state.get("ocr_valor", ""), key=f"v_{st.session_state['form_counter']}")
            data_transacao = st.date_input("Data da Transação", value=datetime.date.today(), key=f"d_{st.session_state['form_counter']}")
            documento_ref = st.text_input("Documento de Referência", value=st.session_state.get("ocr_ref", ""), key=f"doc_{st.session_state['form_counter']}")
            id_micro = st.selectbox("Categoria", ["micro-fisioterapeuta", "micro-farmacia", "micro-supermercado"])
            descricao = st.text_area("Descrição Detalhada", value=st.session_state.get("ocr_desc", ""), key=f"desc_{st.session_state['form_counter']}")
            
            submit_transacao = st.form_submit_button("Validar e Salvar Lançamento")
            
            if submit_transacao:
                valor_limpo = valor_digitado.replace(".", "").replace(",", ".")
                try:
                    valor_float = float(valor_limpo)
                except ValueError:
                    st.error("Valor inválido.")
                    st.stop()
                    
                payload = {
                    "id_conta": id_conta,
                    "id_micro": id_micro,
                    "data_transacao": str(data_transacao),
                    "valor": valor_float,
                    "descricao": descricao,
                    "documento_referencia": documento_ref
                }
                
                sucesso, msg, id_gerado = enviar_lancamento(payload, st.session_state["token"])
                if sucesso:
                    st.session_state["msg_sucesso"] = "Lançamento gravado com sucesso!"
                    st.session_state["form_counter"] += 1
                    st.rerun()
                else:
                    st.error(f"Erro: {msg}")

    elif menu == "Extratos e Relatórios":
        st.title("Extrato Consolidado")
        headers = {"Authorization": f"Bearer {st.session_state['token']}"}
        resposta = requests.get("https://siscuratelapro.onrender.com/transacoes/listar/transacoes/listar", headers=headers)
        if resposta.status_code == 200:
            st.dataframe(pd.DataFrame(resposta.json()), use_container_width=True)
        else:
            st.info("Nenhum dado encontrado.")
