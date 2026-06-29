/**
 * context-reader.js - 项目上下文读取
 * 
 * 功能：
 * - 从窗口标题解析项目信息
 * - 生成上下文摘要
 * - 复制到剪贴板
 */

class ContextReader {
    constructor() {
        this.cache = new Map();
    }

    // 从当前页面读取上下文
    async readCurrentContext() {
        // 获取页面标题
        const title = document.title;
        
        // 获取打开的文件（从 URL 或页面内容）
        const currentFile = this.extractFileFromTitle(title);
        
        // 获取项目名
        const projectName = this.extractProjectName(title);
        
        return {
            title: title,
            projectName: projectName,
            currentFile: currentFile,
            timestamp: new Date().toISOString()
        };
    }

    // 从窗口标题提取文件名
    extractFileFromTitle(title) {
        // 格式: "filename - project - AI"
        const parts = title.split(' - ');
        if (parts.length >= 2) {
            return parts[0].trim();
        }
        return null;
    }

    // 从窗口标题提取项目名
    extractProjectName(title) {
        // 格式: "filename - project - AI"
        const parts = title.split(' - ');
        if (parts.length >= 3) {
            return parts[1].trim();
        }
        return null;
    }

    // 生成上下文文本
    generateContextText(context) {
        let text = '';
        
        if (context.projectName) {
            text += `项目: ${context.projectName}\n`;
        }
        
        if (context.currentFile) {
            text += `当前文件: ${context.currentFile}\n`;
        }
        
        text += '\n---\n';
        
        return text;
    }

    // 复制到剪贴板
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (e) {
            console.error('Failed to copy:', e);
            return false;
        }
    }

    // 格式化选中文本
    formatSelection(selection, context) {
        let text = context ? this.generateContextText(context) : '';
        text += '以下是相关代码：\n```\n' + selection + '\n```';
        return text;
    }
}

// 导出单例
const contextReader = new ContextReader();
