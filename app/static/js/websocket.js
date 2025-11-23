// app/static/js/websocket.js
// WebSocket管理器

class WebSocketManager {
    constructor() {
        this.ws = null;
        this.conversationId = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.currentTypeItInstances = {}; // Store multiple TypeIt instances
    }

    connect(conversationId) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.disconnect();
        }

        this.conversationId = conversationId;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/${conversationId}`;

        console.log(`[DEBUG] Connecting to WebSocket: ${wsUrl}`);

        try {
            this.ws = new WebSocket(wsUrl);
            this.bindEvents();
        } catch (error) {
            console.error('[DEBUG] WebSocket connection failed:', error);
            this.handleReconnect();
        }
    }

    disconnect() {
        console.log('[DEBUG] WebSocket disconnecting...');
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.conversationId = null;
        this.reconnectAttempts = 0;
    }

    bindEvents() {
        this.ws.onopen = () => {
            console.log('[DEBUG] WebSocket connected successfully');
            this.reconnectAttempts = 0;
        };

        this.ws.onmessage = (event) => {
            console.log('[DEBUG] WebSocket message received:', event.data);
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket closed:', event.code);
            if (event.code !== 1000) { // 1000 = normal closure
                this.handleReconnect();
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
            
            setTimeout(() => {
                if (this.conversationId) {
                    this.connect(this.conversationId);
                }
            }, this.reconnectDelay * this.reconnectAttempts);
        } else {
            console.error('Max reconnection attempts reached');
            this.showConnectionError();
        }
    }

    showConnectionError() {
        // 显示连接错误提示
        const errorMessage = document.createElement('div');
        errorMessage.className = 'error';
        errorMessage.textContent = '连接断开，请刷新页面重试';
        
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.appendChild(errorMessage);
        }
    }

    handleMessage(data) {
        const { type, payload } = data;

        switch (type) {
            case 'thinking_chunk':
                this.handleThinkingChunk(payload);
                break;
            case 'answer_chunk':
                this.handleAnswerChunk(payload);
                break;
            case 'complete_response':
                this.handleCompleteResponse(payload);
                break;
            case 'message_complete':
                this.handleMessageComplete(payload);
                break;
            case 'error':
                this.handleError(payload);
                break;
            default:
                console.log('Unknown message type:', type, payload);
        }
    }

    handleThinkingChunk(payload) {
        const { message_id, content } = payload;
        const messageElement = document.querySelector(`[data-message-id="${message_id}"]`);
        if (!messageElement) return;

        const thinkingPhase = messageElement.querySelector('.thinking-phase');
        if (thinkingPhase) thinkingPhase.style.display = 'block';

        const thinkingContent = messageElement.querySelector('.thinking-text-content');
        if (thinkingContent && !this.currentTypeItInstances[message_id + '_thinking']) {
             this.initTypeIt(thinkingContent, content, 50, message_id + '_thinking');
        } else if (this.currentTypeItInstances[message_id + '_thinking']) {
            this.currentTypeItInstances[message_id + '_thinking'].type(content);
        }
    }

    handleAnswerChunk(payload) {
        const { message_id, content } = payload;
        const messageElement = document.querySelector(`[data-message-id="${message_id}"]`);
        if (!messageElement) return;

        // Stop thinking animation and update title
        const thinkingTitle = messageElement.querySelector('.thinking-title');
        if (thinkingTitle) {
            thinkingTitle.innerHTML = `<div class="spinner" style="display: none;"></div> 已完成深度思考`;
        }
        if (this.currentTypeItInstances[message_id + '_thinking']) {
            this.currentTypeItInstances[message_id + '_thinking'].destroy();
            delete this.currentTypeItInstances[message_id + '_thinking'];
        }

        const finalPhase = messageElement.querySelector('.final-answer-phase');
        if (finalPhase) finalPhase.style.display = 'block';
        
        const finalContent = messageElement.querySelector('.final-answer-content');
        if (finalContent && !this.currentTypeItInstances[message_id + '_answer']) {
            this.initTypeIt(finalContent, content, 20, message_id + '_answer', messageElement);
        } else if (this.currentTypeItInstances[message_id + '_answer']) {
            this.currentTypeItInstances[message_id + '_answer'].type(content);
        }
    }

    handleCompleteResponse(payload) {
        const { thinking_content, answer_content } = payload;
        
        // 获取当前活动的消息元素
        const messageElement = document.querySelector('[data-message-id]:last-child');
        if (!messageElement) return;
        
        const messageId = messageElement.getAttribute('data-message-id');

        // 处理thinking内容
        if (thinking_content) {
            const thinkingPhase = messageElement.querySelector('.thinking-phase');
            if (thinkingPhase) thinkingPhase.style.display = 'block';

            const thinkingContent = messageElement.querySelector('.thinking-text-content');
            if (thinkingContent && !this.currentTypeItInstances[messageId + '_thinking']) {
                this.initTypeIt(thinkingContent, thinking_content, 50, messageId + '_thinking');
            }
        }

        // 处理answer内容
        if (answer_content) {
            // 如果有thinking内容，需要等待thinking完成后再显示answer
            const delay = thinking_content ? 1000 : 0;
            
            setTimeout(() => {
                // Stop thinking animation and update title
                const thinkingTitle = messageElement.querySelector('.thinking-title');
                if (thinkingTitle) {
                    thinkingTitle.innerHTML = `<div class="spinner" style="display: none;"></div> 已完成深度思考`;
                }
                if (this.currentTypeItInstances[messageId + '_thinking']) {
                    this.currentTypeItInstances[messageId + '_thinking'].destroy();
                    delete this.currentTypeItInstances[messageId + '_thinking'];
                }

                const finalPhase = messageElement.querySelector('.final-answer-phase');
                if (finalPhase) finalPhase.style.display = 'block';
                
                const finalContent = messageElement.querySelector('.final-answer-content');
                if (finalContent && !this.currentTypeItInstances[messageId + '_answer']) {
                    this.initTypeIt(finalContent, answer_content, 20, messageId + '_answer', messageElement);
                }
            }, delay);
        }

        // 自动触发完成事件
        setTimeout(() => {
            this.handleMessageComplete({ message_id: messageId });
        }, (thinking_content ? 1000 : 0) + (answer_content ? answer_content.length * 20 : 0) + 500);
    }

    handleMessageComplete(payload) {
        const { message_id } = payload;
        const messageElement = document.querySelector(`[data-message-id="${message_id}"]`);
        if (!messageElement) return;

        // Ensure all typing is finished
        if (this.currentTypeItInstances[message_id + '_answer']) {
            this.currentTypeItInstances[message_id + '_answer'].go();
        }

        // Show controls
        const controls = messageElement.querySelector('.controls');
        if (controls) {
            controls.style.opacity = '1';
        }

        // 恢复发送按钮状态
        if (window.uiManager) {
            window.uiManager.showSendButton();
            // 清空保存的输入状态
            window.uiManager.savedInputText = '';
            window.uiManager.savedFiles = [];
            // 重置发送状态
            window.uiManager.isSending = false;
            
            // 强制确保按钮状态正确
            setTimeout(() => {
                if (window.uiManager.ensureButtonState) {
                    window.uiManager.ensureButtonState();
                }
            }, 100);
        }
    }

    handleError(payload) {
        const { message } = payload;
        console.error('WebSocket error:', message);
        if (window.uiManager) {
            window.uiManager.showError(message);
        }
    }

    initTypeIt(element, text, speed, instanceId, messageElementForCallback = null) {
        if (typeof TypeIt === 'undefined') {
            element.innerHTML += text; // Fallback if TypeIt is not available
            return;
        }

        const options = {
            strings: [text],
            speed: speed,
            cursor: false,
            lifeLike: true,
            afterComplete: (instance) => {
                if (messageElementForCallback) {
                    this.finalizeMessageRendering(messageElementForCallback);
                }
                instance.destroy();
                delete this.currentTypeItInstances[instanceId];
            }
        };

        const typeitInstance = new TypeIt(element, options).go();
        this.currentTypeItInstances[instanceId] = typeitInstance;
    }
    
    finalizeMessageRendering(messageElement) {
        // Re-render markdown and icons
        const finalContent = messageElement.querySelector('.final-answer-content');
        if (finalContent && typeof marked !== 'undefined') {
            finalContent.innerHTML = marked.parse(finalContent.textContent);
        }
        if (typeof lucide !== 'undefined') {
            lucide.createIcons({ nodes: [messageElement] });
        }

        // Call agent-specific UI handlers
        if (window.uiManager) {
            window.uiManager.handleAgentSpecificUI(messageElement);
        }
    }

    sendMessage(data) {
        console.log('[DEBUG] sendMessage called with data:', data);
        console.log('[DEBUG] WebSocket readyState:', this.ws ? this.ws.readyState : 'No WebSocket');
        
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            // 直接发送数据，不再包装成messageData格式
            console.log('[DEBUG] Sending data via WebSocket:', data);
            this.ws.send(JSON.stringify(data));
            return true;
        } else {
            console.error('[DEBUG] WebSocket is not connected, readyState:', this.ws ? this.ws.readyState : 'undefined');
            return false;
        }
    }
}

// 创建全局WebSocket管理器实例
window.wsManager = new WebSocketManager();
