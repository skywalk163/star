/**
 * notification-service.js - 任务完成通知服务
 * 
 * 功能：
 * - 请求通知权限
 * - 发送浏览器通知
 * - 音频提示
 * - 通知去重（5分钟内不重复）
 * - 状态变化检测
 */

class NotificationService {
    constructor() {
        this.enabled = false;
        this.soundEnabled = true;
        this.notifiedStars = new Map(); // star_id -> last_notify_time
        this.notifyCooldown = 5 * 60 * 1000; // 5分钟
        this.previousStatuses = new Map(); // 记录上一个状态
    }

    // 请求通知权限
    async requestPermission() {
        if (!('Notification' in window)) {
            console.warn('浏览器不支持通知');
            return false;
        }
        
        if (Notification.permission === 'granted') {
            this.enabled = true;
            return true;
        }
        
        if (Notification.permission !== 'denied') {
            const permission = await Notification.requestPermission();
            this.enabled = permission === 'granted';
            return this.enabled;
        }
        
        return false;
    }

    // 检查状态变化并发送通知
    checkAndNotify(starsData) {
        if (!this.enabled) return;
        
        for (const star of starsData.stars || []) {
            const starId = `${star.star_type}_${star.pid}`;
            const previousStatus = this.previousStatuses.get(starId);
            const currentStatus = star.overall_status;
            
            // 检测状态从工作/等待变为完成
            if (previousStatus && 
                (previousStatus === 'working' || previousStatus === 'waiting') &&
                currentStatus === 'completed') {
                
                // 检查是否在冷却期内
                if (this.isInCooldown(starId)) continue;
                
                // 发送通知
                this.notify(star);
                this.markNotified(starId);
            }
            
            // 更新状态记录
            this.previousStatuses.set(starId, currentStatus);
        }
    }

    // 发送通知
    notify(star) {
        const title = `${star.description || star.star_type} 任务完成`;
        
        // 获取任务摘要
        const taskPreview = star.windows?.[0]?.current_task || '未知任务';
        const body = taskPreview.length > 100 
            ? taskPreview.substring(0, 100) + '...' 
            : taskPreview;
        
        // 浏览器通知
        if (this.enabled) {
            const notification = new Notification(title, {
                body: body,
                icon: '/ui/icon.png',
                tag: `star_${star.star_type}_${star.pid}`,
                requireInteraction: true
            });
            
            notification.onclick = () => {
                window.focus();
                window.location.href = `/remote?hwnd=${star.windows?.[0]?.hwnd || ''}`;
                notification.close();
            };
        }
        
        // 音频提示
        if (this.soundEnabled) {
            this.playSound();
        }
    }

    // 播放提示音（使用 Web Audio API 生成简单音效）
    playSound() {
        try {
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.value = 800;
            oscillator.type = 'sine';
            gainNode.gain.value = 0.3;
            
            oscillator.start();
            
            setTimeout(() => {
                oscillator.stop();
                audioContext.close();
            }, 200);
        } catch (e) {
            console.warn('播放提示音失败:', e);
        }
    }

    isInCooldown(starId) {
        const lastNotify = this.notifiedStars.get(starId);
        if (!lastNotify) return false;
        return Date.now() - lastNotify < this.notifyCooldown;
    }

    markNotified(starId) {
        this.notifiedStars.set(starId, Date.now());
    }

    // 设置管理
    setEnabled(enabled) {
        this.enabled = enabled;
        localStorage.setItem('star_notification_enabled', enabled);
    }

    setSoundEnabled(enabled) {
        this.soundEnabled = enabled;
        localStorage.setItem('star_notification_sound', enabled);
    }

    loadSettings() {
        this.enabled = localStorage.getItem('star_notification_enabled') === 'true';
        this.soundEnabled = localStorage.getItem('star_notification_sound') !== 'false';
    }
}

// 导出单例
const notificationService = new NotificationService();
notificationService.loadSettings();
