#!/bin/bash
# Script de deploy para EC2 - Vega Patentes

echo "🚀 Iniciando deploy..."

# 1. Puxar alterações do Git
git pull origin main

# 2. Matar processos antigos (se houver)
fuser -k 8888/tcp
fuser -k 8080/tcp

# 3. Iniciar o Proxy em background (porta 8888)
# Requer python3 instalado
nohup python3 proxy.py > proxy.log 2>&1 &
echo "✅ Proxy iniciado na porta 8888"

# 4. Servir o dashboard (porta 8080)
# Usando http.server do python para simplicidade
nohup python3 -m http.server 8080 > web.log 2>&1 &
echo "✅ Dashboard iniciado na porta 8080"

echo "✨ Deploy concluído! Acesse http://18.206.184.9:8080"
