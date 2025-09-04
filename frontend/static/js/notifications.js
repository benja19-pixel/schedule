// Notifications.js - Sistema de notificaciones para MediConnect
// Maneja toasts, alerts y notificaciones del sistema

// Estado global de notificaciones
window.notificationState = {
    queue: [],
    activeToasts: [],
    maxToasts: 3,
    defaultDuration: 3000
};

// Tipos de notificación
const NotificationType = {
    SUCCESS: 'success',
    ERROR: 'error',
    WARNING: 'warning',
    INFO: 'info'
};

// Iconos para cada tipo
const NotificationIcons = {
    success: 'fas fa-check-circle',
    error: 'fas fa-times-circle',
    warning: 'fas fa-exclamation-triangle',
    info: 'fas fa-info-circle'
};

// Colores para cada tipo
const NotificationColors = {
    success: {
        bg: '#10b981',
        text: '#ffffff',
        icon: '#6ee7b7'
    },
    error: {
        bg: '#ef4444',
        text: '#ffffff',
        icon: '#fca5a5'
    },
    warning: {
        bg: '#f59e0b',
        text: '#ffffff',
        icon: '#fcd34d'
    },
    info: {
        bg: '#3b82f6',
        text: '#ffffff',
        icon: '#93c5fd'
    }
};

/**
 * Muestra una notificación toast
 * @param {string} message - Mensaje a mostrar
 * @param {string} type - Tipo de notificación (success, error, warning, info)
 * @param {number} duration - Duración en milisegundos (opcional)
 */
function showToast(message, type = 'info', duration = 3000) {
    // Verificar si ya existe un contenedor de toasts
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        toastContainer = createToastContainer();
    }
    
    // Crear el toast
    const toast = createToast(message, type);
    
    // Agregar al contenedor
    toastContainer.appendChild(toast);
    
    // Animar entrada
    setTimeout(() => {
        toast.classList.add('show');
    }, 10);
    
    // Auto-cerrar después de la duración especificada
    if (duration > 0) {
        setTimeout(() => {
            removeToast(toast);
        }, duration);
    }
    
    // Agregar al estado
    window.notificationState.activeToasts.push(toast);
    
    // Limitar número de toasts visibles
    if (window.notificationState.activeToasts.length > window.notificationState.maxToasts) {
        const oldestToast = window.notificationState.activeToasts.shift();
        removeToast(oldestToast);
    }
    
    return toast;
}

/**
 * Crea el contenedor principal de toasts
 */
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.style.cssText = `
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 12px;
        pointer-events: none;
    `;
    document.body.appendChild(container);
    return container;
}

/**
 * Crea un elemento toast
 */
function createToast(message, type) {
    const toast = document.createElement('div');
    toast.className = 'notification-toast';
    
    const colors = NotificationColors[type] || NotificationColors.info;
    const icon = NotificationIcons[type] || NotificationIcons.info;
    
    toast.style.cssText = `
        background: ${colors.bg};
        color: ${colors.text};
        padding: 16px 24px;
        border-radius: 12px;
        box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.3);
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 300px;
        max-width: 500px;
        transform: translateX(400px);
        opacity: 0;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        pointer-events: auto;
        cursor: pointer;
    `;
    
    // Icono
    const iconElement = document.createElement('i');
    iconElement.className = icon;
    iconElement.style.cssText = `
        font-size: 20px;
        flex-shrink: 0;
    `;
    
    // Mensaje
    const messageElement = document.createElement('span');
    messageElement.textContent = message;
    messageElement.style.cssText = `
        flex: 1;
        font-size: 14px;
        font-weight: 500;
        line-height: 1.4;
    `;
    
    // Botón de cerrar
    const closeButton = document.createElement('button');
    closeButton.innerHTML = '<i class="fas fa-times"></i>';
    closeButton.style.cssText = `
        background: none;
        border: none;
        color: ${colors.text};
        opacity: 0.7;
        cursor: pointer;
        padding: 0;
        margin-left: 12px;
        font-size: 16px;
        transition: opacity 0.2s;
    `;
    
    closeButton.onmouseover = () => closeButton.style.opacity = '1';
    closeButton.onmouseout = () => closeButton.style.opacity = '0.7';
    closeButton.onclick = (e) => {
        e.stopPropagation();
        removeToast(toast);
    };
    
    // Click en el toast para cerrarlo
    toast.onclick = () => removeToast(toast);
    
    // Ensamblar el toast
    toast.appendChild(iconElement);
    toast.appendChild(messageElement);
    toast.appendChild(closeButton);
    
    // Clase para mostrar
    toast.classList.add('notification-toast-enter');
    
    return toast;
}

/**
 * Remueve un toast con animación
 */
function removeToast(toast) {
    if (!toast || toast.removing) return;
    
    toast.removing = true;
    toast.style.transform = 'translateX(400px)';
    toast.style.opacity = '0';
    
    setTimeout(() => {
        if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
        }
        
        // Remover del estado
        const index = window.notificationState.activeToasts.indexOf(toast);
        if (index > -1) {
            window.notificationState.activeToasts.splice(index, 1);
        }
    }, 300);
}

/**
 * Muestra una notificación de confirmación
 */
function showConfirm(message, onConfirm, onCancel) {
    // Crear overlay
    const overlay = document.createElement('div');
    overlay.className = 'notification-confirm-overlay';
    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(8px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s ease;
    `;
    
    // Crear modal
    const modal = document.createElement('div');
    modal.className = 'notification-confirm-modal';
    modal.style.cssText = `
        background: white;
        border-radius: 16px;
        padding: 24px;
        max-width: 400px;
        width: 90%;
        transform: scale(0.9);
        transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    `;
    
    // Contenido
    modal.innerHTML = `
        <h3 style="font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 12px;">
            Confirmar acción
        </h3>
        <p style="font-size: 14px; color: #6b7280; margin-bottom: 24px;">
            ${message}
        </p>
        <div style="display: flex; gap: 12px;">
            <button id="confirm-yes" style="
                flex: 1;
                background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            ">Confirmar</button>
            <button id="confirm-no" style="
                flex: 1;
                background: #e5e7eb;
                color: #374151;
                padding: 10px 20px;
                border: none;
                border-radius: 8px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            ">Cancelar</button>
        </div>
    `;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Animar entrada
    setTimeout(() => {
        overlay.style.opacity = '1';
        modal.style.transform = 'scale(1)';
    }, 10);
    
    // Event listeners
    const closeModal = () => {
        overlay.style.opacity = '0';
        modal.style.transform = 'scale(0.9)';
        setTimeout(() => {
            document.body.removeChild(overlay);
        }, 300);
    };
    
    document.getElementById('confirm-yes').onclick = () => {
        closeModal();
        if (onConfirm) onConfirm();
    };
    
    document.getElementById('confirm-no').onclick = () => {
        closeModal();
        if (onCancel) onCancel();
    };
    
    // Cerrar con ESC
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            closeModal();
            if (onCancel) onCancel();
            document.removeEventListener('keydown', handleEscape);
        }
    };
    document.addEventListener('keydown', handleEscape);
}

/**
 * Muestra una notificación de progreso
 */
function showProgress(message, progress = 0) {
    let progressContainer = document.getElementById('progress-notification');
    
    if (!progressContainer) {
        progressContainer = document.createElement('div');
        progressContainer.id = 'progress-notification';
        progressContainer.style.cssText = `
            position: fixed;
            top: 24px;
            left: 50%;
            transform: translateX(-50%);
            background: white;
            border-radius: 12px;
            padding: 16px 24px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
            z-index: 10000;
            min-width: 300px;
        `;
        document.body.appendChild(progressContainer);
    }
    
    progressContainer.innerHTML = `
        <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
            <div class="spinner" style="
                width: 20px;
                height: 20px;
                border: 2px solid #e5e7eb;
                border-top-color: #6366f1;
                border-radius: 50%;
                animation: spin 1s linear infinite;
            "></div>
            <span style="font-size: 14px; font-weight: 500; color: #374151;">${message}</span>
        </div>
        <div style="background: #e5e7eb; height: 4px; border-radius: 2px; overflow: hidden;">
            <div style="
                background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
                height: 100%;
                width: ${progress}%;
                transition: width 0.3s ease;
            "></div>
        </div>
    `;
    
    return {
        update: (newProgress, newMessage) => {
            if (newMessage) {
                progressContainer.querySelector('span').textContent = newMessage;
            }
            progressContainer.querySelector('div[style*="background: linear-gradient"]').style.width = `${newProgress}%`;
        },
        close: () => {
            if (progressContainer.parentNode) {
                progressContainer.parentNode.removeChild(progressContainer);
            }
        }
    };
}

/**
 * Muestra una notificación inline en un elemento
 */
function showInlineNotification(element, message, type = 'info') {
    if (!element) return;
    
    // Remover notificación anterior si existe
    const existingNotification = element.querySelector('.inline-notification');
    if (existingNotification) {
        existingNotification.remove();
    }
    
    const notification = document.createElement('div');
    notification.className = 'inline-notification';
    
    const colors = {
        success: { bg: '#d1fae5', border: '#10b981', text: '#065f46' },
        error: { bg: '#fee2e2', border: '#ef4444', text: '#991b1b' },
        warning: { bg: '#fef3c7', border: '#f59e0b', text: '#92400e' },
        info: { bg: '#dbeafe', border: '#3b82f6', text: '#1e40af' }
    };
    
    const color = colors[type] || colors.info;
    const icon = NotificationIcons[type] || NotificationIcons.info;
    
    notification.style.cssText = `
        background: ${color.bg};
        border: 1px solid ${color.border};
        color: ${color.text};
        padding: 12px 16px;
        border-radius: 8px;
        margin-top: 8px;
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        animation: slideDown 0.3s ease;
    `;
    
    notification.innerHTML = `
        <i class="${icon}"></i>
        <span>${message}</span>
    `;
    
    element.appendChild(notification);
    
    // Auto-remover después de 5 segundos
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'slideUp 0.3s ease';
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.remove();
                }
            }, 300);
        }
    }, 5000);
    
    return notification;
}

// Agregar estilos CSS necesarios
const styles = document.createElement('style');
styles.textContent = `
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    @keyframes slideDown {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes slideUp {
        from {
            opacity: 1;
            transform: translateY(0);
        }
        to {
            opacity: 0;
            transform: translateY(-10px);
        }
    }
    
    .notification-toast.show {
        transform: translateX(0) !important;
        opacity: 1 !important;
    }
`;
document.head.appendChild(styles);

// Exportar funciones globalmente
window.showToast = showToast;
window.showConfirm = showConfirm;
window.showProgress = showProgress;
window.showInlineNotification = showInlineNotification;
window.NotificationType = NotificationType;

// Inicialización
console.log('Notification system initialized');