// app/static/js/api.js
// API客户端

class ApiClient {
    constructor() {
        this.baseURL = '/api/v1';
    }

    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        
        const config = {
            headers: {
                'Content-Type': 'application/json',
            },
            ...options
        };

        try {
            const response = await fetch(url, config);
            
            if (response.status === 401) {
                // 认证失败，重定向到登录页
                window.location.href = '/';
                throw new Error('Authentication failed');
            }

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `HTTP error ${response.status}`);
            }

            // 如果响应体为空，返回一个表示成功的对象
            const contentType = response.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                return await response.json();
            } else {
                return { success: true };
            }
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    }

    // 用户相关API
    async getCurrentUser() {
        return this.request('/me');
    }

    // 对话相关API
    async getConversations() {
        return this.request('/conversations');
    }

    async getConversation(conversationId) {
        return this.request(`/conversations/${conversationId}`);
    }

    async createConversation(title, agentType) {
        return this.request('/conversations', {
            method: 'POST',
            body: JSON.stringify({ title, agent_type: agentType })
        });
    }

    async updateConversation(conversationId, title) {
        return this.request(`/conversations/${conversationId}`, {
            method: 'PUT',
            body: JSON.stringify({ title })
        });
    }

    async deleteConversation(conversationId) {
        return this.request(`/conversations/${conversationId}`, {
            method: 'DELETE'
        });
    }

    // 文件上传API
    async uploadFile(file) {
        const formData = new FormData();
        formData.append('file', file);

        // 对于文件上传，我们需要移除Content-Type头让浏览器自动设置
        const url = `${this.baseURL}/upload`;
        const response = await fetch(url, {
            method: 'POST',
            body: formData
        });
        
        if (response.status === 401) {
            window.location.href = '/';
            throw new Error('Authentication failed');
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Upload failed: ${response.status}`);
        }
        
        return await response.json();
    }

    // 发送消息API
    async sendMessage(conversationId, message, files = []) {
        console.log('[DEBUG] apiClient.sendMessage called:', conversationId, message, files.length);
        
        const formData = new FormData();
        formData.append('message', message);
        
        files.forEach(file => {
            formData.append('files', file);
        });

        // 对于文件上传，我们需要移除Content-Type头让浏览器自动设置
        const url = `${this.baseURL}/conversations/${conversationId}/messages`;
        console.log('[DEBUG] Sending POST request to:', url);
        
        const options = {
            method: 'POST',
            body: formData
        };
        
        const response = await fetch(url, options);
        
        console.log('[DEBUG] API response status:', response.status);
        
        if (response.status === 401) {
            window.location.href = '/';
            throw new Error('Authentication failed');
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Send message failed: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('[DEBUG] API response data:', result);
        return result;
    }

    // 重新生成消息API
    async regenerateMessage(conversationId, messageId) {
        console.log('[DEBUG] apiClient.regenerateMessage called:', conversationId, messageId);
        
        const url = `${this.baseURL}/conversations/${conversationId}/messages/${messageId}/regenerate`;
        console.log('[DEBUG] Sending POST request to:', url);
        
        const options = {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        const response = await fetch(url, options);
        
        console.log('[DEBUG] API response status:', response.status);
        
        if (response.status === 401) {
            window.location.href = '/';
            throw new Error('Authentication failed');
        }
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `Regenerate message failed: ${response.status}`);
        }
        
        const result = await response.json();
        console.log('[DEBUG] API response data:', result);
        return result;
    }

    // 获取智能体信息API
    async getAgents() {
        return this.request('/agents');
    }
}
