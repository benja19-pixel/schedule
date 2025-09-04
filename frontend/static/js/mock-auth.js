/**
 * Mock Authentication for Development
 * Este script simula un token de autenticación para evitar redirecciones a /login
 */

(function() {
    console.log('🔐 Mock Auth: Inicializando autenticación simulada...');
    
    // Simular token de autenticación
    const mockToken = 'mock-development-token-2024';
    const mockUser = {
        id: 'usuario-demo-id',
        email: 'demo@mediconnect.com',
        full_name: 'Dr. Demo',
        plan_type: 'premium',
        is_active: true,
        is_verified: true
    };
    
    // Guardar en localStorage
    if (!localStorage.getItem('access_token')) {
        localStorage.setItem('access_token', mockToken);
        console.log('✅ Mock Auth: Token simulado creado');
    }
    
    if (!localStorage.getItem('user_data')) {
        localStorage.setItem('user_data', JSON.stringify(mockUser));
        console.log('✅ Mock Auth: Datos de usuario simulados creados');
    }
    
    // Sobrescribir la función checkAuth si existe
    if (typeof window.checkAuth !== 'undefined') {
        window.originalCheckAuth = window.checkAuth;
        window.checkAuth = function() {
            console.log('✅ Mock Auth: checkAuth() interceptado - usuario autenticado');
            return true;
        };
    }
    
    // Interceptar fetch para /api/auth/me
    const originalFetch = window.fetch;
    window.fetch = function(url, options) {
        // Si es una petición a /api/auth/me, retornar usuario mock
        if (url.includes('/api/auth/me')) {
            console.log('✅ Mock Auth: Interceptando /api/auth/me');
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve(mockUser)
            });
        }
        
        // Si es una petición a login, simular éxito
        if (url.includes('/login') || url.includes('/api/auth/login')) {
            console.log('✅ Mock Auth: Interceptando login');
            return Promise.resolve({
                ok: true,
                status: 200,
                json: () => Promise.resolve({
                    access_token: mockToken,
                    user: mockUser
                })
            });
        }
        
        // Para otras peticiones de API, agregar el token mock
        if (url.includes('/api/')) {
            options = options || {};
            options.headers = options.headers || {};
            if (!options.headers['Authorization']) {
                options.headers['Authorization'] = `Bearer ${mockToken}`;
            }
        }
        
        return originalFetch.call(this, url, options);
    };
    
    // Evitar redirecciones a /login
    const originalLocation = window.location;
    Object.defineProperty(window, 'location', {
        get: function() { return originalLocation; },
        set: function(value) {
            if (typeof value === 'string' && value.includes('/login')) {
                console.log('⚠️ Mock Auth: Bloqueada redirección a /login');
                return;
            }
            if (value && value.href && value.href.includes('/login')) {
                console.log('⚠️ Mock Auth: Bloqueada redirección a /login');
                return;
            }
            originalLocation.href = value;
        }
    });
    
    console.log('✅ Mock Auth: Sistema de autenticación simulada activo');
    console.log('   Usuario: Dr. Demo (demo@mediconnect.com)');
    console.log('   Plan: Premium');
    console.log('   Token: ' + mockToken.substring(0, 20) + '...');
})();