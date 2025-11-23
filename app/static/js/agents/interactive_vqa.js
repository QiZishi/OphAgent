// app/static/js/agents/interactive_vqa.js
// 智能问答智能体前端逻辑

class InteractiveVQAUI {
    constructor() {
        this.currentTypeitInstance = null;
    }

    // 渲染智能问答结果 - 使用标准的流式输出
    renderInteractiveVQA(messageElement, streamContent) {
        // 智能问答使用标准的markdown渲染，无需特殊处理
        // 内容会通过websocket流式输出并由main.js处理
        
        const finalAnswerContent = messageElement.querySelector('.final-answer-content');
        if (finalAnswerContent && streamContent) {
            // 如果是最终内容，使用marked渲染markdown
            if (window.marked) {
                finalAnswerContent.innerHTML = marked.parse(streamContent);
            } else {
                finalAnswerContent.textContent = streamContent;
            }
        }
    }

    // 处理智能问答特定的UI交互
    setupInteractiveVQAControls(messageElement) {
        // 可以添加智能问答特有的控件，如跟进问题建议等
        const controls = messageElement.querySelector('.controls');
        if (controls) {
            // 添加"提出跟进问题"按钮
            const followUpBtn = document.createElement('button');
            followUpBtn.innerHTML = '<i data-lucide="message-circle-plus"></i>跟进问题';
            followUpBtn.className = 'control-btn';
            followUpBtn.onclick = () => this.suggestFollowUpQuestions(messageElement);
            controls.appendChild(followUpBtn);
            
            // 重新渲染lucide图标
            if (window.lucide) {
                lucide.createIcons();
            }
        }
    }

    suggestFollowUpQuestions(messageElement) {
        // 基于当前回答内容，建议相关的跟进问题
        const suggestions = [
            "这种情况需要什么治疗？",
            "病情的严重程度如何？", 
            "有什么预防措施吗？",
            "需要定期复查吗？"
        ];

        const suggestionsList = suggestions.map(q => 
            `<button class="follow-up-question" onclick="fillUserInput('${q}')">${q}</button>`
        ).join('');

        const suggestionsHTML = `
            <div class="follow-up-suggestions">
                <h4>建议的跟进问题：</h4>
                <div class="suggestions-list">
                    ${suggestionsList}
                </div>
            </div>
        `;

        const existingSuggestions = messageElement.querySelector('.follow-up-suggestions');
        if (existingSuggestions) {
            existingSuggestions.remove();
        } else {
            messageElement.insertAdjacentHTML('beforeend', suggestionsHTML);
        }
    }
}

// 全局实例
window.interactiveVQAUI = new InteractiveVQAUI();

// 填充用户输入的辅助函数
function fillUserInput(question) {
    const userInput = document.getElementById('user-input');
    if (userInput) {
        userInput.value = question;
        userInput.focus();
    }
}
