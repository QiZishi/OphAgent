# app/services/chat_service.py
from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        # 将 conversation_id 映射到其活跃的 WebSocket 连接
        self.active_connections: Dict[int, WebSocket] = {}

    async def connect(self, websocket: WebSocket, conversation_id: int):
        """建立WebSocket连接"""
        await websocket.accept()
        self.active_connections[conversation_id] = websocket

    def disconnect(self, conversation_id: int):
        """断开WebSocket连接"""
        if conversation_id in self.active_connections:
            del self.active_connections[conversation_id]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """发送个人消息"""
        await websocket.send_text(message)

    async def send_to_conversation(self, conversation_id: int, message: str):
        """发送消息到指定对话"""
        if conversation_id in self.active_connections:
            websocket = self.active_connections[conversation_id]
            try:
                await websocket.send_text(message)
            except Exception as e:
                print(f"Error sending message to conversation {conversation_id}: {e}")
                self.disconnect(conversation_id)

    async def broadcast(self, message: str):
        """广播消息给所有连接"""
        for conversation_id in list(self.active_connections.keys()):
            await self.send_to_conversation(conversation_id, message)

# 全局连接管理器实例
connection_manager = ConnectionManager()
