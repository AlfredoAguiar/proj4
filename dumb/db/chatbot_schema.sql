-- Criação das tabelas para o sistema de chatbot institucional

-- Tabela: Categoria
CREATE TABLE Categoria (
    categoria_id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    keywords TEXT[],
    idioma VARCHAR(10) NOT NULL
);

-- Tabela: Chatbot
CREATE TABLE Chatbot (
    chatbot_id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    tipo VARCHAR(10) NOT NULL,
    descricao TEXT,
    mensagem_inicial_EN VARCHAR(255) NOT NULL,
    mensagem_inicial_PT VARCHAR(255) NOT NULL,
    mensagem_no_response_PT VARCHAR(255) NOT NULL,
    mensagem_no_response_EN VARCHAR(255) NOT NULL,
    data_criacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    estado VARCHAR(20) DEFAULT 'desativo',
    cor_rgb VARCHAR(7),
    icone TEXT
);


-- Tabela associativa: Chatbot_Categoria
CREATE TABLE Chatbot_Categoria (
    categoria_id INT REFERENCES Categoria(categoria_id) ON DELETE SET NULL,
    chatbot_id INT REFERENCES Chatbot(chatbot_id) ON DELETE CASCADE,
    PRIMARY KEY (categoria_id, chatbot_id)
);

-- Tabela: Documento
CREATE TABLE Documento (
    documento_id SERIAL PRIMARY KEY,
    chatbot_id INT REFERENCES Chatbot(chatbot_id) ON DELETE CASCADE,
    titulo VARCHAR(255),
    ficheiro_path TEXT
);

-- Tabela: FAQ
CREATE TABLE FAQ (
    faq_id SERIAL PRIMARY KEY,
    chatbot_id INT REFERENCES Chatbot(chatbot_id) ON DELETE CASCADE,
    pergunta TEXT NOT NULL,
    resposta TEXT NOT NULL,
    idioma VARCHAR(10) NOT NULL,
     mostrar_nas_recomendacoes BOOLEAN DEFAULT FALSE

);

-- Tabela associativa: Documento_FAQ
CREATE TABLE Documento_FAQ (
    faq_id INT REFERENCES FAQ(faq_id) ON DELETE CASCADE,
    documento_id INT REFERENCES Documento(documento_id) ON DELETE CASCADE,
    PRIMARY KEY (faq_id, documento_id)
);
CREATE TABLE Faq_Categoria (
    categoria_id INT REFERENCES Categoria(categoria_id) ON DELETE CASCADE,
    faq_id INT REFERENCES FAQ(faq_id) ON DELETE CASCADE,
    PRIMARY KEY (categoria_id, faq_id)
);
-- Tabela: Log
CREATE TABLE Log (
    log_id SERIAL PRIMARY KEY,
    chatbot_id INT REFERENCES Chatbot(chatbot_id) ON DELETE CASCADE,
    data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pergunta_utilizador TEXT,
    respondido BOOLEAN
);

-- Tabela: Administrador
CREATE TABLE Administrador (
    admin_id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

