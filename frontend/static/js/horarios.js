// Horarios.js - JavaScript completo para configuración de horarios con sincronización de calendario
// Versión mejorada con agrupación de eventos recurrentes, sincronización automática y SELECTOR DE CONSULTORIOS
// FIXED: No duplicar consultorio principal en selector

// ==================== GLOBAL STATE ====================
let horarioTemplates = {};
let horarioExceptions = [];
let currentTab = 'regular';
let hasUnsavedChanges = false;
let currentCalendarMonth = new Date().getMonth();
let currentCalendarYear = new Date().getFullYear();
let saveTimeout = null;
let currentBreakBlocks = [];
let currentExceptionBreaks = [];
let pendingDeleteId = null;
let selectedDateForException = null;
let vacationStartDate = null;
let vacationEndDate = null;
let vacationHoverDate = null;

// NEW: Consultorios state
let availableConsultorios = [];
let selectedConsultorioForDay = null;
let selectedConsultorioForException = null;
let principalConsultorioId = null; // Track principal consultorio

// Calendar Sync State
let calendarConnection = null;
let pendingConflicts = [];
let pendingRecurrentEvents = [];
let pendingSpecialEvents = [];
let pendingAllDayEvents = [];
let syncInProgress = false;
let selectedProvider = null;
let autoSyncInterval = null;
let justSyncedEventIds = new Set(); // Track events just synced to avoid self-conflicts

// Days of week mapping
const daysOfWeek = {
    0: { full: 'Lunes', short: 'Lun', lower: 'lunes' },
    1: { full: 'Martes', short: 'Mar', lower: 'martes' },
    2: { full: 'Miércoles', short: 'Mié', lower: 'miércoles' },
    3: { full: 'Jueves', short: 'Jue', lower: 'jueves' },
    4: { full: 'Viernes', short: 'Vie', lower: 'viernes' },
    5: { full: 'Sábado', short: 'Sáb', lower: 'sábado' },
    6: { full: 'Domingo', short: 'Dom', lower: 'domingo' }
};

// Exception type descriptions
const exceptionDescriptions = {
    'closed': 'Cierra el consultorio por el día completo. Útil para días personales o emergencias.',
    'special-hours': 'Modifica el horario de un día que normalmente está abierto.',
    'special-open': 'Abre el consultorio en un día que normalmente está cerrado.',
    'vacation': 'Marca un período de vacaciones. Todos los días seleccionados estarán cerrados.'
};

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Horarios with improved sync and consultorio selector...');
    
    const isHorariosPage = document.getElementById('regular-tab') || 
                          document.getElementById('exceptions-tab') || 
                          document.getElementById('calendar-sync-tab');
    
    if (!isHorariosPage) {
        console.log('Not on horarios page, skipping initialization');
        return;
    }
    
    if (typeof isAuthenticated === 'function' && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    // Load consultorios first
    await loadAvailableConsultorios();
    await loadHorarioData();
    initializeUI();
    
    if (document.getElementById('calendar-sync-tab')) {
        await checkCalendarConnectionStatus();
        initializeCalendarSyncUI();
        
        // Setup auto-sync if connected
        if (calendarConnection && calendarConnection.connected) {
            setupAutoSync();
        }
    }
    
    // Global click handler for date pickers
    document.addEventListener('click', (e) => {
        const datePicker = document.getElementById('date-picker-popup');
        const dateInput = document.getElementById('exception-date');
        const vacationCalendarPopup = document.getElementById('vacation-calendar-popup');
        const vacationInput = document.getElementById('vacation-dates');
        
        if (datePicker && !datePicker.contains(e.target) && e.target !== dateInput) {
            datePicker.classList.add('hidden');
        }
        
        if (vacationCalendarPopup && !vacationCalendarPopup.contains(e.target) && e.target !== vacationInput) {
            if ((vacationStartDate && vacationEndDate) || (!vacationStartDate && !vacationEndDate)) {
                vacationCalendarPopup.classList.add('hidden');
            }
        }
    });
    
    // Listen for messages from popup windows (OAuth callbacks)
    window.addEventListener('message', (event) => {
        console.log('Received message:', event.data);
        if (event.data.type === 'calendar-connected' && event.data.success) {
            console.log('Calendar connected successfully via popup');
            setTimeout(async () => {
                await checkCalendarConnectionStatus();
                showToast('Calendario conectado exitosamente', 'success');
                // Setup auto-sync after successful connection
                setupAutoSync();
                // Perform initial sync
                await syncCalendar(true);
            }, 1000);
        } else if (event.data.type === 'calendar-error') {
            console.error('Calendar connection error:', event.data.error);
            showToast('Error al conectar calendario: ' + event.data.error, 'error');
        }
    });
});

// ==================== CONSULTORIOS FUNCTIONS ====================
async function loadAvailableConsultorios() {
    try {
        const response = await api.makeRequest('/consultorios');
        if (response && response.consultorios) {
            availableConsultorios = response.consultorios;
            
            // Find the principal consultorio
            const principal = availableConsultorios.find(c => c.es_principal);
            principalConsultorioId = principal ? principal.id : null;
            
            console.log('Loaded consultorios:', availableConsultorios);
            console.log('Principal consultorio ID:', principalConsultorioId);
        }
    } catch (error) {
        console.error('Error loading consultorios:', error);
        availableConsultorios = [];
        principalConsultorioId = null;
    }
}

function renderConsultorioSelector(containerId, currentConsultorioId = null) {
    const container = document.getElementById(containerId);
    if (!container) return;
    
    container.innerHTML = '';
    
    // Add header with info
    const header = document.createElement('div');
    header.className = 'consultorio-selector-header';
    
    // Different messaging based on whether consultorios exist
    if (availableConsultorios.length === 0) {
        header.innerHTML = `
            <label class="label">
                <i class="fas fa-map-marker-alt text-purple-500 mr-1"></i>
                Ubicación para este día
            </label>
            <p class="text-xs text-amber-600 italic mt-1">
                <i class="fas fa-exclamation-circle mr-1"></i>
                No tienes consultorios registrados. Cuando crees tu primer consultorio, será asignado automáticamente como principal.
            </p>
        `;
        container.appendChild(header);
        return; // Don't show selector if no consultorios
    } else {
        header.innerHTML = `
            <label class="label">
                <i class="fas fa-map-marker-alt text-purple-500 mr-1"></i>
                Ubicación para este día
            </label>
            <p class="text-xs text-gray-500 italic mt-1">
                Si no seleccionas ninguna, se usará el consultorio principal
            </p>
        `;
    }
    container.appendChild(header);
    
    // Create selector grid
    const selectorGrid = document.createElement('div');
    selectorGrid.className = 'consultorio-selector-grid';
    
    // FIXED: Don't create "Usar principal" option - just show all consultorios directly
    // Show all consultorios including principal, but mark the principal clearly
    availableConsultorios.forEach(consultorio => {
        const item = document.createElement('div');
        // Select the consultorio if it matches the current selection OR if it's the only one
        const isSelected = consultorio.id === currentConsultorioId || 
                          (availableConsultorios.length === 1 && !currentConsultorioId);
        item.className = `consultorio-selector-item ${isSelected ? 'selected' : ''}`;
        item.dataset.consultorioId = consultorio.id;
        
        // Get photo or color
        let avatarContent = '';
        if (consultorio.foto_principal && consultorio.foto_principal.url) {
            avatarContent = `<img src="${consultorio.foto_principal.url}" alt="${consultorio.nombre}">`;
        } else if (consultorio.foto_principal && consultorio.foto_principal.color) {
            avatarContent = `
                <div class="consultorio-color-avatar" style="background: ${consultorio.foto_principal.color}">
                    <i class="fas fa-hospital"></i>
                </div>
            `;
        } else {
            avatarContent = `
                <div class="consultorio-color-avatar" style="background: #6366f1">
                    <i class="fas fa-hospital"></i>
                </div>
            `;
        }
        
        item.innerHTML = `
            <div class="consultorio-selector-avatar">
                ${avatarContent}
                ${consultorio.es_principal ? '<span class="principal-badge-mini" title="Principal"><i class="fas fa-star"></i></span>' : ''}
            </div>
            <div class="consultorio-selector-name">
                ${consultorio.nombre}
                ${consultorio.es_principal ? ' (Principal)' : ''}
            </div>
        `;
        
        item.onclick = () => selectConsultorioForDay(consultorio.id);
        selectorGrid.appendChild(item);
    });
    
    container.appendChild(selectorGrid);
    
    // If only one consultorio exists, auto-select it
    if (availableConsultorios.length === 1 && !currentConsultorioId) {
        selectConsultorioForDay(availableConsultorios[0].id);
    }
}

function selectConsultorioForDay(consultorioId) {
    selectedConsultorioForDay = consultorioId;
    
    // Update visual selection
    document.querySelectorAll('#consultorio-selector .consultorio-selector-item').forEach(item => {
        if (consultorioId && item.dataset.consultorioId === consultorioId) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
}

function selectConsultorioForException(consultorioId) {
    selectedConsultorioForException = consultorioId;
    
    // Update visual selection
    document.querySelectorAll('#exception-consultorio-selector .consultorio-selector-item').forEach(item => {
        if (consultorioId && item.dataset.consultorioId === consultorioId) {
            item.classList.add('selected');
        } else {
            item.classList.remove('selected');
        }
    });
}

function renderExceptionConsultorioSelector() {
    const container = document.getElementById('exception-consultorio-selector');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Check if there are consultorios
    if (availableConsultorios.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-amber-600 text-sm">
                <i class="fas fa-exclamation-triangle mr-1"></i>
                No tienes consultorios registrados
            </div>
        `;
        return;
    }
    
    // Add header
    const header = document.createElement('div');
    header.className = 'consultorio-selector-header';
    header.innerHTML = `
        <label class="label">
            <i class="fas fa-map-marker-alt text-purple-500 mr-1"></i>
            Ubicación para este día especial
        </label>
    `;
    container.appendChild(header);
    
    // Create selector grid
    const selectorGrid = document.createElement('div');
    selectorGrid.className = 'consultorio-selector-grid exception-selector';
    
    // FIXED: Don't create "Usar principal" option - just show all consultorios directly
    // Add all available consultorios
    availableConsultorios.forEach(consultorio => {
        const item = document.createElement('div');
        const isSelected = consultorio.id === selectedConsultorioForException ||
                          (availableConsultorios.length === 1 && !selectedConsultorioForException);
        item.className = `consultorio-selector-item ${isSelected ? 'selected' : ''}`;
        item.dataset.consultorioId = consultorio.id;
        
        // Get photo or color
        let avatarContent = '';
        if (consultorio.foto_principal && consultorio.foto_principal.url) {
            avatarContent = `<img src="${consultorio.foto_principal.url}" alt="${consultorio.nombre}">`;
        } else if (consultorio.foto_principal && consultorio.foto_principal.color) {
            avatarContent = `
                <div class="consultorio-color-avatar" style="background: ${consultorio.foto_principal.color}">
                    <i class="fas fa-hospital"></i>
                </div>
            `;
        } else {
            avatarContent = `
                <div class="consultorio-color-avatar" style="background: #6366f1">
                    <i class="fas fa-hospital"></i>
                </div>
            `;
        }
        
        item.innerHTML = `
            <div class="consultorio-selector-avatar small">
                ${avatarContent}
                ${consultorio.es_principal ? '<span class="principal-badge-mini" title="Principal"><i class="fas fa-star"></i></span>' : ''}
            </div>
            <div class="consultorio-selector-name">
                ${consultorio.nombre}
                ${consultorio.es_principal ? ' (Principal)' : ''}
            </div>
        `;
        
        item.onclick = () => selectConsultorioForException(consultorio.id);
        selectorGrid.appendChild(item);
    });
    
    container.appendChild(selectorGrid);
    
    // Auto-select if only one consultorio
    if (availableConsultorios.length === 1) {
        selectConsultorioForException(availableConsultorios[0].id);
    }
}

function getConsultorioDisplay(consultorioId) {
    if (!consultorioId) {
        // If no specific consultorio, return principal if exists
        if (principalConsultorioId) {
            const principal = availableConsultorios.find(c => c.id === principalConsultorioId);
            if (principal) {
                return getConsultorioDisplayHTML(principal, true);
            }
        }
        return null;
    }
    
    const consultorio = availableConsultorios.find(c => c.id === consultorioId);
    if (!consultorio) return null;
    
    return getConsultorioDisplayHTML(consultorio, false);
}

function getConsultorioDisplayHTML(consultorio, isDefault = false) {
    let avatarHtml = '';
    if (consultorio.foto_principal && consultorio.foto_principal.url) {
        avatarHtml = `<img src="${consultorio.foto_principal.url}" alt="${consultorio.nombre}" class="consultorio-mini-img">`;
    } else if (consultorio.foto_principal && consultorio.foto_principal.color) {
        avatarHtml = `
            <div class="consultorio-mini-color" style="background: ${consultorio.foto_principal.color}">
                <i class="fas fa-hospital text-white text-xs"></i>
            </div>
        `;
    } else {
        avatarHtml = `
            <div class="consultorio-mini-color" style="background: #6366f1">
                <i class="fas fa-hospital text-white text-xs"></i>
            </div>
        `;
    }
    
    return `
        <div class="consultorio-badge">
            ${avatarHtml}
            <span class="consultorio-badge-name">
                ${consultorio.nombre}
                ${isDefault ? ' (Por defecto)' : ''}
            </span>
        </div>
    `;
}

// ==================== AUTO-SYNC SETUP ====================
function setupAutoSync() {
    // Clear any existing interval
    if (autoSyncInterval) {
        clearInterval(autoSyncInterval);
    }
    
    // Set up auto-sync every 5 minutes
    autoSyncInterval = setInterval(async () => {
        if (calendarConnection && calendarConnection.connected && !syncInProgress) {
            console.log('Auto-sync triggered');
            await syncCalendar(true); // Silent sync
        }
    }, 5 * 60 * 1000); // 5 minutes
    
    console.log('Auto-sync enabled - will sync every 5 minutes');
}

// ==================== DATA LOADING ====================
async function loadHorarioData() {
    console.log('Loading horario data...');
    showLoading();
    
    try {
        const templatesResponse = await api.makeRequest('/horarios/templates');
        if (templatesResponse && templatesResponse.templates) {
            horarioTemplates = {};
            templatesResponse.templates.forEach(template => {
                horarioTemplates[template.day_of_week] = template;
            });
        }
        
        const now = new Date();
        const startDate = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const endDate = new Date(now.getFullYear(), now.getMonth() + 3, 0);
        
        const exceptionsResponse = await api.makeRequest(
            `/horarios/exceptions?start_date=${startDate.toISOString().split('T')[0]}&end_date=${endDate.toISOString().split('T')[0]}`
        );
        
        if (exceptionsResponse && exceptionsResponse.exceptions) {
            horarioExceptions = exceptionsResponse.exceptions;
        }
        
        await updateCapacidad();
        updateDayCards();
        
    } catch (error) {
        console.error('Error loading horario data:', error);
        showToast('Error al cargar los datos del horario', 'error');
    } finally {
        hideLoading();
    }
}

async function updateCapacidad() {
    try {
        const capacidadResponse = await api.makeRequest('/horarios/capacidad');
        if (capacidadResponse) {
            updateCapacidadDisplay(capacidadResponse);
        }
    } catch (error) {
        console.error('Error loading capacidad:', error);
    }
}

function updateCapacidadDisplay(capacidad) {
    const hoursEl = document.querySelector('[data-stat="hours"]');
    if (hoursEl) {
        hoursEl.textContent = `${capacidad.total_horas_semana || 0} hrs`;
    }
    
    const slotsEl = document.querySelector('[data-stat="slots"]');
    if (slotsEl) {
        slotsEl.textContent = capacidad.capacidad_display || '0 citas/sem';
    }
    
    const daysEl = document.querySelector('[data-stat="days"]');
    if (daysEl) {
        daysEl.textContent = `${capacidad.dias_laborables || 0}/7`;
    }
}

// ==================== UI INITIALIZATION ====================
function initializeUI() {
    updateDayCards();
    initializeExceptionCalendar();
}

function updateDayCards() {
    for (let day = 0; day < 7; day++) {
        const template = horarioTemplates[day];
        const dayName = daysOfWeek[day].lower;
        const card = document.querySelector(`[data-day="${dayName}"]`);
        
        if (!card) continue;
        
        const toggle = card.querySelector('.toggle');
        const hoursElement = document.getElementById(`${dayName}-hours`);
        
        if (template && template.is_active) {
            toggle.classList.add('active');
            card.classList.remove('inactive');
            
            if (template.opens_at && template.closes_at) {
                const opensAt = formatTime(template.opens_at);
                const closesAt = formatTime(template.closes_at);
                let hoursText = `${opensAt} - ${closesAt}`;
                
                if (template.time_blocks && Array.isArray(template.time_blocks) && template.time_blocks.length > 0) {
                    const breaks = template.time_blocks.filter(block => {
                        return block && block.type && block.type !== 'consultation';
                    });
                    
                    if (breaks.length > 0) {
                        const breakText = breaks.length === 1 ? '1 descanso' : `${breaks.length} descansos`;
                        hoursText += ` <span class="text-xs text-gray-400">(${breakText})</span>`;
                        
                        const syncedBreaks = breaks.filter(b => b.external_event_id);
                        if (syncedBreaks.length > 0) {
                            hoursText += ` <i class="fas fa-sync text-blue-400 text-xs ml-1" title="${syncedBreaks.length} sincronizado(s)"></i>`;
                        }
                    }
                }
                
                // Show consultorio info properly
                if (template.consultorio_id) {
                    const consultorio = availableConsultorios.find(c => c.id === template.consultorio_id);
                    if (consultorio) {
                        hoursText += `<div class="day-consultorio-badge mt-1">`;
                        hoursText += `<i class="fas fa-map-marker-alt text-purple-400 text-xs mr-1"></i>`;
                        hoursText += `<span class="text-xs text-purple-600">${consultorio.nombre}</span>`;
                        hoursText += `</div>`;
                    }
                } else if (principalConsultorioId) {
                    // Show principal as default
                    const principal = availableConsultorios.find(c => c.id === principalConsultorioId);
                    if (principal) {
                        hoursText += `<div class="day-consultorio-badge mt-1">`;
                        hoursText += `<i class="fas fa-star text-amber-400 text-xs mr-1"></i>`;
                        hoursText += `<span class="text-xs text-gray-500">${principal.nombre} (Por defecto)</span>`;
                        hoursText += `</div>`;
                    }
                }
                
                hoursElement.innerHTML = hoursText;
            } else {
                hoursElement.textContent = 'Horario no definido';
            }
        } else {
            toggle.classList.remove('active');
            card.classList.add('inactive');
            hoursElement.textContent = 'No disponible';
        }
    }
    
    updateWeekdayIndicators();
}

function updateWeekdayIndicators() {
    for (let i = 0; i < 7; i++) {
        const weekdayEl = document.getElementById(`weekday-${i}`);
        if (weekdayEl) {
            const template = horarioTemplates[i];
            if (template && template.is_active) {
                weekdayEl.classList.add('open-indicator');
                weekdayEl.title = 'Normalmente abierto';
            } else {
                weekdayEl.classList.remove('open-indicator');
                weekdayEl.title = '';
            }
        }
    }
}

// ==================== TAB MANAGEMENT ====================
function switchTab(tab, element) {
    currentTab = tab;
    
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    element.classList.add('active');
    
    document.getElementById('regular-tab').classList.toggle('hidden', tab !== 'regular');
    document.getElementById('exceptions-tab').classList.toggle('hidden', tab !== 'exceptions');
    document.getElementById('calendar-sync-tab').classList.toggle('hidden', tab !== 'calendar-sync');
    
    if (tab === 'exceptions') {
        updateExceptionsList();
    } else if (tab === 'calendar-sync') {
        updateCalendarSyncPanel();
    }
}

// ==================== DAY MANAGEMENT ====================
function toggleDay(element, dayName) {
    const dayIndex = Object.keys(daysOfWeek).find(key => 
        daysOfWeek[key].lower === dayName
    );
    
    if (dayIndex === undefined) return;
    
    const isActive = element.classList.contains('active');
    element.classList.toggle('active');
    
    const card = element.closest('.day-card');
    const hoursEl = document.getElementById(`${dayName}-hours`);
    
    if (!isActive) {
        card.classList.remove('inactive');
        
        if (!horarioTemplates[dayIndex]) {
            horarioTemplates[dayIndex] = {
                day_of_week: parseInt(dayIndex),
                is_active: true,
                opens_at: '09:00',
                closes_at: '19:00',
                time_blocks: [],
                consultorio_id: null
            };
        } else {
            horarioTemplates[dayIndex].is_active = true;
            horarioTemplates[dayIndex].opens_at = horarioTemplates[dayIndex].opens_at || '09:00';
            horarioTemplates[dayIndex].closes_at = horarioTemplates[dayIndex].closes_at || '19:00';
        }
        
        const opensAt = formatTime(horarioTemplates[dayIndex].opens_at);
        const closesAt = formatTime(horarioTemplates[dayIndex].closes_at);
        hoursEl.innerHTML = `${opensAt} - ${closesAt}`;
        
    } else {
        card.classList.add('inactive');
        hoursEl.textContent = 'No disponible';
        
        if (horarioTemplates[dayIndex]) {
            horarioTemplates[dayIndex].is_active = false;
        } else {
            horarioTemplates[dayIndex] = {
                day_of_week: parseInt(dayIndex),
                is_active: false,
                opens_at: null,
                closes_at: null,
                time_blocks: [],
                consultorio_id: null
            };
        }
    }
    
    hasUnsavedChanges = true;
    autoSaveHorarioTemplate(dayIndex);
}

function autoSaveHorarioTemplate(dayIndex) {
    clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
        saveHorarioTemplate(dayIndex);
    }, 500);
}

async function saveHorarioTemplate(dayIndex) {
    const template = horarioTemplates[dayIndex];
    if (!template) return;
    
    try {
        const response = await api.makeRequest('/horarios/templates', {
            method: 'POST',
            body: JSON.stringify({
                day_of_week: parseInt(dayIndex),
                is_active: template.is_active,
                opens_at: template.opens_at,
                closes_at: template.closes_at,
                time_blocks: template.time_blocks || [],
                consultorio_id: template.consultorio_id || null
            })
        });
        
        hasUnsavedChanges = false;
        
        if (response && response.template_id) {
            const templatesResponse = await api.makeRequest('/horarios/templates');
            if (templatesResponse && templatesResponse.templates) {
                const updatedTemplate = templatesResponse.templates.find(t => t.day_of_week === parseInt(dayIndex));
                if (updatedTemplate) {
                    horarioTemplates[dayIndex] = updatedTemplate;
                }
            }
        }
        
        updateDayCards();
        await updateCapacidad();
        showToast('Horario guardado', 'success');
        
    } catch (error) {
        console.error('Error saving template:', error);
        showToast('Error al guardar horario', 'error');
    }
}

function customizeDay(dayName) {
    const dayIndex = Object.keys(daysOfWeek).find(key => 
        daysOfWeek[key].lower === dayName
    );
    
    if (dayIndex === undefined) return;
    
    const template = horarioTemplates[dayIndex] || {
        opens_at: '09:00',
        closes_at: '19:00',
        time_blocks: [],
        consultorio_id: null
    };
    
    openDayModal(dayName, template);
}

function openDayModal(dayName, template) {
    const modal = document.getElementById('day-modal');
    if (!modal) return;
    
    const modalTitle = modal.querySelector('h3');
    modalTitle.textContent = `Personalizar ${dayName.charAt(0).toUpperCase() + dayName.slice(1)}`;
    
    modal.querySelector('[name="opens_at"]').value = template.opens_at || '09:00';
    modal.querySelector('[name="closes_at"]').value = template.closes_at || '19:00';
    
    currentBreakBlocks = (template.time_blocks || []).filter(block => block.type !== 'consultation');
    renderBreakBlocks(currentBreakBlocks);
    
    // Set selected consultorio
    selectedConsultorioForDay = template.consultorio_id || null;
    renderConsultorioSelector('consultorio-selector', selectedConsultorioForDay);
    
    modal.dataset.currentDay = dayName;
    
    const checkboxContainer = modal.querySelector('.apply-days-container');
    if (checkboxContainer) {
        checkboxContainer.innerHTML = '';
        
        for (let i = 0; i < 7; i++) {
            const otherDayName = daysOfWeek[i].lower;
            if (otherDayName !== dayName) {
                const label = document.createElement('label');
                label.className = 'flex items-center gap-2 cursor-pointer';
                label.innerHTML = `
                    <input type="checkbox" name="apply_to_day" value="${otherDayName}" class="w-4 h-4 text-emerald-600">
                    <span class="text-sm">${daysOfWeek[i].full}</span>
                `;
                checkboxContainer.appendChild(label);
            }
        }
    }
    
    clearModalErrors();
    
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

async function saveDay() {
    const modal = document.getElementById('day-modal');
    const dayName = modal.dataset.currentDay;
    const dayIndex = Object.keys(daysOfWeek).find(key => 
        daysOfWeek[key].lower === dayName
    );
    
    if (dayIndex === undefined) return;
    
    const opensAt = modal.querySelector('[name="opens_at"]').value;
    const closesAt = modal.querySelector('[name="closes_at"]').value;
    
    if (opensAt >= closesAt) {
        showToast('El horario de cierre debe ser posterior al de apertura', 'error');
        return;
    }
    
    let hasErrors = false;
    for (let i = 0; i < currentBreakBlocks.length; i++) {
        const breakBlock = currentBreakBlocks[i];
        
        if (breakBlock.start < opensAt || breakBlock.end > closesAt) {
            showToast(`El descanso ${i + 1} está fuera del horario de trabajo`, 'error');
            hasErrors = true;
            break;
        }
        
        for (let j = i + 1; j < currentBreakBlocks.length; j++) {
            if (isTimeOverlap(breakBlock.start, breakBlock.end, currentBreakBlocks[j].start, currentBreakBlocks[j].end)) {
                showToast(`Los descansos ${i + 1} y ${j + 1} se superponen`, 'error');
                hasErrors = true;
                break;
            }
        }
        
        if (hasErrors) break;
    }
    
    if (hasErrors) return;
    
    const timeBlocks = [];
    let lastEnd = opensAt;
    
    const sortedBreaks = [...currentBreakBlocks].sort((a, b) => a.start.localeCompare(b.start));
    
    sortedBreaks.forEach(breakBlock => {
        if (lastEnd < breakBlock.start) {
            timeBlocks.push({
                start: lastEnd,
                end: breakBlock.start,
                type: 'consultation'
            });
        }
        
        timeBlocks.push(breakBlock);
        lastEnd = breakBlock.end;
    });
    
    if (lastEnd < closesAt) {
        timeBlocks.push({
            start: lastEnd,
            end: closesAt,
            type: 'consultation'
        });
    }
    
    if (!horarioTemplates[dayIndex]) {
        horarioTemplates[dayIndex] = {
            day_of_week: parseInt(dayIndex),
            is_active: true
        };
    }
    
    horarioTemplates[dayIndex].opens_at = opensAt;
    horarioTemplates[dayIndex].closes_at = closesAt;
    horarioTemplates[dayIndex].time_blocks = timeBlocks;
    horarioTemplates[dayIndex].consultorio_id = selectedConsultorioForDay;
    
    const applyToDays = modal.querySelectorAll('[name="apply_to_day"]:checked');
    const templatesToSave = [{...horarioTemplates[dayIndex]}];
    
    applyToDays.forEach(checkbox => {
        const targetDayName = checkbox.value;
        const targetDayIndex = Object.keys(daysOfWeek).find(key => 
            daysOfWeek[key].lower === targetDayName
        );
        
        if (targetDayIndex !== undefined && targetDayIndex !== dayIndex) {
            horarioTemplates[targetDayIndex] = {
                ...horarioTemplates[dayIndex],
                day_of_week: parseInt(targetDayIndex),
                // Don't copy consultorio_id when applying to other days
                consultorio_id: horarioTemplates[targetDayIndex]?.consultorio_id || null
            };
            templatesToSave.push({...horarioTemplates[targetDayIndex]});
        }
    });
    
    showLoading();
    
    try {
        if (templatesToSave.length > 1) {
            await api.makeRequest('/horarios/templates/bulk', {
                method: 'POST',
                body: JSON.stringify({ templates: templatesToSave })
            });
        } else {
            await saveHorarioTemplate(dayIndex);
        }
        
        const templatesResponse = await api.makeRequest('/horarios/templates');
        if (templatesResponse && templatesResponse.templates) {
            horarioTemplates = {};
            templatesResponse.templates.forEach(template => {
                horarioTemplates[template.day_of_week] = template;
            });
        }
        
        closeModal();
        updateDayCards();
        await updateCapacidad();
        showToast('Horario actualizado exitosamente', 'success');
        
    } catch (error) {
        console.error('Error saving day:', error);
        showToast('Error al guardar el horario', 'error');
    } finally {
        hideLoading();
    }
}

async function copyDay(sourceDayName) {
    const sourceDayIndex = Object.keys(daysOfWeek).find(key => 
        daysOfWeek[key].lower === sourceDayName
    );
    
    if (sourceDayIndex === undefined) return;
    
    const sourceTemplate = horarioTemplates[sourceDayIndex];
    if (!sourceTemplate || !sourceTemplate.is_active) {
        showToast('Este día no está activo', 'warning');
        return;
    }
    
    if (!confirm(`¿Copiar el horario de ${daysOfWeek[sourceDayIndex].full} a todos los días activos?`)) {
        return;
    }
    
    showLoading();
    
    try {
        const templates = [];
        
        for (let day = 0; day < 7; day++) {
            if (day !== parseInt(sourceDayIndex) && horarioTemplates[day] && horarioTemplates[day].is_active) {
                horarioTemplates[day] = {
                    ...sourceTemplate,
                    day_of_week: day,
                    // Keep each day's specific consultorio_id
                    consultorio_id: horarioTemplates[day].consultorio_id
                };
                templates.push(horarioTemplates[day]);
            }
        }
        
        if (templates.length > 0) {
            await api.makeRequest('/horarios/templates/bulk', {
                method: 'POST',
                body: JSON.stringify({ templates })
            });
            
            const templatesResponse = await api.makeRequest('/horarios/templates');
            if (templatesResponse && templatesResponse.templates) {
                horarioTemplates = {};
                templatesResponse.templates.forEach(template => {
                    horarioTemplates[template.day_of_week] = template;
                });
            }
            
            updateDayCards();
            await updateCapacidad();
            showToast('Horario copiado exitosamente', 'success');
        }
        
    } catch (error) {
        console.error('Error copying day:', error);
        showToast('Error al copiar el horario', 'error');
    } finally {
        hideLoading();
    }
}

// ==================== BREAK MANAGEMENT ====================
function renderBreakBlocks(breaks) {
    const container = document.getElementById('break-blocks-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    breaks.forEach((block, index) => {
        const breakDiv = document.createElement('div');
        breakDiv.className = 'flex items-center gap-3';
        
        const syncIcon = block.external_event_id ? 
            '<i class="fas fa-sync text-blue-400 text-xs" title="Sincronizado desde calendario externo"></i>' : '';
        
        breakDiv.innerHTML = `
            <input type="time" value="${block.start}" class="input-field" data-break-index="${index}" data-field="start" onchange="validateBreakTime(${index})">
            <span class="text-gray-400">—</span>
            <input type="time" value="${block.end}" class="input-field" data-break-index="${index}" data-field="end" onchange="validateBreakTime(${index})">
            <select class="input-field" data-break-index="${index}" data-field="type" style="min-width: 150px;">
                <option value="lunch" ${block.type === 'lunch' ? 'selected' : ''}>Comida</option>
                <option value="break" ${block.type === 'break' ? 'selected' : ''}>Descanso</option>
                <option value="administrative" ${block.type === 'administrative' ? 'selected' : ''}>Administrativo</option>
            </select>
            ${syncIcon}
            <button class="icon-btn" onclick="removeBreak(${index})" ${block.external_event_id ? 'title="Este descanso está sincronizado"' : ''}>
                <i class="fas fa-trash"></i>
            </button>
        `;
        container.appendChild(breakDiv);
    });
}

function addBreak() {
    const modal = document.getElementById('day-modal');
    const opensAt = modal.querySelector('[name="opens_at"]').value;
    const closesAt = modal.querySelector('[name="closes_at"]').value;
    
    if (!opensAt || !closesAt) {
        showToast('Define primero el horario de apertura y cierre', 'warning');
        return;
    }
    
    let defaultStart = '14:00';
    let defaultEnd = '15:00';
    
    const openTime = parseTimeString(opensAt);
    const closeTime = parseTimeString(closesAt);
    
    if (parseTimeString(defaultStart) < openTime) {
        defaultStart = formatTimeFromMinutes(openTime + 60);
    }
    
    if (parseTimeString(defaultEnd) > closeTime) {
        defaultEnd = formatTimeFromMinutes(closeTime - 30);
    }
    
    if (parseTimeString(defaultStart) >= parseTimeString(defaultEnd)) {
        const midTime = openTime + Math.floor((closeTime - openTime) / 2);
        defaultStart = formatTimeFromMinutes(midTime - 30);
        defaultEnd = formatTimeFromMinutes(midTime + 30);
    }
    
    if (defaultStart < opensAt || defaultEnd > closesAt) {
        showToast('No hay espacio suficiente para agregar un descanso', 'error');
        return;
    }
    
    for (const existingBreak of currentBreakBlocks) {
        if (isTimeOverlap(defaultStart, defaultEnd, existingBreak.start, existingBreak.end)) {
            const existingEnd = parseTimeString(existingBreak.end);
            const potentialStart = existingEnd + 30;
            
            if (potentialStart + 60 <= closeTime) {
                defaultStart = formatTimeFromMinutes(potentialStart);
                defaultEnd = formatTimeFromMinutes(potentialStart + 60);
            } else {
                showToast('No hay espacio disponible para otro descanso', 'warning');
                return;
            }
        }
    }
    
    currentBreakBlocks.push({
        start: defaultStart,
        end: defaultEnd,
        type: 'lunch'
    });
    
    renderBreakBlocks(currentBreakBlocks);
}

function removeBreak(index) {
    const breakToRemove = currentBreakBlocks[index];
    
    if (breakToRemove.external_event_id) {
        if (!confirm('Este descanso está sincronizado desde tu calendario externo. ¿Deseas eliminarlo de todos modos?')) {
            return;
        }
    }
    
    currentBreakBlocks.splice(index, 1);
    renderBreakBlocks(currentBreakBlocks);
    clearModalErrors();
}

function validateBreakTime(index) {
    const modal = document.getElementById('day-modal');
    const opensAt = modal.querySelector('[name="opens_at"]').value;
    const closesAt = modal.querySelector('[name="closes_at"]').value;
    
    const breakStart = document.querySelector(`[data-break-index="${index}"][data-field="start"]`).value;
    const breakEnd = document.querySelector(`[data-break-index="${index}"][data-field="end"]`).value;
    
    currentBreakBlocks[index] = {
        ...currentBreakBlocks[index],
        start: breakStart,
        end: breakEnd,
        type: document.querySelector(`[data-break-index="${index}"][data-field="type"]`).value
    };
    
    const errors = [];
    
    if (breakStart < opensAt || breakEnd > closesAt) {
        errors.push(`El descanso ${index + 1} está fuera del horario de trabajo`);
    }
    
    if (breakStart >= breakEnd) {
        errors.push(`El descanso ${index + 1} tiene horario inválido`);
    }
    
    for (let i = 0; i < currentBreakBlocks.length; i++) {
        if (i !== index) {
            const otherBreak = currentBreakBlocks[i];
            if (isTimeOverlap(breakStart, breakEnd, otherBreak.start, otherBreak.end)) {
                errors.push(`El descanso ${index + 1} se superpone con el descanso ${i + 1}`);
            }
        }
    }
    
    const errorDiv = document.getElementById('breaks-error');
    if (errors.length > 0) {
        errorDiv.textContent = errors[0];
        errorDiv.classList.add('show');
        
        document.querySelector(`[data-break-index="${index}"][data-field="start"]`).classList.add('error');
        document.querySelector(`[data-break-index="${index}"][data-field="end"]`).classList.add('error');
    } else {
        clearBreakError(index);
    }
}

function validateBreaksOnScheduleChange() {
    const modal = document.getElementById('day-modal');
    const opensAt = modal.querySelector('[name="opens_at"]').value;
    const closesAt = modal.querySelector('[name="closes_at"]').value;
    
    if (opensAt >= closesAt) {
        const errorDiv = document.getElementById('schedule-error');
        errorDiv.textContent = 'El horario de cierre debe ser posterior al de apertura';
        errorDiv.classList.add('show');
        return;
    } else {
        document.getElementById('schedule-error').classList.remove('show');
    }
    
    for (let i = 0; i < currentBreakBlocks.length; i++) {
        validateBreakTime(i);
    }
}

// ==================== EXCEPTION CALENDAR ====================
function initializeExceptionCalendar() {
    renderCalendar(currentCalendarMonth, currentCalendarYear);
}

function previousMonth() {
    currentCalendarMonth--;
    if (currentCalendarMonth < 0) {
        currentCalendarMonth = 11;
        currentCalendarYear--;
    }
    renderCalendar(currentCalendarMonth, currentCalendarYear);
}

function nextMonth() {
    currentCalendarMonth++;
    if (currentCalendarMonth > 11) {
        currentCalendarMonth = 0;
        currentCalendarYear++;
    }
    renderCalendar(currentCalendarMonth, currentCalendarYear);
}

function renderCalendar(month, year) {
    const calendarEl = document.getElementById('exception-calendar');
    if (!calendarEl) return;
    
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    
    document.getElementById('calendar-month-year').textContent = `${monthNames[month]} ${year}`;
    
    updateWeekdayIndicators();
    
    let daysGrid = calendarEl.querySelector('.calendar-days-grid');
    if (!daysGrid) return;
    
    daysGrid.innerHTML = '';
    
    const adjustedFirstDay = firstDay === 0 ? 6 : firstDay - 1;
    for (let i = 0; i < adjustedFirstDay; i++) {
        const emptyDay = document.createElement('div');
        daysGrid.appendChild(emptyDay);
    }
    
    for (let day = 1; day <= daysInMonth; day++) {
        const dayEl = document.createElement('div');
        dayEl.className = 'calendar-day non-clickable';
        dayEl.textContent = day;
        
        const date = new Date(year, month, day);
        const dateStr = date.toISOString().split('T')[0];
        
        const today = new Date();
        const isToday = date.toDateString() === today.toDateString();
        
        const exception = horarioExceptions.find(exc => exc.date === dateStr);
        if (exception) {
            if (exception.is_vacation) {
                dayEl.classList.add('vacation');
            } else if (!exception.is_working_day) {
                dayEl.classList.add('exception');
            } else if (exception.is_special_open) {
                dayEl.classList.add('special-open');
            } else {
                dayEl.classList.add('modified-hours');
            }
            
            if (exception.sync_source && exception.sync_source !== 'manual') {
                dayEl.innerHTML = `${day} <i class="fas fa-sync text-xs" style="position: absolute; top: 2px; right: 2px; color: #3b82f6;"></i>`;
                dayEl.title = `Sincronizado desde ${exception.sync_source === 'google' ? 'Google Calendar' : 'Apple Calendar'}`;
            }
        }
        
        if (isToday) {
            dayEl.classList.add('today');
        }
        
        daysGrid.appendChild(dayEl);
    }
}

// ==================== EXCEPTION MANAGEMENT ====================
function toggleExceptionFields() {
    const type = document.getElementById('exception-type').value;
    const timeFields = document.getElementById('exception-time-fields');
    const breaksContainer = document.getElementById('exception-breaks-container');
    const vacationFields = document.getElementById('vacation-range-fields');
    const descriptionEl = document.getElementById('exception-type-description');
    const singleDateContainer = document.getElementById('single-date-container');
    const consultorioSelectorContainer = document.getElementById('exception-consultorio-container');
    
    if (timeFields) timeFields.classList.add('hidden');
    if (breaksContainer) breaksContainer.classList.add('hidden');
    if (vacationFields) vacationFields.classList.add('hidden');
    if (consultorioSelectorContainer) consultorioSelectorContainer.classList.add('hidden');
    
    if (type !== 'vacation') {
        vacationStartDate = null;
        vacationEndDate = null;
        document.getElementById('vacation-dates').value = '';
        document.getElementById('vacation-calendar-title').textContent = 'Selecciona fecha de inicio';
        document.getElementById('vacation-confirm-btn').disabled = true;
    }
    
    if (singleDateContainer) {
        if (type === 'vacation') {
            singleDateContainer.classList.add('hidden');
        } else {
            singleDateContainer.classList.remove('hidden');
        }
    }
    
    if (descriptionEl && exceptionDescriptions[type]) {
        descriptionEl.textContent = exceptionDescriptions[type];
        descriptionEl.classList.remove('hidden');
    } else if (descriptionEl) {
        descriptionEl.classList.add('hidden');
    }
    
    if (type === 'special-hours' || type === 'special-open') {
        if (timeFields) timeFields.classList.remove('hidden');
        if (breaksContainer) breaksContainer.classList.remove('hidden');
        if (consultorioSelectorContainer) {
            consultorioSelectorContainer.classList.remove('hidden');
            renderExceptionConsultorioSelector();
        }
        currentExceptionBreaks = [];
        renderExceptionBreakBlocks(currentExceptionBreaks);
    } else if (type === 'vacation') {
        if (vacationFields) vacationFields.classList.remove('hidden');
    }
    
    if (type !== 'vacation') {
        document.getElementById('exception-date').value = '';
        selectedDateForException = null;
    }
    
    // Reset consultorio selection
    selectedConsultorioForException = null;
}

async function addException() {
    const type = document.getElementById('exception-type').value;
    
    if (!type) {
        showToast('Selecciona el tipo de evento', 'warning');
        return;
    }
    
    if (type === 'vacation') {
        await addVacationRange();
        return;
    }
    
    const reason = document.getElementById('exception-reason').value;
    
    if (!selectedDateForException) {
        showToast('Por favor selecciona una fecha', 'warning');
        return;
    }
    
    const existingException = horarioExceptions.find(exc => exc.date === selectedDateForException);
    if (existingException) {
        showToast('Ya existe un evento para esta fecha', 'warning');
        return;
    }
    
    const exceptionData = {
        date: selectedDateForException,
        is_working_day: type === 'special-hours' || type === 'special-open',
        is_special_open: type === 'special-open',
        reason: reason,
        time_blocks: [],
        consultorio_id: null
    };
    
    if (type === 'special-hours' || type === 'special-open') {
        const opensAt = document.getElementById('exception-opens').value;
        const closesAt = document.getElementById('exception-closes').value;
        
        if (!opensAt || !closesAt) {
            showToast('Por favor ingresa los horarios', 'warning');
            return;
        }
        
        if (opensAt >= closesAt) {
            showToast('El horario de cierre debe ser posterior al de apertura', 'error');
            return;
        }
        
        exceptionData.opens_at = opensAt;
        exceptionData.closes_at = closesAt;
        exceptionData.consultorio_id = selectedConsultorioForException;
        
        if (currentExceptionBreaks.length > 0) {
            const timeBlocks = [];
            let lastEnd = opensAt;
            
            const sortedBreaks = [...currentExceptionBreaks].sort((a, b) => a.start.localeCompare(b.start));
            
            sortedBreaks.forEach(breakBlock => {
                if (lastEnd < breakBlock.start) {
                    timeBlocks.push({
                        start: lastEnd,
                        end: breakBlock.start,
                        type: 'consultation'
                    });
                }
                
                timeBlocks.push(breakBlock);
                lastEnd = breakBlock.end;
            });
            
            if (lastEnd < closesAt) {
                timeBlocks.push({
                    start: lastEnd,
                    end: closesAt,
                    type: 'consultation'
                });
            }
            
            exceptionData.time_blocks = timeBlocks;
        } else {
            exceptionData.time_blocks = [{
                start: opensAt,
                end: closesAt,
                type: 'consultation'
            }];
        }
    }
    
    showLoading();
    
    try {
        const response = await api.makeRequest('/horarios/exceptions', {
            method: 'POST',
            body: JSON.stringify(exceptionData)
        });
        
        horarioExceptions.push({
            ...exceptionData,
            id: response.exception_id
        });
        
        updateExceptionsList();
        renderCalendar(currentCalendarMonth, currentCalendarYear);
        
        // Clear form
        document.getElementById('exception-date').value = '';
        document.getElementById('exception-reason').value = '';
        document.getElementById('exception-opens').value = '';
        document.getElementById('exception-closes').value = '';
        document.getElementById('exception-type').value = '';
        document.getElementById('exception-type-description').classList.add('hidden');
        document.getElementById('exception-time-fields').classList.add('hidden');
        document.getElementById('exception-breaks-container').classList.add('hidden');
        document.getElementById('exception-consultorio-container').classList.add('hidden');
        currentExceptionBreaks = [];
        selectedDateForException = null;
        selectedConsultorioForException = null;
        
        showToast('Evento agregado exitosamente', 'success');
        
    } catch (error) {
        console.error('Error adding exception:', error);
        showToast('Error al agregar evento', 'error');
    } finally {
        hideLoading();
    }
}

function updateExceptionsList() {
    const listContainer = document.getElementById('exception-list');
    if (!listContainer) return;
    
    listContainer.innerHTML = '';
    
    const sortedExceptions = [...horarioExceptions].sort((a, b) => 
        new Date(a.date) - new Date(b.date)
    );
    
    const vacationGroups = {};
    const nonVacationExceptions = [];
    
    sortedExceptions.forEach(exception => {
        if (exception.is_vacation && exception.vacation_group_id) {
            if (!vacationGroups[exception.vacation_group_id]) {
                vacationGroups[exception.vacation_group_id] = [];
            }
            vacationGroups[exception.vacation_group_id].push(exception);
        } else {
            nonVacationExceptions.push(exception);
        }
    });
    
    // Render vacation groups
    Object.values(vacationGroups).forEach(group => {
        if (group.length === 0) return;
        
        const startDate = new Date(group[0].date + 'T00:00:00');
        const endDate = new Date(group[group.length - 1].date + 'T00:00:00');
        
        const card = document.createElement('div');
        card.className = 'day-card magnetic-hover';
        
        const syncIndicator = group[0].sync_source && group[0].sync_source !== 'manual' ? 
            `<i class="fas fa-sync text-blue-400 ml-2" title="Sincronizado"></i>` : '';
        
        card.innerHTML = `
            <div class="flex items-start justify-between">
                <div>
                    <div class="font-bold text-lg text-gray-900">Vacaciones ${syncIndicator}</div>
                    <div class="text-sm text-gray-600 mt-1">
                        ${startDate.toLocaleDateString('es-MX', { day: 'numeric', month: 'long' })} - 
                        ${endDate.toLocaleDateString('es-MX', { day: 'numeric', month: 'long', year: 'numeric' })}
                    </div>
                    <div class="inline-flex items-center gap-2 mt-3 px-3 py-1 bg-purple-100 text-purple-700 rounded-full text-sm font-medium">
                        <i class="fas fa-umbrella-beach"></i>
                        ${group.length} días de vacaciones
                    </div>
                </div>
                <button class="icon-btn" onclick="removeVacationGroup('${group[0].vacation_group_id}')">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        listContainer.appendChild(card);
    });
    
    // Render other exceptions
    nonVacationExceptions.forEach(exception => {
        const card = document.createElement('div');
        card.className = 'day-card magnetic-hover';
        
        const dateObj = new Date(exception.date + 'T00:00:00');
        const dateStr = dateObj.toLocaleDateString('es-MX', { 
            day: 'numeric', 
            month: 'long', 
            year: 'numeric' 
        });
        
        const syncIndicator = exception.sync_source && exception.sync_source !== 'manual' ? 
            `<i class="fas fa-sync text-blue-400 ml-2" title="Sincronizado desde ${exception.sync_source === 'google' ? 'Google Calendar' : 'Apple Calendar'}"></i>` : '';
        
        let statusHtml = '';
        let detailsHtml = '';
        let consultorioHtml = '';
        
        // Add consultorio display if present
        if (exception.consultorio_id) {
            const consultorio = availableConsultorios.find(c => c.id === exception.consultorio_id);
            if (consultorio) {
                consultorioHtml = `
                    <div class="flex items-center gap-2 mt-2">
                        <i class="fas fa-map-marker-alt text-purple-400 text-xs"></i>
                        <span class="text-xs text-purple-600">${consultorio.nombre}</span>
                    </div>
                `;
            }
        }
        
        if (!exception.is_working_day) {
            statusHtml = `
                <div class="inline-flex items-center gap-2 mt-3 px-3 py-1 bg-red-100 text-red-700 rounded-full text-sm font-medium">
                    <i class="fas fa-times-circle"></i>
                    Consultorio cerrado ${syncIndicator}
                </div>
            `;
        } else if (exception.is_special_open) {
            statusHtml = `
                <div class="inline-flex items-center gap-2 mt-3 px-3 py-1 bg-emerald-100 text-emerald-700 rounded-full text-sm font-medium">
                    <i class="fas fa-calendar-plus"></i>
                    Día especial abierto ${syncIndicator}
                    ${exception.opens_at ? ` - ${formatTime(exception.opens_at)} a ${formatTime(exception.closes_at)}` : ''}
                </div>
            `;
            
            if (exception.time_blocks && exception.time_blocks.length > 0) {
                const breaks = exception.time_blocks.filter(b => b.type !== 'consultation');
                if (breaks.length > 0) {
                    detailsHtml = `<div class="text-xs text-gray-500 mt-2">${breaks.length} descanso(s) programado(s)</div>`;
                }
            }
        } else {
            statusHtml = `
                <div class="inline-flex items-center gap-2 mt-3 px-3 py-1 bg-amber-100 text-amber-700 rounded-full text-sm font-medium">
                    <i class="fas fa-clock"></i>
                    Horario especial: ${formatTime(exception.opens_at)} - ${formatTime(exception.closes_at)} ${syncIndicator}
                </div>
            `;
            
            if (exception.time_blocks && exception.time_blocks.length > 0) {
                const breaks = exception.time_blocks.filter(b => b.type !== 'consultation');
                if (breaks.length > 0) {
                    detailsHtml = `<div class="text-xs text-gray-500 mt-2">${breaks.length} descanso(s) programado(s)</div>`;
                }
            }
        }
        
        card.innerHTML = `
            <div class="flex items-start justify-between">
                <div>
                    <div class="font-bold text-lg text-gray-900">${dateStr}</div>
                    ${exception.reason ? `<div class="text-sm text-gray-600 mt-1">${exception.reason}</div>` : ''}
                    ${statusHtml}
                    ${consultorioHtml}
                    ${detailsHtml}
                </div>
                <button class="icon-btn" onclick="showDeleteConfirmation('${exception.id}')">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        listContainer.appendChild(card);
    });
    
    if (sortedExceptions.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fas fa-calendar-check text-4xl mb-3 opacity-50"></i>
                <p>No hay eventos especiales programados</p>
            </div>
        `;
    }
}

// ==================== CALENDAR SYNC FUNCTIONS ====================
async function checkCalendarConnectionStatus() {
    try {
        console.log('Checking calendar connection status...');
        const response = await api.makeRequest('/calendar-sync/status');
        console.log('Connection status response:', response);
        
        if (response && response.connected) {
            calendarConnection = response;
            // Ensure merge_calendars is true by default
            if (!calendarConnection.settings) {
                calendarConnection.settings = { merge_calendars: true, receive_notifications: false };
            } else if (!calendarConnection.settings.hasOwnProperty('merge_calendars')) {
                calendarConnection.settings.merge_calendars = true;
            }
            showConnectedPanel();
        } else {
            showConnectionOptions();
        }
    } catch (error) {
        console.error('Error checking calendar connection:', error);
        showConnectionOptions();
    }
}

function initializeCalendarSyncUI() {
    console.log('Initializing calendar sync UI...');
    
    const googleConnectBtn = document.getElementById('google-calendar-connect');
    const appleConnectBtn = document.getElementById('apple-calendar-connect');
    
    if (googleConnectBtn) {
        googleConnectBtn.addEventListener('click', () => connectGoogleCalendar());
    }
    
    if (appleConnectBtn) {
        appleConnectBtn.addEventListener('click', () => connectAppleCalendar());
    }
    
    const syncNowBtn = document.getElementById('sync-now-btn');
    if (syncNowBtn) {
        syncNowBtn.addEventListener('click', () => syncCalendar(false));
    }
    
    const mergeToggle = document.getElementById('merge-calendars-toggle');
    const notificationsToggle = document.getElementById('notifications-toggle');
    
    if (mergeToggle) {
        // Set to checked by default
        mergeToggle.checked = true;
        mergeToggle.addEventListener('change', (e) => updateSyncSettings('merge_calendars', e.target.checked));
    }
    
    if (notificationsToggle) {
        notificationsToggle.addEventListener('change', (e) => updateSyncSettings('receive_notifications', e.target.checked));
    }
}

function updateCalendarSyncPanel() {
    if (calendarConnection && calendarConnection.connected) {
        showConnectedPanel();
    } else {
        showConnectionOptions();
    }
}

function showConnectedPanel() {
    console.log('Showing connected panel...');
    const connectionPanel = document.getElementById('calendar-connection-panel');
    const connectionOptions = document.getElementById('calendar-connection-options');
    
    if (connectionOptions) connectionOptions.style.display = 'none';
    if (connectionPanel) {
        connectionPanel.style.display = 'block';
        
        if (calendarConnection) {
            const connectedEmailEl = document.getElementById('connected-email');
            const connectedProviderEl = document.getElementById('connected-provider');
            
            if (connectedEmailEl) {
                connectedEmailEl.textContent = calendarConnection.email || calendarConnection.calendar_email || '';
            }
            
            if (connectedProviderEl) {
                connectedProviderEl.textContent = 
                    calendarConnection.provider === 'google' ? 'Google Calendar' : 'Apple Calendar';
            }
            
            if (calendarConnection.last_sync) {
                const lastSync = new Date(calendarConnection.last_sync);
                document.getElementById('last-sync-time').textContent = formatRelativeTime(lastSync);
            }
            
            if (calendarConnection.settings) {
                const mergeToggle = document.getElementById('merge-calendars-toggle');
                const notificationsToggle = document.getElementById('notifications-toggle');
                
                // Default merge_calendars to true
                if (mergeToggle) mergeToggle.checked = calendarConnection.settings.merge_calendars !== false;
                if (notificationsToggle) notificationsToggle.checked = calendarConnection.settings.receive_notifications || false;
            }
        }
    }
}

function showConnectionOptions() {
    console.log('Showing connection options...');
    const connectionPanel = document.getElementById('calendar-connection-panel');
    const connectionOptions = document.getElementById('calendar-connection-options');
    
    if (connectionPanel) connectionPanel.style.display = 'none';
    if (connectionOptions) connectionOptions.style.display = 'block';
}

async function connectGoogleCalendar() {
    try {
        console.log('Starting Google Calendar connection...');
        showLoading('Conectando con Google Calendar...');
        
        const response = await api.makeRequest('/calendar-sync/google/auth');
        console.log('Auth response:', response);
        
        if (response && response.auth_url) {
            sessionStorage.setItem('calendar_sync_state', response.state);
            sessionStorage.setItem('calendar_sync_provider', 'google');
            
            console.log('Opening auth window:', response.auth_url);
            const authWindow = window.open(
                response.auth_url,
                'GoogleCalendarAuth',
                'width=600,height=700,toolbar=no,menubar=no'
            );
            
            const pollInterval = setInterval(async () => {
                if (authWindow.closed) {
                    clearInterval(pollInterval);
                    console.log('Auth window closed, checking connection status...');
                    await checkCalendarConnectionStatus();
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

async function connectAppleCalendar() {
    try {
        showLoading('Conectando con Apple Calendar...');
        showToast('La integración con Apple Calendar estará disponible próximamente', 'info');
        hideLoading();
    } catch (error) {
        console.error('Error connecting Apple Calendar:', error);
        showToast('Error al conectar con Apple Calendar', 'error');
        hideLoading();
    }
}

async function syncCalendar(isSilent = false) {
    if (syncInProgress) {
        if (!isSilent) showToast('Sincronización en progreso...', 'info');
        return;
    }
    
    console.log('Starting calendar sync...', { isSilent });
    syncInProgress = true;
    justSyncedEventIds.clear(); // Clear previous sync tracking
    
    const syncBtn = document.getElementById('sync-now-btn');
    if (syncBtn && !isSilent) {
        syncBtn.disabled = true;
        syncBtn.innerHTML = '<i class="fas fa-sync fa-spin mr-2"></i>Sincronizando...';
    }
    
    try {
        if (!isSilent) showLoading('Sincronizando calendarios...');
        
        // Default merge_calendars to true
        const syncRequest = {
            merge_calendars: document.getElementById('merge-calendars-toggle')?.checked !== false,
            receive_notifications: document.getElementById('notifications-toggle')?.checked || false
        };
        
        console.log('Sync request:', syncRequest);
        
        const response = await api.makeRequest('/calendar-sync/sync', {
            method: 'POST',
            body: JSON.stringify(syncRequest)
        });
        
        console.log('Sync response:', response);
        
        if (response && response.success) {
            // Track just synced events to avoid self-conflicts
            if (response.synced_event_ids) {
                response.synced_event_ids.forEach(id => justSyncedEventIds.add(id));
            }
            
            // Group recurring conflicts
            const groupedConflicts = groupRecurringConflicts(response.conflicts_found || []);
            
            // Process grouped conflicts
            if (groupedConflicts.length > 0) {
                console.log(`Found ${groupedConflicts.length} conflict groups`);
                pendingConflicts = groupedConflicts;
                if (!isSilent) showConflictResolutionModal();
            }
            
            // Process recurrent events
            if (response.recurrent_events && response.recurrent_events.length > 0) {
                console.log(`Found ${response.recurrent_events.length} recurrent events`);
                pendingRecurrentEvents = response.recurrent_events;
                if (!isSilent && groupedConflicts.length === 0) {
                    showRecurrentEventsModal();
                }
            }
            
            // Process special events
            if (response.special_events && response.special_events.length > 0) {
                console.log(`Found ${response.special_events.length} special events`);
                pendingSpecialEvents = response.special_events;
                await processSpecialEvents();
            }
            
            // Process all-day events
            if (response.all_day_events && response.all_day_events.length > 0) {
                console.log(`Found ${response.all_day_events.length} all-day events`);
                pendingAllDayEvents = response.all_day_events;
                await processAllDayEvents();
            }
            
            // Update UI
            if (!isSilent) updateSyncStatus(response);
            
            // Reload schedule data
            await loadHorarioData();
            
            // Show message only if not silent
            if (!isSilent) {
                if (response.synced_events || response.conflicts_found?.length || 
                    response.recurrent_events?.length || response.special_events?.length) {
                    showToast(`Sincronización completa: ${response.synced_events || 0} eventos procesados`, 'success');
                } else {
                    showToast('No se encontraron eventos nuevos para sincronizar', 'info');
                }
            }
            
        } else if (response && !response.success) {
            console.error('Sync failed:', response.error);
            if (!isSilent) showToast(`Error: ${response.error || 'Error durante la sincronización'}`, 'error');
        }
        
    } catch (error) {
        console.error('Error during sync:', error);
        if (!isSilent) showToast('Error durante la sincronización', 'error');
    } finally {
        syncInProgress = false;
        if (syncBtn && !isSilent) {
            syncBtn.disabled = false;
            syncBtn.innerHTML = '<i class="fas fa-sync mr-2"></i>Sincronizar Ahora';
        }
        if (!isSilent) hideLoading();
        
        // Update last sync time
        if (calendarConnection) {
            calendarConnection.last_sync = new Date().toISOString();
            const lastSyncEl = document.getElementById('last-sync-time');
            if (lastSyncEl) lastSyncEl.textContent = 'Hace un momento';
        }
    }
}

// NEW: Group recurring conflicts
function groupRecurringConflicts(conflicts) {
    const groups = {};
    const standaloneConflicts = [];
    
    conflicts.forEach(conflict => {
        // Skip conflicts with events we just synced
        if (justSyncedEventIds.has(conflict.external_event?.id)) {
            console.log('Skipping self-conflict with just-synced event:', conflict.external_event?.id);
            return;
        }
        
        if (conflict.external_event?.recurring_group_id) {
            const groupId = conflict.external_event.recurring_group_id;
            if (!groups[groupId]) {
                groups[groupId] = {
                    group_id: groupId,
                    master_event: conflict.external_event,
                    conflicts: [],
                    pattern: conflict.external_event.pattern || {},
                    count: 0
                };
            }
            groups[groupId].conflicts.push(conflict);
            groups[groupId].count++;
        } else {
            standaloneConflicts.push(conflict);
        }
    });
    
    // Convert groups to array and add standalone conflicts
    const groupedConflicts = Object.values(groups).map(group => ({
        type: 'recurring_group',
        ...group
    }));
    
    // Add standalone conflicts as individual items
    standaloneConflicts.forEach(conflict => {
        groupedConflicts.push({
            type: 'single',
            ...conflict
        });
    });
    
    return groupedConflicts;
}

function showConflictResolutionModal() {
    console.log('Showing conflict resolution modal with grouped conflicts...');
    const modal = document.getElementById('conflict-resolution-modal');
    if (!modal) {
        createConflictResolutionModal();
    }
    
    const conflictsList = document.getElementById('conflicts-list');
    conflictsList.innerHTML = '';
    
    pendingConflicts.forEach((conflict, index) => {
        if (conflict.type === 'recurring_group') {
            const card = createGroupedConflictCard(conflict, index);
            conflictsList.appendChild(card);
        } else {
            const card = createConflictCard(conflict, index);
            conflictsList.appendChild(card);
        }
    });
    
    document.getElementById('conflict-resolution-modal').classList.add('show');
}

// NEW: Create grouped conflict card
function createGroupedConflictCard(conflictGroup, index) {
    const card = document.createElement('div');
    card.className = 'conflict-card grouped-conflict';
    card.dataset.conflictIndex = index;
    
    const masterEvent = conflictGroup.master_event;
    const firstConflict = conflictGroup.conflicts[0];
    const conflictInfo = firstConflict.conflict_with;
    
    // Determine day of week for the pattern
    const dayOfWeek = conflictGroup.pattern?.day_of_week !== undefined ? 
        daysOfWeek[conflictGroup.pattern.day_of_week].full : 
        'día recurrente';
    
    card.innerHTML = `
        <div class="conflict-header">
            <h4 class="font-semibold text-gray-900">
                <i class="fas fa-sync-alt text-blue-500 mr-1"></i>
                Evento Recurrente - Todos los ${dayOfWeek}
            </h4>
            <span class="text-xs text-gray-500">${conflictGroup.count} ocurrencias</span>
        </div>
        <div class="conflict-details">
            <div class="event-comparison">
                <div class="external-event">
                    <label class="text-xs font-semibold text-blue-600">Evento del Calendario:</label>
                    <p class="text-sm font-medium">${masterEvent.summary}</p>
                    <p class="text-xs text-gray-600">
                        ${formatTime(masterEvent.start_time)} - ${formatTime(masterEvent.end_time)}
                    </p>
                    <p class="text-xs text-blue-500 mt-1">
                        <i class="fas fa-repeat mr-1"></i>
                        ${conflictGroup.pattern?.frequency_days === 7 ? 'Semanal' : 
                          conflictGroup.pattern?.frequency_days ? `Cada ${conflictGroup.pattern.frequency_days} días` : 
                          'Recurrente'}
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
                <label class="text-xs font-semibold text-gray-700 mb-2 block">
                    Resolver conflicto para TODAS las ocurrencias:
                </label>
                <div class="grid grid-cols-2 gap-2">
                    <button class="resolution-btn" onclick="resolveGroupConflict(${index}, 'merge_sum')">
                        <i class="fas fa-plus-circle"></i>
                        <span>Sumar tiempos</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveGroupConflict(${index}, 'merge_combine')">
                        <i class="fas fa-compress-alt"></i>
                        <span>Combinar</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveGroupConflict(${index}, 'keep_external')">
                        <i class="fas fa-calendar-check"></i>
                        <span>Usar calendario</span>
                    </button>
                    <button class="resolution-btn" onclick="resolveGroupConflict(${index}, 'keep_internal')">
                        <i class="fas fa-hospital"></i>
                        <span>Mantener actual</span>
                    </button>
                </div>
            </div>
        </div>
    `;
    
    return card;
}

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

// NEW: Resolve group conflict
async function resolveGroupConflict(index, resolutionType) {
    const conflictGroup = pendingConflicts[index];
    
    const card = document.querySelector(`[data-conflict-index="${index}"]`);
    if (card) {
        card.classList.add('resolved');
        card.querySelector('.resolution-options').innerHTML = `
            <div class="text-center text-green-600">
                <i class="fas fa-check-circle mr-1"></i>
                Resuelto para todas las ocurrencias: ${getResolutionText(resolutionType)}
            </div>
        `;
    }
    
    // Apply resolution to all conflicts in the group
    if (conflictGroup.type === 'recurring_group') {
        conflictGroup.resolution = resolutionType;
        conflictGroup.conflicts.forEach(conf => {
            conf.resolution = resolutionType;
        });
    } else {
        conflictGroup.resolution = resolutionType;
    }
    
    const allResolved = pendingConflicts.every(c => c.resolution);
    if (allResolved) {
        document.getElementById('apply-conflict-resolutions').disabled = false;
    }
}

async function resolveConflict(index, resolutionType) {
    const conflict = pendingConflicts[index];
    
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
    
    conflict.resolution = resolutionType;
    
    const allResolved = pendingConflicts.every(c => c.resolution);
    if (allResolved) {
        document.getElementById('apply-conflict-resolutions').disabled = false;
    }
}

async function applyConflictResolutions() {
    const resolutions = [];
    
    pendingConflicts.forEach(item => {
        if (item.type === 'recurring_group' && item.resolution) {
            // Apply resolution to all conflicts in the group
            item.conflicts.forEach(conflict => {
                resolutions.push({
                    event_id: conflict.external_event.id,
                    resolution_type: item.resolution,
                    group_id: item.group_id
                });
            });
        } else if (item.resolution) {
            resolutions.push({
                event_id: item.external_event.id,
                resolution_type: item.resolution
            });
        }
    });
    
    try {
        showLoading('Aplicando resoluciones...');
        
        const response = await api.makeRequest('/calendar-sync/resolve-conflicts', {
            method: 'POST',
            body: JSON.stringify(resolutions)
        });
        
        if (response && response.success) {
            showToast('Conflictos resueltos exitosamente', 'success');
            closeConflictModal();
            await loadHorarioData();
        }
        
    } catch (error) {
        console.error('Error resolving conflicts:', error);
        showToast('Error al resolver conflictos', 'error');
    } finally {
        hideLoading();
    }
}

function showRecurrentEventsModal() {
    console.log('Showing recurrent events modal...');
    const modal = document.getElementById('recurrent-events-modal');
    if (!modal) {
        createRecurrentEventsModal();
    }
    
    const eventsList = document.getElementById('recurrent-events-list');
    eventsList.innerHTML = '';
    
    pendingRecurrentEvents.forEach((event, index) => {
        const eventCard = createRecurrentEventCard(event, index);
        eventsList.appendChild(eventCard);
    });
    
    document.getElementById('recurrent-events-modal').classList.add('show');
}

function createRecurrentEventCard(event, index) {
    const card = document.createElement('div');
    card.className = 'recurrent-event-card';
    card.dataset.eventIndex = index;
    
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
            await loadHorarioData();
        }
        
    } catch (error) {
        console.error('Error classifying events:', error);
        showToast('Error al clasificar eventos', 'error');
    } finally {
        hideLoading();
    }
}

async function processSpecialEvents() {
    console.log('Processing special events:', pendingSpecialEvents);
    
    if (pendingSpecialEvents.length > 0) {
        showToast(`${pendingSpecialEvents.length} eventos especiales agregados como descansos`, 'info');
    }
}

async function processAllDayEvents() {
    console.log('Processing all-day events:', pendingAllDayEvents);
    
    if (pendingAllDayEvents.length > 0) {
        showToast(`${pendingAllDayEvents.length} días marcados como cerrados`, 'info');
    }
}

async function disconnectCalendar() {
    if (!confirm('¿Estás seguro de desconectar tu calendario? Se eliminarán todos los eventos sincronizados.')) {
        return;
    }
    
    try {
        showLoading('Desconectando calendario...');
        
        // Clear auto-sync
        if (autoSyncInterval) {
            clearInterval(autoSyncInterval);
            autoSyncInterval = null;
        }
        
        const response = await api.makeRequest('/calendar-sync/disconnect', {
            method: 'DELETE'
        });
        
        if (response && response.success) {
            calendarConnection = null;
            showConnectionOptions();
            showToast('Calendario desconectado exitosamente', 'success');
            await loadHorarioData();
        }
        
    } catch (error) {
        console.error('Error disconnecting calendar:', error);
        showToast('Error al desconectar calendario', 'error');
    } finally {
        hideLoading();
    }
}

async function changeCalendarAccount() {
    if (calendarConnection && calendarConnection.provider === 'google') {
        await connectGoogleCalendar();
    } else if (calendarConnection && calendarConnection.provider === 'apple') {
        await connectAppleCalendar();
    }
}

async function updateSyncSettings(setting, value) {
    try {
        const settings = {
            ...calendarConnection.settings,
            [setting]: value
        };
        
        const response = await api.makeRequest('/calendar-sync/settings', {
            method: 'PUT',
            body: JSON.stringify(settings)
        });
        
        if (response && response.success) {
            calendarConnection.settings = settings;
            showToast('Configuración actualizada', 'success');
            
            if (setting === 'merge_calendars' && value) {
                await syncCalendar(false);
            }
        }
        
    } catch (error) {
        console.error('Error updating settings:', error);
        showToast('Error al actualizar configuración', 'error');
    }
}

function updateSyncStatus(syncResult) {
    const statusEl = document.getElementById('sync-status');
    if (statusEl) {
        statusEl.innerHTML = `
            <div class="sync-stats">
                <div class="stat-item">
                    <i class="fas fa-check-circle text-green-500"></i>
                    <span>${syncResult.synced_events || 0} eventos sincronizados</span>
                </div>
                ${syncResult.conflicts_found && syncResult.conflicts_found.length > 0 ? `
                <div class="stat-item">
                    <i class="fas fa-exclamation-triangle text-amber-500"></i>
                    <span>${syncResult.conflicts_found.length} conflictos encontrados</span>
                </div>
                ` : ''}
            </div>
        `;
    }
}

function createConflictResolutionModal() {
    const modal = document.createElement('div');
    modal.id = 'conflict-resolution-modal';
    modal.className = 'calendar-sync-modal modal';
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
                    Los eventos recurrentes se han agrupado para tu conveniencia.
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
    modal.className = 'calendar-sync-modal modal';
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

function closeConflictModal() {
    const modal = document.getElementById('conflict-resolution-modal');
    if (modal) modal.classList.remove('show');
    pendingConflicts = [];
}

function closeRecurrentModal() {
    const modal = document.getElementById('recurrent-events-modal');
    if (modal) modal.classList.remove('show');
    pendingRecurrentEvents = [];
}

// ==================== DATE PICKER FUNCTIONS ====================
// [Keeping all existing date picker functions as they are]
function openDatePicker(event) {
    event.stopPropagation();
    const popup = document.getElementById('date-picker-popup');
    const miniCalendar = document.getElementById('mini-calendar');
    const exceptionType = document.getElementById('exception-type').value;
    
    if (!exceptionType || exceptionType === '') {
        showToast('Selecciona primero el tipo de evento', 'warning');
        return;
    }
    
    popup.classList.remove('hidden');
    
    const rect = event.target.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const requiredHeight = 500;
    
    popup.style.position = 'absolute';
    
    if (spaceBelow < requiredHeight && spaceAbove > spaceBelow) {
        popup.style.bottom = '100%';
        popup.style.top = 'auto';
        popup.style.marginBottom = '8px';
        popup.style.marginTop = '0';
    } else {
        popup.style.top = '100%';
        popup.style.bottom = 'auto';
        popup.style.marginTop = '8px';
        popup.style.marginBottom = '0';
    }
    
    renderMiniCalendar(miniCalendar, exceptionType);
}

function closeDatePicker() {
    document.getElementById('date-picker-popup').classList.add('hidden');
}

function renderMiniCalendar(container, exceptionType) {
    if (!container) return;
    
    const today = new Date();
    const currentMonth = today.getMonth();
    const currentYear = today.getFullYear();
    
    container.innerHTML = '';
    container.dataset.month = currentMonth;
    container.dataset.year = currentYear;
    
    const nav = document.createElement('div');
    nav.className = 'flex justify-between items-center mb-3';
    
    const prevBtn = document.createElement('button');
    prevBtn.type = 'button';
    prevBtn.className = 'text-gray-600 hover:text-gray-900';
    prevBtn.innerHTML = '<i class="fas fa-chevron-left"></i>';
    prevBtn.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        changeMiniMonth(-1, e);
        return false;
    };
    
    const monthLabel = document.createElement('span');
    monthLabel.className = 'font-semibold text-sm';
    monthLabel.id = 'mini-month-year';
    monthLabel.textContent = `${getMonthName(currentMonth)} ${currentYear}`;
    
    const nextBtn = document.createElement('button');
    nextBtn.type = 'button';
    nextBtn.className = 'text-gray-600 hover:text-gray-900';
    nextBtn.innerHTML = '<i class="fas fa-chevron-right"></i>';
    nextBtn.onclick = function(e) {
        e.preventDefault();
        e.stopPropagation();
        changeMiniMonth(1, e);
        return false;
    };
    
    nav.appendChild(prevBtn);
    nav.appendChild(monthLabel);
    nav.appendChild(nextBtn);
    container.appendChild(nav);
    
    const gridContainer = document.createElement('div');
    gridContainer.style.minHeight = '350px';
    container.appendChild(gridContainer);
    
    const grid = document.createElement('div');
    grid.className = 'grid grid-cols-7 gap-1';
    grid.id = 'mini-calendar-grid';
    gridContainer.appendChild(grid);
    
    renderMiniCalendarDays(currentMonth, currentYear, exceptionType);
}

function renderMiniCalendarDays(month, year, exceptionType) {
    const grid = document.getElementById('mini-calendar-grid');
    if (!grid) return;
    
    grid.innerHTML = '';
    
    const weekdays = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
    weekdays.forEach(day => {
        const header = document.createElement('div');
        header.className = 'text-xs font-bold text-gray-500 text-center';
        header.textContent = day;
        grid.appendChild(header);
    });
    
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    
    const adjustedFirstDay = firstDay === 0 ? 6 : firstDay - 1;
    
    for (let i = 0; i < adjustedFirstDay; i++) {
        grid.appendChild(document.createElement('div'));
    }
    
    for (let day = 1; day <= daysInMonth; day++) {
        const dayEl = document.createElement('div');
        const date = new Date(year, month, day);
        const dateStr = date.toISOString().split('T')[0];
        const dayOfWeek = date.getDay() === 0 ? 6 : date.getDay() - 1;
        const template = horarioTemplates[dayOfWeek];
        
        dayEl.className = 'mini-calendar-day';
        dayEl.textContent = day;
        
        const existingException = horarioExceptions.find(exc => exc.date === dateStr);
        
        let isEligible = false;
        
        if (exceptionType === 'vacation') {
            isEligible = true;
        } else if (exceptionType === 'closed') {
            isEligible = template && template.is_active;
        } else if (exceptionType === 'special-hours') {
            isEligible = template && template.is_active;
        } else if (exceptionType === 'special-open') {
            isEligible = !template || !template.is_active;
        }
        
        if (isEligible) {
            dayEl.classList.add('eligible');
            dayEl.onclick = () => selectDateFromMiniCalendar(dateStr);
        } else {
            dayEl.classList.add('not-eligible');
        }
        
        if (existingException) {
            dayEl.style.position = 'relative';
            const indicator = document.createElement('div');
            indicator.style.position = 'absolute';
            indicator.style.top = '2px';
            indicator.style.right = '2px';
            indicator.style.width = '6px';
            indicator.style.height = '6px';
            indicator.style.borderRadius = '50%';
            
            if (existingException.is_vacation) {
                indicator.style.background = '#8b5cf6';
            } else if (!existingException.is_working_day) {
                indicator.style.background = '#ef4444';
            } else if (existingException.is_special_open) {
                indicator.style.background = '#10b981';
            } else {
                indicator.style.background = '#fbbf24';
            }
            
            dayEl.appendChild(indicator);
        }
        
        grid.appendChild(dayEl);
    }
}

function selectDateFromMiniCalendar(dateStr) {
    document.getElementById('exception-date').value = dateStr;
    document.getElementById('date-picker-popup').classList.add('hidden');
    selectedDateForException = dateStr;
}

function changeMiniMonth(direction) {
    const miniCalendar = document.getElementById('mini-calendar');
    if (!miniCalendar) return;
    
    let month = parseInt(miniCalendar.dataset.month || new Date().getMonth());
    let year = parseInt(miniCalendar.dataset.year || new Date().getFullYear());
    
    month += direction;
    if (month < 0) {
        month = 11;
        year--;
    } else if (month > 11) {
        month = 0;
        year++;
    }
    
    miniCalendar.dataset.month = month;
    miniCalendar.dataset.year = year;
    
    const monthName = getMonthName(month);
    const monthYearEl = document.getElementById('mini-month-year');
    if (monthYearEl) {
        monthYearEl.textContent = `${monthName} ${year}`;
    }
    
    const exceptionType = document.getElementById('exception-type').value;
    renderMiniCalendarDays(month, year, exceptionType);
}

// ==================== VACATION AND DELETE FUNCTIONS ====================
// [Keeping all existing vacation and delete functions as they are]
function openVacationCalendar(event) {
    event.stopPropagation();
    
    const popup = document.getElementById('vacation-calendar-popup');
    const calendar = document.getElementById('vacation-calendar');
    
    const titleEl = document.getElementById('vacation-calendar-title');
    const confirmBtn = document.getElementById('vacation-confirm-btn');
    
    if (!vacationStartDate) {
        if (titleEl) titleEl.textContent = 'Selecciona fecha de inicio';
        if (confirmBtn) confirmBtn.disabled = true;
    } else if (!vacationEndDate) {
        if (titleEl) titleEl.textContent = 'Selecciona fecha de fin';
        if (confirmBtn) confirmBtn.disabled = true;
    } else {
        if (titleEl) titleEl.textContent = 'Período seleccionado';
        if (confirmBtn) confirmBtn.disabled = false;
    }
    
    popup.classList.remove('hidden');
    
    const rect = event.target.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const requiredHeight = 500;
    
    popup.style.position = 'absolute';
    
    if (spaceBelow < requiredHeight && spaceAbove > spaceBelow) {
        popup.style.bottom = '100%';
        popup.style.top = 'auto';
        popup.style.marginBottom = '8px';
        popup.style.marginTop = '0';
    } else {
        popup.style.top = '100%';
        popup.style.bottom = 'auto';
        popup.style.marginTop = '8px';
        popup.style.marginBottom = '0';
    }
    
    renderVacationRangeCalendar(calendar);
}

function closeVacationCalendar() {
    if ((vacationStartDate && vacationEndDate) || (!vacationStartDate && !vacationEndDate)) {
        document.getElementById('vacation-calendar-popup').classList.add('hidden');
    } else {
        showToast('Por favor completa la selección de fechas o usa el botón Limpiar', 'warning');
    }
}

function renderVacationRangeCalendar(container) {
    if (!container) return;
    
    const today = new Date();
    let currentMonth = parseInt(container.dataset.month || today.getMonth());
    let currentYear = parseInt(container.dataset.year || today.getFullYear());
    
    if (!container.dataset.month) {
        if (vacationStartDate) {
            const startDate = new Date(vacationStartDate);
            currentMonth = startDate.getMonth();
            currentYear = startDate.getFullYear();
        }
        container.dataset.month = currentMonth;
        container.dataset.year = currentYear;
    }
    
    container.innerHTML = '';
    
    const nav = document.createElement('div');
    nav.className = 'flex justify-between items-center mb-3';
    nav.innerHTML = `
        <button type="button" onclick="event.preventDefault(); event.stopPropagation(); changeVacationCalendarMonth(-1);" class="text-gray-600 hover:text-gray-900">
            <i class="fas fa-chevron-left"></i>
        </button>
        <span class="font-semibold text-sm" id="vacation-month-year">${getMonthName(currentMonth)} ${currentYear}</span>
        <button type="button" onclick="event.preventDefault(); event.stopPropagation(); changeVacationCalendarMonth(1);" class="text-gray-600 hover:text-gray-900">
            <i class="fas fa-chevron-right"></i>
        </button>
    `;
    container.appendChild(nav);
    
    const gridContainer = document.createElement('div');
    gridContainer.style.minHeight = '350px';
    container.appendChild(gridContainer);
    
    const grid = document.createElement('div');
    grid.className = 'grid grid-cols-7 gap-1';
    gridContainer.appendChild(grid);
    
    const weekdays = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
    weekdays.forEach(day => {
        const header = document.createElement('div');
        header.className = 'text-xs font-bold text-gray-500 text-center';
        header.textContent = day;
        grid.appendChild(header);
    });
    
    const firstDay = new Date(currentYear, currentMonth, 1).getDay();
    const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
    
    const adjustedFirstDay = firstDay === 0 ? 6 : firstDay - 1;
    
    for (let i = 0; i < adjustedFirstDay; i++) {
        grid.appendChild(document.createElement('div'));
    }
    
    for (let day = 1; day <= daysInMonth; day++) {
        const dayEl = document.createElement('div');
        const date = new Date(currentYear, currentMonth, day);
        const dateStr = date.toISOString().split('T')[0];
        
        dayEl.className = 'mini-calendar-day neutral';
        dayEl.textContent = day;
        dayEl.dataset.date = dateStr;
        
        const hasException = horarioExceptions.some(exc => exc.date === dateStr);
        
        if (hasException) {
            dayEl.style.position = 'relative';
            const indicator = document.createElement('div');
            indicator.style.position = 'absolute';
            indicator.style.top = '2px';
            indicator.style.right = '2px';
            indicator.style.width = '6px';
            indicator.style.height = '6px';
            indicator.style.borderRadius = '50%';
            indicator.style.background = '#ef4444';
            indicator.title = 'Tiene evento programado';
            dayEl.appendChild(indicator);
        }
        
        if (vacationStartDate === dateStr) {
            dayEl.classList.add('vacation-start-selected');
        } else if (vacationEndDate === dateStr) {
            dayEl.classList.add('vacation-end-selected');
        } else if (vacationStartDate && vacationEndDate) {
            const start = new Date(vacationStartDate);
            const end = new Date(vacationEndDate);
            if (date > start && date < end) {
                dayEl.classList.add('vacation-range-preview');
            }
        }
        
        dayEl.onclick = (e) => {
            e.stopPropagation();
            selectVacationRangeDate(dateStr);
        };
        
        grid.appendChild(dayEl);
    }
}

function selectVacationRangeDate(dateStr) {
    const titleEl = document.getElementById('vacation-calendar-title');
    const confirmBtn = document.getElementById('vacation-confirm-btn');
    const datesInput = document.getElementById('vacation-dates');
    
    if (!vacationStartDate) {
        vacationStartDate = dateStr;
        vacationEndDate = null;
        
        if (titleEl) titleEl.textContent = 'Selecciona fecha de fin';
        if (confirmBtn) confirmBtn.disabled = true;
        
        datesInput.value = formatDateForDisplay(dateStr) + ' - ...';
    } else if (!vacationEndDate) {
        if (dateStr < vacationStartDate) {
            vacationEndDate = vacationStartDate;
            vacationStartDate = dateStr;
        } else if (dateStr === vacationStartDate) {
            vacationEndDate = dateStr;
        } else {
            vacationEndDate = dateStr;
        }
        
        if (titleEl) titleEl.textContent = 'Período seleccionado';
        if (confirmBtn) confirmBtn.disabled = false;
        
        datesInput.value = formatDateForDisplay(vacationStartDate) + ' - ' + formatDateForDisplay(vacationEndDate);
    } else {
        vacationStartDate = dateStr;
        vacationEndDate = null;
        
        if (titleEl) titleEl.textContent = 'Selecciona fecha de fin';
        if (confirmBtn) confirmBtn.disabled = true;
        
        datesInput.value = formatDateForDisplay(dateStr) + ' - ...';
    }
    
    renderVacationRangeCalendar(document.getElementById('vacation-calendar'));
}

function clearVacationDates(event) {
    if (event) event.stopPropagation();
    
    vacationStartDate = null;
    vacationEndDate = null;
    
    document.getElementById('vacation-dates').value = '';
    document.getElementById('vacation-calendar-title').textContent = 'Selecciona fecha de inicio';
    document.getElementById('vacation-confirm-btn').disabled = true;
    
    renderVacationRangeCalendar(document.getElementById('vacation-calendar'));
    
    return false;
}

function confirmVacationDates(event) {
    if (event) event.stopPropagation();
    
    if (!vacationStartDate || !vacationEndDate) {
        showToast('Selecciona las fechas de inicio y fin', 'warning');
        return false;
    }
    
    document.getElementById('vacation-calendar-popup').classList.add('hidden');
    
    showToast('Fechas de vacaciones seleccionadas', 'success');
    
    return false;
}

function changeVacationCalendarMonth(direction) {
    const calendar = document.getElementById('vacation-calendar');
    if (!calendar) return;
    
    let month = parseInt(calendar.dataset.month);
    let year = parseInt(calendar.dataset.year);
    
    month += direction;
    if (month < 0) {
        month = 11;
        year--;
    } else if (month > 11) {
        month = 0;
        year++;
    }
    
    calendar.dataset.month = month;
    calendar.dataset.year = year;
    
    renderVacationRangeCalendar(calendar);
}

async function addVacationRange() {
    if (!vacationStartDate || !vacationEndDate) {
        showToast('Selecciona las fechas de inicio y fin en el calendario', 'warning');
        return;
    }
    
    const reason = document.getElementById('exception-reason').value || 'Vacaciones';
    
    showLoading();
    
    try {
        const vacationGroupId = generateUUID();
        const start = new Date(vacationStartDate);
        const end = new Date(vacationEndDate);
        const createdExceptions = [];
        
        for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
            const dateStr = d.toISOString().split('T')[0];
            
            const exceptionData = {
                date: dateStr,
                is_working_day: false,
                is_vacation: true,
                vacation_group_id: vacationGroupId,
                reason: reason
            };
            
            const response = await api.makeRequest('/horarios/exceptions', {
                method: 'POST',
                body: JSON.stringify(exceptionData)
            });
            
            createdExceptions.push({
                ...exceptionData,
                id: response.exception_id
            });
        }
        
        horarioExceptions = horarioExceptions.concat(createdExceptions);
        
        updateExceptionsList();
        renderCalendar(currentCalendarMonth, currentCalendarYear);
        
        // Clear form
        document.getElementById('exception-reason').value = '';
        document.getElementById('exception-type').value = '';
        document.getElementById('exception-type-description').classList.add('hidden');
        document.getElementById('vacation-range-fields').classList.add('hidden');
        document.getElementById('vacation-dates').value = '';
        vacationStartDate = null;
        vacationEndDate = null;
        
        showToast('Período de vacaciones agregado exitosamente', 'success');
        
    } catch (error) {
        console.error('Error creating vacation period:', error);
        showToast('Error al crear período de vacaciones', 'error');
    } finally {
        hideLoading();
    }
}

function showDeleteConfirmation(exceptionId) {
    pendingDeleteId = exceptionId;
    const modal = document.getElementById('confirm-modal');
    if (modal) {
        modal.classList.add('show');
    }
}

async function confirmDelete() {
    if (!pendingDeleteId) return;
    
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.remove('show');
    
    showLoading();
    
    try {
        // Verificar si es un grupo de vacaciones (UUID format)
        const isVacationGroup = pendingDeleteId.match(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
        
        if (isVacationGroup) {
            // Es un grupo de vacaciones, eliminar todas las excepciones del grupo
            const vacationExceptions = horarioExceptions.filter(exc => 
                exc.vacation_group_id === pendingDeleteId
            );
            
            // Eliminar cada excepción del grupo
            for (const exc of vacationExceptions) {
                await api.makeRequest(`/horarios/exceptions/${exc.id}`, {
                    method: 'DELETE'
                });
            }
            
            // Actualizar el array local
            horarioExceptions = horarioExceptions.filter(exc => 
                exc.vacation_group_id !== pendingDeleteId
            );
        } else {
            // Es una excepción individual
            await api.makeRequest(`/horarios/exceptions/${pendingDeleteId}`, {
                method: 'DELETE'
            });
            
            horarioExceptions = horarioExceptions.filter(exc => exc.id !== pendingDeleteId);
        }
        
        updateExceptionsList();
        renderCalendar(currentCalendarMonth, currentCalendarYear);
        
        showToast('Evento eliminado exitosamente', 'success');
        
    } catch (error) {
        console.error('Error deleting exception:', error);
        showToast('Error al eliminar el evento', 'error');
    } finally {
        hideLoading();
        pendingDeleteId = null;
    }
}

function cancelDelete() {
    pendingDeleteId = null;
    const modal = document.getElementById('confirm-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

async function removeVacationGroup(groupId) {
    pendingDeleteId = groupId;
    const modal = document.getElementById('confirm-modal');
    const message = document.getElementById('confirm-message');
    
    if (message) {
        message.textContent = '¿Estás seguro de eliminar todo el período de vacaciones?';
    }
    
    if (modal) {
        modal.classList.add('show');
    }
}

// Exception break management
function renderExceptionBreakBlocks(breaks) {
    const container = document.getElementById('exception-break-blocks-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    const opensAt = document.getElementById('exception-opens').value;
    const closesAt = document.getElementById('exception-closes').value;
    
    breaks.forEach((block, index) => {
        const isOutOfRange = opensAt && closesAt && (block.start < opensAt || block.end > closesAt);
        
        const breakDiv = document.createElement('div');
        breakDiv.className = 'flex items-center gap-3';
        breakDiv.innerHTML = `
            <input type="time" value="${block.start}" class="input-field ${isOutOfRange ? 'error' : ''}" data-exception-break-index="${index}" data-field="start" onchange="validateExceptionBreakTime(${index})">
            <span class="text-gray-400">—</span>
            <input type="time" value="${block.end}" class="input-field ${isOutOfRange ? 'error' : ''}" data-exception-break-index="${index}" data-field="end" onchange="validateExceptionBreakTime(${index})">
            <select class="input-field" data-exception-break-index="${index}" data-field="type" style="min-width: 150px;">
                <option value="lunch" ${block.type === 'lunch' ? 'selected' : ''}>Comida</option>
                <option value="break" ${block.type === 'break' ? 'selected' : ''}>Descanso</option>
                <option value="administrative" ${block.type === 'administrative' ? 'selected' : ''}>Administrativo</option>
            </select>
            <button class="icon-btn" onclick="removeExceptionBreak(${index})">
                <i class="fas fa-trash"></i>
            </button>
        `;
        container.appendChild(breakDiv);
        
        if (isOutOfRange) {
            showToast('Ajusta el descanso al horario especial configurado', 'warning');
        }
    });
}

function validateExceptionTime() {
    const opensAt = document.getElementById('exception-opens').value;
    const closesAt = document.getElementById('exception-closes').value;
    
    if (opensAt && closesAt) {
        renderExceptionBreakBlocks(currentExceptionBreaks);
    }
}

function validateExceptionBreakTime(index) {
    const opensAt = document.getElementById('exception-opens').value;
    const closesAt = document.getElementById('exception-closes').value;
    
    if (!opensAt || !closesAt) return;
    
    const breakStart = document.querySelector(`[data-exception-break-index="${index}"][data-field="start"]`).value;
    const breakEnd = document.querySelector(`[data-exception-break-index="${index}"][data-field="end"]`).value;
    
    currentExceptionBreaks[index] = {
        ...currentExceptionBreaks[index],
        start: breakStart,
        end: breakEnd,
        type: document.querySelector(`[data-exception-break-index="${index}"][data-field="type"]`).value
    };
    
    const errors = [];
    
    if (breakStart < opensAt || breakEnd > closesAt) {
        errors.push(`El descanso está fuera del horario especial`);
    }
    
    if (breakStart >= breakEnd) {
        errors.push(`El descanso tiene horario inválido`);
    }
    
    for (let i = 0; i < currentExceptionBreaks.length; i++) {
        if (i !== index) {
            const otherBreak = currentExceptionBreaks[i];
            if (isTimeOverlap(breakStart, breakEnd, otherBreak.start, otherBreak.end)) {
                errors.push(`Los descansos se superponen`);
            }
        }
    }
    
    if (errors.length > 0) {
        document.querySelector(`[data-exception-break-index="${index}"][data-field="start"]`).classList.add('error');
        document.querySelector(`[data-exception-break-index="${index}"][data-field="end"]`).classList.add('error');
        showToast(errors[0], 'error');
    } else {
        document.querySelector(`[data-exception-break-index="${index}"][data-field="start"]`).classList.remove('error');
        document.querySelector(`[data-exception-break-index="${index}"][data-field="end"]`).classList.remove('error');
    }
}

function addExceptionBreak() {
    const opensAt = document.getElementById('exception-opens').value;
    const closesAt = document.getElementById('exception-closes').value;
    
    if (!opensAt || !closesAt) {
        showToast('Define primero el horario de apertura y cierre', 'warning');
        return;
    }
    
    let defaultStart = '14:00';
    let defaultEnd = '15:00';
    
    const openTime = parseTimeString(opensAt);
    const closeTime = parseTimeString(closesAt);
    
    if (parseTimeString(defaultStart) < openTime) {
        defaultStart = formatTimeFromMinutes(openTime + 60);
    }
    
    if (parseTimeString(defaultEnd) > closeTime) {
        defaultEnd = formatTimeFromMinutes(closeTime - 30);
    }
    
    if (parseTimeString(defaultStart) >= parseTimeString(defaultEnd)) {
        const midTime = openTime + Math.floor((closeTime - openTime) / 2);
        defaultStart = formatTimeFromMinutes(midTime - 30);
        defaultEnd = formatTimeFromMinutes(midTime + 30);
    }
    
    if (defaultStart < opensAt || defaultEnd > closesAt) {
        showToast('No hay espacio suficiente para agregar un descanso', 'error');
        return;
    }
    
    for (const existingBreak of currentExceptionBreaks) {
        if (isTimeOverlap(defaultStart, defaultEnd, existingBreak.start, existingBreak.end)) {
            const existingEnd = parseTimeString(existingBreak.end);
            const potentialStart = existingEnd + 30;
            
            if (potentialStart + 60 <= closeTime) {
                defaultStart = formatTimeFromMinutes(potentialStart);
                defaultEnd = formatTimeFromMinutes(potentialStart + 60);
            } else {
                showToast('No hay espacio disponible para otro descanso', 'warning');
                return;
            }
        }
    }
    
    currentExceptionBreaks.push({
        start: defaultStart,
        end: defaultEnd,
        type: 'lunch'
    });
    
    renderExceptionBreakBlocks(currentExceptionBreaks);
}

function removeExceptionBreak(index) {
    currentExceptionBreaks.splice(index, 1);
    renderExceptionBreakBlocks(currentExceptionBreaks);
}

// ==================== UTILITY FUNCTIONS ====================
function formatTime(timeStr) {
    if (!timeStr) return '';
    const [hours, minutes] = timeStr.split(':');
    const h = parseInt(hours);
    const period = h >= 12 ? 'PM' : 'AM';
    const displayHours = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    return `${displayHours}:${minutes} ${period}`;
}

function formatDateForDisplay(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('es-MX', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });
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

function getMonthName(monthIndex) {
    const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                       'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    return monthNames[monthIndex];
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

function parseTimeString(timeStr) {
    if (!timeStr) return 0;
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

function formatTimeFromMinutes(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}`;
}

function isTimeOverlap(start1, end1, start2, end2) {
    return (start1 < end2 && end1 > start2);
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function clearBreakError(index) {
    const errorDiv = document.getElementById('breaks-error');
    errorDiv.classList.remove('show');
    
    document.querySelector(`[data-break-index="${index}"][data-field="start"]`).classList.remove('error');
    document.querySelector(`[data-break-index="${index}"][data-field="end"]`).classList.remove('error');
}

function clearModalErrors() {
    document.getElementById('schedule-error').classList.remove('show');
    document.getElementById('breaks-error').classList.remove('show');
    
    document.querySelectorAll('.input-field.error').forEach(field => {
        field.classList.remove('error');
    });
}

function closeModal() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
    document.body.style.overflow = '';
    currentBreakBlocks = [];
    selectedConsultorioForDay = null;
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

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const messageEl = document.getElementById('toast-message');
    const iconEl = toast?.querySelector('i');
    
    if (!toast || !messageEl) return;
    
    messageEl.textContent = message;
    
    if (iconEl) {
        switch(type) {
            case 'success':
                iconEl.className = 'fas fa-check-circle text-emerald-400';
                break;
            case 'error':
                iconEl.className = 'fas fa-times-circle text-red-400';
                break;
            case 'warning':
                iconEl.className = 'fas fa-exclamation-triangle text-amber-400';
                break;
            default:
                iconEl.className = 'fas fa-info-circle text-blue-400';
        }
    }
    
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// Export functions for global use
window.toggleDay = toggleDay;
window.customizeDay = customizeDay;
window.copyDay = copyDay;
window.switchTab = switchTab;
window.addException = addException;
window.removeException = showDeleteConfirmation;
window.confirmDelete = confirmDelete;
window.cancelDelete = cancelDelete;
window.removeVacationGroup = removeVacationGroup;
window.toggleExceptionFields = toggleExceptionFields;
window.addBreak = addBreak;
window.removeBreak = removeBreak;
window.addExceptionBreak = addExceptionBreak;
window.removeExceptionBreak = removeExceptionBreak;
window.saveDay = saveDay;
window.closeModal = closeModal;
window.toggleSidebar = toggleSidebar;
window.previousMonth = previousMonth;
window.nextMonth = nextMonth;
window.validateBreakTime = validateBreakTime;
window.validateExceptionBreakTime = validateExceptionBreakTime;
window.validateBreaksOnScheduleChange = validateBreaksOnScheduleChange;
window.validateExceptionTime = validateExceptionTime;
window.openDatePicker = openDatePicker;
window.closeDatePicker = closeDatePicker;
window.selectDateFromMiniCalendar = selectDateFromMiniCalendar;
window.changeMiniMonth = changeMiniMonth;
window.openVacationCalendar = openVacationCalendar;
window.closeVacationCalendar = closeVacationCalendar;
window.renderVacationRangeCalendar = renderVacationRangeCalendar;
window.selectVacationRangeDate = selectVacationRangeDate;
window.clearVacationDates = clearVacationDates;
window.confirmVacationDates = confirmVacationDates;
window.changeVacationCalendarMonth = changeVacationCalendarMonth;
window.connectGoogleCalendar = connectGoogleCalendar;
window.connectAppleCalendar = connectAppleCalendar;
window.disconnectCalendar = disconnectCalendar;
window.changeCalendarAccount = changeCalendarAccount;
window.syncCalendar = syncCalendar;
window.resolveConflict = resolveConflict;
window.resolveGroupConflict = resolveGroupConflict;
window.applyConflictResolutions = applyConflictResolutions;
window.applyRecurrentClassifications = applyRecurrentClassifications;
window.closeConflictModal = closeConflictModal;
window.closeRecurrentModal = closeRecurrentModal;
window.selectConsultorioForDay = selectConsultorioForDay;
window.selectConsultorioForException = selectConsultorioForException;