// Main application JavaScript for TruthLens

// Global state
const appState = {
    currentVerification: null,
    user: null,
    subscription: null,
};

// Protected routes that require authentication
const protectedRoutes = ['/dashboard', '/verify', '/account', '/verification'];

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    // Store Google Client ID if available
    const googleClientId = document.querySelector('meta[name="google-client-id"]')?.content || 
                          window.GOOGLE_CLIENT_ID;
    if (googleClientId) {
        window.GOOGLE_CLIENT_ID = googleClientId;
        console.log('Google Client ID available:', googleClientId);
    }
    
    // Check if we're on a protected route
    const currentPath = window.location.pathname;
    const isProtectedRoute = protectedRoutes.some(route => currentPath.startsWith(route));
    
    // Check authentication
    if (isAuthenticated()) {
        try {
            // Load user data
            const response = await fetch('/api/auth/me', {  // CORREGIDO: era /api/user/me
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                }
            });
            
            if (response.ok) {
                appState.user = await response.json();
                localStorage.setItem('user', JSON.stringify(appState.user));
                
                // Load subscription data if needed
                if (currentPath.includes('pricing') || currentPath.includes('account')) {
                    try {
                        const subResponse = await fetch('/api/subscription/current-subscription', {
                            headers: {
                                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
                            }
                        });
                        if (subResponse.ok) {
                            appState.subscription = await subResponse.json();
                        }
                    } catch (error) {
                        console.error('Error loading subscription:', error);
                    }
                }
            } else {
                throw new Error('Invalid token');
            }
        } catch (error) {
            console.error('Error loading user data:', error);
            // If token is invalid, clear it
            localStorage.removeItem('access_token');
            localStorage.removeItem('user');
            updateNavigationAuth();
            
            // Redirect to login if on protected route
            if (isProtectedRoute) {
                window.location.href = '/login';
                return;
            }
        }
    } else if (isProtectedRoute) {
        // Not authenticated and trying to access protected route
        window.location.href = '/login';
        return;
    }
    
    // Setup global event listeners
    setupEventListeners();
    
    // Update navigation
    updateNavigationAuth();
    
    // Check for URL params
    handleUrlParams();
});

// Setup event listeners
function setupEventListeners() {
    // Logout buttons
    document.querySelectorAll('[data-action="logout"]').forEach(btn => {
        btn.addEventListener('click', handleLogout);
    });
    
    // Mobile menu toggle
    const mobileMenuBtn = document.getElementById('mobile-menu-btn');
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', toggleMobileMenu);
    }
}

// Handle URL parameters
function handleUrlParams() {
    const urlParams = new URLSearchParams(window.location.search);
    
    // Check for verification success
    if (urlParams.get('verification_success') === 'true') {
        showNotification('Verificación completada exitosamente', 'success');
    }
    
    // Check for payment success
    if (urlParams.get('payment_success') === 'true') {
        showNotification('¡Pago procesado exitosamente! Tu plan ha sido actualizado.', 'success');
    }
    
    // Check for subscription success
    if (urlParams.get('subscription') === 'success') {
        showNotification('¡Suscripción actualizada exitosamente!', 'success');
    }
    
    // Check for cancellation
    if (urlParams.get('cancelled') === 'true') {
        showNotification('Proceso cancelado', 'info');
    }
}

// Handle logout
async function handleLogout() {
    try {
        const token = localStorage.getItem('access_token');
        if (token) {
            await fetch('/api/auth/logout', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });
        }
    } catch (error) {
        console.error('Logout error:', error);
    } finally {
        // Always clear local storage and redirect
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('subscription');
        window.location.href = '/';
    }
}

// Toggle mobile menu
function toggleMobileMenu() {
    const mobileMenu = document.getElementById('mobile-menu');
    if (mobileMenu) {
        mobileMenu.classList.toggle('hidden');
    }
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

// Update navigation based on auth state
function updateNavigationAuth() {
    const navContainer = document.getElementById('nav-auth-container');
    if (!navContainer) return;
    
    if (isAuthenticated()) {
        const user = getCurrentUser();
        navContainer.innerHTML = `
            <a href="/dashboard" class="btn-secondary text-sm">Dashboard</a>
            <div class="relative group">
                <button class="text-gray-400 hover:text-white flex items-center">
                    <i class="fas fa-user-circle text-xl"></i>
                </button>
                <div class="absolute right-0 mt-2 w-48 bg-gray-900 rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all duration-200">
                    <div class="p-3 border-b border-gray-800">
                        <p class="text-sm font-medium">${user?.full_name || user?.email || 'Usuario'}</p>
                        <p class="text-xs text-gray-400">${user?.plan_type || 'free'} plan</p>
                    </div>
                    <a href="/account" class="block px-3 py-2 text-sm hover:bg-gray-800 transition">
                        <i class="fas fa-cog mr-2"></i> Mi cuenta
                    </a>
                    <button onclick="handleLogout()" class="w-full text-left px-3 py-2 text-sm hover:bg-gray-800 transition">
                        <i class="fas fa-sign-out-alt mr-2"></i> Cerrar sesión
                    </button>
                </div>
            </div>
        `;
    } else {
        navContainer.innerHTML = `
            <a href="/login" class="btn-secondary text-sm">Iniciar sesión</a>
            <a href="/login?register=true" class="btn-primary text-sm">Empezar gratis</a>
        `;
    }
}

// Format currency
function formatCurrency(amount, currency = 'MXN') {
    return new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: currency,
    }).format(amount / 100); // Convert from cents
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

// Update usage stats
async function updateUsageStats() {
    if (!isAuthenticated()) return;
    
    try {
        const stats = await api.getUsageStats();
        
        // Update UI elements
        const verificationsToday = document.getElementById('verifications-today');
        if (verificationsToday) {
            verificationsToday.textContent = stats.verifications_today || 0;
        }
        
        const remainingVerifications = document.getElementById('remaining-verifications');
        if (remainingVerifications) {
            const remaining = stats.remaining_verifications;
            remainingVerifications.textContent = remaining === -1 ? '∞' : remaining;
        }
    } catch (error) {
        console.error('Error updating usage stats:', error);
    }
}

// Check plan limits
function checkPlanLimits(action) {
    const user = getCurrentUser();
    if (!user) return false;
    
    const limits = {
        'free': {
            verifications_per_day: 5,
            words_per_verification: 800,
            corrections_per_day: 1
        },
        'pro': {
            verifications_per_day: 20,
            words_per_verification: 3000,
            corrections_per_day: -1
        },
        'premium': {
            verifications_per_day: -1,
            words_per_verification: -1,
            corrections_per_day: -1
        },
        'developer': {
            verifications_per_day: -1,
            words_per_verification: -1,
            corrections_per_day: -1
        }
    };
    
    const userLimits = limits[user.plan_type] || limits.free;
    
    switch(action) {
        case 'verify':
            if (userLimits.verifications_per_day === -1) return true;
            const verificationsToday = parseInt(document.getElementById('verifications-today')?.textContent || 0);
            return verificationsToday < userLimits.verifications_per_day;
            
        case 'correct':
            if (user.plan_type === 'free') {
                if (userLimits.corrections_per_day === -1) return true;
                // Check corrections today (would need to track this)
                return true; // For now
            }
            return true;
            
        default:
            return true;
    }
}

// Show upgrade prompt
function showUpgradePrompt(feature) {
    const messages = {
        verifications: 'Has alcanzado el límite de verificaciones diarias.',
        words: 'El texto excede el límite de palabras para tu plan.',
        corrections: 'Has alcanzado el límite de correcciones automáticas.',
        sources: 'La mejora de fuentes requiere un plan Pro o superior.',
        export: 'La exportación requiere un plan Pro o superior.',
    };
    
    const message = messages[feature] || 'Esta función requiere un plan superior.';
    
    if (confirm(`${message}\n\n¿Deseas ver los planes disponibles?`)) {
        window.location.href = '/pricing';
    }
}

// Auto-save draft
const saveDraft = debounce((text) => {
    if (text.trim()) {
        localStorage.setItem('draft_verification', text);
    }
}, 1000);

// Load draft
function loadDraft() {
    const draft = localStorage.getItem('draft_verification');
    if (draft) {
        const textarea = document.getElementById('verification-text');
        if (textarea && !textarea.value) {
            textarea.value = draft;
            if (typeof updateWordCount === 'function') {
                updateWordCount();
            }
        }
    }
}

// Clear draft
function clearDraft() {
    localStorage.removeItem('draft_verification');
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

// Export results
async function exportResults(format = 'pdf') {
    if (!appState.currentVerification) {
        showNotification('No hay resultados para exportar', 'warning');
        return;
    }
    
    try {
        await api.exportVerification(appState.currentVerification.id, format);
        showNotification(`Archivo ${format.toUpperCase()} descargado exitosamente`, 'success');
    } catch (error) {
        showNotification('Error al exportar el archivo', 'error');
    }
}

// Initialize tooltips
function initializeTooltips() {
    // Would integrate with a tooltip library like Tippy.js
    const elements = document.querySelectorAll('[data-tooltip]');
    elements.forEach(el => {
        el.title = el.getAttribute('data-tooltip');
    });
}

// Error boundary
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    // Don't show notification for every error, only critical ones
    if (event.error && event.error.message && event.error.message.includes('NetworkError')) {
        showNotification('Error de conexión. Por favor verifica tu internet.', 'error');
    }
});

// Unhandled promise rejection
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    // Only show for specific cases
    if (event.reason && event.reason.message && event.reason.message.includes('fetch')) {
        showNotification('Error al procesar la solicitud', 'error');
    }
});

// Export functions for global use
window.isAuthenticated = isAuthenticated;
window.getCurrentUser = getCurrentUser;
window.updateNavigationAuth = updateNavigationAuth;
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;
window.showUpgradePrompt = showUpgradePrompt;
window.saveDraft = saveDraft;
window.loadDraft = loadDraft;
window.clearDraft = clearDraft;