import asyncio
import websockets
import logging
from logging.handlers import RotatingFileHandler
import json
import time
import sys


logger = logging.getLogger('WebSocketServer')
logger.setLevel(logging.INFO)

handler = logging.FileHandler('server.log', encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)

console_handler = logging.StreamHandler(stream=sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
console_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)


clients = {}  
message_history = []  
MAX_HISTORY = 100  
TA_PASSWORD = "ta_password123" 
PING_INTERVAL = 5  
CLIENT_TIMEOUT = 60  

async def handle_client(websocket):
   
    client_ip = websocket.remote_address[0]
    username = None
    is_ta = False
    try:
       
        message = await websocket.recv()
        logger.info(f"Received login message from {client_ip}: {message}")
        data = json.loads(message)
        if data.get("type") != "login" or not data.get("username"):
            await websocket.send(json.dumps({"error": "لطفاً نام کاربری معتبر ارسال کنید"}, ensure_ascii=False))
            return
        username = data["username"]
   
        if username.startswith("TA"):
            if data.get("password") != TA_PASSWORD:
                await websocket.send(json.dumps({"error": "رمز عبور اشتباه است"}, ensure_ascii=False))
                return
            is_ta = True
        logger.info(f"Client connected: {client_ip} (Username: {username}, TA: {is_ta})")
        
       
        clients[websocket] = {"username": username, "is_ta": is_ta, "last_pong": time.time()}
        
   
        for msg in message_history:
            await websocket.send(json.dumps(msg, ensure_ascii=False))
        
    
        users_list = [info["username"] for info in clients.values()]
        broadcast_message = {
            "users": users_list,
            "ta_connected": any(info["is_ta"] for info in clients.values())
        }
        message_history.append(broadcast_message)
        if len(message_history) > MAX_HISTORY:
            message_history.pop(0)
        await broadcast(json.dumps(broadcast_message, ensure_ascii=False))
        
       
        async for message in websocket:
           
            clients[websocket]["last_pong"] = time.time()
        
            data = json.loads(message)
            if data.get("type") == "message":
                msg = data.get("message", "")
                logger.info(f"Message from {username} ({client_ip}): {msg}")
                
                message_content = f"[TA] {username}: {msg}" if is_ta else f"{username}: {msg}"
                broadcast_message = {
                    "message": message_content,
                    "users": users_list,
                    "ta_connected": any(info["is_ta"] for info in clients.values())
                }
                message_history.append(broadcast_message)
                if len(message_history) > MAX_HISTORY:
                    message_history.pop(0)
                await broadcast(json.dumps(broadcast_message, ensure_ascii=False))
            elif data.get("type") == "pong":
                logger.info(f"Pong received from {username} ({client_ip})")
            elif data.get("type") == "request_users":
                logger.info(f"Users list requested by {username} ({client_ip})")
                users_list = [info["username"] for info in clients.values()]
                await websocket.send(json.dumps({
                    "users": users_list,
                    "ta_connected": any(info["is_ta"] for info in clients.values())
                }, ensure_ascii=False))
    except Exception as e:
        logger.info(f"Error with client {username or client_ip}: {str(e)}")
    finally:
       
        if websocket in clients:
            logger.info(f"Client disconnected: {username} ({client_ip}, TA: {is_ta})")
            del clients[websocket]
            logger.info(f"Client removed from list: {username} ({client_ip})")
       
            users_list = [info["username"] for info in clients.values()]
            broadcast_message = {
                "users": users_list,
                "ta_connected": any(info["is_ta"] for info in clients.values())
            }
            message_history.append(broadcast_message)
            if len(message_history) > MAX_HISTORY:
                message_history.pop(0)
            await broadcast(json.dumps(broadcast_message, ensure_ascii=False))

async def broadcast(message):

    logger.info(f"Broadcast: {message}")
 
    if clients:
        await asyncio.gather(*(client.send(message) for client in clients), return_exceptions=True)

async def send_ping():
    while True:
        if clients:
            ping_message = json.dumps({"type": "ping"})
            logger.info("Sending ping to clients")
            await asyncio.gather(*(client.send(ping_message) for client in clients), return_exceptions=True)
      
            current_time = time.time()
            disconnected_clients = [
                ws for ws, info in clients.items()
                if current_time - info["last_pong"] > CLIENT_TIMEOUT
            ]
            for ws in disconnected_clients:
                logger.info(f"Timeout: Disconnecting {clients[ws]['username']} ({ws.remote_address[0]})")
                await ws.close()
        await asyncio.sleep(PING_INTERVAL) 

async def main():
    
    async with websockets.serve(handle_client, "localhost", 8765, ping_interval=None, ping_timeout=None):
        logger.info("Server started on ws://localhost:8765")
       
        asyncio.create_task(send_ping())
        await asyncio.Future() 

if __name__ == "__main__":
    asyncio.run(main())