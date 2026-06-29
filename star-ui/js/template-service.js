/**
 * template-service.js - 快捷指令模板服务
 * 
 * 功能：
 * - 预设模板
 * - 用户自定义模板 CRUD
 * - 变量替换
 * - 导入导出
 */

class TemplateService {
    constructor() {
        this.storageKey = 'star_command_templates';
        this.defaultTemplates = [
            {
                id: 'explain',
                name: '解释代码',
                content: '解释以下代码的作用：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'optimize',
                name: '优化函数',
                content: '优化以下函数，提高性能和可读性：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'review',
                name: '代码审查',
                content: '对以下代码进行审查，指出潜在问题和改进建议：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'test',
                name: '生成测试',
                content: '为以下代码生成单元测试：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'translate',
                name: '翻译注释',
                content: '将以下代码的注释翻译成中文：\n{selection}',
                variables: ['selection']
            },
            {
                id: 'fixbug',
                name: '修复 Bug',
                content: '修复以下代码中的 Bug：\n{selection}',
                variables: ['selection']
            }
        ];
    }

    // 获取所有模板
    getAll() {
        const stored = localStorage.getItem(this.storageKey);
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch {
                return this.defaultTemplates;
            }
        }
        return this.defaultTemplates;
    }

    // 保存所有模板
    saveAll(templates) {
        localStorage.setItem(this.storageKey, JSON.stringify(templates));
    }

    // 获取单个模板
    getById(id) {
        const templates = this.getAll();
        return templates.find(t => t.id === id);
    }

    // 添加模板
    add(template) {
        const templates = this.getAll();
        template.id = 'custom_' + Date.now();
        templates.push(template);
        this.saveAll(templates);
        return template;
    }

    // 更新模板
    update(id, updates) {
        const templates = this.getAll();
        const index = templates.findIndex(t => t.id === id);
        if (index >= 0) {
            templates[index] = { ...templates[index], ...updates };
            this.saveAll(templates);
            return templates[index];
        }
        return null;
    }

    // 删除模板
    delete(id) {
        const templates = this.getAll();
        const filtered = templates.filter(t => t.id !== id);
        this.saveAll(filtered);
    }

    // 替换变量
    render(template, context = {}) {
        let content = template.content;
        for (const [key, value] of Object.entries(context)) {
            const regex = new RegExp(`\\{${key}\\}`, 'g');
            content = content.replace(regex, value);
        }
        return content;
    }

    // 导出模板
    export() {
        const templates = this.getAll();
        const customTemplates = templates.filter(t => t.id.startsWith('custom_'));
        return JSON.stringify(customTemplates, null, 2);
    }

    // 导入模板
    import(jsonString) {
        try {
            const imported = JSON.parse(jsonString);
            if (Array.isArray(imported)) {
                const templates = this.getAll();
                for (const t of imported) {
                    t.id = 'custom_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
                    templates.push(t);
                }
                this.saveAll(templates);
                return { success: true, count: imported.length };
            }
            return { success: false, error: 'Invalid format' };
        } catch (e) {
            return { success: false, error: e.message };
        }
    }

    // 重置为默认模板
    reset() {
        localStorage.removeItem(this.storageKey);
    }
}

// 导出单例
const templateService = new TemplateService();
