// API Client for TruthLens with improved error handling and validation
const API_BASE_URL = '/api';

const api = {
    // Helper function to make authenticated requests
    async makeRequest(endpoint, options = {}) {
        const token = localStorage.getItem('access_token');
        
        const defaultHeaders = {
            'Content-Type': 'application/json',
        };
        
        if (token) {
            defaultHeaders['Authorization'] = `Bearer ${token}`;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, {
                ...options,
                headers: {
                    ...defaultHeaders,
                    ...options.headers,
                },
            });
            
            // Handle non-JSON responses first
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return await response.text();
            }
            
            const data = await response.json();
            
            if (!response.ok) {
                // Handle specific error codes
                if (response.status === 401) {
                    // Token expired or invalid
                    this.clearAuth();
                    // Only redirect if we're not already on login page
                    if (!window.location.pathname.includes('/login')) {
                        window.location.href = '/login';
                    }
                    throw new Error('Session expired. Please login again.');
                } else if (response.status === 422) {
                    // Validation error - extract details
                    let errorMessage = 'Error de validación: ';
                    
                    // FastAPI validation errors come in a specific format
                    if (data.detail && Array.isArray(data.detail)) {
                        const errors = data.detail.map(err => {
                            const field = err.loc[err.loc.length - 1];
                            return `${field}: ${err.msg}`;
                        });
                        errorMessage += errors.join(', ');
                    } else if (data.detail) {
                        errorMessage = data.detail;
                    }
                    
                    throw new Error(errorMessage);
                } else if (response.status === 429) {
                    // Rate limit - extract wait time if available
                    const waitTime = data.detail || 'Too many requests. Please wait a moment and try again.';
                    throw new Error(waitTime);
                }
                
                throw new Error(data.detail || `Error ${response.status}: ${response.statusText}`);
            }
            
            return data;
        } catch (error) {
            // Handle network errors
            if (error instanceof TypeError && error.message === 'Failed to fetch') {
                throw new Error('Network error. Please check your connection.');
            }
            // Re-throw parsed errors
            throw error;
        }
    },
    
    // Clear authentication data
    clearAuth() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user');
        localStorage.removeItem('subscription');
    },
    
    // Authentication - NEW METHODS
    preRegister: async function(data) {
        try {
            return await this.makeRequest('/auth/pre-register', {
                method: 'POST',
                body: JSON.stringify({
                    email: data.email,
                    password: data.password,
                    full_name: data.full_name,
                    phone_number: data.phone_number,
                }),
            });
        } catch (error) {
            // Handle specific pre-register errors
            if (error.message.includes('El número debe incluir código de país')) {
                throw new Error('El número debe incluir código de país (ej: +52 para México)');
            } else if (error.message.includes('Número de teléfono inválido')) {
                throw new Error('Número de teléfono inválido. Debe tener entre 11 y 16 dígitos incluyendo el código de país');
            } else if (error.message.includes('Este correo ya está registrado')) {
                throw new Error('Este correo ya está registrado. Por favor inicia sesión.');
            } else if (error.message.includes('Este número de teléfono ya está registrado')) {
                throw new Error('Este número de teléfono ya está registrado con otra cuenta.');
            }
            throw error;
        }
    },
    
    verifyCodes: async function(data) {
        return this.makeRequest('/auth/verify-codes', {
            method: 'POST',
            body: JSON.stringify({
                email: data.email,
                email_code: data.email_code,
                sms_code: data.sms_code,
            }),
        });
    },
    
    resendCode: async function(data) {
        try {
            return await this.makeRequest('/auth/resend-code', {
                method: 'POST',
                body: JSON.stringify({
                    email: data.email,
                    code_type: data.code_type,
                }),
            });
        } catch (error) {
            // Make rate limit errors more user-friendly
            if (error.message.includes('Espera')) {
                // Extract the wait time from the message
                const match = error.message.match(/\d+/);
                const seconds = match ? match[0] : '30';
                throw new Error(`Por favor espera ${seconds} segundos antes de solicitar otro código`);
            }
            throw error;
        }
    },
    
    // Google OAuth methods
    googleAuth: async function(idToken) {
        return this.makeRequest('/auth/google/auth', {
            method: 'POST',
            body: JSON.stringify({
                id_token: idToken
            }),
        });
    },
    
    googleVerifyPhone: async function(data) {
        try {
            return await this.makeRequest('/auth/google/verify-phone', {
                method: 'POST',
                body: JSON.stringify({
                    session_id: data.session_id,
                    phone_number: data.phone_number
                }),
            });
        } catch (error) {
            // Handle specific phone verification errors
            if (error.message.includes('El número debe incluir código de país')) {
                throw new Error('El número debe incluir código de país (ej: +52 para México)');
            } else if (error.message.includes('Número de teléfono inválido')) {
                throw new Error('Número de teléfono inválido. Debe tener entre 11 y 16 dígitos incluyendo el código de país');
            } else if (error.message.includes('Este número de teléfono ya está registrado')) {
                throw new Error('Este número de teléfono ya está registrado con otra cuenta.');
            }
            throw error;
        }
    },
    
    googleVerifyCode: async function(data) {
        return this.makeRequest('/auth/google/verify-code', {
            method: 'POST',
            body: JSON.stringify({
                session_id: data.session_id,
                sms_code: data.sms_code
            }),
        });
    },
    
    linkGoogleAccount: async function(idToken) {
        return this.makeRequest('/auth/link-google', {
            method: 'POST',
            body: JSON.stringify({
                id_token: idToken
            }),
        });
    },
    
    // Existing auth methods remain unchanged
    register: async function(email, password, fullName = null) {
        return this.makeRequest('/auth/register', {
            method: 'POST',
            body: JSON.stringify({
                email,
                password,
                full_name: fullName,
            }),
        });
    },
    
    login: async function(email, password) {
        return this.makeRequest('/auth/login', {
            method: 'POST',
            body: JSON.stringify({
                email,
                password,
            }),
        });
    },
    
    logout: async function() {
        try {
            const response = await this.makeRequest('/auth/logout', {
                method: 'POST',
            });
            return response;
        } finally {
            // Always clear local data
            this.clearAuth();
        }
    },
    
    getMe: async function() {
        return this.makeRequest('/auth/me');  // CORREGIDO: era /user/me
    },
    
    // User
    updateProfile: async function(data) {
        return this.makeRequest('/user/profile', {
            method: 'PATCH',
            body: JSON.stringify(data),
        });
    },
    
    updatePassword: async function(currentPassword, newPassword) {
        return this.makeRequest('/user/update-password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword,
            }),
        });
    },
    
    getUsageStats: async function() {
        return this.makeRequest('/user/usage-stats');
    },
    
    getActiveDevices: async function() {
        return this.makeRequest('/user/active-devices');
    },
    
    deleteAccount: async function(confirmation) {
        return this.makeRequest('/user/account?confirmation=' + encodeURIComponent(confirmation), {
            method: 'DELETE',
        });
    },
    
    // Subscription - FIXED ENDPOINTS
    createCheckoutSession: async function(planType, billingPeriod = 'monthly') {
        return this.makeRequest('/subscription/create-checkout-session', {
            method: 'POST',
            body: JSON.stringify({
                plan_type: planType,
                billing_period: billingPeriod,
            }),
        });
    },
    
    convertTrialToPaid: async function() {
        return this.makeRequest('/subscription/convert-trial-to-paid', {
            method: 'POST',
        });
    },
    
    confirmPayment: async function(subscriptionId) {
        return this.makeRequest('/subscription/confirm-payment', {
            method: 'POST',
            body: JSON.stringify({
                subscription_id: subscriptionId
            }),
        });
    },
    
    previewPlanChange: async function(newPlanType, billingPeriod = 'monthly') {
        return this.makeRequest('/subscription/preview-plan-change', {
            method: 'POST',
            body: JSON.stringify({
                new_plan_type: newPlanType,
                billing_period: billingPeriod,
            }),
        });
    },
    
    changePlan: async function(newPlanType, billingPeriod = 'monthly') {
        // Clear cache before changing plan
        this.clearCaches();
        
        return this.makeRequest('/subscription/change-plan', {
            method: 'POST',
            body: JSON.stringify({
                new_plan_type: newPlanType,
                billing_period: billingPeriod,
            }),
        });
    },
    
    cancelDowngrade: async function() {
        // Clear cache when canceling downgrade
        this.clearCaches();
        
        return this.makeRequest('/subscription/cancel-downgrade', {
            method: 'POST',
        });
    },
    
    cancelSubscription: async function() {
        // Clear cache when canceling
        this.clearCaches();
        
        return this.makeRequest('/subscription/cancel-subscription', {
            method: 'POST',
        });
    },
    
    reactivateSubscription: async function() {
        // Clear cache when reactivating
        this.clearCaches();
        
        return this.makeRequest('/subscription/reactivate-subscription', {
            method: 'POST',
        });
    },
    
    pauseSubscription: async function(months) {
        return this.makeRequest('/subscription/pause-subscription', {
            method: 'POST',
            body: JSON.stringify({
                months: months,
            }),
        });
    },
    
    getCustomerPortalUrl: async function() {
        return this.makeRequest('/subscription/customer-portal');
    },
    
    getCurrentSubscription: async function() {
        try {
            const subscription = await this.makeRequest('/subscription/current-subscription');
            
            // Validate response data - ensure all fields are present
            if (subscription && typeof subscription === 'object') {
                // Set defaults for missing fields
                subscription.plan_type = subscription.plan_type || 'free';
                subscription.actual_plan = subscription.actual_plan || subscription.plan_type;
                subscription.has_subscription = subscription.has_subscription || false;
                subscription.cancel_at_period_end = subscription.cancel_at_period_end || false;
                subscription.pending_downgrade = subscription.pending_downgrade || null;
                subscription.is_trialing = subscription.is_trialing || false;
                
                // Ensure limits object exists
                if (!subscription.limits) {
                    subscription.limits = {
                        verifications_per_day: 5,
                        words_per_verification: 800,
                        corrections_per_day: 1
                    };
                }
                
                // Cache subscription data with timestamp
                const cacheData = {
                    subscription,
                    timestamp: Date.now()
                };
                localStorage.setItem('subscription', JSON.stringify(cacheData));
            }
            
            return subscription;
        } catch (error) {
            // If error, try to use cached data
            const cached = localStorage.getItem('subscription');
            if (cached) {
                try {
                    const cacheData = JSON.parse(cached);
                    // Use cache if less than 5 minutes old
                    if (Date.now() - cacheData.timestamp < 5 * 60 * 1000) {
                        return cacheData.subscription;
                    }
                } catch (e) {
                    // Invalid cache data
                    localStorage.removeItem('subscription');
                }
            }
            throw error;
        }
    },
    
    syncSubscriptionFromStripe: async function() {
        try {
            const response = await this.makeRequest('/subscription/sync-from-stripe', {
                method: 'POST'
            });
            
            // If sync successful, clear cache to force refresh
            if (response.synced) {
                localStorage.removeItem('subscription');
            }
            
            return response;
        } catch (error) {
            console.error('Error syncing subscription:', error);
            return { synced: false };
        }
    },
    
    // Verification - NEW METHODS
    verifyText: async function(text) {
        return this.makeRequest('/verification/verify', {
            method: 'POST',
            body: JSON.stringify({
                text,
            }),
        });
    },
    
    correctErrors: async function(verificationId) {
        return this.makeRequest(`/verification/${verificationId}/correct`, {
            method: 'POST',
        });
    },
    
    improveSources: async function(verificationId) {
        return this.makeRequest(`/verification/${verificationId}/improve-sources`, {
            method: 'POST',
        });
    },
    
    getChanges: async function(verificationId) {
        return this.makeRequest(`/verification/${verificationId}/changes`);
    },
    
    applyChanges: async function(verificationId, changeIds) {
        return this.makeRequest(`/verification/${verificationId}/apply-changes`, {
            method: 'POST',
            body: JSON.stringify({
                change_ids: changeIds,
            }),
        });
    },
    
    editChange: async function(verificationId, changeId, newText) {
        return this.makeRequest(`/verification/${verificationId}/change`, {
            method: 'PUT',
            body: JSON.stringify({
                change_id: changeId,
                new_text: newText,
            }),
        });
    },
    
    revertChange: async function(verificationId, changeId) {
        return this.makeRequest(`/verification/${verificationId}/change/${changeId}`, {
            method: 'DELETE',
        });
    },
    
    getVerification: async function(verificationId) {
        return this.makeRequest(`/verification/${verificationId}`);
    },
    
    getRecentVerifications: async function(limit = 10) {
        return this.makeRequest(`/verification/recent?limit=${limit}`);
    },
    
    exportVerification: async function(verificationId, format = 'txt') {
        return this.makeRequest(`/verification/${verificationId}/export?format=${format}`, {
            method: 'POST',
        });
    },
    
    // Helper function to clear all caches
    clearCaches: function() {
        localStorage.removeItem('subscription');
        localStorage.removeItem('user');
    },
    
    // Helper function to check if user has a paid plan
    hasPaidPlan: async function() {
        try {
            const subscription = await this.getCurrentSubscription();
            return subscription.has_subscription && subscription.plan_type !== 'free';
        } catch (error) {
            return false;
        }
    },
    
    // Helper function to check if user is in trial
    isInTrial: async function() {
        try {
            const subscription = await this.getCurrentSubscription();
            return subscription.is_trialing || false;
        } catch (error) {
            return false;
        }
    },
    
    // Helper function to format currency values safely
    formatCurrency: function(amount, currency = 'MXN') {
        try {
            // Ensure amount is a number
            const numAmount = parseFloat(amount) || 0;
            
            return new Intl.NumberFormat('es-MX', {
                style: 'currency',
                currency: currency,
            }).format(numAmount);
        } catch (error) {
            console.error('Error formatting currency:', error);
            return `${(parseFloat(amount) || 0).toFixed(2)} ${currency}`;
        }
    },
    
    // Helper function to check subscription status
    checkSubscriptionStatus: async function() {
        try {
            const subscription = await this.getCurrentSubscription();
            
            return {
                isActive: subscription.has_subscription && !subscription.cancel_at_period_end,
                isPaused: subscription.status === 'paused',
                isTrialing: subscription.is_trialing || false,
                planType: subscription.plan_type || 'free',
                daysRemaining: this.calculateDaysRemaining(subscription.current_period_end),
                pendingDowngrade: subscription.pending_downgrade || null,
            };
        } catch (error) {
            console.error('Error checking subscription status:', error);
            return {
                isActive: false,
                isPaused: false,
                isTrialing: false,
                planType: 'free',
                daysRemaining: 0,
                pendingDowngrade: null,
            };
        }
    },
    
    // Helper function to calculate days remaining
    calculateDaysRemaining: function(endDate) {
        if (!endDate) return 0;
        
        const end = new Date(endDate);
        const now = new Date();
        const diff = end - now;
        
        return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
    },
    
    // Rate limiting helper
    _requestQueue: [],
    _isProcessing: false,
    
    _processQueue: async function() {
        if (this._isProcessing || this._requestQueue.length === 0) return;
        
        this._isProcessing = true;
        const { request, resolve, reject } = this._requestQueue.shift();
        
        try {
            const result = await request();
            resolve(result);
        } catch (error) {
            reject(error);
        } finally {
            this._isProcessing = false;
            // Process next request after a small delay
            setTimeout(() => this._processQueue(), 100);
        }
    },
    
    queueRequest: async function(request) {
        return new Promise((resolve, reject) => {
            this._requestQueue.push({ request, resolve, reject });
            this._processQueue();
        });
    },
};

// Export for use in other modules
window.api = api;