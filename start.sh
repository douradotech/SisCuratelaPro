#!/bin/bash

# 1. Entra na pasta do backend e inicia a API (FastAPI) em segundo plano
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 &

# 2. Retorna para a pasta raiz do projeto
cd ..

# 3. Inicia o frontend (Streamlit) usando a porta dinâmica exigida pelo Render
streamlit run frontend/app.py --server.port $PORT --server.address 0.0.0.0