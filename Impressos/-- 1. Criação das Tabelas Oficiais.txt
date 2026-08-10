-- 1. Criação das Tabelas Oficiais
CREATE TABLE IF NOT EXISTS usuarios (
    id_usuario VARCHAR PRIMARY KEY,
    nome VARCHAR,
    email VARCHAR,
    perfil VARCHAR
);

CREATE TABLE IF NOT EXISTS contas_bancarias (
    id_conta VARCHAR PRIMARY KEY,
    banco VARCHAR,
    agencia VARCHAR,
    numero_conta VARCHAR,
    tipo_conta VARCHAR
);

CREATE TABLE IF NOT EXISTS categorias_macro (
    id_macro VARCHAR PRIMARY KEY,
    nome VARCHAR,
    descricao VARCHAR
);

CREATE TABLE IF NOT EXISTS categorias_micro (
    id_micro VARCHAR PRIMARY KEY,
    id_macro VARCHAR,
    nome VARCHAR
);

CREATE TABLE IF NOT EXISTS transacoes (
    id_transacao VARCHAR PRIMARY KEY,
    id_conta VARCHAR REFERENCES contas_bancarias(id_conta),
    id_usuario VARCHAR REFERENCES usuarios(id_usuario),
    id_micro VARCHAR REFERENCES categorias_micro(id_micro),
    data_transacao DATE,
    valor NUMERIC(15,2),
    descricao TEXT,
    documento_referencia VARCHAR,
    exige_alvara BOOLEAN,
    criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Inserção dos Dados Iniciais de Teste
INSERT INTO usuarios (id_usuario, nome, email, perfil) VALUES 
('uuid-allan-001', 'Allan Dourado', 'allan@siscuratela.com.br', 'CURADOR_ADMIN'),
('uuid-itamar-002', 'Itamar Pereira', 'itamar@siscuratela.com.br', 'CURADOR_ADMIN')
ON CONFLICT (id_usuario) DO NOTHING;

INSERT INTO contas_bancarias (id_conta, banco, agencia, numero_conta, tipo_conta) VALUES 
('conta-bb-principal', 'Banco do Brasil', '1234-5', '98765-4', 'CORRENTE')
ON CONFLICT (id_conta) DO NOTHING;

INSERT INTO categorias_macro (id_macro, nome, descricao) VALUES 
('macro-saude', 'Saúde e Cuidados', 'Despesas relacionadas a tratamentos'),
('macro-alimentacao', 'Alimentação', 'Despesas com supermercado e afins')
ON CONFLICT (id_macro) DO NOTHING;

INSERT INTO categorias_micro (id_micro, id_macro, nome) VALUES 
('micro-farmacia', 'macro-saude', 'Farmácia e Medicamentos'),
('micro-supermercado', 'macro-alimentacao', 'Supermercado')
ON CONFLICT (id_micro) DO NOTHING;