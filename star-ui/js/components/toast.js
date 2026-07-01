// star-ui/js/components/toast.js
(function() {
    const Toast = {
        container: null,

        _ensureContainer: function() {
            if (!this.container) {
                this.container = document.createElement('div');
                this.container.id = 'toast-container';
                this.container.className = 'toast-container';
                document.body.appendChild(this.container);
            }
        },

        show: function(message, type, duration) {
            type = type || 'info';
            duration = duration || 3000;
            this._ensureContainer();

            const toast = document.createElement('div');
            toast.className = 'toast toast-' + type;
            toast.setAttribute('role', 'alert');
            toast.setAttribute('aria-live', 'polite');
            toast.innerHTML = `
                <span class="toast-icon">${this._getIcon(type)}</span>
                <span class="toast-message">${UICommon.escapeHtml(message)}</span>
            `;

            this.container.appendChild(toast);

            requestAnimationFrame(() => {
                toast.classList.add('show');
            });

            if (duration > 0) {
                setTimeout(() => {
                    toast.classList.remove('show');
                    setTimeout(() => {
                        if (toast.parentNode) {
                            toast.parentNode.removeChild(toast);
                        }
                    }, 300);
                }, duration);
            }

            return toast;
        },

        _getIcon: function(type) {
            const icons = {
                success: '✓',
                error: '✕',
                warning: '⚠',
                info: 'ℹ'
            };
            return icons[type] || icons.info;
        },

        success: function(msg, dur) { return this.show(msg, 'success', dur); },
        error: function(msg, dur) { return this.show(msg, 'error', dur); },
        warning: function(msg, dur) { return this.show(msg, 'warning', dur); },
        info: function(msg, dur) { return this.show(msg, 'info', dur); }
    };

    if (typeof window !== 'undefined') {
        window.Toast = Toast;
    }
})();