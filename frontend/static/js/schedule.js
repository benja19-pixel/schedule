// ESTE ARCHIVO SE DEBE RENOMBRAR A: schedule-old.js (como respaldo)
// El nuevo archivo configurar-horario.js lo reemplaza con funcionalidad real

// Schedule Management JavaScript for MediConnect

// Global state
let currentMode = 'quick';
let currentWeekStart = null;
let scheduleTemplates = {};
let scheduleExceptions = [];
let selectedDays = new Set();
let selectedPreset = null;
let isDragging = false;
let draggedBlock = null;

// Days of week mapping
const daysOfWeek = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];
const daysOfWeekShort = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication
    if (!isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    // Initialize current week
    currentWeekStart = getMonday(new Date());
    
    // Load existing schedule data
    await loadScheduleData();
    
    // Initialize UI
    initializeUI();
    updateStatistics();
});

// Initialize UI components
function initializeUI() {
    // Set up time slots for advanced view
    generateTimeSlots();
    
    // Update week display
    updateWeekDisplay();
    
    // Initialize day toggles
    updateDayToggles();
    
    // Set up drag and drop
    setupDragAndDrop();
}

// Switch between quick and advanced modes
function switchMode(mode) {
    currentMode = mode;
    
    // Update button states
    document.querySelectorAll('.mode-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.getElementById(`${mode}-mode-btn`).classList.add('active');
    
    // Show/hide content
    document.getElementById('quick-mode').classList.toggle('hidden', mode !== 'quick');
    document.getElementById('advanced-mode').classList.toggle('hidden', mode !== 'advanced');
    
    // Refresh advanced view if switching to it
    if (mode === 'advanced') {
        renderWeeklySchedule();
    }
}

// Load schedule data from API
async function loadScheduleData() {
    try {
        // Load templates
        const templatesResponse = await api.makeRequest('/schedule/templates');
        if (templatesResponse.templates) {
            templatesResponse.templates.forEach(template => {
                scheduleTemplates[template.day_of_week] = template;
            });
        }
        
        // Load exceptions for current month
        const now = new Date();
        const startDate = new Date(now.getFullYear(), now.getMonth(), 1);
        const endDate = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        
        const exceptionsResponse = await api.makeRequest(
            `/schedule/exceptions?start_date=${startDate.toISOString().split('T')[0]}&end_date=${endDate.toISOString().split('T')[0]}`
        );
        
        if (exceptionsResponse.exceptions) {
            scheduleExceptions = exceptionsResponse.exceptions;
        }
        
        // Update UI with loaded data
        updateDayToggles();
        
    } catch (error) {
        console.error('Error loading schedule data:', error);
        showNotification('Error al cargar horarios', 'error');
    }
}

// Select a preset template
function selectPreset(preset) {
    // Remove selected class from all cards
    document.querySelectorAll('.setup-card').forEach(card => {
        card.classList.remove('selected');
    });
    
    // Add selected class to clicked card
    document.querySelector(`[data-preset="${preset}"]`).classList.add('selected');
    
    selectedPreset = preset;
    
    // Update day selection based on preset
    selectedDays.clear();
    
    switch (preset) {
        case 'morning':
        case 'afternoon':
        case 'full_day':
            // Monday to Friday
            for (let i = 0; i < 5; i++) {
                selectedDays.add(i);
            }
            break;
        case 'weekend':
            // Saturday only
            selectedDays.add(5);
            break;
    }
    
    // Update day toggles
    updateDayToggles();
    
    // Set time inputs based on preset
    switch (preset) {
        case 'morning':
            document.getElementById('opens-at').value = '08:00';
            document.getElementById('closes-at').value = '14:00';
            document.getElementById('lunch-toggle').classList.remove('active');
            document.getElementById('break-time-inputs').classList.add('hidden');
            break;
        case 'afternoon':
            document.getElementById('opens-at').value = '15:00';
            document.getElementById('closes-at').value = '20:00';
            document.getElementById('lunch-toggle').classList.remove('active');
            document.getElementById('break-time-inputs').classList.add('hidden');
            break;
        case 'full_day':
            document.getElementById('opens-at').value = '09:00';
            document.getElementById('closes-at').value = '19:00';
            document.getElementById('lunch-toggle').classList.add('active');
            document.getElementById('break-time-inputs').classList.remove('hidden');
            document.getElementById('lunch-start').value = '14:00';
            document.getElementById('lunch-end').value = '15:00';
            break;
        case 'weekend':
            document.getElementById('opens-at').value = '09:00';
            document.getElementById('closes-at').value = '14:00';
            document.getElementById('lunch-toggle').classList.remove('active');
            document.getElementById('break-time-inputs').classList.add('hidden');
            break;
    }
}

// Toggle day selection
function toggleDay(dayIndex) {
    if (selectedDays.has(dayIndex)) {
        selectedDays.delete(dayIndex);
    } else {
        selectedDays.add(dayIndex);
    }
    
    updateDayToggles();
    
    // Clear preset selection when manually toggling days
    selectedPreset = null;
    document.querySelectorAll('.setup-card').forEach(card => {
        card.classList.remove('selected');
    });
}

// Update day toggle UI
function updateDayToggles() {
    document.querySelectorAll('.day-toggle').forEach((toggle, index) => {
        const dayIndex = parseInt(toggle.dataset.day);
        const template = scheduleTemplates[dayIndex];
        const isActive = template ? template.is_active : false;
        const isSelected = selectedDays.has(dayIndex);
        
        toggle.classList.toggle('active', isActive || isSelected);
        
        // Update hours display
        const hoursElement = toggle.querySelector('.day-hours');
        if (template && template.is_active && template.opens_at && template.closes_at) {
            hoursElement.textContent = `${template.opens_at} - ${template.closes_at}`;
        } else if (!isActive) {
            hoursElement.textContent = 'Cerrado';
        }
    });
}

// Toggle lunch break
function toggleBreak(toggle) {
    toggle.classList.toggle('active');
    document.getElementById('break-time-inputs').classList.toggle('hidden');
}

// Apply time to selected days
async function applyTimeToSelectedDays() {
    if (selectedDays.size === 0 && !selectedPreset) {
        showNotification('Por favor selecciona al menos un día', 'warning');
        return;
    }
    
    // If a preset is selected, apply it
    if (selectedPreset) {
        try {
            showLoading();
            await api.makeRequest(`/schedule/quick-setup/${selectedPreset}`, {
                method: 'POST'
            });
            
            await loadScheduleData();
            updateStatistics();
            hideLoading();
            showNotification('Horario aplicado exitosamente', 'success');
            
        } catch (error) {
            hideLoading();
            showNotification('Error al aplicar horario', 'error');
        }
        return;
    }
    
    // Otherwise, apply custom configuration
    const opensAt = document.getElementById('opens-at').value;
    const closesAt = document.getElementById('closes-at').value;
    const hasLunch = document.getElementById('lunch-toggle').classList.contains('active');
    const lunchStart = document.getElementById('lunch-start').value;
    const lunchEnd = document.getElementById('lunch-end').value;
    const defaultDuration = parseInt(document.getElementById('default-duration').value);
    const bufferTime = parseInt(document.getElementById('buffer-time').value);
    
    // Validate times
    if (!opensAt || !closesAt) {
        showNotification('Por favor ingresa horarios válidos', 'warning');
        return;
    }
    
    // Create time blocks
    const timeBlocks = [];
    
    if (hasLunch) {
        // Morning consultation block
        timeBlocks.push({
            start: opensAt,
            end: lunchStart,
            type: 'consultation'
        });
        
        // Lunch block
        timeBlocks.push({
            start: lunchStart,
            end: lunchEnd,
            type: 'lunch'
        });
        
        // Afternoon consultation block
        timeBlocks.push({
            start: lunchEnd,
            end: closesAt,
            type: 'consultation'
        });
    } else {
        // Single consultation block
        timeBlocks.push({
            start: opensAt,
            end: closesAt,
            type: 'consultation'
        });
    }
    
    // Prepare templates for selected days
    const templates = [];
    for (const dayIndex of selectedDays) {
        templates.push({
            day_of_week: dayIndex,
            is_active: true,
            opens_at: opensAt,
            closes_at: closesAt,
            default_duration: defaultDuration,
            buffer_time: bufferTime,
            time_blocks: timeBlocks
        });
    }
    
    try {
        showLoading();
        
        // Bulk update templates
        await api.makeRequest('/schedule/templates/bulk', {
            method: 'POST',
            body: JSON.stringify({ templates })
        });
        
        // Reload data
        await loadScheduleData();
        updateStatistics();
        
        hideLoading();
        showNotification('Horarios actualizados exitosamente', 'success');
        
        // Clear selection
        selectedDays.clear();
        updateDayToggles();
        
    } catch (error) {
        hideLoading();
        showNotification('Error al actualizar horarios', 'error');
    }
}

// Generate time slots for advanced view
function generateTimeSlots() {
    const calendar = document.getElementById('weekly-calendar');
    const startHour = 7;
    const endHour = 21;
    
    // Clear existing slots (keep headers)
    const headers = calendar.querySelectorAll('.calendar-header');
    calendar.innerHTML = '';
    headers.forEach(header => calendar.appendChild(header));
    
    // Generate time slots
    for (let hour = startHour; hour < endHour; hour++) {
        // Time label
        const timeLabel = document.createElement('div');
        timeLabel.className = 'time-label';
        timeLabel.textContent = `${hour.toString().padStart(2, '0')}:00`;
        calendar.appendChild(timeLabel);
        
        // Day slots
        for (let day = 0; day < 7; day++) {
            const slot = document.createElement('div');
            slot.className = 'time-slot';
            slot.dataset.day = day;
            slot.dataset.hour = hour;
            slot.dataset.time = `${hour.toString().padStart(2, '0')}:00`;
            
            // Add drop zone functionality
            slot.addEventListener('dragover', handleDragOver);
            slot.addEventListener('drop', handleDrop);
            slot.addEventListener('click', () => handleSlotClick(day, hour));
            
            calendar.appendChild(slot);
        }
    }
}

// Render weekly schedule with blocks
function renderWeeklySchedule() {
    // Clear existing blocks
    document.querySelectorAll('.time-block').forEach(block => block.remove());
    
    // Get the dates for current week
    const weekDates = [];
    for (let i = 0; i < 7; i++) {
        const date = new Date(currentWeekStart);
        date.setDate(date.getDate() + i);
        weekDates.push(date);
    }
    
    // Render blocks for each day
    weekDates.forEach((date, dayIndex) => {
        const dayOfWeek = date.getDay() === 0 ? 6 : date.getDay() - 1; // Adjust for Monday start
        const dateStr = date.toISOString().split('T')[0];
        
        // Check for exceptions first
        const exception = scheduleExceptions.find(exc => exc.date === dateStr);
        
        let timeBlocks = [];
        if (exception) {
            if (exception.is_working_day) {
                timeBlocks = exception.time_blocks || [];
            }
        } else {
            // Use template
            const template = scheduleTemplates[dayOfWeek];
            if (template && template.is_active) {
                timeBlocks = template.time_blocks || [];
            }
        }
        
        // Render blocks
        timeBlocks.forEach(block => {
            renderTimeBlock(dayIndex, block);
        });
    });
}

// Other functions remain the same...
// (All the rest of the functions from the original file)

// Update statistics
function updateStatistics() {
    let totalHours = 0;
    let workingDays = 0;
    let totalSlots = 0;
    
    // Calculate from templates
    Object.values(scheduleTemplates).forEach(template => {
        if (template.is_active && template.opens_at && template.closes_at) {
            workingDays++;
            
            const opens = new Date(`2000-01-01T${template.opens_at}`);
            const closes = new Date(`2000-01-01T${template.closes_at}`);
            const hours = (closes - opens) / (1000 * 60 * 60);
            
            totalHours += hours;
            
            // Calculate slots
            const duration = template.default_duration || 30;
            const daySlots = Math.floor((hours * 60) / duration);
            totalSlots += daySlots;
        }
    });
    
    // Update UI
    document.getElementById('total-hours').textContent = Math.round(totalHours);
    document.getElementById('available-slots').textContent = totalSlots;
    document.getElementById('working-days').textContent = workingDays;
    document.getElementById('avg-daily-hours').textContent = 
        workingDays > 0 ? Math.round(totalHours / workingDays) : 0;
}

// Save all changes
async function saveAllChanges() {
    // In the current implementation, changes are saved immediately
    // This function could be used to save any pending changes
    showNotification('Los cambios se guardan automáticamente', 'info');
}

// UI Helper functions
function showLoading() {
    document.getElementById('loading-overlay').classList.remove('hidden');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.add('hidden');
}

function closeSuccessModal() {
    document.getElementById('success-modal').classList.add('hidden');
}

// Get Monday of the week
function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(d.setDate(diff));
}

// Export functions for global use
window.switchMode = switchMode;
window.selectPreset = selectPreset;
window.toggleDay = toggleDay;
window.toggleBreak = toggleBreak;
window.applyTimeToSelectedDays = applyTimeToSelectedDays;
window.saveAllChanges = saveAllChanges;
window.closeSuccessModal = closeSuccessModal;