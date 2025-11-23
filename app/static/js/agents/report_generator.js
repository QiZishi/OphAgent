// app/static/js/agents/report_generator.js
// 报告生成智能体专属UI逻辑

class ReportGeneratorUI {
    constructor() {
        this.reportContent = '';
        this.reportData = null;
    }

    // 处理报告生成结果
    renderReport(messageElement, content) {
        this.reportContent = content;
        this.createReportView(messageElement, content);
    }

    createReportView(messageElement, content) {
        const contentWrapper = messageElement.querySelector('.final-answer-content');
        if (!contentWrapper) return;

        // 创建报告视图容器
        const reportContainer = document.createElement('div');
        reportContainer.className = 'report-view';

        // 渲染Markdown内容
        const reportHTML = this.renderMarkdown(content);
        reportContainer.innerHTML = reportHTML;

        // 添加报告工具栏
        const toolbar = this.createReportToolbar();
        
        // 组装报告视图
        const reportWrapper = document.createElement('div');
        reportWrapper.className = 'report-wrapper';
        reportWrapper.appendChild(toolbar);
        reportWrapper.appendChild(reportContainer);

        contentWrapper.appendChild(reportWrapper);

        // 添加打印样式
        this.addPrintStyles();
    }

    createReportToolbar() {
        const toolbar = document.createElement('div');
        toolbar.className = 'report-toolbar';
        toolbar.style.cssText = `
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 12px 16px;
            background: #f8f9fa;
            border: 1px solid #e1e5e9;
            border-bottom: none;
            border-radius: 8px 8px 0 0;
            margin-bottom: 0;
        `;

        const leftSection = document.createElement('div');
        leftSection.innerHTML = `
            <h4 style="margin: 0; color: #333; font-size: 16px;">
                <i data-lucide="file-text" style="width: 18px; height: 18px; margin-right: 8px; vertical-align: text-bottom;"></i>
                诊断报告
            </h4>
        `;

        const rightSection = document.createElement('div');
        rightSection.style.cssText = 'display: flex; gap: 8px;';

        // 导出PDF按钮
        const pdfBtn = document.createElement('button');
        pdfBtn.className = 'control-btn';
        pdfBtn.title = '导出PDF';
        pdfBtn.innerHTML = '<i data-lucide="download"></i>';
        pdfBtn.addEventListener('click', () => this.exportToPDF());

        // 打印按钮
        const printBtn = document.createElement('button');
        printBtn.className = 'control-btn';
        printBtn.title = '打印报告';
        printBtn.innerHTML = '<i data-lucide="printer"></i>';
        printBtn.addEventListener('click', () => this.printReport());

        // 复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'control-btn';
        copyBtn.title = '复制报告';
        copyBtn.innerHTML = '<i data-lucide="copy"></i>';
        copyBtn.addEventListener('click', () => this.copyReport());

        // 编辑按钮
        const editBtn = document.createElement('button');
        editBtn.className = 'control-btn';
        editBtn.title = '编辑报告';
        editBtn.innerHTML = '<i data-lucide="edit-3"></i>';
        editBtn.addEventListener('click', () => this.editReport());

        rightSection.appendChild(copyBtn);
        rightSection.appendChild(editBtn);
        rightSection.appendChild(printBtn);
        rightSection.appendChild(pdfBtn);

        toolbar.appendChild(leftSection);
        toolbar.appendChild(rightSection);

        return toolbar;
    }

    renderMarkdown(content) {
        if (typeof marked !== 'undefined') {
            // 自定义渲染器以适应报告格式
            const renderer = new marked.Renderer();
            
            // 自定义标题渲染
            renderer.heading = function(text, level) {
                const className = level === 1 ? 'report-title' : 
                                level === 2 ? 'report-section' : 
                                'report-subsection';
                return `<h${level} class="${className}">${text}</h${level}>`;
            };

            // 自定义列表渲染
            renderer.list = function(body, ordered) {
                const tag = ordered ? 'ol' : 'ul';
                return `<${tag} class="report-list">${body}</${tag}>`;
            };

            // 自定义表格渲染
            renderer.table = function(header, body) {
                return `<table class="report-table">
                    <thead>${header}</thead>
                    <tbody>${body}</tbody>
                </table>`;
            };

            marked.setOptions({
                renderer: renderer,
                gfm: true,
                breaks: true,
                sanitize: false
            });

            return marked.parse(content);
        } else {
            // 简单的Markdown渲染后备方案
            return content
                .replace(/^# (.*$)/gm, '<h1 class="report-title">$1</h1>')
                .replace(/^## (.*$)/gm, '<h2 class="report-section">$1</h2>')
                .replace(/^### (.*$)/gm, '<h3 class="report-subsection">$1</h3>')
                .replace(/^\*\*(.*)\*\*/gm, '<strong>$1</strong>')
                .replace(/^\* (.*$)/gm, '<li>$1</li>')
                .replace(/\n/g, '<br>');
        }
    }

    addPrintStyles() {
        if (document.getElementById('report-print-styles')) return;

        const style = document.createElement('style');
        style.id = 'report-print-styles';
        style.textContent = `
            @media print {
                .report-toolbar {
                    display: none !important;
                }
                
                .report-view {
                    box-shadow: none !important;
                    border: none !important;
                    margin: 0 !important;
                    padding: 20px !important;
                }
                
                .report-title {
                    page-break-after: avoid;
                    border-bottom: 2px solid #000 !important;
                    print-color-adjust: exact;
                }
                
                .report-section {
                    page-break-after: avoid;
                    margin-top: 20px !important;
                }
                
                .report-list li {
                    page-break-inside: avoid;
                }
                
                .report-table {
                    page-break-inside: avoid;
                }
            }
        `;
        
        document.head.appendChild(style);
    }

    exportToPDF() {
        if (typeof html2pdf === 'undefined') {
            console.error('html2pdf library not loaded');
            alert('PDF导出功能暂不可用，请使用打印功能');
            return;
        }

        const reportElement = document.querySelector('.report-view');
        if (!reportElement) return;

        // 创建一个副本用于PDF导出
        const clonedElement = reportElement.cloneNode(true);
        
        // 移除工具栏
        const toolbar = clonedElement.querySelector('.report-toolbar');
        if (toolbar) {
            toolbar.remove();
        }

        const opt = {
            margin: [15, 15, 15, 15],
            filename: `眼科诊断报告_${new Date().toISOString().split('T')[0]}.pdf`,
            image: { type: 'jpeg', quality: 0.98 },
            html2canvas: { 
                scale: 2,
                useCORS: true,
                letterRendering: true
            },
            jsPDF: { 
                unit: 'mm', 
                format: 'a4', 
                orientation: 'portrait',
                compress: true
            }
        };

        html2pdf().set(opt).from(clonedElement).save().then(() => {
            console.log('PDF导出完成');
        }).catch(error => {
            console.error('PDF导出失败:', error);
            alert('PDF导出失败，请稍后重试');
        });
    }

    printReport() {
        const reportElement = document.querySelector('.report-view');
        if (!reportElement) return;

        // 创建打印窗口
        const printWindow = window.open('', '_blank');
        
        // 构建打印内容
        const printContent = `
            <!DOCTYPE html>
            <html>
            <head>
                <title>眼科诊断报告</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 800px;
                        margin: 0 auto;
                        padding: 20px;
                    }
                    .report-title {
                        text-align: center;
                        border-bottom: 2px solid #333;
                        padding-bottom: 16px;
                        margin-bottom: 24px;
                    }
                    .report-section {
                        color: #4A90E2;
                        border-bottom: 1px solid #e1e5e9;
                        padding-bottom: 8px;
                        margin-top: 24px;
                        margin-bottom: 12px;
                    }
                    .report-list {
                        margin: 12px 0;
                        padding-left: 20px;
                    }
                    .report-list li {
                        margin-bottom: 6px;
                    }
                    .report-table {
                        width: 100%;
                        border-collapse: collapse;
                        margin: 16px 0;
                    }
                    .report-table th,
                    .report-table td {
                        border: 1px solid #ddd;
                        padding: 8px 12px;
                        text-align: left;
                    }
                    .report-table th {
                        background: #f8f9fa;
                    }
                    @media print {
                        body { margin: 0; }
                        .report-title { page-break-after: avoid; }
                        .report-section { page-break-after: avoid; }
                    }
                </style>
            </head>
            <body>
                ${reportElement.innerHTML}
            </body>
            </html>
        `;

        printWindow.document.write(printContent);
        printWindow.document.close();
        
        // 等待内容加载完成后打印
        printWindow.onload = () => {
            printWindow.print();
            printWindow.close();
        };
    }

    async copyReport() {
        try {
            await navigator.clipboard.writeText(this.reportContent);
            this.showToast('报告已复制到剪贴板', 'success');
        } catch (error) {
            console.error('复制失败:', error);
            
            // 回退方案
            const textArea = document.createElement('textarea');
            textArea.value = this.reportContent;
            textArea.style.position = 'fixed';
            textArea.style.left = '-999999px';
            textArea.style.top = '-999999px';
            document.body.appendChild(textArea);
            textArea.focus();
            textArea.select();
            
            try {
                document.execCommand('copy');
                this.showToast('报告已复制到剪贴板', 'success');
            } catch (e) {
                this.showToast('复制失败，请手动选择文本复制', 'error');
            }
            
            document.body.removeChild(textArea);
        }
    }

    editReport() {
        const reportElement = document.querySelector('.report-view');
        if (!reportElement) return;

        // 创建编辑器模态框
        this.createEditModal();
    }

    createEditModal() {
        // 创建模态框
        const modal = document.createElement('div');
        modal.className = 'report-edit-modal';
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            z-index: 10000;
            display: flex;
            align-items: center;
            justify-content: center;
        `;

        const modalContent = document.createElement('div');
        modalContent.style.cssText = `
            background: white;
            width: 90%;
            max-width: 800px;
            height: 80%;
            border-radius: 12px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        `;

        const modalHeader = document.createElement('div');
        modalHeader.style.cssText = `
            padding: 16px 20px;
            border-bottom: 1px solid #e1e5e9;
            display: flex;
            justify-content: space-between;
            align-items: center;
        `;
        modalHeader.innerHTML = `
            <h3 style="margin: 0;">编辑报告</h3>
            <button class="control-btn" onclick="this.closest('.report-edit-modal').remove()">
                <i data-lucide="x"></i>
            </button>
        `;

        const editor = document.createElement('textarea');
        editor.style.cssText = `
            flex: 1;
            padding: 20px;
            border: none;
            outline: none;
            resize: none;
            font-family: monospace;
            font-size: 14px;
            line-height: 1.5;
        `;
        editor.value = this.reportContent;

        const modalFooter = document.createElement('div');
        modalFooter.style.cssText = `
            padding: 16px 20px;
            border-top: 1px solid #e1e5e9;
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        `;
        modalFooter.innerHTML = `
            <button class="control-btn" onclick="this.closest('.report-edit-modal').remove()">取消</button>
            <button class="control-btn" style="background: #4A90E2; color: white;" onclick="reportGeneratorUI.saveEditedReport(this)">保存</button>
        `;

        modalContent.appendChild(modalHeader);
        modalContent.appendChild(editor);
        modalContent.appendChild(modalFooter);
        modal.appendChild(modalContent);
        document.body.appendChild(modal);

        // 重新创建图标
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }

    saveEditedReport(button) {
        const modal = button.closest('.report-edit-modal');
        const editor = modal.querySelector('textarea');
        const newContent = editor.value;

        // 更新报告内容
        this.reportContent = newContent;
        
        // 重新渲染报告
        const reportElement = document.querySelector('.report-view');
        if (reportElement) {
            reportElement.innerHTML = this.renderMarkdown(newContent);
        }

        // 关闭模态框
        modal.remove();

        this.showToast('报告已更新', 'success');
    }

    showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 8px;
            color: white;
            font-weight: 500;
            z-index: 10001;
            animation: slideIn 0.3s ease-out;
            ${type === 'success' ? 'background: #28a745;' : 
              type === 'error' ? 'background: #dc3545;' : 
              'background: #17a2b8;'}
        `;
        toast.textContent = message;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }
}

// 创建全局实例
window.reportGeneratorUI = new ReportGeneratorUI();
