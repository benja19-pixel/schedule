// Calendar Sync JavaScript - Frontend functionality for calendar integration
// Handles Google/Apple Calendar sync, conflict resolution, and UI updates

// Global state for calendar sync - Using window to avoid conflicts
window.calendarSyncState = {
    connection: null,
    pendingConflicts: [],
    pendingRecurrentEvents: [],
    pendingSpecialEvents: [],
    pendingAllDayEvents: [],
    syncInProgress: false,
    selectedProvider: null
};

// Initialize calendar sync on page load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Calendar Sync...');
    
    // Check if we're on the calendar sync tab
    if (document.getElementById('calendar-sync-tab')) {
        await checkConnectionStatus();
        initializeCalendarSyncUI();
    }
});

// Check current connection status
async function checkConnectionStatus() {
    try {
        const response = await api.makeRequest('/calendar-sync/status');
        if (response && response.connected) {
            window.calendarSyncState.connection = response;
            showConnectedPanel();
        } else {
            showConnectionOptions();
        }
    } catch (error) {
        console.error('Error checking calendar connection:', error);
        showConnectionOptions();
    }
}

// Initialize UI components
function initializeCalendarSyncUI() {
    // Add event listeners for connection buttons
    const googleConnectBtn = document.getElementById('google-calendar-connect');
    const appleConnectBtn = document.getElementById('apple-calendar-connect');
    
    if (googleConnectBtn) {
        googleConnectBtn.addEventListener('click', () => connectGoogleCalendar());
    }
    
    if (appleConnectBtn) {
        appleConnectBtn.addEventListener('click', () => connectAppleCalendar());
    }
    
    // Sync now button
    const syncNowBtn = document.getElementById('sync-now-btn');
    if (syncNowBtn) {
        syncNowBtn.addEventListener('click', () => performSync());
    }
    
    // Settings toggles
    const mergeToggle = document.getElementById('merge-calendars-toggle');
    const notificationsToggle = document.getElementById('notifications-toggle');
    
    if (mergeToggle) {
        mergeToggle.addEventListener('change', (e) => updateSyncSettings('merge_calendars', e.target.checked));
    }
    
    if (notificationsToggle) {
        notificationsToggle.addEventListener('change', (e) => updateSyncSettings('receive_notifications', e.target.checked));
    }
}

// Connect Google Calendar
async function connectGoogleCalendar() {
    try {
        showLoading('Conectando con Google Calendar...');
        
        const response = await api.makeRequest('/calendar-sync/google/auth');
        if (response && response.auth_url) {
            // Store state in session storage for callback
            sessionStorage.setItem('calendar_sync_state', response.state);
            sessionStorage.setItem('calendar_sync_provider', 'google');
            
            // Open OAuth window
            const authWindow = window.open(
                response.auth_url,
                'GoogleCalendarAuth',
                'width=600,height=700,toolbar=no,menubar=no'
            );
            
            // Poll for completion
            const pollInterval = setInterval(async () => {
                if (authWindow.closed) {
                    clearInterval(pollInterval);
                    await checkConnectionStatus();
                    hideLoading();
                }
            }, 1000);
        }
    } catch (error) {
        console.error('Error connecting Google Calendar:', error);
        showToast('Error al conectar con Google Calendar', 'error');
        hideLoading();
    }
}

// Connect Apple Calendar (via Nylas)
async function connectAppleCalendar() {
    try {
        showLoading('Conectando con Apple Calendar...');
        
        // For Apple Calendar, we need Nylas OAuth
        showToast('La integración con Apple Calendar estará disponible próximamente', 'info');
        hideLoading();
        
        // TODO: Implement Nylas OAuth flow
        // This would require Nylas configuration first
        
    } catch (error) {
        console.error('Error connecting Apple Calendar:', error);
        showToast('Error al conectar con Apple Calendar', 'error');
        hideLoading();
    }
}

// Show connected panel
function showConnectedPanel() {
    const connectionPanel = document.getElementById('calendar-connection-panel');
    const connectionOptions = document.getElementById('calendar-connection-options');
    
    if (connectionOptions) connectionOptions.style.display = 'none';
    if (connectionPanel) {
        connectionPanel.style.display = 'block';
        
        // Update connection info
        document.getElementById('connected-email').textContent = window.calendarSyncState.connection.email || '';
        document.getElementById('connected-provider').textContent = 
            window.calendarSyncState.connection.provider === 'google' ? 'Google Calendar' : 'Apple Calendar';
        
        // Update last sync time
        if (window.calendarSyncState.connection.last_sync) {
            const lastSync = new Date(window.calendarSyncState.connection.last_sync);
            document.getElementById('last-sync-time').textContent = formatRelativeTime(lastSync);
        }
        
        // Update settings toggles
        if (window.calendarSyncState.connection.settings) {
            document.getElementById('merge-calendars-toggle').checked = 
                window.calendarSyncState.connection.settings.merge_calendars || false;
            document.getElementById('notifications-toggle').checked = 
                window.calendarSyncState.connection.settings.receive_notifications || false;
        }
    }
}

// Show connection options
function showConnectionOptions() {
    const connectionPanel = document.getElementById('calendar-connection-panel');
    const connectionOptions = document.getElementById('calendar-connection-options');
    
    if (connectionPanel) connectionPanel.style.display = 'none';
    if (connectionOptions) connectionOptions.style.display = 'block';
}

// Perform sync
async function performSync() {
    if (window.calendarSyncState.syncInProgress) {
        showToast('Sincronización en progreso...', 'info');
        return;
    }
    
    window.calendarSyncState.syncInProgress = true;
    const syncBtn = document.getElementById('sync-now-btn');
    if (syncBtn) {
        syncBtn.disabled = true;
        syncBtn.innerHTML = '<i class="fas fa-sync fa-spin mr-2"></i>Sincronizando...';
    }
    
    try {
        showLoading('Sincronizando calendarios...');
        
        const response = await api.makeRequest('/calendar-sync/sync', {
            method: 'POST',
            body: JSON.stringify({
                merge_calendars: document.getElementById('merge-calendars-toggle')?.checked || false,
                receive_notifications: document.getElementById('notifications-toggle')?.checked || false
            })
        });
        
        if (response && response.success) {
            // Handle conflicts
            if (response.conflicts_found && response.conflicts_found.length > 0) {
                window.calendarSyncState.pendingConflicts = response.conflicts_found;
                showConflictResolutionModal();
            }
            
            // Handle recurrent events
            if (response.recurrent_events && response.recurrent_events.length > 0) {
                window.calendarSyncState.pendingRecurrentEvents = response.recurrent_events;
                showRecurrentEventsModal();
            }
            
            // Handle special events
            if (response.special_events && response.special_events.length > 0) {
                window.calendarSyncState.pendingSpecialEvents = response.special_events;
                // Auto-process special events as breaks
                await processSpecialEvents();
            }
            
            // Handle all-day events
            if (response.all_day_events && response.all_day_events.length > 0) {
                window.calendarSyncState.pendingAllDayEvents = response.all_day_events;
                // Auto-process as closed days
                await processAllDayEvents();
            }
            
            // Update UI
            updateSyncStatus(response);
            
            // Refresh calendar display if on horarios page
            if (typeof loadHorarioData === 'function') {
                await loadHorarioData();
            }
            
            showToast(`Sincronización completa: ${response.synced_events} eventos procesados`, 'success');
        }
        
    } catch (error) {
        console.error('Error during sync:', error);
        showToast('Error durante la sincronización', 'error');
    } finally {
        window.calendarSyncState.syncInProgress = false;
        if (syncBtn) {
            syncBtn.disabled = false;
            syncBtn.innerHTML = '<i class="fas fa-sync mr-2"></i>Sincronizar Ahora';
        }
        hideLoading();
        
        // Update last sync time
        window.calendarSyncState.connection.last_sync = new Date().toISOString();
        document.getElementById('last-sync-time').textContent = 'Hace un momento';
    }
}

// Show conflict resolution modal
function showConflictResolutionModal() {
    const modal = document.getElementById('conflict-resolution-modal');
    if (!modal) {
        createConflictResolutionModal();
    }
    
    const conflictsList = document.getElementById('conflicts-list');
    conflictsList.innerHTML = '';
    
    window.calendarSyncState.pendingConflicts.forEach((conflict, index) => {
        const conflictCard = createConflictCard(conflict, index);
        conflictsList.appendChild(conflictCard);
    });
    
    document.getElementById('conflict-resolution-modal').classList.add('show');
}

// Create conflict card
function createConflictCard(conflict, index) {
    const card = document.createElement('div');
    card.className = 'conflict-card';
    card.dataset.conflictIndex = index;
    
    const externalEvent = conflict.external_event;
    const conflictInfo = conflict.conflict_with;
    
    card.innerHTML = `
        <div class="conflict-header">
            <h4 class="font-semibold text-gray-900">Conflicto Detectado</h4>
            <span class="text-xs text-gray-500">${formatEventDate(externalEvent.start_date)}</span>
        </div>
        <div class="conflict-details">
            <div class="event-comparison">
                <div class="external-event">
                    <label class="text-xs font-semibold text-blue-600">Evento del Calendario:</label>
                    <p class="text-sm">${externalEvent.summary}</p>
                    <p class="text-xs text-gray-600">
                        ${formatTime(externalEvent.start_time)} - ${formatTime(externalEvent.end_time)}
                    </p>
                </div>
                <div class="conflict-icon">
                    <i class="fas fa-arrows-alt-h text-amber-500"></i>
                </div>
                <div class="internal-event">
                    <label class="text-xs font-semibold text-purple-600">Descanso en MediConnect:</label>
                    <p class="text-sm">${conflictInfo.break_type}</p>
                    <p class="text-xs text-gray-600">${conflictInfo.break_time}</p>
                </div>
            </div>
            <div class="resolution-options mt-4">
                <label class="text-xs font-semibold text-gray-700 mb-2 block">Resolver conflicto:</label>
                <div class="grid grid-cols-2 gap-2">
                    <button class="resolution-btn" onclick="resolveConflict(${index}, 'merge_sum')">
                        <i class="fas fa-plus-circle"></i>
                        <span>Sumar tiempos</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveConflict(${index}, 'merge_combine')">
                        <i class="fas fa-compress-alt"></i>
                        <span>Combinar</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveConflict(${index}, 'keep_external')">
                        <i class="fas fa-calendar-check"></i>
                        <span>Usar calendario</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveConflict(${index}, 'keep_internal')">
                        <i class="fas fa-hospital"></i>
                        <span>Mantener actual</span>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    return card;
}

// Show recurrent events modal
function showRecurrentEventsModal() {
    const modal = document.getElementById('recurrent-events-modal');
    if (!modal) {
        createRecurrentEventsModal();
    }
    
    const eventsList = document.getElementById('recurrent-events-list');
    eventsList.innerHTML = '';
    
    window.calendarSyncState.pendingRecurrentEvents.forEach((event, index) => {
        const eventCard = createRecurrentEventCard(event, index);
        eventsList.appendChild(eventCard);
    });
    
    document.getElementById('recurrent-events-modal').classList.add('show');
}

// Create recurrent event card
function createRecurrentEventCard(event, index) {
    const card = document.createElement('div');
    card.className = 'recurrent-event-card';
    card.dataset.eventIndex = index;
    
    // Determine day of week
    const dayOfWeek = new Date(event.start_date).getDay();
    const dayName = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'][dayOfWeek];
    
    card.innerHTML = `
        <div class="event-header">
            <h4 class="font-semibold text-gray-900">${event.summary}</h4>
            <span class="text-xs text-gray-500">${dayName}s</span>
        </div>
        <div class="event-details">
            <p class="text-sm text-gray-600">
                <i class="fas fa-clock mr-1"></i>
                ${formatTime(event.start_time)} - ${formatTime(event.end_time)}
            </p>
            ${event.description ? `<p class="text-xs text-gray-500 mt-1">${event.description}</p>` : ''}
        </div>
        <div class="classification-section mt-3">
            <label class="text-xs font-semibold text-gray-700">Clasificar como:</label>
            <select class="classification-select" data-event-id="${event.id}">
                <option value="">-- Seleccionar tipo --</option>
                <option value="lunch">Comida</option>
                <option value="break">Descanso</option>
                <option value="administrative">Administrativo</option>
            </select>
        </div>
        ${event.has_conflict ? `
        <div class="conflict-warning mt-2">
            <i class="fas fa-exclamation-triangle text-amber-500 mr-1"></i>
            <span class="text-xs text-amber-600">Conflicto con descanso existente</span>
        </div>
        ` : ''}
    `;
    
    return card;
}

// Resolve conflict
async function resolveConflict(index, resolutionType) {
    const conflict = window.calendarSyncState.pendingConflicts[index];
    
    // Mark as resolved in UI
    const card = document.querySelector(`[data-conflict-index="${index}"]`);
    if (card) {
        card.classList.add('resolved');
        card.querySelector('.resolution-options').innerHTML = `
            <div class="text-center text-green-600">
                <i class="fas fa-check-circle mr-1"></i>
                Resuelto: ${getResolutionText(resolutionType)}
            </div>
        `;
    }
    
    // Store resolution
    conflict.resolution = resolutionType;
    
    // Check if all conflicts are resolved
    const allResolved = window.calendarSyncState.pendingConflicts.every(c => c.resolution);
    if (allResolved) {
        document.getElementById('apply-conflict-resolutions').disabled = false;
    }
}

// Apply all conflict resolutions
async function applyConflictResolutions() {
    const resolutions = window.calendarSyncState.pendingConflicts
        .filter(c => c.resolution)
        .map(c => ({
            event_id: c.external_event.id,
            resolution_type: c.resolution,
            merge_start: c.merge_start,
            merge_end: c.merge_end
        }));
    
    try {
        showLoading('Aplicando resoluciones...');
        
        const response = await api.makeRequest('/calendar-sync/resolve-conflicts', {
            method: 'POST',
            body: JSON.stringify(resolutions)
        });
        
        if (response && response.success) {
            showToast('Conflictos resueltos exitosamente', 'success');
            closeConflictModal();
            
            // Refresh schedule
            if (typeof loadHorarioData === 'function') {
                await loadHorarioData();
            }
        }
        
    } catch (error) {
        console.error('Error resolving conflicts:', error);
        showToast('Error al resolver conflictos', 'error');
    } finally {
        hideLoading();
    }
}

// Apply recurrent event classifications
async function applyRecurrentClassifications() {
    const classifications = [];
    
    document.querySelectorAll('.classification-select').forEach(select => {
        if (select.value) {
            classifications.push({
                external_event_id: select.dataset.eventId,
                classification: select.value
            });
        }
    });
    
    if (classifications.length === 0) {
        showToast('Por favor clasifica al menos un evento', 'warning');
        return;
    }
    
    try {
        showLoading('Aplicando clasificaciones...');
        
        const response = await api.makeRequest('/calendar-sync/classify-recurrent', {
            method: 'POST',
            body: JSON.stringify(classifications)
        });
        
        if (response && response.success) {
            showToast('Eventos recurrentes clasificados', 'success');
            closeRecurrentModal();
            
            // Refresh schedule
            if (typeof loadHorarioData === 'function') {
                await loadHorarioData();
            }
        }
        
    } catch (error) {
        console.error('Error classifying events:', error);
        showToast('Error al clasificar eventos', 'error');
    } finally {
        hideLoading();
    }
}

// Process special events automatically
async function processSpecialEvents() {
    // Special events are automatically added as breaks
    console.log('Processing special events:', window.calendarSyncState.pendingSpecialEvents);
    
    // These are handled in the backend automatically
    // Just show a notification
    if (window.calendarSyncState.pendingSpecialEvents.length > 0) {
        showToast(`${window.calendarSyncState.pendingSpecialEvents.length} eventos especiales agregados como descansos`, 'info');
    }
}

// Process all-day events automatically
async function processAllDayEvents() {
    // All-day events are automatically marked as closed days
    console.log('Processing all-day events:', window.calendarSyncState.pendingAllDayEvents);
    
    // These are handled in the backend automatically
    // Just show a notification
    if (window.calendarSyncState.pendingAllDayEvents.length > 0) {
        showToast(`${window.calendarSyncState.pendingAllDayEvents.length} días marcados como cerrados`, 'info');
    }
}

// Disconnect calendar
async function disconnectCalendar() {
    if (!confirm('¿Estás seguro de desconectar tu calendario? Se eliminarán todos los eventos sincronizados.')) {
        return;
    }
    
    try {
        showLoading('Desconectando calendario...');
        
        const response = await api.makeRequest('/calendar-sync/disconnect', {
            method: 'DELETE'
        });
        
        if (response && response.success) {
            window.calendarSyncState.connection = null;
            showConnectionOptions();
            showToast('Calendario desconectado exitosamente', 'success');
            
            // Refresh schedule to remove synced events
            if (typeof loadHorarioData === 'function') {
                await loadHorarioData();
            }
        }
        
    } catch (error) {
        console.error('Error disconnecting calendar:', error);
        showToast('Error al desconectar calendario', 'error');
    } finally {
        hideLoading();
    }
}

// Update sync settings
async function updateSyncSettings(setting, value) {
    try {
        const settings = {
            ...window.calendarSyncState.connection.settings,
            [setting]: value
        };
        
        const response = await api.makeRequest('/calendar-sync/settings', {
            method: 'PUT',
            body: JSON.stringify(settings)
        });
        
        if (response && response.success) {
            window.calendarSyncState.connection.settings = settings;
            showToast('Configuración actualizada', 'success');
            
            // If enabling merge_calendars, trigger sync
            if (setting === 'merge_calendars' && value) {
                await performSync();
            }
        }
        
    } catch (error) {
        console.error('Error updating settings:', error);
        showToast('Error al actualizar configuración', 'error');
    }
}

// Create modals dynamically
function createConflictResolutionModal() {
    const modal = document.createElement('div');
    modal.id = 'conflict-resolution-modal';
    modal.className = 'calendar-sync-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="text-xl font-bold text-gray-900">Resolver Conflictos de Calendario</h3>
                <button onclick="closeConflictModal()" class="close-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <p class="text-sm text-gray-600 mb-4">
                    Se encontraron eventos que coinciden con tus descansos configurados. 
                    Elige cómo resolver cada conflicto:
                </p>
                <div id="conflicts-list" class="space-y-4 max-h-96 overflow-y-auto"></div>
            </div>
            <div class="modal-footer">
                <button id="apply-conflict-resolutions" class="btn-primary" onclick="applyConflictResolutions()" disabled>
                    Aplicar Resoluciones
                </button>
                <button class="btn-secondary" onclick="closeConflictModal()">
                    Cancelar
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

function createRecurrentEventsModal() {
    const modal = document.createElement('div');
    modal.id = 'recurrent-events-modal';
    modal.className = 'calendar-sync-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="text-xl font-bold text-gray-900">Eventos Recurrentes Encontrados</h3>
                <button onclick="closeRecurrentModal()" class="close-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="modal-body">
                <p class="text-sm text-gray-600 mb-4">
                    Clasifica los siguientes eventos recurrentes de tu calendario:
                </p>
                <div id="recurrent-events-list" class="space-y-4 max-h-96 overflow-y-auto"></div>
            </div>
            <div class="modal-footer">
                <button class="btn-primary" onclick="applyRecurrentClassifications()">
                    Aplicar Clasificaciones
                </button>
                <button class="btn-secondary" onclick="closeRecurrentModal()">
                    Omitir
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

// Modal control functions
function closeConflictModal() {
    document.getElementById('conflict-resolution-modal').classList.remove('show');
    window.calendarSyncState.pendingConflicts = [];
}

function closeRecurrentModal() {
    document.getElementById('recurrent-events-modal').classList.remove('show');
    window.calendarSyncState.pendingRecurrentEvents = [];
}

// Update sync status in UI
function updateSyncStatus(syncResult) {
    const statusEl = document.getElementById('sync-status');
    if (statusEl) {
        statusEl.innerHTML = `
            <div class="sync-stats">
                <div class="stat-item">
                    <i class="fas fa-check-circle text-green-500"></i>
                    <span>${syncResult.synced_events} eventos sincronizados</span>
                </div>
                ${syncResult.conflicts_found.length > 0 ? `
                <div class="stat-item">
                    <i class="fas fa-exclamation-triangle text-amber-500"></i>
                    <span>${syncResult.conflicts_found.length} conflictos resueltos</span>
                </div>
                ` : ''}
            </div>
        `;
    }
}

// Utility functions
function formatTime(timeStr) {
    if (!timeStr) return '';
    const [hours, minutes] = timeStr.split(':');
    const h = parseInt(hours);
    const period = h >= 12 ? 'PM' : 'AM';
    const displayHours = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    return `${displayHours}:${minutes} ${period}`;
}

function formatEventDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('es-MX', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });
}

function formatRelativeTime(date) {
    const now = new Date();
    const diff = now - date;
    const minutes = Math.floor(diff / 60000);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    
    if (minutes < 1) return 'Hace un momento';
    if (minutes < 60) return `Hace ${minutes} minuto${minutes > 1 ? 's' : ''}`;
    if (hours < 24) return `Hace ${hours} hora${hours > 1 ? 's' : ''}`;
    return `Hace ${days} día${days > 1 ? 's' : ''}`;
}

function getResolutionText(type) {
    const texts = {
        'merge_sum': 'Sumar tiempos',
        'merge_combine': 'Combinar horarios',
        'keep_external': 'Usar evento del calendario',
        'keep_internal': 'Mantener configuración actual'
    };
    return texts[type] || type;
}

function showLoading(message = 'Cargando...') {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        const messageEl = overlay.querySelector('.loading-message');
        if (messageEl) messageEl.textContent = message;
        overlay.classList.remove('hidden');
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.add('hidden');
}

// Export functions for global use
window.connectGoogleCalendar = connectGoogleCalendar;
window.connectAppleCalendar = connectAppleCalendar;
window.disconnectCalendar = disconnectCalendar;
window.performSync = performSync;
window.resolveConflict = resolveConflict;
window.applyConflictResolutions = applyConflictResolutions;
window.applyRecurrentClassifications = applyRecurrentClassifications;
window.closeConflictModal = closeConflictModal;
window.closeRecurrentModal = closeRecurrentModal;