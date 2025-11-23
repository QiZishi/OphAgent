// app/static/js/ui.js
// UI渲染与交互逻辑

class UIManager {
    constructor() {
        this.currentConversationId = null;
        this.currentAgent = null;
        this.conversations = [];
        this.agents = [];
        this.selectedFiles = [];
        this.savedInputText = '';
        this.savedFiles = [];
        this.isSending = false;
        this.currentTypeItInstance = null;
        this.lastUserMessageId = null;
        this.lastAssistantMessageId = null;
        
        // 初始化智能体UI实例
        this.agentUIs = {
            interactive_vqa: null,
            lesion_localizer: null,
            aux_diagnosis: null,
            report_generator: null,
            knowledge_base: null
        };
    }

    async init() {
        // 清理任何遗留的UI元素
        this.cleanupResidualElements();
        
        // 初始化智能体UI实例
        this.initializeAgentUIs();
        
        await this.loadAgents();
        await this.loadConversations();
        this.bindEvents();
        this.showWelcome();
        this.applySettings(); // 应用保存的设置
        this.initButtonState(); // 初始化按钮状态
    }

    initializeAgentUIs() {
        console.log('[DEBUG] Initializing agent UI instances');
        
        // 检查智能体UI类是否存在，然后初始化
        try {
            if (typeof InteractiveVQAUI !== 'undefined') {
                this.agentUIs.interactive_vqa = new InteractiveVQAUI();
                console.log('[DEBUG] Initialized InteractiveVQAUI');
                // 同时设置到window对象上，以便向后兼容
                window.interactiveVQAUI = this.agentUIs.interactive_vqa;
            }
        } catch (error) {
            console.error('[DEBUG] Failed to initialize InteractiveVQAUI:', error);
        }
        
        try {
            if (typeof LesionLocalizerUI !== 'undefined') {
                this.agentUIs.lesion_localizer = new LesionLocalizerUI();
                console.log('[DEBUG] Initialized LesionLocalizerUI');
                // 同时设置到window对象上，以便向后兼容
                window.lesionLocalizerUI = this.agentUIs.lesion_localizer;
            }
        } catch (error) {
            console.error('[DEBUG] Failed to initialize LesionLocalizerUI:', error);
        }
        
        try {
            if (typeof AuxDiagnosisUI !== 'undefined') {
                this.agentUIs.aux_diagnosis = new AuxDiagnosisUI();
                console.log('[DEBUG] Initialized AuxDiagnosisUI');
                // 同时设置到window对象上，以便向后兼容
                window.auxDiagnosisUI = this.agentUIs.aux_diagnosis;
            }
        } catch (error) {
            console.error('[DEBUG] Failed to initialize AuxDiagnosisUI:', error);
        }
        
        try {
            if (typeof ReportGeneratorUI !== 'undefined') {
                this.agentUIs.report_generator = new ReportGeneratorUI();
                console.log('[DEBUG] Initialized ReportGeneratorUI');
                // 同时设置到window对象上，以便向后兼容
                window.reportGeneratorUI = this.agentUIs.report_generator;
            }
        } catch (error) {
            console.error('[DEBUG] Failed to initialize ReportGeneratorUI:', error);
        }
        
        try {
            if (typeof KnowledgeBaseUI !== 'undefined') {
                this.agentUIs.knowledge_base = new KnowledgeBaseUI();
                console.log('[DEBUG] Initialized KnowledgeBaseUI');
                // 同时设置到window对象上，以便向后兼容
                window.knowledgeBaseUI = this.agentUIs.knowledge_base;
            }
        } catch (error) {
            console.error('[DEBUG] Failed to initialize KnowledgeBaseUI:', error);
        }
        
        console.log('[DEBUG] Agent UI initialization complete:', this.agentUIs);
    }

    async loadAgents() {
        try {
            if (window.apiClient) {
                const response = await window.apiClient.getAgents();
                this.agents = response.agents || [];
            } else {
                throw new Error('API client not available');
            }
        } catch (error) {
            console.warn('Failed to load agents from API, using default configuration:', error);
            // 静默失败，使用默认配置，不显示错误消息给用户
            this.agents = [
                {
                    type: "interactive_vqa",
                    name: "智能问答",
                    description: "围绕上传的眼科影像进行自由问答，提供详细精准的解答",
                    welcome_message: "你好，我是智能问答智能体。请上传眼科影像并提出您的问题，我将基于图像内容为您提供详细的解答。",
                    icon: "💬"
                },
                {
                    type: "lesion_localizer",
                    name: "病灶定位",
                    description: "在用户上传的医学图像上用边界框标出检测到的病灶",
                    welcome_message: "你好，我是病灶定位智能体。请上传眼科医学影像，我将为您精确标注图像中的病灶位置。",
                    icon: "🎯"
                },
                {
                    type: "aux_diagnosis",
                    name: "辅助诊断",
                    description: "提供多种可能的疾病诊断，并附上置信度分数和分析依据",
                    welcome_message: "你好，我是辅助诊断智能体。请上传眼科影像，我将为您提供可能的诊断建议和分析依据。",
                    icon: "🩺"
                },
                {
                    type: "report_generator",
                    name: "报告生成",
                    description: "根据用户提供的资料，生成一份完整的、分章节的结构化诊断报告",
                    welcome_message: "你好，我是报告生成智能体。请上传眼科影像和相关信息，我将为您生成专业的诊断报告。",
                    icon: "📄"
                },
                {
                    type: "knowledge_base",
                    name: "眼科知识库",
                    description: "一个纯文本问答功能，解答眼科领域的专业知识",
                    welcome_message: "你好，我是眼科知识库。请直接输入您的眼科问题，我将为您提供专业的知识解答。",
                    icon: "🧠"
                }
            ];
        }
    }

    async loadConversations() {
        try {
            if (window.apiClient) {
                this.conversations = await window.apiClient.getConversations();
                this.renderConversationHistory();
            }
        } catch (error) {
            console.warn('Failed to load conversations:', error);
            // 静默失败，不显示错误给用户
            this.conversations = [];
        }
    }

    bindEvents() {
        // 侧边栏折叠按钮
        const sidebarToggle = document.getElementById('sidebar-toggle-btn');
        if (sidebarToggle) {
            sidebarToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleSidebar();
            });
        }

        // Logo点击也可以折叠侧边栏
        const logo = document.querySelector('.logo');
        if (logo) {
            logo.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleSidebar();
            });
        }

        // 新建对话
        const newChatBtn = document.getElementById('new-chat-btn');
        if (newChatBtn) {
            newChatBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.showAgentSelector();
            });
        }

        // 智能体选择
        this.bindAgentSelectorEvents();

        // 欢迎页面的智能体卡片
        document.addEventListener('click', (e) => {
            if (e.target.closest('.agent-card')) {
                const agentType = e.target.closest('.agent-card').dataset.agent;
                this.selectAgent(agentType);
            }
        });

        // 用户菜单
        this.bindUserMenuEvents();

        // 头部按钮
        this.bindHeaderButtonEvents();

        // 文件上传
        this.bindFileUploadEvents();

        // 消息发送
        this.bindMessageEvents();

        // 搜索功能
        this.bindSearchEvents();
    }

    bindUserMenuEvents() {
        const userMenu = document.getElementById('user-menu');
        const logoutBtn = document.getElementById('logout-btn');
        
        if (userMenu) {
            userMenu.addEventListener('click', (e) => {
                e.stopPropagation();
                const popup = userMenu.querySelector('.user-menu-popup');
                if (popup) {
                    const isVisible = popup.style.display === 'block';
                    popup.style.display = isVisible ? 'none' : 'block';
                }
            });
        }

        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.logout();
            });
        }

        // 点击其他地方关闭菜单
        document.addEventListener('click', (e) => {
            if (!e.target.closest('#user-menu')) {
                const popup = document.querySelector('.user-menu-popup');
                if (popup) {
                    popup.style.display = 'none';
                }
            }
        });

        // 切换账号按钮
        const switchAccountBtn = document.getElementById('switch-account-btn');
        if (switchAccountBtn) {
            switchAccountBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.switchAccount();
            });
        }
    }

    bindHeaderButtonEvents() {
        // 右上角导出按钮
        const exportBtn = document.getElementById('export-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.exportCurrentConversation());
        }

        // 右上角设置按钮
        const settingsBtn = document.getElementById('settings-btn');
        if (settingsBtn) {
            settingsBtn.addEventListener('click', () => this.showSettings());
        }
    }

    switchAccount() {
        if (confirm('确定要切换账号吗？当前会话将被保存。')) {
            // 清除当前登录状态
            localStorage.removeItem('access_token');
            // 重定向到登录页面
            window.location.href = '/';
        }
    }

    exportCurrentConversation() {
        if (!this.currentConversationId) {
            alert('请先选择一个对话');
            return;
        }

        // 创建导出选项菜单
        const existingMenu = document.querySelector('.export-conversation-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        const menu = document.createElement('div');
        menu.className = 'export-conversation-menu';
        menu.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            z-index: 1000;
        `;

        menu.innerHTML = `
            <h3 style="margin: 0 0 16px 0; font-size: 16px;">导出整个对话</h3>
            <button class="export-btn doc-btn" style="display: block; width: 100%; margin-bottom: 8px; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: white; cursor: pointer;">导出为DOC文件</button>
            <button class="export-btn pdf-btn" style="display: block; width: 100%; padding: 8px 16px; border: 1px solid #ddd; border-radius: 4px; background: white; cursor: pointer;">导出为PDF文件</button>
            <button class="cancel-btn" style="display: block; width: 100%; margin-top: 16px; padding: 8px 16px; border: none; background: #f5f5f5; border-radius: 4px; cursor: pointer;">取消</button>
        `;

        document.body.appendChild(menu);

        // 绑定事件
        menu.querySelector('.doc-btn').addEventListener('click', () => {
            this.exportConversationToDoc();
            menu.remove();
        });

        menu.querySelector('.pdf-btn').addEventListener('click', () => {
            this.exportConversationToPdf();
            menu.remove();
        });

        menu.querySelector('.cancel-btn').addEventListener('click', () => {
            menu.remove();
        });

        // 点击菜单外部关闭
        document.addEventListener('click', function closeMenu(e) {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        });
    }

    exportConversationToDoc() {
        if (!this.currentConversationId) {
            this.showError('请先选择一个对话');
            return;
        }

        // 获取所有消息
        const messageElements = document.querySelectorAll('.message-container');
        if (messageElements.length === 0) {
            this.showError('当前对话没有消息');
            return;
        }

        let content = '';
        
        messageElements.forEach((messageElement, index) => {
            const isUser = messageElement.classList.contains('user-message');
            const role = isUser ? '用户' : '助手';
            
            let messageContent = '';
            
            if (isUser) {
                const messageText = messageElement.querySelector('.message-text');
                if (messageText) {
                    messageContent = messageText.textContent.trim();
                }
            } else {
                // 助手消息
                const thinkingContent = messageElement.querySelector('.thinking-text-content');
                const finalContent = messageElement.querySelector('.final-answer-content');
                
                if (thinkingContent && thinkingContent.textContent.trim()) {
                    messageContent += '**思考过程：**\n' + thinkingContent.textContent.trim() + '\n\n';
                }
                
                if (finalContent) {
                    messageContent += '**回答：**\n' + finalContent.textContent.trim();
                }
            }
            
            if (messageContent) {
                content += `<div style="margin-bottom: 20px;"><strong>${role}:</strong><br/>${messageContent.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
            }
        });

        if (!content) {
            this.showError('没有找到可导出的内容');
            return;
        }

        const docContent = `
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>对话导出</title>
            </head>
            <body>
                <h1>灵瞳医疗AI系统 - 完整对话导出</h1>
                <div style="padding: 20px; border: 1px solid #ddd; margin: 20px 0;">
                    ${content}
                </div>
                <p style="color: #666; font-size: 12px;">导出时间: ${new Date().toLocaleString()}</p>
            </body>
            </html>
        `;

        const blob = new Blob([docContent], { type: 'application/msword' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `完整对话导出_${new Date().getTime()}.doc`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showToast('已导出完整对话为DOC文件', 'success');
    }

    exportConversationToPdf() {
        if (!this.currentConversationId) {
            this.showError('请先选择一个对话');
            return;
        }

        // 获取所有消息
        const messageElements = document.querySelectorAll('.message-container');
        if (messageElements.length === 0) {
            this.showError('当前对话没有消息');
            return;
        }

        let content = '';
        
        messageElements.forEach((messageElement, index) => {
            const isUser = messageElement.classList.contains('user-message');
            const role = isUser ? '用户' : '助手';
            
            let messageContent = '';
            
            if (isUser) {
                const messageText = messageElement.querySelector('.message-text');
                if (messageText) {
                    messageContent = messageText.textContent.trim();
                }
            } else {
                // 助手消息
                const thinkingContent = messageElement.querySelector('.thinking-text-content');
                const finalContent = messageElement.querySelector('.final-answer-content');
                
                if (thinkingContent && thinkingContent.textContent.trim()) {
                    messageContent += '**思考过程：**\n' + thinkingContent.textContent.trim() + '\n\n';
                }
                
                if (finalContent) {
                    messageContent += '**回答：**\n' + finalContent.textContent.trim();
                }
            }
            
            if (messageContent) {
                content += `<div style="margin-bottom: 20px; padding: 10px; border-left: 3px solid #ddd;"><strong>${role}:</strong><br/>${messageContent.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')}</div>`;
            }
        });

        if (!content) {
            this.showError('没有找到可导出的内容');
            return;
        }

        const printWindow = window.open('', '_blank');
        printWindow.document.write(`
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <title>完整对话导出</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .header { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 20px; }
                    .content { line-height: 1.6; margin: 20px 0; }
                    .footer { margin-top: 40px; color: #666; font-size: 12px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>灵瞳医疗AI系统 - 完整对话导出</h1>
                </div>
                <div class="content">
                    ${content}
                </div>
                <div class="footer">
                    导出时间: ${new Date().toLocaleString()}
                </div>
            </body>
            </html>
        `);
        printWindow.document.close();
        
        printWindow.onload = function() {
            printWindow.print();
            printWindow.close();
        };
        
        this.showToast('已打开打印对话框', 'success');
    }

    showSettings() {
        // 创建设置面板
        const existingPanel = document.querySelector('.settings-panel');
        if (existingPanel) {
            existingPanel.remove();
        }

        const panel = document.createElement('div');
        panel.className = 'settings-panel';
        panel.style.cssText = `
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            z-index: 1000;
            width: 400px;
            max-height: 80vh;
            overflow-y: auto;
        `;

        panel.innerHTML = `
            <h3 style="margin: 0 0 20px 0; font-size: 18px;">系统设置</h3>
            
            <div style="margin-bottom: 16px;">
                <label style="display: block; margin-bottom: 8px; font-weight: bold;">主题设置</label>
                <select id="theme-select" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                    <option value="light">浅色主题</option>
                    <option value="dark">深色主题</option>
                    <option value="auto">跟随系统</option>
                </select>
            </div>
            
            <div style="margin-bottom: 16px;">
                <label style="display: block; margin-bottom: 8px; font-weight: bold;">字体大小</label>
                <select id="font-size-select" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                    <option value="small">小</option>
                    <option value="normal">正常</option>
                    <option value="large">大</option>
                </select>
            </div>
            
            <div style="margin-bottom: 20px;">
                <label style="display: flex; align-items: center;">
                    <input type="checkbox" id="auto-save-checkbox" style="margin-right: 8px;">
                    自动保存对话
                </label>
            </div>
            
            <div style="display: flex; gap: 8px; justify-content: flex-end;">
                <button class="cancel-btn" style="padding: 8px 16px; border: 1px solid #ddd; background: white; border-radius: 4px; cursor: pointer;">取消</button>
                <button class="save-btn" style="padding: 8px 16px; border: none; background: #007bff; color: white; border-radius: 4px; cursor: pointer;">保存</button>
            </div>
        `;

        document.body.appendChild(panel);

        // 加载当前设置
        this.loadCurrentSettings(panel);

        // 绑定事件
        panel.querySelector('.save-btn').addEventListener('click', () => {
            this.saveSettings(panel);
            panel.remove();
        });

        panel.querySelector('.cancel-btn').addEventListener('click', () => {
            panel.remove();
        });

        // 点击外部关闭
        document.addEventListener('click', function closePanel(e) {
            if (!panel.contains(e.target)) {
                panel.remove();
                document.removeEventListener('click', closePanel);
            }
        });
    }

    loadCurrentSettings(panel) {
        // 从localStorage加载设置
        const theme = localStorage.getItem('theme') || 'light';
        const fontSize = localStorage.getItem('fontSize') || 'normal';
        const autoSave = localStorage.getItem('autoSave') === 'true';

        panel.querySelector('#theme-select').value = theme;
        panel.querySelector('#font-size-select').value = fontSize;
        panel.querySelector('#auto-save-checkbox').checked = autoSave;
    }

    saveSettings(panel) {
        const theme = panel.querySelector('#theme-select').value;
        const fontSize = panel.querySelector('#font-size-select').value;
        const autoSave = panel.querySelector('#auto-save-checkbox').checked;

        localStorage.setItem('theme', theme);
        localStorage.setItem('fontSize', fontSize);
        localStorage.setItem('autoSave', autoSave);

        // 应用设置
        this.applySettings();
        
        alert('设置已保存');
    }

    applySettings() {
        const theme = localStorage.getItem('theme') || 'light';
        const fontSize = localStorage.getItem('fontSize') || 'normal';

        // 应用主题
        document.body.className = theme === 'dark' ? 'dark-theme' : '';

        // 应用字体大小
        const fontSizeClass = fontSize === 'small' ? 'font-small' : fontSize === 'large' ? 'font-large' : '';
        if (fontSizeClass) {
            document.body.classList.add(fontSizeClass);
        }
    }

    bindFileUploadEvents() {
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        
        if (uploadBtn && fileInput) {
            // 移除之前的事件监听器
            uploadBtn.replaceWith(uploadBtn.cloneNode(true));
            fileInput.replaceWith(fileInput.cloneNode(true));
            
            // 重新获取元素引用
            const newUploadBtn = document.getElementById('upload-btn');
            const newFileInput = document.getElementById('file-input');
            
            newUploadBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                if (this.currentAgent === 'knowledge_base') {
                    this.showError('眼科知识库不支持文件上传，仅支持文本问答');
                    return;
                }
                if (!this.currentAgent) {
                    this.showError('请先选择一个智能体');
                    return;
                }
                
                // 重置文件输入
                newFileInput.value = '';
                newFileInput.click();
            });

            newFileInput.addEventListener('change', (e) => {
                if (e.target.files && e.target.files.length > 0) {
                    // 如果已有文件，合并而不是替换
                    const newFiles = Array.from(e.target.files);
                    this.selectedFiles = [...(this.selectedFiles || []), ...newFiles];
                    this.showFilePreview();
                }
            });
        }

        // 绑定全屏按钮
        const fullscreenBtn = document.getElementById('fullscreen-btn');
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.toggleFullscreenInput();
            });
        }
    }

    showFilePreview() {
        const filePreviewArea = document.getElementById('file-preview-area');
        if (!filePreviewArea) return;
        filePreviewArea.innerHTML = '';
        if (!this.selectedFiles || this.selectedFiles.length === 0) {
            filePreviewArea.style.display = 'none';
            return;
        }
        filePreviewArea.style.display = 'flex';
        this.selectedFiles.forEach((file, idx) => {
            const item = document.createElement('div');
            item.className = 'file-preview-item';
            if (file.type.startsWith('image/')) {
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.className = 'file-preview-thumb';
                img.onload = () => URL.revokeObjectURL(img.src);
                item.appendChild(img);
            }
            const name = document.createElement('span');
            name.className = 'file-preview-name';
            name.textContent = file.name;
            item.appendChild(name);
            const removeBtn = document.createElement('button');
            removeBtn.className = 'file-preview-remove';
            removeBtn.textContent = '×';
            removeBtn.onclick = () => { this.selectedFiles.splice(idx, 1); this.showFilePreview(); };
            item.appendChild(removeBtn);
            filePreviewArea.appendChild(item);
        });
    }

    bindMessageEvents() {
        const sendBtn = document.getElementById('send-btn');
        const userInput = document.getElementById('user-input');

        if (sendBtn) {
            sendBtn.addEventListener('click', () => {
                if (this.isSending) {
                    this.stopMessageGeneration();
                } else {
                    this.sendMessage();
                }
            });
        }

        if (userInput) {
            userInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            // 自动调整输入框高度（最多8行）
            userInput.addEventListener('input', () => {
                userInput.style.height = 'auto';
                const lineHeight = parseInt(getComputedStyle(userInput).lineHeight);
                const maxHeight = lineHeight * 8; // 8行的高度
                userInput.style.height = Math.min(userInput.scrollHeight, maxHeight) + 'px';
            });

            // 全屏输入功能
            userInput.addEventListener('keydown', (e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                    e.preventDefault();
                    this.toggleFullscreenInput();
                }
            });
        }
    }

    bindSearchEvents() {
        const searchInput = document.getElementById('conversation-search');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterConversations(e.target.value);
            });
        }
    }

    filterConversations(searchTerm) {
        const historyItems = document.querySelectorAll('.history-item');
        const searchLower = searchTerm.toLowerCase();

        historyItems.forEach(item => {
            const title = item.querySelector('.history-item-title').textContent.toLowerCase();
            if (title.includes(searchLower)) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });

        // 隐藏空的分组
        const groups = document.querySelectorAll('.history-group');
        groups.forEach(group => {
            const visibleItems = group.querySelectorAll('.history-item[style*="block"], .history-item:not([style*="none"])');
            if (visibleItems.length === 0) {
                group.style.display = 'none';
            } else {
                group.style.display = 'block';
            }
        });
    }

    toggleSidebar() {
        const appContainer = document.getElementById('app-container');
        if (appContainer) {
            appContainer.classList.toggle('sidebar-collapsed');
        }
    }

    showAgentSelector() {
        // 刷新页面，实现完全重置
        window.location.reload();
    }

    resetApplicationState() {
        // 清除当前选择的智能体和对话
        this.currentAgent = null;
        this.currentConversationId = null;
        
        // 清理当前对话
        this.clearCurrentConversation();
        
        // 重置文件选择状态
        this.selectedFiles = [];
        this.savedFiles = [];
        this.savedInputText = '';
        
        // 清空输入框
        const messageInput = document.getElementById('message-input');
        if (messageInput) {
            messageInput.value = '';
        }
        
        // 清空文件输入框
        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.value = '';
        }
        
        // 隐藏文件显示区域
        const fileDisplay = document.getElementById('file-display');
        if (fileDisplay) {
            fileDisplay.style.display = 'none';
            fileDisplay.innerHTML = '';
        }
        
        // 更新UI状态
        this.updateAgentSelection();
        this.showWelcome();
        this.updateConversationTitle('选择智能体开始对话');
        this.initButtonState();
        
        // 清除侧边栏中的智能体选择状态
        const agentButtons = document.querySelectorAll('.agent-btn');
        agentButtons.forEach(btn => {
            btn.classList.remove('active');
        });
        
        // 清除历史对话的高亮状态
        const historyItems = document.querySelectorAll('.history-item');
        historyItems.forEach(item => {
            item.classList.remove('active');
        });
        
        // 重新加载对话历史（刷新侧边栏）
        this.loadConversations();
        
        console.log('应用状态已重置，类似于刷新页面');
    }

    bindAgentSelectorEvents() {
        // 绑定侧边栏中的智能体按钮
        document.querySelectorAll('.agent-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const agentType = btn.dataset.agent;
                this.selectAgent(agentType);
            });
        });
    }

    async selectAgent(agentType) {
        if (this.currentAgent === agentType && this.currentConversationId) return;

        this.currentAgent = agentType;
        
        // 清理工作
        this.clearCurrentConversation();
        
        // 更新UI
        this.updateAgentSelectionInSidebar();
        this.updateConversationTitle(`正在与 ${this.agents.find(a => a.type === agentType)?.name || '智能体'} 对话...`);
        this.updateInputState();

        try {
            // 创建新对话
            const agent = this.agents.find(a => a.type === agentType);
            const conversation = await apiClient.createConversation(
                agent ? agent.name : '新对话',
                agentType
            );
            
            this.currentConversationId = conversation.id;
            
            // 重新加载对话历史并高亮当前会话
            await this.loadConversations();
            
            // 显示智能体欢迎消息
            this.showAgentWelcome(agentType);
            
            // WebSocket功能已被HTTP API替代，不需要连接
            console.log('[DEBUG] Conversation created successfully:', conversation.id);
            
        } catch (error) {
            console.error('Failed to create conversation:', error);
            this.showError('创建对话失败，请稍后重试');
            // 如果失败，重置状态
            this.currentAgent = null;
            this.currentConversationId = null;
            this.showWelcome();
        }
    }

    showAgentWelcome(agentType) {
        const agent = this.agents.find(a => a.type === agentType);
        const chatMessages = document.getElementById('chat-messages');
        const welcomeMessage = document.getElementById('welcome-message');

        if (chatMessages) {
            // 隐藏主欢迎页
            if (welcomeMessage) {
                welcomeMessage.style.display = 'none';
            }
            
            // 清空并显示智能体欢迎页
            chatMessages.innerHTML = '';
            const agentWelcome = document.createElement('div');
            agentWelcome.className = 'agent-welcome-container'; // 使用新的class
            
            if (agent) {
                agentWelcome.innerHTML = `
                    <div class="agent-welcome-icon">${agent.icon || '✨'}</div>
                    <h2 class="agent-welcome-title">欢迎使用 ${agent.name}</h2>
                    <p class="agent-welcome-description">${agent.welcome_message || ''}</p>
                `;
            } else {
                 agentWelcome.innerHTML = `<h2>欢迎</h2><p>请开始您的对话。</p>`;
            }
            chatMessages.appendChild(agentWelcome);
        }
    }

    clearCurrentConversation() {
        // 清空聊天消息区域
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.innerHTML = '';
        }
        
        // 断开当前WebSocket连接
        if (window.wsManager && this.currentConversationId) {
            window.wsManager.disconnect();
        }
        
        // 重置当前对话ID
        this.currentConversationId = null;
        
        // 清空文件选择
        this.selectedFiles = [];
        this.showFilePreview(); // 使用 showFilePreview 替代
        
        // 重置输入框
        const userInput = document.getElementById('user-input');
        if (userInput) {
            userInput.value = '';
            userInput.style.height = 'auto'; // 重置高度
        }
    }

    updateAgentSelectionInSidebar() {
        // 更新侧边栏智能体按钮状态
        const agentButtons = document.querySelectorAll('#agent-selector .agent-btn');
        agentButtons.forEach(btn => {
            btn.classList.toggle('active', btn.dataset.agent === this.currentAgent);
        });
    }

    showWelcome() {
        const chatMessages = document.getElementById('chat-messages');
        const welcomeMessage = document.getElementById('welcome-message');
        
        if (chatMessages && welcomeMessage) {
            // 清空聊天消息
            chatMessages.innerHTML = '';
            
            // 重新插入并显示欢迎消息
            chatMessages.appendChild(welcomeMessage);
            welcomeMessage.style.display = 'block';

            // 确保欢迎页中的智能体卡片事件是绑定的
            this.bindWelcomeAgentCardEvents();
        }
    }

    bindWelcomeAgentCardEvents() {
        const welcomeMessage = document.getElementById('welcome-message');
        if (welcomeMessage) {
            welcomeMessage.addEventListener('click', (e) => {
                const card = e.target.closest('.agent-card');
                if (card) {
                    const agentType = card.dataset.agent;
                    this.selectAgent(agentType);
                }
            });
        }
    }

    updateConversationTitle(title) {
        const titleElement = document.getElementById('conversation-title');
        if (titleElement) {
            titleElement.textContent = title;
        }
    }

    updateInputState() {
        const uploadBtn = document.getElementById('upload-btn');
        const userInput = document.getElementById('user-input');
        
        if (this.currentAgent === 'knowledge_base') {
            // 眼科知识库禁用文件上传
            if (uploadBtn) {
                uploadBtn.disabled = true;
                uploadBtn.style.opacity = '0.5';
                uploadBtn.title = '眼科知识库不支持文件上传';
            }
            
            if (userInput) {
                userInput.placeholder = '请输入您的眼科问题...';
            }
        } else {
            // 其他智能体启用文件上传
            if (uploadBtn) {
                uploadBtn.disabled = false;
                uploadBtn.style.opacity = '1';
                uploadBtn.title = '上传PDF文件或图片';
            }
            
            if (userInput) {
                userInput.placeholder = '给灵瞳发送消息...';
            }
        }
    }

    renderConversationHistory() {
        const historyList = document.getElementById('history-list');
        if (!historyList) return;

        historyList.innerHTML = '';

        if (this.conversations.length === 0) {
            historyList.innerHTML = '<p style="color: rgba(255,255,255,0.6); padding: 16px; text-align: center; font-size: 14px;">暂无对话历史</p>';
            return;
        }

        // 按时间分组
        const groups = this.groupConversationsByTime(this.conversations);
        
        Object.entries(groups).forEach(([groupName, conversations]) => {
            const groupElement = document.createElement('div');
            groupElement.className = 'history-group';
            
            groupElement.innerHTML = `
                <div class="history-group-title">${groupName}</div>
                ${conversations.map(conv => this.createHistoryItem(conv)).join('')}
            `;
            
            historyList.appendChild(groupElement);
        });
    }

    groupConversationsByTime(conversations) {
        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);
        const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
        const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

        const groups = {
            '今天': [],
            '昨天': [],
            '7天内': [],
            '30天内': [],
            '更早': []
        };

        conversations.forEach(conv => {
            const convDate = new Date(conv.created_at);
            
            if (convDate >= today) {
                groups['今天'].push(conv);
            } else if (convDate >= yesterday) {
                groups['昨天'].push(conv);
            } else if (convDate >= weekAgo) {
                groups['7天内'].push(conv);
            } else if (convDate >= monthAgo) {
                groups['30天内'].push(conv);
            } else {
                groups['更早'].push(conv);
            }
        });

        // 移除空组
        Object.keys(groups).forEach(key => {
            if (groups[key].length === 0) {
                delete groups[key];
            }
        });

        return groups;
    }

    createHistoryItem(conversation) {
        const isActive = conversation.id === this.currentConversationId;
        const agent = this.agents.find(a => a.type === conversation.agent_type);
        const agentIcon = agent ? agent.icon : '💬';
        
        return `
            <div class="history-item ${isActive ? 'active' : ''}" 
                 onclick="uiManager.loadConversation(${conversation.id})"
                 data-conversation-id="${conversation.id}">
                <div class="history-item-content">
                    <div class="history-item-title">
                        ${agentIcon} ${conversation.title}
                    </div>
                    <div class="history-item-time">
                        ${this.formatTime(conversation.created_at)}
                    </div>
                </div>
                <div class="history-item-menu">
                    <button class="control-btn" onclick="uiManager.showConversationMenu(event, ${conversation.id})" title="更多选项">
                        <i data-lucide="more-horizontal"></i>
                    </button>
                </div>
            </div>
        `;
    }

    formatTime(dateString) {
        if (!dateString) {
            return '时间未知';
        }
        
        try {
            // 直接解析日期字符串（后端现在返回北京时间）
            const date = new Date(dateString);
            
            // 检查日期是否有效
            if (isNaN(date.getTime())) {
                console.warn('Invalid date string:', dateString);
                return '时间格式错误';
            }
            
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);

            if (diffMs < 60000) { // 小于1分钟
                return '刚刚';
            } else if (diffMins < 60) {
                return `${diffMins}分钟前`;
            } else if (diffHours < 24) {
                return `${diffHours}小时前`;
            } else if (diffDays < 7) {
                return `${diffDays}天前`;
            } else {
                // 对于较旧的日期，显示具体日期
                const options = { 
                    year: 'numeric', 
                    month: 'short', 
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                };
                return date.toLocaleDateString('zh-CN', options);
            }
        } catch (error) {
            console.warn('Error parsing date:', dateString, error);
            return '时间格式错误';
        }
    }

    async loadConversation(conversationId) {
        // 如果点击的是当前对话，则不重新加载
        if (this.currentConversationId === conversationId) {
            return;
        }
        
        try {
            const conversation = await apiClient.getConversation(conversationId);
            
            this.currentConversationId = conversationId;
            this.currentAgent = conversation.agent_type;
            
            // 更新UI状态
            this.updateAgentSelectionInSidebar();
            this.updateConversationTitle(conversation.title);
            this.updateInputState();
            
            // 重新渲染历史记录以更新active状态
            this.renderConversationHistory();
            
            // 渲染对话消息
            this.renderConversationMessages(conversation.messages);
            
            // 不再连接WebSocket，因为我们使用HTTP API
            console.log('[DEBUG] Conversation loaded successfully:', conversationId);
            
        } catch (error) {
            console.error('Failed to load conversation:', error);
            this.showError('加载对话失败');
        }
    }

    renderConversationMessages(messages) {
        const chatMessages = document.getElementById('chat-messages');
        const welcomeMessage = document.getElementById('welcome-message');
        
        if (!chatMessages) return;
        
        // 隐藏欢迎消息
        if (welcomeMessage) {
            welcomeMessage.style.display = 'none';
        }
        
        // 清空现有消息
        chatMessages.innerHTML = '';
        
        // 渲染消息
        messages.forEach(message => {
            const messageElement = this.createMessageElement(message);
            chatMessages.appendChild(messageElement);
        });
        
        // 滚动到底部
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        // 重新创建图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    createMessageElement(message) {
        const messageContainer = document.createElement('div');
        messageContainer.className = `message-container ${message.role}-message group`;
        messageContainer.dataset.messageId = message.id;
        messageContainer.dataset.dbMessageId = message.id; // 添加数据库ID
        
        if (message.role === 'user') {
            messageContainer.innerHTML = this.createUserMessage(message);
        } else {
            messageContainer.innerHTML = this.createAssistantMessage(message);
        }
        
        return messageContainer;
    }

    createUserMessage(message) {
        let attachmentsHtml = '';
        
        // 处理数据库中的附件
        if (message.attachments && message.attachments.length > 0) {
            attachmentsHtml = `
                <div class="attachment-preview">
                    ${message.attachments.map(att => `
                        <div class="attachment-item">
                            <img src="${att.file_path}" alt="${att.original_filename}" style="max-width: 200px; max-height: 200px; border-radius: 8px;">
                        </div>
                    `).join('')}
                </div>
            `;
        }
        // 处理临时文件预览（发送时的临时显示）
        else if (message.file_path) {
            attachmentsHtml = `
                <div class="attachment-preview">
                    <div class="attachment-item">
                        <img src="${message.file_path}" alt="上传的图片" style="max-width: 200px; max-height: 200px; border-radius: 8px;">
                    </div>
                </div>
            `;
        }
        
        return `
            <img src="/static/icons/user_avatar.png" class="avatar">
            <div class="message-content-wrapper">
                <div class="message-bubble">
                    <div class="message-text">
                        ${message.content}
                        ${attachmentsHtml}
                    </div>
                </div>
            </div>
        `;
    }

    createAssistantMessage(message) {
        const hasThinking = message.thinking_content;
        const thinkingTime = message.thinking_time_s || 0;
        
        let thinkingHtml = '';
        if (hasThinking) {
            thinkingHtml = `
                <div class="thinking-phase">
                    <h4 class="thinking-title">
                        已完成深度思考（用时${thinkingTime}秒）
                    </h4>
                    <div class="thinking-text-content">${message.thinking_content}</div>
                </div>
            `;
        }
        
        return `
            <img src="/static/icons/system_logo.png" class="avatar">
            <div class="message-content-wrapper">
                <div class="message-bubble">
                    ${thinkingHtml}
                    <div class="final-answer-phase">
                        <div class="final-answer-content markdown-body">${this.renderMarkdownContent(message.content)}</div>
                    </div>
                </div>
                <div class="message-footer">
                    <p class="disclaimer">本回答由AI生成，内容仅供参考，如有不适请及时就医。</p>
                    <div class="controls opacity-100">
                        <button class="control-btn" onclick="uiManager.copyMessage('${message.id}')" title="复制">
                            <i data-lucide="copy"></i>
                        </button>
                        <button class="control-btn" onclick="uiManager.regenerateMessage('${message.id}')" title="重新生成">
                            <i data-lucide="refresh-cw"></i>
                        </button>
                        <button class="control-btn" onclick="uiManager.exportMessage('${message.id}')" title="导出">
                            <i data-lucide="download"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    renderMarkdownContent(content) {
        if (typeof marked !== 'undefined') {
            return marked.parse(content);
        }
        return content.replace(/\n/g, '<br>');
    }

    handleFileSelection(files) {
        this.selectedFiles = Array.from(files);
        this.showSelectedFiles();
    }

    showSelectedFiles() {
        const fileDisplay = document.getElementById('file-display');
        if (!fileDisplay) return;

        if (this.selectedFiles.length === 0) {
            fileDisplay.style.display = 'none';
            return;
        }

        fileDisplay.style.display = 'flex';
        fileDisplay.innerHTML = '';

        this.selectedFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            
            // 创建图片预览（如果是图片文件）
            if (file.type.startsWith('image/')) {
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.className = 'file-preview';
                img.onload = () => URL.revokeObjectURL(img.src);
                
                const removeBtn = document.createElement('button');
                removeBtn.className = 'file-remove-btn';
                removeBtn.innerHTML = '×';
                removeBtn.onclick = () => this.removeFile(index);
                
                fileItem.appendChild(img);
                fileItem.appendChild(removeBtn);
            } else {
                // 非图片文件显示文件名
                const fileName = document.createElement('span');
                fileName.className = 'file-name';
                fileName.textContent = file.name;
                
                const removeBtn = document.createElement('button');
                removeBtn.className = 'file-remove-btn';
                removeBtn.innerHTML = '×';
                removeBtn.onclick = () => this.removeFile(index);
                
                fileItem.appendChild(fileName);
                fileItem.appendChild(removeBtn);
            }
            
            fileDisplay.appendChild(fileItem);
        });
    }

    removeFile(index) {
        this.selectedFiles.splice(index, 1);
        this.showSelectedFiles();
        
        // 清空文件输入框
        const fileInput = document.getElementById('file-input');
        if (fileInput) {
            fileInput.value = '';
        }
    }

    updateFileDisplay() {
        this.showSelectedFiles();
    }

    // 显示发送按钮，隐藏中断按钮
    showSendButton() {
        console.log('[DEBUG] showSendButton called');
        const sendBtn = document.getElementById('send-btn');
        
        if (sendBtn) {
            sendBtn.style.display = 'block';
            sendBtn.disabled = false;
            console.log('[DEBUG] Send button: displayed and enabled');
        } else {
            console.error('[DEBUG] Send button not found');
        }
    }

    // 初始化按钮状态（显示发送按钮）
    initButtonState() {
        this.showSendButton();
    }

    // 保存当前输入状态
    saveInputState() {
        const userInput = document.getElementById('user-input');
        if (userInput) {
            this.savedInputText = userInput.value;
            this.savedFiles = [...this.selectedFiles];
        }
    }

    // 恢复输入状态
    restoreInputState() {
        const userInput = document.getElementById('user-input');
        if (userInput) {
            userInput.value = this.savedInputText;
            this.selectedFiles = [...(this.savedFiles || [])];
            this.showFilePreview();
        }
    }

    async sendMessage() {
        // 防止重复发送
        if (this.isSending) {
            return;
        }

        const userInput = document.getElementById('user-input');
        const message = userInput.value.trim();
        
        if (!message && this.selectedFiles.length === 0) return;
        
        // 检查是否选择了智能体
        if (!this.currentAgent) {
            this.showError('请先选择一个智能体再开始对话。');
            return;
        }
        
        // 如果没有对话ID，则说明是新对话的第一次消息
        if (!this.currentConversationId) {
            console.warn("No conversation ID, but trying to send message. This should have been handled by selectAgent.");
            this.showError("发生未知错误，请重新选择智能体。");
            return;
        }

        // 设置发送状态
        this.isSending = true;
        this.updateButtonToStop();

        // 保存当前输入状态以供中断后恢复
        this.saveInputState();

        // 保存当前文件列表用于API调用
        const filesToSend = [...this.selectedFiles];

        // 立即清空输入框和文件选择
        userInput.value = '';
        userInput.style.height = 'auto';
        this.selectedFiles = [];
        this.showFilePreview();

        // 隐藏智能体欢迎页
        const agentWelcome = document.querySelector('.agent-welcome-container');
        if (agentWelcome) {
            agentWelcome.style.display = 'none';
        }

        try {
            // 1. 创建并显示用户消息
            const userMessageData = {
                id: `user-${Date.now()}`,
                role: 'user',
                content: message,
                attachments: filesToSend.map(file => ({
                    file_path: URL.createObjectURL(file),
                    original_filename: file.name
                }))
            };
            const userMessageElement = this.createMessageElement(userMessageData);
            const chatMessages = document.getElementById('chat-messages');
            chatMessages.appendChild(userMessageElement);
            this.lastUserMessageId = userMessageData.id;
            

            // 2. 创建并显示AI助手消息的占位符
            const assistantMessageId = `assistant-${Date.now()}`;
            const assistantMessageElement = this.createAssistantMessagePlaceholder(assistantMessageId);
            chatMessages.appendChild(assistantMessageElement);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            this.lastAssistantMessageId = assistantMessageId;

            // 重新创建所有图标
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }

            // 3. 通过HTTP API发送消息到后端
            console.log('[DEBUG] Sending message via HTTP API...');
            console.log('[DEBUG] Current agent:', this.currentAgent);
            console.log('[DEBUG] Conversation ID:', this.currentConversationId);
            console.log('[DEBUG] Files to send count:', filesToSend.length);
            
            try {
                const response = await apiClient.sendMessage(
                    this.currentConversationId, 
                    message, 
                    filesToSend
                );
                console.log('[DEBUG] API response:', response);
                
                // 更新消息元素的数据库ID
                if (response.message_id || (response.payload && response.payload.message_id)) {
                    const messageId = response.message_id || response.payload.message_id;
                    const messageElement = document.querySelector(`[data-message-id="${assistantMessageId}"]`);
                    if (messageElement) {
                        messageElement.dataset.dbMessageId = messageId;
                        console.log('[DEBUG] Updated message element with DB ID:', messageId);
                    }
                }
                
                // 处理响应数据
                if (response.type === 'complete_response') {
                    this.handleCompleteResponse(response.payload, assistantMessageId);
                } else if (response.type === 'final_structured_content') {
                    // 对于结构化内容，直接使用payload进行处理
                    this.handleCompleteResponse(response.payload, assistantMessageId);
                } else if (response.type === 'error') {
                    throw new Error(response.payload.message);
                } else {
                    // 处理其他响应类型
                    this.handleCompleteResponse({
                        thinking_content: response.thinking_content || '',
                        answer_content: response.answer_content || response.content || '未知响应格式'
                    }, assistantMessageId);
                }
                
            } catch (error) {
                console.error('[DEBUG] Error sending message:', error);
                throw error;
            }

            // 发送成功，重置状态
            this.isSending = false;
            
            // 注意：按钮状态的恢复会在finalizeMessage中处理
            // 这里不需要立即恢复，因为消息可能还在打字机效果中

        } catch (error) {
            console.error('Failed to send message:', error);
            
            this.showError('发送消息失败，请检查网络连接并重试。');
            
            // 发送失败时移除已显示的消息
            const assistantMessages = document.querySelectorAll('.assistant-message[data-message-id^="assistant-"]');
            assistantMessages.forEach(msg => {
                const messageId = msg.dataset.messageId;
                if (messageId && messageId.startsWith('assistant-')) {
                    msg.remove();
                }
            });
            
            const userMessages = document.querySelectorAll('.user-message[data-message-id^="user-"]');
            if (userMessages.length > 0) {
                const lastUserMessage = userMessages[userMessages.length - 1];
                const messageId = lastUserMessage.dataset.messageId;
                if (messageId && messageId.startsWith('user-')) {
                    lastUserMessage.remove();
                }
            }
            
            // 恢复输入状态和按钮
            this.restoreInputState();
            this.isSending = false;
            this.updateButtonToSend();
            
            // 如果聊天区域为空，显示智能体欢迎页
            const chatMessages = document.getElementById('chat-messages');
            const messageContainers = chatMessages.querySelectorAll('.message-container');
            if (messageContainers.length === 0) {
                this.showAgentWelcome(this.currentAgent);
            }
        }
    }

    createAssistantMessagePlaceholder(messageId) {
        const element = document.createElement('div');
        element.className = 'message-container assistant-message group';
        element.dataset.messageId = messageId;
        element.dataset.currentResult = '0'; // 当前显示的结果索引
        element.innerHTML = `
            <img src="/static/icons/system_logo.png" class="avatar">
            <div class="message-content-wrapper">
                <div class="message-bubble">
                    <div class="thinking-phase" style="display: block;">
                        <h4 class="thinking-title">
                            <div class="spinner"></div>正在思考...
                        </h4>
                        <div class="thinking-text-content"></div>
                    </div>
                    <div class="final-answer-phase" style="display: none;">
                        <div class="results-container">
                            <div class="final-answer-content markdown-body result-content active" data-result-index="0"></div>
                        </div>
                        <div class="result-navigation" style="display: none;">
                            <button class="nav-btn prev-btn" onclick="uiManager.showPreviousResult('${messageId}')" title="上一个结果">
                                <i data-lucide="chevron-left"></i>
                            </button>
                            <span class="result-indicator">1 / 1</span>
                            <button class="nav-btn next-btn" onclick="uiManager.showNextResult('${messageId}')" title="下一个结果">
                                <i data-lucide="chevron-right"></i>
                            </button>
                        </div>
                    </div>
                </div>
                <div class="message-footer">
                    <p class="disclaimer">本回答由AI生成，内容仅供参考，如有不适请及时就医。</p>
                    <div class="controls opacity-0 transition-opacity">
                        <button class="control-btn" onclick="uiManager.copyMessage('${messageId}')" title="复制"><i data-lucide="copy"></i></button>
                        <button class="control-btn" onclick="uiManager.regenerateMessage('${messageId}')" title="重新生成"><i data-lucide="refresh-cw"></i></button>
                        <button class="control-btn" onclick="uiManager.exportMessage('${messageId}')" title="导出"><i data-lucide="download"></i></button>
                    </div>
                </div>
            </div>
        `;
        return element;
    }

    getConversationHistory() {
        const messages = [];
        const messageElements = document.querySelectorAll('.message-container');
        
        messageElements.forEach(element => {
            const role = element.classList.contains('user-message') ? 'user' : 'assistant';
            let content = '';
            
            if (role === 'user') {
                const messageText = element.querySelector('.message-text');
                if (messageText) {
                    content = messageText.textContent.trim();
                }
            } else {
                // 获取当前显示的结果内容
                const activeResult = element.querySelector('.result-content.active');
                if (activeResult) {
                    // 获取原始文本内容，而不是HTML
                    const textContent = activeResult.textContent.trim();
                    if (textContent) {
                        content = textContent;
                    }
                } else {
                    // 兼容旧版本结构
                    const finalContent = element.querySelector('.final-answer-content');
                    if (finalContent) {
                        content = finalContent.textContent.trim();
                    }
                }
            }
            
            if (content) {
                messages.push({
                    role: role,
                    content: content
                });
            }
        });
        
        console.log('[DEBUG] Conversation history:', messages);
        return messages;
    }

    handleCompleteResponse(payload, messageId) {
        console.log('[DEBUG] handleCompleteResponse called with:', payload, messageId);
        
        try {
            // 处理各种可能的响应格式
            let thinking_content, answer_content;
            
            if (payload.thinking_content !== undefined && payload.answer_content !== undefined) {
                // 标准格式
                thinking_content = payload.thinking_content;
                answer_content = payload.answer_content;
            } else if (payload.content !== undefined) {
                // 简单格式，只有内容
                answer_content = payload.content;
            } else if (typeof payload === 'string') {
                // 字符串格式
                answer_content = payload;
            } else if (payload.response !== undefined) {
                // 嵌套格式
                if (typeof payload.response === 'string') {
                    answer_content = payload.response;
                } else {
                    answer_content = JSON.stringify(payload.response);
                }
            } else {
                // 未知格式，尝试转为JSON字符串
                console.warn('[DEBUG] Unknown response format:', payload);
                answer_content = JSON.stringify(payload);
            }
            
            // 获取消息元素
            const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
            if (!messageElement) {
                console.error('[DEBUG] Message element not found:', messageId);
                // 如果找不到消息元素，也要恢复按钮状态
                this.showSendButton();
                this.isSending = false;
                this.savedInputText = '';
                this.savedFiles = [];
                return;
            }

            // 处理thinking内容
            if (thinking_content) {
                console.log('[DEBUG] Starting thinking phase...');
                const thinkingPhase = messageElement.querySelector('.thinking-phase');
                if (thinkingPhase) thinkingPhase.style.display = 'block';

                const thinkingContent = messageElement.querySelector('.thinking-text-content');

                // 将思考内容与第一个结果关联
                const firstResult = messageElement.querySelector('.result-content[data-result-index="0"]');
                if (firstResult) {
                    firstResult.dataset.thinkingContent = thinking_content;
                }

                if (thinkingContent) {
                    // 思考阶段的打字机效果
                    this.typewriterEffect(thinkingContent, thinking_content, 30, () => {
                        console.log('[DEBUG] Thinking phase completed');
                        
                        // 思考完成后，更新标题并添加折叠功能
                        const thinkingTitle = messageElement.querySelector('.thinking-title');
                        if (thinkingTitle) {
                            thinkingTitle.innerHTML = `
                                <div class="spinner" style="display: none;"></div>
                                <span class="thinking-toggle" style="cursor: pointer;">🤔 已完成深度思考 <span class="collapse-icon">▼</span></span>
                            `;
                            this.bindThinkingToggle(messageElement);
                        }
                        
                        // 思考完成后，开始输出最终结果
                        this.startAnswerPhase(messageElement, answer_content);
                    });
                } else {
                    // 如果没有找到thinking-text-content元素，直接进入答案阶段
                    console.log('[DEBUG] No thinking-text-content element found, skipping to answer phase');
                    this.startAnswerPhase(messageElement, answer_content);
                }
            } else {
                // 没有thinking内容，直接开始answer阶段
                this.startAnswerPhase(messageElement, answer_content);
            }
            
        } catch (error) {
            console.error('[DEBUG] Error in handleCompleteResponse:', error);
            // 发生错误时，确保恢复按钮状态
            this.showSendButton();
            this.isSending = false;
            this.savedInputText = '';
            this.savedFiles = [];
        }
    }

    startAnswerPhase(messageElement, answer_content) {
        console.log('[DEBUG] Starting answer phase...');

        const thinkingPhase = messageElement.querySelector('.thinking-phase');
        if (thinkingPhase) {
            const thinkingTitle = thinkingPhase.querySelector('.thinking-title');
            // 如果没有思考内容（标题仍然是"正在思考..."），则隐藏思考区域
            if (thinkingTitle && thinkingTitle.textContent.includes('正在思考')) {
                thinkingPhase.style.display = 'none';
            }
        }
        
        if (!answer_content) {
            console.log('[DEBUG] No answer content to display');
            this.finalizeMessage(messageElement);
            return;
        }

        const finalPhase = messageElement.querySelector('.final-answer-phase');
        if (finalPhase) finalPhase.style.display = 'block';
        
        // 使用第一个结果内容元素（对于新生成的消息）
        const finalContent = messageElement.querySelector('.result-content[data-result-index="0"]');
        if (finalContent) {
            // 尝试解析可能的结构化数据
            let structuredData = null;
            try {
                if (typeof answer_content === 'string' && 
                   (answer_content.trim().startsWith('{') || answer_content.trim().startsWith('['))) {
                    // 尝试解析为JSON
                    structuredData = JSON.parse(answer_content);
                    console.log('[DEBUG] Successfully parsed structured data:', structuredData);
                }
            } catch (e) {
                console.warn('[DEBUG] Failed to parse answer_content as JSON:', e);
                // 继续使用原始文本
            }
            
            // 对于结构化数据，直接渲染，无需打字机效果
            if (structuredData) {
                console.log('[DEBUG] Using structured data rendering');
                // 存储结构化数据到元素属性中，便于后续处理
                finalContent.dataset.structuredData = JSON.stringify(structuredData);
                
                // 为特定智能体使用特殊处理
                if (this.currentAgent === 'lesion_localizer' || 
                    this.currentAgent === 'aux_diagnosis') {
                    // 清空内容，让 agent-specific UI 模块来渲染
                    finalContent.innerHTML = '';
                    // 直接完成消息，会触发finalizeMessage中的智能体特定UI处理
                    this.finalizeMessage(messageElement, structuredData);
                    return;
                } else {
                    // 其他智能体，显示格式化的JSON
                    finalContent.innerHTML = `<pre class="json-content">${JSON.stringify(structuredData, null, 2)}</pre>`;
                    this.finalizeMessage(messageElement, structuredData);
                    return;
                }
            }
            
            // 对于普通文本，使用打字机效果
            this.typewriterEffect(finalContent, answer_content, 20, () => {
                console.log('[DEBUG] Answer phase completed');
                // 答案输出完成后的回调
                this.finalizeMessage(messageElement);
            });
        } else {
            // 如果没有找到result-content元素，直接调用finalizeMessage
            console.log('[DEBUG] No result-content element found, calling finalizeMessage directly');
            this.finalizeMessage(messageElement);
        }
    }

    typewriterEffect(element, text, speed, callback) {
        console.log('[DEBUG] typewriterEffect called:', text.length, 'characters');
        
        // 确保清除任何可能存在的计时器
        if (this.fallbackTypewriterTimer) {
            clearInterval(this.fallbackTypewriterTimer);
            this.fallbackTypewriterTimer = null;
        }

        if (typeof TypeIt !== 'undefined') {
            // 使用TypeIt库
            this.currentTypeItInstance = new TypeIt(element, {
                strings: [text],
                speed: speed,
                cursor: false,
                lifeLike: true,
                afterComplete: () => {
                    this.currentTypeItInstance = null;
                    if (callback) callback();
                }
            });
            this.currentTypeItInstance.go();
        } else {
            // 简单的打字机效果fallback
            element.textContent = '';
            let i = 0;
            const timer = setInterval(() => {
                if (i < text.length) {
                    element.textContent += text.charAt(i);
                    i++;
                } else {
                    clearInterval(timer);
                    this.fallbackTypewriterTimer = null; // 完成后清除
                    if (callback) callback();
                }
            }, speed);
            this.fallbackTypewriterTimer = timer; // 保存计时器ID
        }
    }

    // 通用的文本输入方法
    async typeText(text, element, speed = 20) {
        return new Promise((resolve) => {
            this.typewriterEffect(element, text, speed, resolve);
        });
    }

    finalizeMessage(messageElement, structuredData = null) {
        console.log('[DEBUG] finalizeMessage called', structuredData ? 'with structured data' : 'without structured data');
        
        // 如果提供了结构化数据，保存到元素属性中
        if (structuredData) {
            messageElement.dataset.hasStructuredData = 'true';
            // 已经在startAnswerPhase中处理过结构化数据，不需要再解析markdown
        } 
        // 没有提供结构化数据，但可能从元素属性中获取
        else {
            // 检查元素是否已有结构化数据
            const resultContent = messageElement.querySelector('.result-content.active');
            if (resultContent && resultContent.dataset.structuredData) {
                try {
                    structuredData = JSON.parse(resultContent.dataset.structuredData);
                    messageElement.dataset.hasStructuredData = 'true';
                    console.log('[DEBUG] Retrieved structured data from element attribute');
                } catch (e) {
                    console.warn('[DEBUG] Failed to parse structuredData from element attribute', e);
                }
            }
            
            // 如果没有结构化数据，按常规方式处理markdown
            if (!structuredData) {
                // 重新渲染markdown - 处理所有结果内容
                const resultContents = messageElement.querySelectorAll('.result-content');
                if (resultContents.length > 0 && typeof marked !== 'undefined') {
                    resultContents.forEach(content => {
                        // 检查是否含有class="json-content"，有则跳过markdown处理
                        if (!content.querySelector('.json-content')) {
                            const markdownText = content.textContent;
                            content.innerHTML = marked.parse(markdownText);
                        }
                    });
                }
            }
        }
        
        // 重新创建图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons({ nodes: [messageElement] });
        }

        // 显示控制按钮
        const controls = messageElement.querySelector('.controls');
        if (controls) {
            controls.style.opacity = '1';
        }

        // 强制刷新图标，特别是新创建的消息元素
        setTimeout(() => {
            if (typeof lucide !== 'undefined') {
                lucide.createIcons();
            }
            // 如果全局刷新函数存在，也调用它
            if (typeof window.refreshIcons === 'function') {
                window.refreshIcons();
            }
        }, 100);

        // 调用特定智能体的UI处理 - 传递结构化数据
        this.handleAgentSpecificUI(messageElement, structuredData);

        // 恢复发送按钮状态
        this.isSending = false;
        this.updateButtonToSend();
        
        // 清空保存的输入状态
        this.savedInputText = '';
        this.savedFiles = [];
    }

    // 尝试从响应内容中提取结构化数据
    extractStructuredContent(html) {
        try {
            // 尝试查找JSON对象
            const jsonMatches = html.match(/\{[\s\S]*?\}/g);
            if (jsonMatches) {
                for (const match of jsonMatches) {
                    try {
                        return JSON.parse(match);
                    } catch (e) {
                        // 不是有效的JSON，继续尝试下一个匹配
                        continue;
                    }
                }
            }
            
            // 如果没有找到JSON，检查是否有带有data-attributes的元素
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = html;
            
            const dataElements = tempDiv.querySelectorAll('[data-structured]');
            if (dataElements.length > 0) {
                const dataElement = dataElements[0];
                const structuredData = dataElement.getAttribute('data-structured');
                if (structuredData) {
                    try {
                        return JSON.parse(structuredData);
                    } catch (e) {
                        console.warn('Invalid JSON in data-structured attribute');
                    }
                }
            }
            
            return null;
        } catch (error) {
            console.error('Error extracting structured content:', error);
            return null;
        }
    }
    
    // 处理病灶定位数据
    processBoundingBoxData(messageElement, data) {
        console.log('[DEBUG] Processing bounding box data:', data);
        
        if (!data) {
            // 查找响应中是否包含final_structured_content类型的数据
            const structuredContentDiv = messageElement.querySelector('.final-answer-content [data-type="final_structured_content"]');
            if (structuredContentDiv) {
                try {
                    data = JSON.parse(structuredContentDiv.textContent);
                } catch (e) {
                    console.warn('Failed to parse final_structured_content:', e);
                }
            }
        }
        
        // 如果找不到任何结构化数据，尝试使用lesion_localizer.js中的全局UI实例
        if (window.lesionLocalizerUI && typeof window.lesionLocalizerUI.renderLesionLocalization === 'function') {
            console.log('[DEBUG] Calling lesionLocalizerUI.renderLesionLocalization with message element');
            
            // 尝试在消息内容中查找上传的图像URL
            const userMessage = messageElement.previousElementSibling;
            let imageUrl = null;
            
            if (userMessage && userMessage.classList.contains('user-message')) {
                const imgs = userMessage.querySelectorAll('img');
                if (imgs.length > 0) {
                    imageUrl = imgs[0].src;
                }
            }
            
            // 如果data中有image_url，优先使用
            if (data && data.image_url) {
                imageUrl = data.image_url;
            }
            
            // 如果找到了数据，调用lesion_localizer的渲染函数
            if (data && data.boxes && imageUrl) {
                const renderData = {
                    image_url: imageUrl,
                    boxes: data.boxes
                };
                window.lesionLocalizerUI.renderLesionLocalization(messageElement, renderData);
            } else if (this.agentUIs.lesion_localizer) {
                // 如果无法找到结构化数据，但存在lesion_localizer实例，直接传递消息元素
                this.agentUIs.lesion_localizer.renderLesionLocalization(messageElement, {});
            }
        } else {
            console.warn('lesionLocalizerUI not found or renderLesionLocalization not available');
        }
    }

    showToast(message, type = 'info') {
        // 创建toast元素
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: ${type === 'success' ? '#4CAF50' : type === 'error' ? '#f44336' : '#2196F3'};
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 10000;
            font-size: 14px;
            max-width: 300px;
            word-wrap: break-word;
            opacity: 0;
            transform: translateX(100%);
            transition: all 0.3s ease;
        `;
        
        toast.textContent = message;
        document.body.appendChild(toast);
        
        // 显示动画
        setTimeout(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateX(0)';
        }, 100);
        
        // 自动消失
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }

    showSuccess(message) {
        // 创建成功提示Toast
        const toast = document.createElement('div');
        toast.className = 'toast success-toast';
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 14px;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            transform: translateX(100%);
            transition: transform 0.3s ease;
            max-width: 300px;
            word-wrap: break-word;
        `;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        // 显示动画
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 10);
        
        // 3秒后隐藏
        setTimeout(() => {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }

    showError(message) {
        // 创建错误提示
        const errorElement = document.createElement('div');
        errorElement.className = 'error';
        errorElement.textContent = message;
        
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            chatMessages.appendChild(errorElement);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            
            // 3秒后自动移除
            setTimeout(() => {
                if (errorElement.parentNode) {
                    errorElement.parentNode.removeChild(errorElement);
                }
            }, 3000);
        }
    }

    logout() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('token_type');
        window.location.href = '/';
    }

    // 消息操作方法（占位符）
    copyMessage(messageId) {
        console.log('Copy message:', messageId);
        
        // 找到对应的消息元素
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) {
            console.error('Message element not found:', messageId);
            return;
        }
        
        // 获取消息内容
        let content = '';
        
        // 如果有thinking内容，先复制thinking
        const thinkingContent = messageElement.querySelector('.thinking-text-content');
        if (thinkingContent && thinkingContent.textContent.trim()) {
            content += '**思考过程：**\n' + thinkingContent.textContent.trim() + '\n\n';
        }
        
        // 复制最终答案内容
        const finalContent = messageElement.querySelector('.final-answer-content');
        if (finalContent) {
            content += '**回答：**\n' + finalContent.textContent.trim();
        }
        
        // 如果没有内容，尝试获取消息文本
        if (!content) {
            const messageText = messageElement.querySelector('.message-text');
            if (messageText) {
                content = messageText.textContent.trim();
            }
        }
        
        if (!content) {
            this.showError('没有找到可复制的内容');
            return;
        }
        
        // 复制到剪贴板
        if (navigator.clipboard) {
            navigator.clipboard.writeText(content).then(() => {
                this.showToast('内容已复制到剪贴板', 'success');
            }).catch(err => {
                console.error('复制失败:', err);
                this.fallbackCopyText(content);
            });
        } else {
            this.fallbackCopyText(content);
        }
    }
    
    fallbackCopyText(text) {
        // 备用复制方法
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.top = '-1000px';
        textArea.style.left = '-1000px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            const successful = document.execCommand('copy');
            if (successful) {
                this.showToast('内容已复制到剪贴板', 'success');
            } else {
                this.showError('复制失败，请手动复制');
            }
        } catch (err) {
            console.error('复制失败:', err);
            this.showError('复制失败，请手动复制');
        }
        
        document.body.removeChild(textArea);
    }

    regenerateMessage(messageId) {
        console.log('Regenerate message:', messageId);
        
        // 防止重复生成
        if (this.isSending) {
            this.showError('正在处理中，请稍候');
            return;
        }
        
        // 找到对应的消息元素
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) {
            console.error('Message element not found:', messageId);
            return;
        }
        
        // 检查是否是助手消息
        if (!messageElement.classList.contains('assistant-message')) {
            this.showError('只能重新生成助手消息');
            return;
        }
        
        // 获取真实的数据库消息ID
        const realMessageId = messageElement.getAttribute('data-db-message-id');
        if (!realMessageId) {
            this.showError('无法获取消息ID，请刷新页面重试');
            return;
        }
        
        // 直接调用重新生成API
        this.regenerateMessageWithAPI(messageElement, realMessageId);
    }
    
    async regenerateMessageWithAPI(messageElement, messageId) {
        try {
            this.isSending = true;
            
            // 不重置现有的消息内容，而是为新结果做准备
            const resultsContainer = messageElement.querySelector('.results-container');
            const resultNavigation = messageElement.querySelector('.result-navigation');
            
            // 创建新的结果容器
            const newResultIndex = resultsContainer.children.length;
            const newResultElement = document.createElement('div');
            newResultElement.className = 'final-answer-content markdown-body result-content';
            newResultElement.dataset.resultIndex = newResultIndex;
            newResultElement.style.display = 'none'; // 先隐藏
            
            // 添加到结果容器
            resultsContainer.appendChild(newResultElement);
            
            // 显示思考阶段
            const thinkingPhase = messageElement.querySelector('.thinking-phase');
            const finalPhase = messageElement.querySelector('.final-answer-phase');
            const thinkingTitle = messageElement.querySelector('.thinking-title');
            const thinkingContent = messageElement.querySelector('.thinking-text-content');
            
            if (thinkingPhase) thinkingPhase.style.display = 'block';
            if (finalPhase) finalPhase.style.display = 'none'; // 重新生成时先隐藏旧答案
            if (thinkingTitle) {
                thinkingTitle.innerHTML = `<div class="spinner"></div>正在重新生成...`;
            }
            if (thinkingContent) thinkingContent.textContent = '';
            
            // 隐藏控制按钮
            const controls = messageElement.querySelector('.controls');
            if (controls) {
                controls.style.opacity = '0';
            }
            
            // 调用重新生成API
            const response = await apiClient.regenerateMessage(this.currentConversationId, messageId);
            
            let answer_content;
            let thinking_content;
            let structuredData = null;

            // 统一处理响应数据
            if (response.type === 'complete_response' && response.payload) {
                thinking_content = response.payload.thinking_content;
                answer_content = response.payload.answer_content;
                try {
                    // 对于特殊智能体，answer_content本身就是JSON字符串
                    if ((this.currentAgent === 'lesion_localizer' || this.currentAgent === 'aux_diagnosis') && 
                        typeof answer_content === 'string' && (answer_content.trim().startsWith('{') || answer_content.trim().startsWith('['))) {
                        structuredData = JSON.parse(answer_content);
                    }
                } catch (e) {
                    console.warn('[DEBUG] Failed to parse answer_content as JSON during regeneration:', e);
                }
            } else if (response.type === 'final_structured_content') {
                structuredData = response.payload;
                answer_content = JSON.stringify(response.payload);
            } else if (response.type === 'error') {
                throw new Error(response.payload.message);
            } else {
                // 处理其他或旧格式的响应类型
                answer_content = response.answer_content || response.content || '未知响应格式';
                thinking_content = response.thinking_content;
            }

            // 将新的思考内容与新的结果关联
            if (thinking_content) {
                newResultElement.dataset.thinkingContent = thinking_content;
            }

            // 处理思考内容 - 现在只负责更新UI，实际切换由switchToResult处理
            if (thinking_content && thinkingContent) {
                 // 更新思考内容前先清空
                thinkingContent.textContent = '';
                await this.typeText(thinking_content, thinkingContent, 30);
                // 更新标题
                if (thinkingTitle) {
                    thinkingTitle.innerHTML = `
                        <div class="spinner" style="display: none;"></div>
                        <span class="thinking-toggle" style="cursor: pointer;">🤔 已完成深度思考 <span class="collapse-icon">▼</span></span>
                    `;
                    this.bindThinkingToggle(messageElement);
                }
            } else if (thinkingPhase) {
                // 如果这次重新生成没有思考内容，则隐藏思考区域
                thinkingPhase.style.display = 'none';
            }
            
            // 隐藏思考阶段，显示最终答案阶段
            // if (thinkingPhase) thinkingPhase.style.display = 'block'; // 保持显示，让用户看到
            if (finalPhase) finalPhase.style.display = 'block';
            
            // 隐藏所有现有结果
            const existingResults = resultsContainer.querySelectorAll('.result-content');
            existingResults.forEach(result => {
                result.style.display = 'none';
                result.classList.remove('active');
            });
            
            // 显示新结果
            newResultElement.style.display = 'block';
            newResultElement.classList.add('active');
            
            // 更新当前结果索引
            messageElement.dataset.currentResult = newResultIndex;
            
            // 显示并更新导航
            if (resultNavigation) {
                resultNavigation.style.display = 'flex';
                this.updateResultNavigation(messageElement);
            }
            
            // 处理答案内容
            if (structuredData) {
                newResultElement.dataset.structuredData = JSON.stringify(structuredData);
                if (this.currentAgent === 'lesion_localizer' || this.currentAgent === 'aux_diagnosis') {
                    newResultElement.innerHTML = '';
                } else {
                    // 对于其他智能体，显示格式化的JSON
                    newResultElement.innerHTML = `<pre class="json-content">${JSON.stringify(structuredData, null, 2)}</pre>`;
                }
            } else if (answer_content) {
                await this.typeText(answer_content, newResultElement);
            }
            
            this.finalizeMessage(messageElement, structuredData);
            
            // 恢复控制按钮
            if (controls) {
                controls.style.opacity = '1';
            }
            
        } catch (error) {
            console.error('重新生成失败:', error);
            this.showError('重新生成失败: ' + error.message);
            
            // 移除失败的新结果元素
            const resultsContainer = messageElement.querySelector('.results-container');
            const newResultElement = resultsContainer.querySelector(`[data-result-index="${resultsContainer.children.length - 1}"]`);
            if (newResultElement) {
                newResultElement.remove();
            }
            
            // 恢复控制按钮
            const controls = messageElement.querySelector('.controls');
            if (controls) {
                controls.style.opacity = '1';
            }
            
            // 恢复显示
            const thinkingPhase = messageElement.querySelector('.thinking-phase');
            const finalPhase = messageElement.querySelector('.final-answer-phase');
            if (thinkingPhase) thinkingPhase.style.display = 'none';
            if (finalPhase) finalPhase.styledisplay = 'block';
            
        } finally {
            this.isSending = false;
        }
    }

    exportMessage(messageId) {
        console.log('Export message:', messageId);
        
        // 创建导出选项菜单
        const existingMenu = document.querySelector('.export-menu');
        if (existingMenu) {
            existingMenu.remove();
        }

        // 找到对应的消息元素
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) {
            console.error('Message element not found:', messageId);
            return;
        }

        // 检查是否是助手消息
        if (!messageElement.classList.contains('assistant-message')) {
            this.showError('只能导出助手消息');
            return;
        }

        const menu = document.createElement('div');
        menu.className = 'export-menu';
        menu.style.cssText = `
            position: fixed;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 8px 0;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            min-width: 120px;
            font-size: 14px;
        `;

        // 获取按钮位置
        const button = event.target.closest('.control-btn');
        const rect = button.getBoundingClientRect();
        menu.style.left = (rect.left - 50) + 'px';
        menu.style.top = (rect.bottom + 5) + 'px';

        menu.innerHTML = `
            <div class="menu-item" style="padding: 12px 16px; cursor: pointer; display: flex; align-items: center; transition: background-color 0.2s;" data-action="export-docx" onmouseover="this.style.backgroundColor='#f5f5f5'" onmouseout="this.style.backgroundColor='transparent'">
                <i data-lucide="file-text" style="width: 16px; height: 16px; margin-right: 8px;"></i>
                导出为Word文档
            </div>
            <div class="menu-item" style="padding: 12px 16px; cursor: pointer; display: flex; align-items: center; transition: background-color 0.2s;" data-action="export-pdf" onmouseover="this.style.backgroundColor='#f5f5f5'" onmouseout="this.style.backgroundColor='transparent'">
                <i data-lucide="file-down" style="width: 16px; height: 16px; margin-right: 8px;"></i>
                导出为PDF文档
            </div>
        `;

        document.body.appendChild(menu);

        // 初始化菜单中的图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }

        // 绑定菜单项事件
        menu.addEventListener('click', (e) => {
            const menuItem = e.target.closest('.menu-item');
            if (!menuItem) return;
            
            const action = menuItem.dataset.action;
            if (action === 'export-docx') {
                this.exportToDocx(messageElement);
            } else if (action === 'export-pdf') {
                this.exportToPdf(messageElement);
            }
            menu.remove();
        });

        // 点击外部关闭菜单
        const closeMenu = (e) => {
            if (!menu.contains(e.target) && !button.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        
        // 延迟绑定点击事件，避免立即触发
        setTimeout(() => {
            document.addEventListener('click', closeMenu);
        }, 0);
    }

    exportToDocx(messageElement) {
        try {
            // 检查docx库是否加载
            if (typeof docx === 'undefined') {
                // 如果docx库未加载，回退到RTF格式
                this.exportToRTF(messageElement);
                return;
            }

            // 获取完整的对话内容
            const content = this.getCompleteMessageContent(messageElement);
            console.log('Exporting content:', content);
            
            // 使用docx库创建真正的Word文档
            const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } = docx;
            
            const doc = new Document({
                sections: [{
                    properties: {},
                    children: [
                        // 标题
                        new Paragraph({
                            text: "灵瞳眼科智慧诊疗系统 - 诊疗报告",
                            heading: HeadingLevel.TITLE,
                            alignment: AlignmentType.CENTER,
                        }),
                        
                        // 生成时间
                        new Paragraph({
                            children: [
                                new TextRun({
                                    text: `生成时间：${new Date().toLocaleString('zh-CN')}`,
                                    bold: false,
                                }),
                            ],
                            spacing: { after: 200 },
                        }),
                        
                        ...this.createDocxSections(content)
                    ],
                }],
            });
            
            // 生成并下载文档
            Packer.toBlob(doc).then((blob) => {
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `灵瞳诊疗报告_${new Date().toISOString().split('T')[0]}.docx`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
                
                this.showSuccess('Word文档已下载到本地');
            }).catch((error) => {
                console.error('DOCX generation failed:', error);
                // 回退到RTF格式
                this.exportToRTF(messageElement);
            });
            
        } catch (error) {
            console.error('Export to DOCX failed:', error);
            // 回退到RTF格式
            this.exportToRTF(messageElement);
        }
    }

    createDocxSections(content) {
        const { Paragraph, TextRun, HeadingLevel, ExternalHyperlink, ImageRun } = docx;
        const sections = [];
        
        // 用户提问部分
        if (content.userQuestion) {
            sections.push(
                new Paragraph({
                    text: "用户提问",
                    heading: HeadingLevel.HEADING_1,
                    spacing: { before: 400, after: 200 },
                }),
                new Paragraph({
                    children: [
                        new TextRun({
                            text: content.userQuestion,
                            color: "000000",
                        }),
                    ],
                    spacing: { after: 200 },
                })
            );
        }
        
        // 上传文件部分
        if (content.userFiles.length > 0 || (content.userFileImages && content.userFileImages.length > 0)) {
            sections.push(
                new Paragraph({
                    text: "上传文件",
                    heading: HeadingLevel.HEADING_1,
                    spacing: { before: 400, after: 200 },
                })
            );
            
            // 如果有图片，添加图片链接说明
            if (content.userFileImages && content.userFileImages.length > 0) {
                sections.push(
                    new Paragraph({
                        children: [
                            new TextRun({
                                text: "上传图片总数: " + content.userFileImages.length,
                                bold: true,
                                color: "000000",
                            }),
                        ],
                        spacing: { after: 200 },
                    })
                );
                
                content.userFileImages.forEach((file, index) => {
                    // 在Word中无法直接嵌入图片，但我们可以提供文件名和序号
                    sections.push(
                        new Paragraph({
                            children: [
                                new TextRun({
                                    text: `图片 ${index+1}: ${file.name}`,
                                    color: "000000",
                                }),
                            ],
                            spacing: { after: 100 },
                        })
                    );
                });
                
                sections.push(
                    new Paragraph({
                        children: [
                            new TextRun({
                                text: "注：由于文档格式限制，图片未能直接嵌入，请参考原始对话查看图片。",
                                italics: true,
                                color: "666666",
                            }),
                        ],
                        spacing: { after: 200, before: 200 },
                    })
                );
            } else {
                // 如果没有图片，只列出文件名
                content.userFiles.forEach(fileName => {
                    sections.push(
                        new Paragraph({
                            children: [
                                new TextRun({
                                    text: `• ${fileName}`,
                                    color: "000000",
                                }),
                            ],
                            spacing: { after: 100 },
                        })
                    );
                });
            }
        }
        
        // 分析过程部分
        if (content.thinking) {
            sections.push(
                new Paragraph({
                    text: "分析过程",
                    heading: HeadingLevel.HEADING_1,
                    spacing: { before: 400, after: 200 },
                }),
                new Paragraph({
                    children: [
                        new TextRun({
                            text: content.thinking,
                            color: "0066CC",
                        }),
                    ],
                    spacing: { after: 200 },
                })
            );
        }
        
        // 诊疗结果部分 - 处理HTML格式
        if (content.answer) {
            sections.push(
                new Paragraph({
                    text: "诊疗结果",
                    heading: HeadingLevel.HEADING_1,
                    spacing: { before: 400, after: 200 },
                })
            );
            
            // Special handling for lesion localizer with rendered image
            if (this.currentAgent === 'lesion_localizer' && content.renderedImage) {
                const base64Data = content.renderedImage.replace(/^data:image\/png;base64,/, "");
                sections.push(
                    new Paragraph({
                        children: [
                            new ImageRun({
                                data: base64Data,
                                transformation: {
                                    width: 450,
                                    height: 350,
                                },
                            }),
                        ],
                    })
                );
            }
            
            // 将HTML转换为纯文本
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = content.answer;
            // For lesion localizer, remove the image so it's not duplicated as text
            if (this.currentAgent === 'lesion_localizer') {
                const imgElement = tempDiv.querySelector('img');
                if (imgElement) {
                    imgElement.remove();
                }
            }

            const plainText = tempDiv.textContent || tempDiv.innerText || content.answer;
            
            // 将文本按段落分割，创建多个段落
            const paragraphs = plainText.split('\n\n');
            
            paragraphs.forEach(para => {
                if (para.trim()) {
                    sections.push(
                        new Paragraph({
                            children: [
                                new TextRun({
                                    text: para.trim(),
                                    color: "000000",
                                }),
                            ],
                            spacing: { after: 200 },
                        })
                    );
                }
            });
        }
        
        // 免责声明
        sections.push(
            new Paragraph({
                children: [
                    new TextRun({
                        text: "本报告由灵瞳眼科智慧诊疗系统AI生成，仅供医疗参考，最终诊断请以临床医师判断为准。",
                        color: "666666",
                        size: 20,
                    }),
                ],
                spacing: { before: 400 },
            })
        );
        
        return sections;
    }

    // 备用RTF导出方法
    exportToRTF(messageElement) {
        try {
            console.log('Using RTF fallback for Word export');
            // 获取完整的对话内容
            const content = this.getCompleteMessageContent(messageElement);
            
            // 创建RTF格式的文档内容
            const rtfContent = this.createRTFDocument(content);
            
            // 尝试转换为DOC格式
            this.convertRTFtoDOC(rtfContent, `灵瞳诊疗报告_${new Date().toISOString().split('T')[0]}`);
        } catch (error) {
            console.error('RTF export failed:', error);
            this.showError('导出Word文档失败：' + error.message);
        }
    }
    
    // 将RTF转换为DOC格式
    convertRTFtoDOC(rtfContent, filename) {
        try {
            // 设置正确的MIME类型
            const blob = new Blob([rtfContent], { type: 'application/msword' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${filename}.doc`;  // 使用.doc扩展名
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.showSuccess('Word文档已下载到本地');
        } catch (error) {
            console.error('RTF to DOC conversion failed:', error);
            
            // 如果转换失败，回退到普通RTF下载
            const blob = new Blob([rtfContent], { type: 'application/rtf' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${filename}.rtf`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.showToast('无法转换为DOC格式，已导出为RTF格式', 'warning');
        }
    }

    exportToPdf(messageElement) {
        try {
            // 检查html2pdf库是否加载
            if (typeof html2pdf === 'undefined') {
                this.showError('PDF导出功能暂时不可用，请稍后重试');
                return;
            }

            // 获取完整的对话内容
            const content = this.getCompleteMessageContent(messageElement);
            
            // 创建临时容器用于PDF生成
            const container = document.createElement('div');
            container.style.cssText = `
                font-family: "微软雅黑", Arial, sans-serif;
                line-height: 1.6;
                padding: 40px;
                background: white;
                color: black;
            `;
            
            let containerHTML = `
                <h1 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">灵瞳眼科智慧诊疗系统 - 诊疗报告</h1>
                <p><strong>生成时间：</strong>${new Date().toLocaleString('zh-CN')}</p>
            `;
            
            // 添加用户问题
            if (content.userQuestion) {
                containerHTML += `
                    <h2 style="color: #34495e; margin-top: 30px;">用户提问</h2>
                    <div style="margin: 20px 0; padding: 15px; background: #f8f9fa; border-left: 4px solid #28a745;">
                        ${this.escapeHtml(content.userQuestion)}
                    </div>
                `;
            }
            
            // 添加上传文件信息和图片预览
            if (content.userFiles.length > 0 || content.userFileImages.length > 0) {
                containerHTML += `
                    <h2 style="color: #34495e; margin-top: 30px;">上传文件</h2>
                    <div style="margin: 20px 0; display: flex; flex-wrap: wrap; gap: 15px;">
                `;
                
                // 添加图片预览
                if (content.userFileImages.length > 0) {
                    content.userFileImages.forEach(file => {
                        containerHTML += `
                            <div style="margin-bottom: 15px; text-align: center; width: 200px;">
                                <img src="${file.src}" alt="${file.name}" style="max-width: 200px; max-height: 200px; border-radius: 4px; border: 1px solid #ddd;">
                                <p style="margin-top: 5px; font-size: 12px;">${this.escapeHtml(file.name)}</p>
                            </div>
                        `;
                    });
                } else {
                    // 如果没有图片，只显示文件名
                    containerHTML += `<ul style="margin: 20px 0;">`;
                    content.userFiles.forEach(fileName => {
                        containerHTML += `<li>${this.escapeHtml(fileName)}</li>`;
                    });
                    containerHTML += `</ul>`;
                }
                
                containerHTML += `</div>`;
            }
            
            // 添加分析过程
            if (content.thinking) {
                containerHTML += `
                    <h2 style="color: #34495e; margin-top: 30px;">分析过程</h2>
                    <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0;">
                        ${content.thinking.replace(/\n/g, '<br>')}
                    </div>
                `;
            }
            
            // 添加诊疗结果 - 使用原始HTML内容，不再转义
            if (content.answer) {
                containerHTML += `
                    <h2 style="color: #34495e; margin-top: 30px;">诊疗结果</h2>
                    <div style="margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 4px;">
                        ${content.answer}
                    </div>
                `;
            }
            
            // 添加免责声明
            containerHTML += `
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666;">
                    <p>本报告由灵瞳眼科智慧诊疗系统AI生成，仅供医疗参考，最终诊断请以临床医师判断为准。</p>
                </div>
            `;
            
            container.innerHTML = containerHTML;
            
            // PDF生成配置
            const options = {
                margin: 1,
                filename: `灵瞳诊疗报告_${new Date().toISOString().split('T')[0]}.pdf`,
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { scale: 2, useCORS: true },
                jsPDF: { unit: 'in', format: 'a4', orientation: 'portrait' }
            };
            
            // 生成并下载PDF
            html2pdf().set(options).from(container).save().then(() => {
                this.showSuccess('PDF文档已下载到本地');
            }).catch((error) => {
                console.error('PDF generation failed:', error);
                this.showError('生成PDF失败：' + error.message);
            });
            
        } catch (error) {
            console.error('Export to PDF failed:', error);
            this.showError('导出PDF失败：' + error.message);
        }
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML.replace(/\n/g, '<br>');
    }

    getMessageContent(messageElement) {
        const content = { thinking: '', answer: '' };
        
        // 获取思考内容
        const thinkingElement = messageElement.querySelector('.thinking-text-content');
        if (thinkingElement) {
            content.thinking = thinkingElement.innerHTML;
        }
        
        // 获取答案内容（当前显示的结果）
        const activeResult = messageElement.querySelector('.result-content.active');
        if (activeResult) {
            content.answer = activeResult.innerHTML;
        } else {
            // 如果没有找到，尝试获取第一个结果
            const firstResult = messageElement.querySelector('.result-content');
            if (firstResult) {
                content.answer = firstResult.innerHTML;
            }
        }
        
        return content;
    }

    getCompleteMessageContent(messageElement) {
        const content = { userQuestion: '', userFiles: [], userFileImages: [], thinking: '', answer: '', renderedImage: null };
        console.log('Getting complete message content for element:', messageElement);
        
        // 获取用户问题 - 找到前一个用户消息
        const userMessage = messageElement.previousElementSibling;
        console.log('Found user message:', userMessage);
        
        if (userMessage && userMessage.classList.contains('user-message')) {
            // 获取用户消息文本
            const messageText = userMessage.querySelector('.message-text');
            if (messageText) {
                content.userQuestion = messageText.textContent.trim();
                console.log('User question:', content.userQuestion);
            }
            
            // 获取用户上传的文件信息和图片
            const attachments = userMessage.querySelectorAll('.attachment-item');
            if (attachments.length === 0) {
                // 尝试新格式的附件预览
                const attachmentPreviews = userMessage.querySelectorAll('.attachment-preview img');
                console.log('Found attachment previews:', attachmentPreviews.length);
                attachmentPreviews.forEach(img => {
                    const src = img.getAttribute('src');
                    const alt = img.getAttribute('alt') || '上传的图片';
                    content.userFiles.push(alt);
                    content.userFileImages.push({
                        src: src,
                        name: alt
                    });
                });
            } else {
                console.log('Found attachments:', attachments.length);
                attachments.forEach(attachment => {
                    const img = attachment.querySelector('img');
                    const fileName = attachment.querySelector('.attachment-name') || attachment.querySelector('.file-name');
                    const name = fileName ? fileName.textContent.trim() : (img ? (img.alt || '上传的图片') : '文件');
                    content.userFiles.push(name);
                    
                    if (img) {
                        content.userFileImages.push({
                            src: img.src,
                            name: name
                        });
                    }
                });
            }
        }
        
        // 获取AI的思考内容
        const thinkingElement = messageElement.querySelector('.thinking-text-content');
        if (thinkingElement) {
            content.thinking = this.cleanTextContent(thinkingElement.textContent || thinkingElement.innerText);
            console.log('Thinking content length:', content.thinking.length);
        } else {
            console.log('No thinking element found');
        }
        
        // 获取AI的答案内容（当前显示的结果）
        const activeResult = messageElement.querySelector('.result-content.active');
        if (activeResult) {
            if (this.currentAgent === 'lesion_localizer' && activeResult.querySelector('.lesion-canvas')) {
                const canvas = activeResult.querySelector('.lesion-canvas');
                try {
                    const dataUrl = canvas.toDataURL('image/png');
                    content.renderedImage = dataUrl; // For docx

                    // Create HTML with img tag for PDF export
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = activeResult.innerHTML;
                    const canvasInTemp = tempDiv.querySelector('.lesion-canvas');
                    if (canvasInTemp) {
                        const img = document.createElement('img');
                        img.src = dataUrl;
                        img.style.width = canvas.style.width;
                        img.style.height = canvas.style.height;
                        img.style.maxWidth = '100%';
                        canvasInTemp.parentNode.replaceChild(img, canvasInTemp);
                    }
                    content.answer = tempDiv.innerHTML;

                } catch (e) {
                    console.error("Failed to convert canvas to dataURL for export", e);
                    content.answer = activeResult.innerHTML; // Fallback
                }
            } else {
                // 使用innerHTML保留所有格式，包括HTML标签
                content.answer = activeResult.innerHTML;
            }
            console.log('Answer content from active result, length:', content.answer.length);
        } else {
            // 如果没有找到，尝试获取第一个结果
            const firstResult = messageElement.querySelector('.result-content');
            if (firstResult) {
                content.answer = firstResult.innerHTML;
                console.log('Answer content from first result, length:', content.answer.length);
            } else {
                // 如果还是没有找到，尝试获取所有可能的答案内容
                const finalAnswerContent = messageElement.querySelector('.final-answer-content');
                if (finalAnswerContent) {
                    content.answer = finalAnswerContent.innerHTML;
                    console.log('Answer content from final-answer-content, length:', content.answer.length);
                } else {
                    console.log('No answer content found');
                }
            }
        }
        
        console.log('Final content object:', {
            userQuestion: content.userQuestion ? 'present' : 'empty',
            userFiles: content.userFiles.length,
            userFileImages: content.userFileImages.length,
            thinking: content.thinking ? 'present' : 'empty',
            answer: content.answer ? 'present' : 'empty'
        });
        
        return content;
    }

    cleanTextContent(text) {
        if (!text) return '';
        // 清理文本，移除多余的空白字符和换行
        return text.replace(/\s+/g, ' ').trim();
    }

    createRTFDocument(content) {
        // RTF文档头部
        let rtf = `{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Microsoft YaHei;}{\\f1 SimSun;}}`;
        
        // 颜色表
        rtf += `{\\colortbl;\\red44\\green62\\blue80;\\red52\\green73\\blue94;\\red0\\green123\\blue255;\\red102\\green102\\blue102;\\red153\\green51\\blue0;}`;
        
        // 文档标题
        rtf += `\\f0\\fs32\\cf1\\b 灵瞳眼科智慧诊疗系统 - 诊疗报告\\b0\\par`;
        rtf += `\\fs20\\par`;
        
        // 生成时间
        const now = new Date();
        rtf += `\\b 生成时间：\\b0 ${now.toLocaleString('zh-CN')}\\par\\par`;
        
        // 用户问题部分
        if (content.userQuestion) {
            rtf += `\\fs24\\cf2\\b 用户提问\\b0\\fs20\\cf0\\par`;
            rtf += `${this.escapeRTF(content.userQuestion)}\\par\\par`;
        }
        
        // 上传文件部分
        if (content.userFiles.length > 0 || (content.userFileImages && content.userFileImages.length > 0)) {
            rtf += `\\fs24\\cf2\\b 上传文件\\b0\\fs20\\cf0\\par`;
            
            // 如果有图片，添加图片信息
            if (content.userFileImages && content.userFileImages.length > 0) {
                rtf += `\\b 上传图片总数: ${content.userFileImages.length}\\b0\\par\\par`;
                
                content.userFileImages.forEach((file, index) => {
                    rtf += `图片 ${index+1}: ${this.escapeRTF(file.name)}\\par`;
                });
                
                rtf += `\\i\\cf4 注：由于文档格式限制，图片未能直接嵌入，请参考原始对话查看图片。\\i0\\cf0\\par\\par`;
            } else {
                // 如果没有图片，只列出文件名
                content.userFiles.forEach(fileName => {
                    rtf += `• ${this.escapeRTF(fileName)}\\par`;
                });
                rtf += `\\par`;
            }
        }
        
        // 分析过程部分
        if (content.thinking) {
            rtf += `\\fs24\\cf2\\b 分析过程\\b0\\fs20\\cf0\\par`;
            // 添加左边框效果（用缩进模拟）
            rtf += `\\li720`; // 左缩进
            rtf += `\\cf3 ${this.escapeRTF(content.thinking)}\\cf0`;
            rtf += `\\li0\\par\\par`; // 恢复缩进
        }
        
        // 诊疗结果部分 - 处理HTML内容
        if (content.answer) {
            rtf += `\\fs24\\cf2\\b 诊疗结果\\b0\\fs20\\cf0\\par`;
            
            // 将HTML转换为纯文本
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = content.answer;
            const plainText = tempDiv.textContent || tempDiv.innerText || content.answer;
            
            // 分段处理，使得文档更易读
            const paragraphs = plainText.split('\n\n');
            
            paragraphs.forEach(para => {
                if (para.trim()) {
                    // 处理可能的Markdown标题（#开头）
                    if (para.trim().startsWith('#')) {
                        rtf += `\\b ${this.escapeRTF(para.trim())}\\b0\\par\\par`;
                    } else {
                        rtf += `${this.escapeRTF(para.trim())}\\par\\par`;
                    }
                }
            });
            
            // 如果没有段落，就直接显示整个文本
            if (paragraphs.length <= 1 && !paragraphs[0].trim()) {
                rtf += `${this.escapeRTF(plainText)}\\par\\par`;
            }
        }
        
        // 免责声明
        rtf += `\\fs16\\cf4\\par`;
        rtf += `本报告由灵瞳眼科智慧诊疗系统AI生成，仅供医疗参考，最终诊断请以临床医师判断为准。\\par`;
        
        // 文档结尾
        rtf += `}`;
        
        return rtf;
    }

    escapeRTF(text) {
        if (!text) return '';
        // 转义RTF特殊字符
        return text
            .replace(/\\/g, '\\\\')  // 反斜杠
            .replace(/\{/g, '\\{')   // 左大括号
            .replace(/\}/g, '\\}')   // 右大括号
            .replace(/\n/g, '\\par') // 换行
            .replace(/\t/g, '\\tab'); // 制表符
    }

    async renameConversation(conversationId) {
        const newTitle = prompt('请输入新的对话标题：');
        if (newTitle && newTitle.trim()) {
            try {
                await apiClient.updateConversation(conversationId, newTitle.trim());
                await this.loadConversations();
            } catch (error) {
                console.error('Failed to rename conversation:', error);
                alert('重命名失败，请稍后重试');
            }
        }
    }

    async deleteConversation(conversationId) {
        if (confirm('确定要删除这个对话吗？此操作不可撤销。')) {
            try {
                await apiClient.deleteConversation(conversationId);
                await this.loadConversations();
                
                // 如果删除的是当前对话，返回到欢迎页面
                if (this.currentConversationId === conversationId) {
                    this.currentConversationId = null;
                    this.showWelcome();
                }
            } catch (error) {
                console.error('Failed to delete conversation:', error);
                alert('删除失败，请稍后重试');
            }
        }
    }

    // 全屏输入功能
    toggleFullscreenInput() {
        const inputArea = document.querySelector('.input-area');
        const userInput = document.getElementById('user-input');
        
        if (!inputArea || !userInput) return;
        
        if (inputArea.classList.contains('fullscreen')) {
            // 退出全屏
            inputArea.classList.remove('fullscreen');
            userInput.style.height = 'auto';
            const lineHeight = parseInt(getComputedStyle(userInput).lineHeight);
            const maxHeight = lineHeight * 8;
            userInput.style.height = Math.min(userInput.scrollHeight, maxHeight) + 'px';
        } else {
            // 进入全屏
            inputArea.classList.add('fullscreen');
            userInput.style.height = '60vh';
        }
    }

    // 清理任何遗留的UI元素
    cleanupResidualElements() {
        try {
            // 清理所有可能的模态框覆盖层
            const overlays = document.querySelectorAll('.modal-overlay, .sidebar-overlay, .loading-overlay');
            overlays.forEach(overlay => {
                if (overlay && overlay.parentNode) {
                    overlay.parentNode.removeChild(overlay);
                }
            });

            // 清理所有可能的模态框
            const modals = document.querySelectorAll('.modal, [id*="modal"], [class*="modal"]');
            modals.forEach(modal => {
                // 只清理动态创建的模态框，不清理静态HTML中的
                if (modal.style.display !== '' || modal.style.position === 'fixed') {
                    modal.style.display = 'none';
                }
            });

            // 清理所有Toast消息
            const toasts = document.querySelectorAll('.toast, [class*="toast"]');
            toasts.forEach(toast => {
                if (toast && toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            });

            // 清理body上可能的overflow隐藏
            document.body.style.overflow = '';
            
            // 清理可能的active类
            document.body.classList.remove('modal-open', 'sidebar-open');
            
            console.log('清理遗留UI元素完成');
        } catch (error) {
            console.warn('清理遗留UI元素时出错:', error);
        }
    }

    showConversationMenu(event, conversationId) {
        event.stopPropagation(); // 阻止事件冒泡，避免触发对话选择
        
        // 移除已存在的菜单
        const existingMenu = document.querySelector('.conversation-menu-popup');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        // 创建菜单，使用与用户菜单相同的样式
        const menu = document.createElement('div');
        menu.className = 'user-menu-popup conversation-menu-popup';
        menu.style.display = 'block';
        menu.style.position = 'absolute';
        menu.style.bottom = 'auto';
        menu.style.top = '100%';
        menu.style.left = 'auto';
        menu.style.right = '0';
        menu.style.minWidth = '120px';
        menu.innerHTML = `
            <button type="button" onclick="uiManager.renameConversation(${conversationId}); this.parentElement.remove();">
                <i data-lucide="edit-2" style="width: 16px; height: 16px; margin-right: 8px;"></i>
                重命名
            </button>
            <button type="button" onclick="uiManager.deleteConversation(${conversationId}); this.parentElement.remove();" style="color: #dc3545;">
                <i data-lucide="trash-2" style="width: 16px; height: 16px; margin-right: 8px;"></i>
                删除
            </button>
        `;
        
        // 添加到按钮的父元素
        const button = event.target.closest('button');
        const historyItem = button.closest('.history-item');
        historyItem.style.position = 'relative';
        historyItem.appendChild(menu);
        
        // 创建图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons({ nodes: [menu] });
        }
        
        // 点击其他地方关闭菜单
        const closeMenu = (e) => {
            if (!menu.contains(e.target)) {
                menu.remove();
                document.removeEventListener('click', closeMenu);
            }
        };
        
        // 延迟添加事件监听器，避免立即触发
        setTimeout(() => {
            document.addEventListener('click', closeMenu);
        }, 0);
    }

    // 结果导航功能
    updateResultNavigation(messageElement) {
        const resultsContainer = messageElement.querySelector('.results-container');
        const resultNavigation = messageElement.querySelector('.result-navigation');
        const resultIndicator = resultNavigation.querySelector('.result-indicator');
        const prevBtn = resultNavigation.querySelector('.prev-btn');
        const nextBtn = resultNavigation.querySelector('.next-btn');
        
        const totalResults = resultsContainer.children.length;
        const currentIndex = parseInt(messageElement.dataset.currentResult || '0');
        
        // 更新指示器
        resultIndicator.textContent = `${currentIndex + 1} / ${totalResults}`;
        
        // 更新按钮状态
        prevBtn.disabled = currentIndex === 0;
        nextBtn.disabled = currentIndex === totalResults - 1;
        
        // 只有多个结果时才显示导航
        if (totalResults > 1) {
            resultNavigation.style.display = 'flex';
        } else {
            resultNavigation.style.display = 'none';
        }
    }
    
    showPreviousResult(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) return;
        
        const currentIndex = parseInt(messageElement.dataset.currentResult || '0');
        if (currentIndex > 0) {
            this.switchToResult(messageElement, currentIndex - 1);
        }
    }
    
    showNextResult(messageId) {
        const messageElement = document.querySelector(`[data-message-id="${messageId}"]`);
        if (!messageElement) return;
        
        const resultsContainer = messageElement.querySelector('.results-container');
        const currentIndex = parseInt(messageElement.dataset.currentResult || '0');
        const totalResults = resultsContainer.children.length;
        
        if (currentIndex < totalResults - 1) {
            this.switchToResult(messageElement, currentIndex + 1);
        }
    }
    
    switchToResult(messageElement, targetIndex) {
        const resultsContainer = messageElement.querySelector('.results-container');
        const resultElements = resultsContainer.querySelectorAll('.result-content');
        
        // 隐藏所有结果
        resultElements.forEach(result => {
            result.style.display = 'none';
            result.classList.remove('active');
        });
        
        // 显示目标结果
        const targetResult = resultElements[targetIndex];
        if (targetResult) {
            targetResult.style.display = 'block';
            targetResult.classList.add('active');
            
            // 更新当前结果索引
            messageElement.dataset.currentResult = targetIndex;
            
            // 更新导航
            this.updateResultNavigation(messageElement);

            // 更新思考内容显示
            const thinkingPhase = messageElement.querySelector('.thinking-phase');
            const thinkingContent = messageElement.querySelector('.thinking-text-content');
            if (thinkingPhase && thinkingContent) {
                const storedThinking = targetResult.dataset.thinkingContent;
                if (storedThinking) {
                    thinkingPhase.style.display = 'block';
                    thinkingContent.textContent = storedThinking;
                    
                    // 确保标题是"已完成"状态
                    const thinkingTitle = messageElement.querySelector('.thinking-title');
                    if(thinkingTitle && !thinkingTitle.querySelector('.thinking-toggle')){
                         thinkingTitle.innerHTML = `
                            <div class="spinner" style="display: none;"></div>
                            <span class="thinking-toggle" style="cursor: pointer;">🤔 已完成深度思考 <span class="collapse-icon">▼</span></span>
                        `;
                    }

                } else {
                    thinkingPhase.style.display = 'none';
                }
            }
        }
    }

    // 处理特定智能体的UI渲染
    handleAgentSpecificUI(messageElement, structuredData = null) {
        console.log('[DEBUG] Handling agent-specific UI for:', this.currentAgent, structuredData ? 'with structured data' : 'without structured data');
        
        if (!messageElement || !this.currentAgent) return;
        
        try {
            // 获取消息内容 - 修正：应该获取当前激活的结果
            const finalAnswerContent = messageElement.querySelector('.result-content.active');
            if (!finalAnswerContent) {
                console.warn('[DEBUG] No active result content found in handleAgentSpecificUI for message:', messageElement.dataset.messageId);
                return;
            }
            
            // 获取消息的数据库ID
            const messageId = messageElement.dataset.dbMessageId;
            console.log('[DEBUG] Processing message ID:', messageId);
            
            // 如果没有提供结构化数据，尝试从元素中提取
            if (!structuredData) {
                // 首先尝试从data属性获取结构化数据
                if (finalAnswerContent.dataset.structuredData) {
                    try {
                        structuredData = JSON.parse(finalAnswerContent.dataset.structuredData);
                        console.log('[DEBUG] Structured data retrieved from element attribute');
                    } catch (e) {
                        console.warn('[DEBUG] Failed to parse structuredData from attribute', e);
                    }
                }
                
                // 如果仍未获取到，尝试从内容中提取
                if (!structuredData) {
                    structuredData = this.extractJsonFromElement(finalAnswerContent);
                    console.log('[DEBUG] Structured data extracted from element content');
                }
            }
            
            // 记录找到的结构化数据
            if (structuredData) {
                console.log('[DEBUG] Structured data for UI processing:', structuredData);
            } else {
                console.warn('[DEBUG] No structured data found for agent-specific UI');
            }
            
            switch(this.currentAgent) {
                case 'lesion_localizer':
                    this.handleLesionLocalizerUI(messageElement, structuredData);
                    break;
                
                case 'aux_diagnosis':
                    this.handleAuxDiagnosisUI(messageElement, structuredData);
                    break;
                    
                // 可以添加更多智能体的处理
                default:
                    // 其他智能体不需要特殊处理
                    console.log('[DEBUG] No special UI handling for agent:', this.currentAgent);
                    break;
            }
        } catch (error) {
            console.error('[DEBUG] Error in handleAgentSpecificUI:', error);
        }
    }
    
    // 处理病灶定位智能体UI
    handleLesionLocalizerUI(messageElement, data) {
        console.log('[DEBUG] Handling lesion_localizer UI');
        
        // 查找上传的图片URL
        const userMessage = messageElement.previousElementSibling;
        let imageUrl = null;
        if (userMessage && userMessage.classList.contains('user-message')) {
            const imgs = userMessage.querySelectorAll('img');
            if (imgs.length > 0) {
                imageUrl = imgs[0].src;
            }
        }
        
        // 如果提供的数据中包含图片URL，使用它
        if (data && data.image_url) {
            imageUrl = data.image_url;
        }
        
        // 准备渲染数据
        const renderData = {
            image_url: imageUrl,
            boxes: data && data.boxes ? data.boxes : []
        };
        
        // 优先使用this.agentUIs中的实例
        if (this.agentUIs.lesion_localizer && typeof this.agentUIs.lesion_localizer.renderLesionLocalization === 'function') {
            console.log('[DEBUG] Calling this.agentUIs.lesion_localizer.renderLesionLocalization with data:', renderData);
            this.agentUIs.lesion_localizer.renderLesionLocalization(messageElement, renderData);
        } 
        // 备用：检查window对象上是否有对应的UI实例
        else if (window.lesionLocalizerUI && typeof window.lesionLocalizerUI.renderLesionLocalization === 'function') {
            console.log('[DEBUG] Falling back to window.lesionLocalizerUI');
            window.lesionLocalizerUI.renderLesionLocalization(messageElement, renderData);
        } else {
            console.error('[DEBUG] lesion_localizer UI instance not available in both this.agentUIs and window objects');
            // 如果没有找到UI实例，显示警告
            const warning = document.createElement('div');
            warning.className = 'ui-warning';
            warning.innerHTML = '<strong>无法加载病灶定位UI</strong>: 请检查lesion_localizer.js是否已正确加载。';
            warning.style.color = 'red';
            warning.style.padding = '10px';
            warning.style.marginTop = '10px';
            messageElement.querySelector('.message-content-wrapper').appendChild(warning);
        }
    }
    
    // 处理辅助诊断智能体UI
    handleAuxDiagnosisUI(messageElement, data) {
        console.log('[DEBUG] Handling aux_diagnosis UI');
        
        // 优先使用this.agentUIs中的实例
        if (this.agentUIs.aux_diagnosis && typeof this.agentUIs.aux_diagnosis.renderDiagnosisResults === 'function') {
            console.log('[DEBUG] Calling this.agentUIs.aux_diagnosis.renderDiagnosisResults with data:', data);
            this.agentUIs.aux_diagnosis.renderDiagnosisResults(messageElement, data || {});
        }
        // 备用：检查window对象上是否有对应的UI实例
        else if (window.auxDiagnosisUI && typeof window.auxDiagnosisUI.renderDiagnosisResults === 'function') {
            console.log('[DEBUG] Falling back to window.auxDiagnosisUI');
            window.auxDiagnosisUI.renderDiagnosisResults(messageElement, data || {});
        } else {
            console.error('[DEBUG] aux_diagnosis UI instance not available in both this.agentUIs and window objects');
            // 如果没有找到UI实例，显示警告
            const warning = document.createElement('div');
            warning.className = 'ui-warning';
            warning.innerHTML = '<strong>无法加载辅助诊断UI</strong>: 请检查aux_diagnosis.js是否已正确加载。';
            warning.style.color = 'red';
            warning.style.padding = '10px';
            warning.style.marginTop = '10px';
            messageElement.querySelector('.message-content-wrapper').appendChild(warning);
        }
    }
    
    // 从元素内容中提取JSON数据
    extractJsonFromElement(element) {
        try {
            if (!element) return null;
            
            // 首先检查是否有data-json属性（可能有些实现会通过属性传递JSON）
            const jsonAttr = element.getAttribute('data-json');
            if (jsonAttr) {
                try {
                    return JSON.parse(jsonAttr);
                } catch (e) {
                    console.warn('[DEBUG] Failed to parse data-json attribute:', e);
                    // 失败时继续尝试其他方法
                }
            }
            
            // 获取内容
            const content = element.textContent || element.innerHTML;
            if (!content) return null;
            
            // 尝试查找以```json或```开始、```结束的代码块
            const codeBlockRegex = /```(?:json)?\s*([\s\S]*?)```/g;
            const codeMatches = Array.from(content.matchAll(codeBlockRegex));
            
            if (codeMatches && codeMatches.length > 0) {
                for (const match of codeMatches) {
                    if (match[1]) {
                        try {
                            return JSON.parse(match[1].trim());
                        } catch (e) {
                            console.warn('[DEBUG] Failed to parse JSON in code block:', e);
                            // 继续尝试下一个匹配
                        }
                    }
                }
            }
            
            // 尝试寻找JSON格式的内容
            const jsonRegex = /(\{[\s\S]*?\}|\[[\s\S]*?\])/g;
            const matches = Array.from(content.matchAll(jsonRegex));
            
            if (matches && matches.length > 0) {
                // 按长度排序，优先尝试更长的（可能更完整的）JSON字符串
                const sortedMatches = matches
                    .map(m => m[0])
                    .sort((a, b) => b.length - a.length);
                
                // 尝试解析找到的每一个可能的JSON字符串
                for (const match of sortedMatches) {
                    try {
                        const parsed = JSON.parse(match);
                        console.log('[DEBUG] Successfully parsed JSON:', parsed);
                        return parsed;
                    } catch (e) {
                        // 如果解析失败，尝试下一个匹配
                        console.warn('[DEBUG] Failed to parse potential JSON:', match.substring(0, 50) + '...');
                    }
                }
            }
            
            // 如果没有找到有效的JSON，尝试把整个内容作为JSON解析
            try {
                const trimmedContent = content.trim();
                if (trimmedContent.startsWith('{') || trimmedContent.startsWith('[')) {
                    return JSON.parse(trimmedContent);
                }
            } catch (e) {
                // 解析失败，可能不是JSON格式
                console.warn('[DEBUG] Failed to parse entire content as JSON');
            }
            
            // 如果上面的方法都失败了，尝试创建一个默认的结构化数据
            console.warn('[DEBUG] Could not extract JSON data, creating default structure');
            return { 
                extracted: false,
                rawContent: content.substring(0, 100) + (content.length > 100 ? '...' : ''),
                message: "无法提取结构化数据，请检查API响应格式"
            };
        } catch (error) {
            console.error('[DEBUG] Error in extractJsonFromElement:', error);
            return {
                error: true,
                message: "提取JSON时发生错误: " + error.message
            };
        }
    }

    bindThinkingToggle(messageElement) {
        const thinkingTitle = messageElement.querySelector('.thinking-title');
        const thinkingContent = messageElement.querySelector('.thinking-text-content');
        const toggle = thinkingTitle ? thinkingTitle.querySelector('.thinking-toggle') : null;

        if (toggle && thinkingContent) {
            // 为防止重复绑定，先移除旧的监听器（通过克隆节点实现）
            const newToggle = toggle.cloneNode(true);
            toggle.parentNode.replaceChild(newToggle, toggle);

            newToggle.addEventListener('click', () => {
                const isVisible = thinkingContent.style.display !== 'none';
                thinkingContent.style.display = isVisible ? 'none' : 'block';
                const icon = newToggle.querySelector('.collapse-icon');
                if (icon) {
                    icon.textContent = isVisible ? '▶' : '▼';
                }
            });
        }
    }

    updateButtonToStop() {
        const sendBtn = document.getElementById('send-btn');
        const interruptBtn = document.getElementById('interrupt-btn');
        
        if (!sendBtn || !interruptBtn) return;
        
        sendBtn.style.display = 'none'; // 隐藏发送按钮
        interruptBtn.style.display = 'block'; // 显示中断按钮
    }
    
    updateButtonToSend() {
        const sendBtn = document.getElementById('send-btn');
        const interruptBtn = document.getElementById('interrupt-btn');
        
        if (!sendBtn || !interruptBtn) return;
        
        sendBtn.style.display = 'block'; // 显示发送按钮
        sendBtn.disabled = false;
        interruptBtn.style.display = 'none'; // 隐藏中断按钮
    }

    stopMessageGeneration() {
        if (!this.isSending) return;
        
        console.log('[DEBUG] User requested to stop message generation.');

        // Stop typewriter effect if it's running
        if (this.currentTypeItInstance) {
            this.currentTypeItInstance.destroy();
            this.currentTypeItInstance = null;
        }

        // Stop fallback typewriter if it's running
        if (this.fallbackTypewriterTimer) {
            clearInterval(this.fallbackTypewriterTimer);
            this.fallbackTypewriterTimer = null;
        }

        // Remove the placeholders
        if (this.lastUserMessageId) {
            const userMsg = document.querySelector(`[data-message-id="${this.lastUserMessageId}"]`);
            if (userMsg) userMsg.remove();
            this.lastUserMessageId = null;
        }
        
        if (this.lastAssistantMessageId) {
            const assistantMsg = document.querySelector(`[data-message-id="${this.lastAssistantMessageId}"]`);
            if (assistantMsg) assistantMsg.remove();
            this.lastAssistantMessageId = null;
        }

        // Restore input
        this.restoreInputState();

        // Reset button and state
        this.isSending = false;
        this.updateButtonToSend();

        this.showToast('已中断', 'info');
        
        // If chat area is empty, show agent welcome page
        const chatMessages = document.getElementById('chat-messages');
        if (chatMessages) {
            const messageContainers = chatMessages.querySelectorAll('.message-container');
            if (messageContainers.length === 0) {
                this.showAgentWelcome(this.currentAgent);
            }
        }
    }
}

// 创建全局UI管理器实例
window.uiManager = new UIManager();
