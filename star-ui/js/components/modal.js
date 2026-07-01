// star-ui/js/components/modal.js
(function() {
    const Modal = {
        _stack: [],
        _escHandler: null,

        show: function(options) {
            options = options || {};
            const id = 'modal_' + Date.now() + '_' + Math.random().toString(36).substr(2, 5);
            const titleId = 'modal-title-' + id;

            const modal = document.createElement('div');
            modal.id = id;
            modal.className = 'modal-overlay';
            modal.setAttribute('role', 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', titleId);
            modal.innerHTML = `
                <div class="modal-dialog ${options.size || ''}">
                    <div class="modal-header">
                        <h3 class="modal-title" id="${titleId}">${UICommon.escapeHtml(options.title || '提示')}</h3>
                        ${options.closable !== false ? '<button class="modal-close">&times;</button>' : ''}
                    </div>
                    <div class="modal-body">
                        ${UICommon.escapeHtml(options.content || '')}
                    </div>
                    ${options.footer !== false ? `
                    <div class="modal-footer">
                        ${options.footer ? UICommon.escapeHtml(options.footer) : `
                            <button class="btn btn-secondary modal-cancel">取消</button>
                            <button class="btn btn-primary modal-confirm">确定</button>
                        `}
                    </div>` : ''}
                </div>
            `;

            document.body.appendChild(modal);
            this._stack.push(id);

            const self = this;

            const closeBtn = modal.querySelector('.modal-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => self.close(id));
            }

            const cancelBtn = modal.querySelector('.modal-cancel');
            if (cancelBtn) {
                cancelBtn.addEventListener('click', () => {
                    if (options.onCancel) options.onCancel();
                    self.close(id);
                });
            }

            const confirmBtn = modal.querySelector('.modal-confirm');
            if (confirmBtn) {
                confirmBtn.addEventListener('click', () => {
                    if (options.onConfirm) {
                        const result = options.onConfirm();
                        if (result !== false) self.close(id);
                    } else {
                        self.close(id);
                    }
                });
            }

            if (options.closable !== false) {
                modal.addEventListener('click', (e) => {
                    if (e.target === modal) self.close(id);
                });
            }

            // ESC 键关闭支持
            if (!this._escHandler) {
                this._escHandler = (e) => {
                    if (e.key === 'Escape' && self._stack.length > 0) {
                        self.close(self._stack[self._stack.length - 1]);
                    }
                };
                document.addEventListener('keydown', this._escHandler);
            }

            requestAnimationFrame(() => {
                modal.classList.add('show');
            });

            return id;
        },

        close: function(id) {
            const modal = document.getElementById(id);
            if (!modal) return;

            modal.classList.remove('show');
            setTimeout(() => {
                if (modal.parentNode) {
                    modal.parentNode.removeChild(modal);
                }
            }, 300);

            const idx = this._stack.indexOf(id);
            if (idx > -1) this._stack.splice(idx, 1);
        },

        confirm: function(message, onConfirm) {
            return this.show({
                title: '确认',
                content: `<p>${UICommon.escapeHtml(message)}</p>`,
                onConfirm: onConfirm
            });
        },

        alert: function(message, onClose) {
            return this.show({
                title: '提示',
                content: `<p>${UICommon.escapeHtml(message)}</p>`,
                footer: '<button class="btn btn-primary modal-confirm">知道了</button>',
                onConfirm: onClose
            });
        }
    };

    if (typeof window !== 'undefined') {
        window.Modal = Modal;
    }
})();