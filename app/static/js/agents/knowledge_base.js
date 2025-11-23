// app/static/js/agents/knowledge_base.js
// 眼科知识库智能体前端逻辑

class KnowledgeBaseUI {
    constructor() {
        this.currentTypeitInstance = null;
        this.commonQuestions = [
            "什么是青光眼？",
            "糖尿病视网膜病变的症状有哪些？",
            "白内障如何治疗？",
            "高度近视有什么风险？",
            "黄斑变性是什么？",
            "如何预防干眼症？",
            "眼底检查的重要性是什么？",
            "近视激光手术安全吗？"
        ];
    }

    // 当选择知识库智能体时，禁用文件上传
    onAgentSelected() {
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        
        if (uploadBtn) {
            uploadBtn.disabled = true;
            uploadBtn.style.display = 'none';
            uploadBtn.title = '知识库模式不支持文件上传';
        }
        
        if (fileInput) {
            fileInput.disabled = true;
        }

        // 显示常用问题建议
        this.showCommonQuestions();
    }

    // 当离开知识库智能体时，恢复文件上传
    onAgentDeselected() {
        const uploadBtn = document.getElementById('upload-btn');
        const fileInput = document.getElementById('file-input');
        
        if (uploadBtn) {
            uploadBtn.disabled = false;
            uploadBtn.style.display = 'block';
            uploadBtn.title = '上传PDF文件或图片';
        }
        
        if (fileInput) {
            fileInput.disabled = false;
        }

        // 隐藏常用问题
        this.hideCommonQuestions();
    }

    // 显示常用问题建议
    showCommonQuestions() {
        const chatContainer = document.getElementById('chat-container');
        if (!chatContainer) return;

        // 检查是否已存在
        let questionsContainer = document.getElementById('common-questions-container');
        if (questionsContainer) {
            questionsContainer.style.display = 'block';
            return;
        }

        // 创建常用问题容器
        questionsContainer = document.createElement('div');
        questionsContainer.id = 'common-questions-container';
        questionsContainer.className = 'common-questions-container';
        
        const questionsHTML = `
            <div class="common-questions">
                <h3>💡 常用问题</h3>
                <p>您可以点击下方问题快速开始，或直接输入您的问题：</p>
                <div class="questions-grid">
                    ${this.commonQuestions.map(q => `
                        <button class="question-btn" onclick="knowledgeBaseUI.askQuestion('${q}')">
                            ${q}
                        </button>
                    `).join('')}
                </div>
            </div>
        `;
        
        questionsContainer.innerHTML = questionsHTML;
        
        // 插入到聊天容器的开头
        chatContainer.insertBefore(questionsContainer, chatContainer.firstChild);
    }

    // 隐藏常用问题
    hideCommonQuestions() {
        const questionsContainer = document.getElementById('common-questions-container');
        if (questionsContainer) {
            questionsContainer.style.display = 'none';
        }
    }

    // 点击问题时自动填入并发送
    askQuestion(question) {
        const userInput = document.getElementById('user-input');
        const sendBtn = document.getElementById('send-btn');
        
        if (userInput && sendBtn) {
            userInput.value = question;
            sendBtn.click();
        }
    }

    // 渲染知识库回答 - 使用标准的流式输出
    renderKnowledgeBase(messageElement, streamContent) {
        // 知识库使用标准的markdown渲染，无需特殊处理
        const finalAnswerContent = messageElement.querySelector('.final-answer-content');
        if (finalAnswerContent && streamContent) {
            // 使用marked渲染markdown
            if (window.marked) {
                finalAnswerContent.innerHTML = marked.parse(streamContent);
            } else {
                finalAnswerContent.textContent = streamContent;
            }
        }
    }

    // 设置知识库特定的控件
    setupKnowledgeBaseControls(messageElement) {
        const controls = messageElement.querySelector('.controls');
        if (controls) {
            // 添加"相关问题"按钮
            const relatedBtn = document.createElement('button');
            relatedBtn.innerHTML = '<i data-lucide="help-circle"></i>相关问题';
            relatedBtn.className = 'control-btn';
            relatedBtn.onclick = () => this.showRelatedQuestions(messageElement);
            controls.appendChild(relatedBtn);
            
            // 重新渲染lucide图标
            if (window.lucide) {
                lucide.createIcons();
            }
        }
    }

    // 显示相关问题
    showRelatedQuestions(messageElement) {
        // 基于回答内容生成相关问题
        const relatedQuestions = [
            "这种疾病的发病原因是什么？",
            "有哪些治疗方法？",
            "如何预防这种情况？",
            "需要注意什么？"
        ];

        const questionsList = relatedQuestions.map(q => 
            `<button class="related-question" onclick="knowledgeBaseUI.askQuestion('${q}')">${q}</button>`
        ).join('');

        const relatedHTML = `
            <div class="related-questions">
                <h4>🔗 相关问题：</h4>
                <div class="questions-list">
                    ${questionsList}
                </div>
            </div>
        `;

        const existingRelated = messageElement.querySelector('.related-questions');
        if (existingRelated) {
            existingRelated.remove();
        } else {
            messageElement.insertAdjacentHTML('beforeend', relatedHTML);
        }
    }
}

// 全局实例
window.knowledgeBaseUI = new KnowledgeBaseUI();
