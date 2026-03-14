#!/bin/bash
# Script de deploy para EC2 - Vega Patentes

echo "🚀 Iniciando deploy..."

# 1. Puxar alterações do Git
git pull origin main

# 2. Matar processos antigos (se houver)
fuser -k 8888/tcp 2>/dev/null || true
fuser -k 8080/tcp 2>/dev/null || true
sleep 2

# 3. Iniciar o Proxy em background (porta 8888)
# O proxy já inicia a coleta de cache em background automaticamente
nohup python3 proxy.py > proxy.log 2>&1 &
PROXY_PID=$!
echo "✅ Proxy iniciado (PID $PROXY_PID) na porta 8888"

# 4. Aguarda o proxy ficar disponível
echo "⏳ Aguardando proxy inicializar..."
for i in {1..15}; do
  sleep 2
  STATUS=$(curl -s http://localhost:8888/cache-status 2>/dev/null)
  if [ -n "$STATUS" ]; then
    echo "✅ Proxy respondendo! Status do cache: $STATUS"
    break
  fi
  echo "   Tentativa $i/15..."
done

# 5. Servir o dashboard (porta 8080)
nohup python3 -m http.server 8080 > web.log 2>&1 &
echo "✅ Dashboard iniciado na porta 8080"

echo ""
echo "✨ Deploy concluído!"
echo "   Dashboard: http://18.206.184.9:8080"
echo "   Status cache: curl http://localhost:8888/cache-status"
echo "   Logs proxy: tail -f proxy.log"
