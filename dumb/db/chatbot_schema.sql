-- Criação das tabelas para o sistema de chatbot institucional

-- Tabela: Categoria
CREATE TABLE Categoria (
    categoria_id SERIAL PRIMARY KEY,
    nome VARCHAR(100) NOT NULL
);

-- Tabela: Chatbot
CREATE TABLE chatbot (
    chatbot_id SERIAL PRIMARY KEY,
    categoria_id INT REFERENCES categoria(categoria_id) ON DELETE SET NULL,
    nome VARCHAR(100) NOT NULL,
    idioma VARCHAR(10) NOT NULL,
    descricao TEXT
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
    resposta TEXT NOT NULL
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
    password TEXT NOT NULL,  -- Armazena o hash da senha
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
