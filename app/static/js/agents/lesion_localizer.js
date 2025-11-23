// app/static/js/agents/lesion_localizer.js
// 病灶定位智能体专属UI逻辑

class LesionLocalizerUI {
    constructor() {
        this.canvas = null;
        this.ctx = null;
        this.imageElement = null;
        this.boundingBoxes = [];
    }

    // 处理病灶定位结果
    renderLesionLocalization(messageElement, data) {
        try {
            const responseData = typeof data === 'string' ? JSON.parse(data) : data;
            const { image_url, boxes } = responseData;

            if (!image_url || !boxes) {
                console.error('Invalid lesion localization data');
                return;
            }

            this.boundingBoxes = boxes;
            this.createLesionCanvas(messageElement, image_url, boxes);
        } catch (error) {
            console.error('Error rendering lesion localization:', error);
        }
    }

    createLesionCanvas(messageElement, imageUrl, boxes) {
        const contentWrapper = messageElement.querySelector('.final-answer-content');
        if (!contentWrapper) return;

        // 创建画布容器
        const canvasContainer = document.createElement('div');
        canvasContainer.className = 'lesion-canvas-container';

        // 创建图片元素
        this.imageElement = document.createElement('img');
        this.imageElement.onload = () => {
            this.setupCanvas(canvasContainer, boxes);
        };
        this.imageElement.src = imageUrl;
        this.imageElement.style.display = 'none'; // 隐藏原始图片

        // 创建画布
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'lesion-canvas';
        this.ctx = this.canvas.getContext('2d');

        canvasContainer.appendChild(this.imageElement);
        canvasContainer.appendChild(this.canvas);
        contentWrapper.appendChild(canvasContainer);

        // 添加病灶列表
        if (boxes && boxes.length > 0) {
            this.createLesionList(contentWrapper, boxes);
        } 
    }

    setupCanvas(container, boxes) {
        const img = this.imageElement;
        const canvas = this.canvas;
        const ctx = this.ctx;

        // 设置画布尺寸
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;

        // 计算显示尺寸（保持宽高比）
        const maxWidth = Math.min(600, container.clientWidth);
        const aspectRatio = img.naturalHeight / img.naturalWidth;
        const displayWidth = maxWidth;
        const displayHeight = displayWidth * aspectRatio;

        canvas.style.width = displayWidth + 'px';
        canvas.style.height = displayHeight + 'px';

        // 绘制背景图片
        ctx.drawImage(img, 0, 0);

        // 绘制边界框
        this.drawBoundingBoxes(ctx, boxes);

        // 添加交互事件
        this.addCanvasInteractions(canvas, boxes);
    }

    drawBoundingBoxes(ctx, boxes) {
        boxes.forEach((box, index) => {
            const { coords, label, confidence } = box;
            const [x1, y1, x2, y2] = coords;

            // 设置边界框样式
            ctx.strokeStyle = this.getBoxColor(confidence);
            ctx.lineWidth = 3;
            ctx.fillStyle = this.getBoxColor(confidence, 0.2);

            // 绘制边界框
            const width = x2 - x1;
            const height = y2 - y1;
            ctx.fillRect(x1, y1, width, height);
            ctx.strokeRect(x1, y1, width, height);

            // 绘制标签背景
            const labelText = `${label} (${(confidence * 100).toFixed(1)}%)`;
            const textMetrics = ctx.measureText(labelText);
            const labelWidth = textMetrics.width + 12;
            const labelHeight = 24;

            ctx.fillStyle = this.getBoxColor(confidence);
            ctx.fillRect(x1, y1 - labelHeight, labelWidth, labelHeight);

            // 绘制标签文字
            ctx.fillStyle = '#ffffff';
            ctx.font = '12px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
            ctx.textBaseline = 'middle';
            ctx.fillText(labelText, x1 + 6, y1 - labelHeight / 2);
        });
    }

    getBoxColor(confidence, alpha = 1) {
        // 根据置信度返回颜色
        if (confidence >= 0.8) {
            return alpha === 1 ? '#dc3545' : `rgba(220, 53, 69, ${alpha})`; // 红色 - 高置信度
        } else if (confidence >= 0.6) {
            return alpha === 1 ? '#fd7e14' : `rgba(253, 126, 20, ${alpha})`; // 橙色 - 中等置信度
        } else {
            return alpha === 1 ? '#ffc107' : `rgba(255, 193, 7, ${alpha})`; // 黄色 - 低置信度
        }
    }

    addCanvasInteractions(canvas, boxes) {
        let tooltip = null;

        canvas.addEventListener('mousemove', (event) => {
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            const x = (event.clientX - rect.left) * scaleX;
            const y = (event.clientY - rect.top) * scaleY;

            // 检查鼠标是否在任何边界框内
            const hoveredBox = boxes.find(box => {
                const [x1, y1, x2, y2] = box.coords;
                return x >= x1 && x <= x2 && y >= y1 && y <= y2;
            });

            if (hoveredBox) {
                canvas.style.cursor = 'pointer';
                this.showTooltip(event, hoveredBox);
            } else {
                canvas.style.cursor = 'default';
                this.hideTooltip();
            }
        });

        canvas.addEventListener('mouseleave', () => {
            this.hideTooltip();
        });

        canvas.addEventListener('click', (event) => {
            const rect = canvas.getBoundingClientRect();
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            const x = (event.clientX - rect.left) * scaleX;
            const y = (event.clientY - rect.top) * scaleY;

            const clickedBox = boxes.find(box => {
                const [x1, y1, x2, y2] = box.coords;
                return x >= x1 && x <= x2 && y >= y1 && y <= y2;
            });

            if (clickedBox) {
                this.highlightLesion(clickedBox);
            }
        });
    }

    showTooltip(event, box) {
        this.hideTooltip();

        const tooltip = document.createElement('div');
        tooltip.className = 'lesion-tooltip';
        tooltip.innerHTML = `
            <strong>${box.label}</strong><br>
            置信度: ${(box.confidence * 100).toFixed(1)}%<br>
            位置: (${box.coords[0]}, ${box.coords[1]})
        `;
        tooltip.style.cssText = `
            position: absolute;
            background: rgba(0, 0, 0, 0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            line-height: 1.4;
            z-index: 1000;
            pointer-events: none;
            left: ${event.pageX + 10}px;
            top: ${event.pageY - 10}px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        `;

        document.body.appendChild(tooltip);
        this.tooltip = tooltip;
    }

    hideTooltip() {
        if (this.tooltip) {
            document.body.removeChild(this.tooltip);
            this.tooltip = null;
        }
    }

    highlightLesion(box) {
        // 高亮显示选中的病灶
        console.log('Highlighted lesion:', box);
        
        // 可以添加更多的交互效果，比如放大显示、详细信息等
    }

    createLesionList(container, boxes) {
        const listContainer = document.createElement('div');
        listContainer.className = 'lesion-list';
        listContainer.innerHTML = `
            <h4 style="margin: 20px 0 12px 0; color: #333;">检测到的病灶 (${boxes.length}个)</h4>
        `;

        const list = document.createElement('ul');
        list.style.cssText = 'margin: 0; padding-left: 20px; list-style-type: none;';

        boxes.forEach((box, index) => {
            const listItem = document.createElement('li');
            listItem.style.cssText = `
                margin-bottom: 8px;
                padding: 8px 12px;
                background: #f8f9fa;
                border-left: 4px solid ${this.getBoxColor(box.confidence)};
                border-radius: 0 6px 6px 0;
                cursor: pointer;
                transition: background-color 0.2s ease;
            `;
            
            listItem.innerHTML = `
                <strong>${box.label}</strong>
                <span style="float: right; color: #666;">${(box.confidence * 100).toFixed(1)}%</span>
                <br>
                <small style="color: #888;">位置: (${box.coords[0]}, ${box.coords[1]}) - (${box.coords[2]}, ${box.coords[3]})</small>
            `;

            listItem.addEventListener('mouseenter', () => {
                listItem.style.backgroundColor = '#e9ecef';
            });

            listItem.addEventListener('mouseleave', () => {
                listItem.style.backgroundColor = '#f8f9fa';
            });

            listItem.addEventListener('click', () => {
                this.highlightLesion(box);
            });

            list.appendChild(listItem);
        });

        listContainer.appendChild(list);
        container.appendChild(listContainer);
    }

    // 根据md文档规范渲染病灶边界框
    renderLesionBoxes(imageUrl, boxes) {
        const canvas = document.getElementById('lesion-canvas'); // 假设HTML中已有此canvas
        if (!canvas) return;
        
        const ctx = canvas.getContext('2d');
        const img = new Image();

        img.onload = () => {
            // 设置canvas尺寸与图片一致
            canvas.width = img.width;
            canvas.height = img.height;
            // 绘制背景图
            ctx.drawImage(img, 0, 0);

            // 遍历并绘制边界框
            boxes.forEach(box => {
                const [x_min, y_min, x_max, y_max] = box.coords;
                const label = `${box.label} (${(box.confidence * 100).toFixed(1)}%)`;

                // 绘制矩形框
                ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)'; // 红色
                ctx.lineWidth = 2;
                ctx.strokeRect(x_min, y_min, x_max - x_min, y_max - y_min);

                // 绘制标签背景
                ctx.fillStyle = 'rgba(255, 0, 0, 0.8)';
                const textMetrics = ctx.measureText(label);
                ctx.fillRect(x_min, y_min - 20, textMetrics.width + 8, 20);

                // 绘制标签文字
                ctx.fillStyle = '#FFFFFF';
                ctx.font = '14px Arial';
                ctx.fillText(label, x_min + 4, y_min - 5);
            });
        };
        img.src = imageUrl;
    }
}

// 创建全局实例
window.lesionLocalizerUI = new LesionLocalizerUI();
