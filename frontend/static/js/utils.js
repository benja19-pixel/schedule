// Utility functions for TruthLens

// Show notification
function showNotification(message, type = 'info') {
    // Remove any existing notifications
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(notif => notif.remove());
    
    // Create new notification
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    let icon;
    switch(type) {
        case 'success':
            icon = 'fa-check-circle';
            break;
        case 'error':
            icon = 'fa-exclamation-circle';
            break;
        case 'warning':
            icon = 'fa-exclamation-triangle';
            break;
        default:
            icon = 'fa-info-circle';
    }
    
    notification.innerHTML = `
        <div class="flex items-center space-x-3">
            <i class="fas ${icon}"></i>
            <span>${message}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return date.toLocaleDateString('es-MX', options);
}

// Format number with commas
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Check if user is authenticated
function isAuthenticated() {
    return !!localStorage.getItem('access_token');
}

// Get current user
function getCurrentUser() {
    const userStr = localStorage.getItem('user');
    return userStr ? JSON.parse(userStr) : null;
}

// Redirect if not authenticated
function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

// Calculate word count
function countWords(text) {
    return text.trim().split(/\s+/).filter(word => word.length > 0).length;
}

// Highlight text with errors
function highlightText(text, errors) {
    let highlightedText = text;
    
    // Sort errors by position (descending) to avoid position shifts
    errors.sort((a, b) => b.position_end - a.position_start);
    
    errors.forEach(error => {
        const errorText = text.substring(error.position_start, error.position_end);
        let className = '';
        
        switch(error.category) {
            case 'red':
                className = 'error-red';
                break;
            case 'yellow':
                className = 'error-yellow';
                break;
            case 'orange':
                className = 'error-orange';
                break;
        }
        
        const replacement = `<span class="${className}" data-error-id="${error.id}">${errorText}</span>`;
        highlightedText = highlightedText.substring(0, error.position_start) + 
                         replacement + 
                         highlightedText.substring(error.position_end);
    });
    
    return highlightedText;
}

// Copy to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showNotification('Texto copiado al portapapeles', 'success');
    } catch (err) {
        showNotification('Error al copiar el texto', 'error');
    }
}

// Add slideOut animation
const style = document.createElement('style');
style.textContent = `
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
    
    .error-red {
        background-color: rgba(239, 68, 68, 0.2);
        border-bottom: 2px solid #ef4444;
        cursor: pointer;
    }
    
    .error-yellow {
        background-color: rgba(245, 158, 11, 0.2);
        border-bottom: 2px solid #f59e0b;
        cursor: pointer;
    }
    
    .error-orange {
        background-color: rgba(251, 146, 60, 0.2);
        border-bottom: 2px dotted #fb923c;
        cursor: pointer;
    }
`;
document.head.appendChild(style);