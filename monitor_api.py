"""
API de Monitoramento com FastAPI + Evolution API
Arquivo: monitor_api.py
"""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
import asyncio
from datetime import datetime
from typing import Dict
import os
from pydantic import BaseModel

app = FastAPI(title="Monitor JulgadosBR", version="1.0.0")

# Configurações Evolution API
EVOLUTION_API_URL = os.getenv("WHATSAPP_API_URL", "")
EVOLUTION_INSTANCE = os.getenv("WHATSAPP_INSTANCE", "monitor-julgados-2")
EVOLUTION_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
WHATSAPP_PHONE = os.getenv("WHATSAPP_PHONE", "")

# Serviços a monitorar - AJUSTE AS URLs
SERVICES = {
    "frontend_dev": {
        "name": "Frontend Dev",
        "url": "https://dev.julgadosbr.com.br/health",
        "interval": 60
    },
    "frontend_prod": {
        "name": "Frontend Prod",
        "url": "https://julgadosbr.com.br/health",
        "interval": 60
    },
    "backend": {
        "name": "Backend API",
        "url": "https://api.dev.julgadosbr.com.br/health",
        "interval": 60
    }
}

# Estado dos serviços
service_status: Dict[str, dict] = {}

class ServiceStatus(BaseModel):
    name: str
    url: str
    status: str
    last_check: str
    response_time: float = 0
    error_message: str = ""

async def check_service(service_id: str, config: dict) -> dict:
    """Verifica o status de um serviço"""
    start_time = datetime.now()
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(config["url"])
            response_time = (datetime.now() - start_time).total_seconds()
            
            if response.status_code == 200:
                return {
                    "status": "online",
                    "response_time": response_time,
                    "error_message": ""
                }
            else:
                return {
                    "status": "error",
                    "response_time": response_time,
                    "error_message": f"HTTP {response.status_code}"
                }
    except httpx.TimeoutException:
        response_time = (datetime.now() - start_time).total_seconds()
        return {
            "status": "offline",
            "response_time": response_time,
            "error_message": "Timeout - Serviço não respondeu"
        }
    except httpx.ConnectError:
        response_time = (datetime.now() - start_time).total_seconds()
        return {
            "status": "offline",
            "response_time": response_time,
            "error_message": "Erro de conexão - Serviço offline"
        }
    except Exception as e:
        response_time = (datetime.now() - start_time).total_seconds()
        return {
            "status": "offline",
            "response_time": response_time,
            "error_message": f"Erro: {str(e)}"
        }

async def send_whatsapp_evolution(message: str) -> bool:
    """Envia mensagem via Evolution API"""
    
    if not EVOLUTION_API_URL or not EVOLUTION_API_KEY or not WHATSAPP_PHONE:
        print(f"⚠️ WhatsApp não configurado")
        print(f"Mensagem que seria enviada:\n{message}")
        return False
    
    try:
        url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
        
        payload = {
            "number": WHATSAPP_PHONE,
            "text": message
        }
        
        headers = {
            "apikey": EVOLUTION_API_KEY,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if response.status_code == 201 or response.status_code == 200:
                print(f"✅ WhatsApp enviado com sucesso")
                return True
            else:
                print(f"❌ Erro ao enviar WhatsApp: {response.status_code}")
                print(f"Resposta: {response.text}")
                return False
                
    except Exception as e:
        print(f"❌ Erro ao enviar WhatsApp: {e}")
        return False

async def send_whatsapp_alert(service_name: str, status: str, error: str = ""):
    """Formata e envia alerta via WhatsApp"""
    
    emoji = "🔴" if status == "offline" else "⚠️" if status == "error" else "✅"
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    
    message = f"""{emoji} *Alerta JulgadosBR*

*Serviço:* {service_name}
*Status:* {status.upper()}
*Data/Hora:* {timestamp}"""
    
    if error:
        message += f"\n*Erro:* {error}"
    
    await send_whatsapp_evolution(message)

async def monitor_service(service_id: str, config: dict):
    """Loop de monitoramento de um serviço"""
    previous_status = "online"
    consecutive_failures = 0
    
    print(f"🔍 Iniciando monitoramento: {config['name']} ({config['url']})")
    
    while True:
        result = await check_service(service_id, config)
        current_status = result["status"]
        
        # Atualiza status global
        service_status[service_id] = {
            "name": config["name"],
            "url": config["url"],
            "status": current_status,
            "last_check": datetime.now().isoformat(),
            "response_time": result["response_time"],
            "error_message": result["error_message"]
        }
        
        # Log do status
        status_emoji = "✅" if current_status == "online" else "❌"
        print(f"{status_emoji} {config['name']}: {current_status} ({result['response_time']:.2f}s)")
        
        # Detecta mudança de status
        if current_status != "online":
            consecutive_failures += 1
            
            # Envia alerta após 2 falhas consecutivas (reduz falsos positivos)
            if consecutive_failures == 2 and previous_status == "online":
                print(f"🚨 ALERTA: {config['name']} está {current_status}!")
                await send_whatsapp_alert(
                    config["name"],
                    current_status,
                    result["error_message"]
                )
        else:
            # Serviço voltou
            if previous_status != "online" and consecutive_failures >= 2:
                print(f"✅ RECUPERADO: {config['name']} voltou ao ar!")
                await send_whatsapp_alert(
                    config["name"],
                    "online",
                    "Serviço recuperado ✅"
                )
            consecutive_failures = 0
        
        previous_status = current_status
        await asyncio.sleep(config["interval"])

@app.on_event("startup")
async def startup_event():
    """Inicia monitoramento ao iniciar a API"""
    print("\n" + "="*60)
    print("🚀 Monitor JulgadosBR Iniciado")
    print("="*60)
    print(f"Evolution API: {EVOLUTION_API_URL}")
    print(f"Instância: {EVOLUTION_INSTANCE}")
    print(f"Número WhatsApp: {WHATSAPP_PHONE}")
    print(f"Serviços monitorados: {len(SERVICES)}")
    print("="*60 + "\n")
    
    for service_id, config in SERVICES.items():
        asyncio.create_task(monitor_service(service_id, config))
    
    # Envia mensagem de inicialização
    await send_whatsapp_evolution(
        f"🚀 *Monitor JulgadosBR Iniciado*\n\n"
        f"Monitorando {len(SERVICES)} serviços.\n"
        f"Você receberá alertas caso algo fique offline."
    )

@app.get("/")
async def root():
    """Endpoint raiz"""
    return {
        "message": "Monitor JulgadosBR",
        "services": len(SERVICES),
        "status": "running",
        "evolution_api": EVOLUTION_API_URL,
        "instance": EVOLUTION_INSTANCE
    }

@app.get("/status")
async def get_status():
    """Retorna status atual de todos os serviços"""
    return {
        "timestamp": datetime.now().isoformat(),
        "services": service_status
    }

@app.get("/health")
async def health():
    """Health check do monitor"""
    return {
        "status": "ok",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "services_monitored": len(SERVICES)
    }

@app.post("/test-alert")
async def test_alert():
    """Endpoint para testar notificação do WhatsApp"""
    success = await send_whatsapp_evolution(
        "🧪 *Teste de Notificação*\n\n"
        "Se você recebeu esta mensagem, o sistema de alertas está funcionando! ✅"
    )
    
    return {
        "message": "Teste enviado",
        "success": success,
        "phone": WHATSAPP_PHONE
    }

@app.post("/check/{service_id}")
async def force_check(service_id: str):
    """Força uma verificação manual de um serviço"""
    if service_id not in SERVICES:
        return JSONResponse(
            status_code=404,
            content={"error": "Serviço não encontrado"}
        )
    
    result = await check_service(service_id, SERVICES[service_id])
    return {
        "service": SERVICES[service_id]["name"],
        "result": result
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)