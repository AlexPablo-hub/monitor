# Imagem base
FROM python:3.11-slim

# Evita buffers no log
ENV PYTHONUNBUFFERED=1

# Diretório da aplicação
WORKDIR /app

# Copiar requirements primeiro (melhor cache)
COPY requirements.txt .

# Instalar dependências
RUN pip install --no-cache-dir -r requirements.txt

# Copiar restante da aplicação
COPY . .

# Expor porta do servidor
EXPOSE 8000

# Comando para rodar a API FastAPI
CMD ["uvicorn", "monitor_api:app", "--host", "0.0.0.0", "--port", "8000"]
