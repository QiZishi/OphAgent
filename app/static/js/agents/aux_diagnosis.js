// app/static/js/agents/aux_diagnosis.js
// 辅助诊断智能体专属UI逻辑

class AuxDiagnosisUI {
    constructor() {
        this.diagnosisData = [];
    }

    // 处理辅助诊断结果
    renderDiagnosisResults(messageElement, data) {
        try {
            const responseData = typeof data === 'string' ? JSON.parse(data) : data;
            const { diagnoses } = responseData;

            if (!diagnoses || !Array.isArray(diagnoses)) {
                console.error('Invalid diagnosis data');
                return;
            }

            this.diagnosisData = diagnoses;
            this.createDiagnosisList(messageElement, diagnoses);
        } catch (error) {
            console.error('Error rendering diagnosis results:', error);
        }
    }

    createDiagnosisList(messageElement, diagnoses) {
        const contentWrapper = messageElement.querySelector('.final-answer-content');
        if (!contentWrapper) return;

        // 创建诊断列表容器
        const listContainer = document.createElement('div');
        listContainer.className = 'diagnosis-list';

        // 添加标题
        const title = document.createElement('h4');
        title.textContent = `诊断结果 (${diagnoses.length}个可能性)`;
        title.style.cssText = 'margin: 0 0 16px 0; color: #333; font-size: 18px;';
        listContainer.appendChild(title);

        // 创建诊断项
        diagnoses.forEach((diagnosis, index) => {
            const diagnosisItem = this.createDiagnosisItem(diagnosis, index);
            listContainer.appendChild(diagnosisItem);
        });

        contentWrapper.appendChild(listContainer);
    }

    createDiagnosisItem(diagnosis, index) {
        const { condition, confidence, reasoning } = diagnosis;
        
        const itemContainer = document.createElement('div');
        itemContainer.className = 'diagnosis-item';
        itemContainer.dataset.index = index;

        // 创建诊断头部
        const header = document.createElement('div');
        header.className = 'diagnosis-header';
        
        const infoSection = document.createElement('div');
        infoSection.className = 'diagnosis-info';
        
        const conditionTitle = document.createElement('div');
        conditionTitle.className = 'diagnosis-condition';
        conditionTitle.textContent = condition;
        
        const confidenceSection = document.createElement('div');
        confidenceSection.style.cssText = 'display: flex; align-items: center; margin-top: 8px;';
        
        const confidenceBar = this.createConfidenceBar(confidence);
        const confidenceText = document.createElement('span');
        confidenceText.className = 'confidence-text';
        confidenceText.textContent = `${(confidence * 100).toFixed(1)}%`;
        
        confidenceSection.appendChild(confidenceBar);
        confidenceSection.appendChild(confidenceText);
        
        infoSection.appendChild(conditionTitle);
        infoSection.appendChild(confidenceSection);
        
        const expandIcon = document.createElement('i');
        expandIcon.setAttribute('data-lucide', 'chevron-down');
        expandIcon.style.cssText = 'transition: transform 0.2s ease; color: #666;';
        
        header.appendChild(infoSection);
        header.appendChild(expandIcon);
        
        // 创建推理内容区域
        const reasoningSection = document.createElement('div');
        reasoningSection.className = 'diagnosis-reasoning';
        reasoningSection.style.display = 'none';
        reasoningSection.innerHTML = `
            <h5 style="margin: 0 0 8px 0; color: #4A90E2; font-size: 14px;">分析依据：</h5>
            <p style="margin: 0; line-height: 1.6;">${reasoning}</p>
        `;
        
        // 添加点击事件
        header.addEventListener('click', () => {
            this.toggleDiagnosisItem(itemContainer, expandIcon, reasoningSection);
        });
        
        itemContainer.appendChild(header);
        itemContainer.appendChild(reasoningSection);
        
        return itemContainer;
    }

    createConfidenceBar(confidence) {
        const barContainer = document.createElement('div');
        barContainer.className = 'confidence-bar';
        
        const barFill = document.createElement('div');
        barFill.className = 'confidence-fill';
        
        // 根据置信度设置颜色
        let color;
        if (confidence >= 0.8) {
            color = '#28a745'; // 绿色 - 高置信度
        } else if (confidence >= 0.6) {
            color = '#ffc107'; // 黄色 - 中等置信度
        } else {
            color = '#dc3545'; // 红色 - 低置信度
        }
        
        barFill.style.cssText = `
            width: ${confidence * 100}%;
            background: linear-gradient(90deg, ${color}, ${this.lightenColor(color, 20)});
            transition: width 0.5s ease;
        `;
        
        barContainer.appendChild(barFill);
        return barContainer;
    }

    toggleDiagnosisItem(itemContainer, expandIcon, reasoningSection) {
        const isExpanded = reasoningSection.style.display === 'block';
        
        if (isExpanded) {
            // 收起
            reasoningSection.style.display = 'none';
            expandIcon.style.transform = 'rotate(0deg)';
            itemContainer.classList.remove('expanded');
        } else {
            // 展开
            reasoningSection.style.display = 'block';
            expandIcon.style.transform = 'rotate(180deg)';
            itemContainer.classList.add('expanded');
            
            // 添加动画效果
            reasoningSection.style.opacity = '0';
            reasoningSection.style.transform = 'translateY(-10px)';
            
            setTimeout(() => {
                reasoningSection.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
                reasoningSection.style.opacity = '1';
                reasoningSection.style.transform = 'translateY(0)';
            }, 10);
        }
        
        // 重新创建图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    lightenColor(color, percent) {
        // 简单的颜色变亮函数
        const amount = Math.round(2.55 * percent);
        const R = parseInt(color.slice(1, 3), 16);
        const G = parseInt(color.slice(3, 5), 16);
        const B = parseInt(color.slice(5, 7), 16);
        
        const newR = Math.min(255, R + amount).toString(16).padStart(2, '0');
        const newG = Math.min(255, G + amount).toString(16).padStart(2, '0');
        const newB = Math.min(255, B + amount).toString(16).padStart(2, '0');
        
        return `#${newR}${newG}${newB}`;
    }

    // 导出诊断结果
    exportDiagnosis() {
        if (this.diagnosisData.length === 0) return;
        
        let content = '# 辅助诊断结果\n\n';
        content += `生成时间: ${new Date().toLocaleString('zh-CN')}\n\n`;
        
        this.diagnosisData.forEach((diagnosis, index) => {
            content += `## ${index + 1}. ${diagnosis.condition}\n\n`;
            content += `**置信度:** ${(diagnosis.confidence * 100).toFixed(1)}%\n\n`;
            content += `**分析依据:** ${diagnosis.reasoning}\n\n`;
            content += '---\n\n';
        });
        
        // 创建下载链接
        const blob = new Blob([content], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `辅助诊断结果_${new Date().toISOString().split('T')[0]}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // 获取最高置信度的诊断
    getTopDiagnosis() {
        if (this.diagnosisData.length === 0) return null;
        return this.diagnosisData[0]; // 假设数据已按置信度排序
    }

    // 获取需要进一步检查的诊断
    getDiagnosesNeedingReview() {
        return this.diagnosisData.filter(d => d.confidence < 0.7);
    }

    // 根据md文档规范渲染诊断卡片
    renderDiagnosticCards(diagnoses) {
        const container = document.getElementById('diagnoses-container'); // 结果容器
        if (!container) return;
        
        container.innerHTML = ''; // 清空旧内容
        diagnoses.forEach((diag, index) => {
            const confidencePercentage = (diag.confidence * 100).toFixed(1);
            const cardHtml = `
                <div class="diag-card">
                    <div class="diag-header">
                        <span class="diag-condition">${diag.condition}</span>
                        <span class="diag-confidence">置信度: ${confidencePercentage}%</span>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" style="width: ${confidencePercentage}%;"></div>
                    </div>
                    <div class="diag-reasoning">
                        <button class="reasoning-toggle" onclick="auxDiagnosisUI.toggleReasoning(this)">显示分析依据</button>
                        <p class="reasoning-text" style="display: none;">${diag.reasoning}</p>
                    </div>
                </div>
            `;
            container.innerHTML += cardHtml;
        });
    }

    toggleReasoning(button) {
        const reasoningText = button.nextElementSibling;
        const isVisible = reasoningText.style.display === 'block';
        reasoningText.style.display = isVisible ? 'none' : 'block';
        button.textContent = isVisible ? '显示分析依据' : '隐藏分析依据';
    }
}

// 创建全局实例
window.auxDiagnosisUI = new AuxDiagnosisUI();
