from alembic import op
import sqlalchemy as sa

revision = 'c06c6a1f7e55'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    connection = op.get_bind()
    
    # Cria o tipo ENUM no PostgreSQL de forma segura (ignora se já existir)
    connection.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE tipo_perfil AS ENUM ('CURADOR_ADMIN', 'ADVOGADO_AUDITOR');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """))

    # Cria a tabela de usuários via SQL puro (idempotente)
    connection.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id_usuario VARCHAR PRIMARY KEY,
            nome VARCHAR(150) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            senha_hash VARCHAR(255) NOT NULL,
            perfil tipo_perfil NOT NULL,
            tentativas_falhas INTEGER DEFAULT 0,
            bloqueado_ate TIMESTAMP,
            ativo BOOLEAN DEFAULT TRUE,
            criado_em TIMESTAMP DEFAULT NOW(),
            atualizado_em TIMESTAMP DEFAULT NOW()
        );
    """))

    # Cria a tabela de logs de auditoria via SQL puro (idempotente)
    connection.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS logs_auditoria (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP DEFAULT NOW(),
            email VARCHAR NOT NULL,
            acao VARCHAR NOT NULL,
            status VARCHAR NOT NULL
        );
    """))

def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("DROP TABLE IF EXISTS logs_auditoria CASCADE;"))
    connection.execute(sa.text("DROP TABLE IF EXISTS usuarios CASCADE;"))
    connection.execute(sa.text("DROP TYPE IF EXISTS tipo_perfil CASCADE;"))