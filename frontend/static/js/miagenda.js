// Mi Agenda - Complete functional calendar and appointments management

// Global state
let currentView = 'day';
let currentDate = new Date();
let appointments = [];
let availableSlots = [];
let scheduleTemplates = {};
let scheduleExceptions = [];
let appointmentTypes = [];
let selectedAppointment = null;
let selectedDate = null;
let selectedTime = null;
let isLoading = false;

// View configurations
const viewConfig = {
    day: { days: 1, label: 'Día' },
    week: { days: 7, label: 'Semana' },
    month: { days: 30, label: 'Mes' }
};

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Mi Agenda...');
    
    // Check authentication
    if (typeof isAuthenticated === 'function' && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    // Initialize calendar
    await initializeCalendar();
    
    // Load initial data
    await loadCalendarData();
    
    // Set up event listeners
    setupEventListeners();
    
    // Start auto-refresh
    startAutoRefresh();
    
    // Update current date display
    updateCurrentDateDisplay();
});

// Initialize calendar
async function initializeCalendar() {
    console.log('Initializing calendar components...');
    
    // Set current date
    updateDateDisplay();
    
    // Initialize time slots for day view
    initializeDayViewSlots();
    
    // Initialize week view grid
    initializeWeekViewGrid();
    
    // Load appointment types
    await loadAppointmentTypes();
}

// Load appointment types
async function loadAppointmentTypes() {
    try {
        const response = await api.makeRequest('/schedule/appointment-types');
        if (response.appointment_types) {
            appointmentTypes = response.appointment_types;
            console.log('Appointment types loaded:', appointmentTypes);
        }
    } catch (error) {
        console.error('Error loading appointment types:', error);
    }
}

// Load calendar data
async function loadCalendarData() {
    if (isLoading) return;
    isLoading = true;
    
    console.log('Loading calendar data...');
    showLoading();
    
    try {
        // Determine date range based on view
        const dateRange = getDateRange();
        console.log('Date range:', dateRange);
        
        // Load appointments
        const appointmentsResponse = await api.makeRequest(
            `/schedule/appointments?start_date=${dateRange.start}&end_date=${dateRange.end}`
        );
        
        if (appointmentsResponse.appointments) {
            appointments = appointmentsResponse.appointments;
            console.log(`Loaded ${appointments.length} appointments`);
        }
        
        // Load schedule templates for availability
        const templatesResponse = await api.makeRequest('/schedule/templates');
        if (templatesResponse.templates) {
            scheduleTemplates = {};
            templatesResponse.templates.forEach(template => {
                scheduleTemplates[template.day_of_week] = template;
            });
            console.log('Templates loaded:', scheduleTemplates);
        }
        
        // Load exceptions
        const exceptionsResponse = await api.makeRequest(
            `/schedule/exceptions?start_date=${dateRange.start}&end_date=${dateRange.end}`
        );
        
        if (exceptionsResponse.exceptions) {
            scheduleExceptions = exceptionsResponse.exceptions;
            console.log('Exceptions loaded:', scheduleExceptions);
        }
        
        // Load availability for current date
        if (currentView === 'day') {
            await loadDayAvailability(currentDate);
        }
        
        // Update UI
        renderView();
        updateStatistics();
        updateUpcomingAppointments();
        updateNotifications();
        
    } catch (error) {
        console.error('Error loading calendar data:', error);
        showToast('Error al cargar los datos del calendario', 'error');
    } finally {
        hideLoading();
        isLoading = false;
    }
}

// Load availability for a specific day
async function loadDayAvailability(date) {
    try {
        const dateStr = date.toISOString().split('T')[0];
        const response = await api.makeRequest(`/schedule/availability/${dateStr}`);
        
        if (response.available_slots) {
            availableSlots = response.available_slots;
            console.log(`${availableSlots.length} slots available for ${dateStr}`);
        }
    } catch (error) {
        console.error('Error loading availability:', error);
    }
}

// Get date range for current view
function getDateRange() {
    let start, end;
    
    switch (currentView) {
        case 'day':
            start = new Date(currentDate);
            end = new Date(currentDate);
            break;
            
        case 'week':
            start = getMonday(currentDate);
            end = new Date(start);
            end.setDate(end.getDate() + 6);
            break;
            
        case 'month':
            start = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
            end = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);
            break;
    }
    
    return {
        start: start.toISOString().split('T')[0],
        end: end.toISOString().split('T')[0]
    };
}

// Switch view (day/week/month)
function switchView(view, button) {
    console.log('Switching to view:', view);
    currentView = view;
    
    // Update buttons
    document.querySelectorAll('.view-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    button.classList.add('active');
    
    // Hide all views
    document.getElementById('day-view').classList.add('hidden');
    document.getElementById('week-view').classList.add('hidden');
    document.getElementById('month-view').classList.add('hidden');
    
    // Show selected view
    document.getElementById(`${view}-view`).classList.remove('hidden');
    
    // Update date display
    updateDateDisplay();
    
    // Reload data and render
    loadCalendarData();
}

// Navigate to previous period
function previousPeriod() {
    switch (currentView) {
        case 'day':
            currentDate.setDate(currentDate.getDate() - 1);
            break;
        case 'week':
            currentDate.setDate(currentDate.getDate() - 7);
            break;
        case 'month':
            currentDate.setMonth(currentDate.getMonth() - 1);
            break;
    }
    
    updateDateDisplay();
    loadCalendarData();
}

// Navigate to next period
function nextPeriod() {
    switch (currentView) {
        case 'day':
            currentDate.setDate(currentDate.getDate() + 1);
            break;
        case 'week':
            currentDate.setDate(currentDate.getDate() + 7);
            break;
        case 'month':
            currentDate.setMonth(currentDate.getMonth() + 1);
            break;
    }
    
    updateDateDisplay();
    loadCalendarData();
}

// Go to today
function goToToday() {
    currentDate = new Date();
    updateDateDisplay();
    loadCalendarData();
}

// Update date display
function updateDateDisplay() {
    const displayEl = document.getElementById('current-date-display');
    const yearEl = document.getElementById('year-selector');
    const todayBtn = document.getElementById('today-button');
    
    if (!displayEl) return;
    
    const options = {
        day: { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' },
        week: { year: 'numeric', month: 'long', day: 'numeric' },
        month: { year: 'numeric', month: 'long' }
    };
    
    let displayText = '';
    
    switch (currentView) {
        case 'day':
            displayText = currentDate.toLocaleDateString('es-MX', options.day);
            if (yearEl) yearEl.textContent = currentDate.getFullYear();
            if (todayBtn) todayBtn.textContent = `Hoy (${getDayName(new Date()).slice(0, 3).toLowerCase()} ${new Date().getDate()})`;
            break;
            
        case 'week':
            const weekStart = getMonday(currentDate);
            const weekEnd = new Date(weekStart);
            weekEnd.setDate(weekEnd.getDate() + 6);
            
            displayText = `${weekStart.toLocaleDateString('es-MX', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('es-MX', options.week)}`;
            if (yearEl) yearEl.textContent = currentDate.getFullYear();
            if (todayBtn) todayBtn.textContent = 'Esta semana';
            break;
            
        case 'month':
            displayText = currentDate.toLocaleDateString('es-MX', options.month);
            if (yearEl) yearEl.textContent = currentDate.getFullYear();
            if (todayBtn) todayBtn.textContent = currentDate.toLocaleDateString('es-MX', { month: 'long' });
            break;
    }
    
    displayEl.textContent = displayText;
}

// Update current date in header
function updateCurrentDateDisplay() {
    const today = new Date();
    const dayNames = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
    const dayName = dayNames[today.getDay()];
    const dayNumber = today.getDate();
    
    const todayBtn = document.getElementById('today-button');
    if (todayBtn) {
        todayBtn.textContent = `Hoy (${dayName} ${dayNumber})`;
    }
}

// Render current view
function renderView() {
    console.log('Rendering view:', currentView);
    
    switch (currentView) {
        case 'day':
            renderDayView();
            break;
        case 'week':
            renderWeekView();
            break;
        case 'month':
            renderMonthView();
            break;
    }
}

// Initialize day view time slots
function initializeDayViewSlots() {
    const container = document.querySelector('#day-view > div');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Create time slots from 7 AM to 8 PM
    for (let hour = 7; hour <= 20; hour++) {
        const timeSlot = document.createElement('div');
        timeSlot.className = 'time-slot';
        timeSlot.dataset.hour = hour;
        
        const timeLabel = document.createElement('span');
        timeLabel.className = 'time-label absolute left-4 top-4';
        timeLabel.textContent = formatHour(hour);
        
        timeSlot.appendChild(timeLabel);
        container.appendChild(timeSlot);
    }
}

// Render day view
function renderDayView() {
    const container = document.querySelector('#day-view > div');
    if (!container) return;
    
    // Clear and recreate time slots
    initializeDayViewSlots();
    
    // Filter appointments for current day
    const dayAppointments = appointments.filter(apt => 
        apt.appointment_date === currentDate.toISOString().split('T')[0]
    );
    
    console.log(`Rendering ${dayAppointments.length} appointments for day view`);
    
    // Render each appointment
    dayAppointments.forEach(appointment => {
        const block = createAppointmentBlock(appointment);
        const slot = findTimeSlot(appointment.start_time);
        if (slot) {
            slot.appendChild(block);
        }
    });
    
    // Highlight available slots
    highlightAvailableSlots();
    
    // Update day header if exists
    const dayHeader = document.querySelector('#day-view .day-column-header');
    if (dayHeader) {
        const isToday = isDateToday(currentDate);
        dayHeader.classList.toggle('today', isToday);
        
        dayHeader.innerHTML = `
            <div class="text-xs font-semibold text-gray-500 uppercase">${getDayName(currentDate)}</div>
            <div class="${isToday ? 'day-number' : 'text-lg font-bold'}">${currentDate.getDate()}</div>
        `;
    }
}

// Initialize week view grid
function initializeWeekViewGrid() {
    const container = document.querySelector('#week-view');
    if (!container) return;
    
    // Create week structure
    container.innerHTML = `
        <div class="week-header">
            <div></div>
            ${[0, 1, 2, 3, 4, 5, 6].map(i => `
                <div class="week-day-header">
                    <div class="text-xs font-semibold text-gray-500"></div>
                    <div class="text-lg font-bold"></div>
                </div>
            `).join('')}
        </div>
        <div class="week-grid">
            <div class="time-column">
                ${Array.from({length: 14}, (_, i) => i + 7).map(hour => `
                    <div class="week-time-slot flex items-center justify-center text-xs text-gray-500">
                        ${formatHour(hour)}
                    </div>
                `).join('')}
            </div>
            ${[0, 1, 2, 3, 4, 5, 6].map(day => `
                <div class="day-column" data-day="${day}">
                    ${Array.from({length: 14}, (_, i) => i + 7).map(hour => `
                        <div class="week-time-slot" data-hour="${hour}"></div>
                    `).join('')}
                </div>
            `).join('')}
        </div>
    `;
}

// Render week view
function renderWeekView() {
    const weekStart = getMonday(currentDate);
    
    // Initialize grid if needed
    initializeWeekViewGrid();
    
    // Update day headers
    const dayHeaders = document.querySelectorAll('#week-view .week-day-header');
    const dayNames = ['LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB', 'DOM'];
    
    dayHeaders.forEach((header, i) => {
        const dayDate = new Date(weekStart);
        dayDate.setDate(dayDate.getDate() + i);
        
        const isToday = isDateToday(dayDate);
        header.classList.toggle('today', isToday);
        
        header.innerHTML = `
            <div class="text-xs font-semibold ${isToday ? 'text-purple-600' : 'text-gray-500'}">${dayNames[i]}</div>
            <div class="text-lg font-bold ${isToday ? 'text-purple-600' : ''}">${dayDate.getDate()}</div>
        `;
    });
    
    // Clear all appointment blocks
    document.querySelectorAll('#week-view .week-appointment').forEach(el => el.remove());
    
    // Render appointments for each day
    for (let i = 0; i < 7; i++) {
        const dayDate = new Date(weekStart);
        dayDate.setDate(dayDate.getDate() + i);
        
        const dayAppointments = appointments.filter(apt => 
            apt.appointment_date === dayDate.toISOString().split('T')[0]
        );
        
        const dayColumn = document.querySelector(`#week-view .day-column[data-day="${i}"]`);
        if (!dayColumn) continue;
        
        dayAppointments.forEach(appointment => {
            const hour = parseInt(appointment.start_time.split(':')[0]);
            const slot = dayColumn.querySelector(`[data-hour="${hour}"]`);
            
            if (slot) {
                const block = createAppointmentBlock(appointment, true);
                slot.appendChild(block);
            }
        });
    }
}

// Render month view
function renderMonthView() {
    const container = document.querySelector('#month-view .grid');
    if (!container) return;
    
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const daysInPrevMonth = new Date(year, month, 0).getDate();
    
    // Clear container (keep headers)
    const headers = container.querySelectorAll('.bg-gray-50');
    container.innerHTML = '';
    headers.forEach(header => container.appendChild(header));
    
    // Re-add headers if they were removed
    if (container.children.length === 0) {
        const dayHeaders = ['DOM', 'LUN', 'MAR', 'MIÉ', 'JUE', 'VIE', 'SÁB'];
        dayHeaders.forEach(day => {
            const header = document.createElement('div');
            header.className = 'text-center p-2 font-bold text-gray-600 bg-gray-50';
            header.textContent = day;
            container.appendChild(header);
        });
    }
    
    // Add days from previous month
    const adjustedFirstDay = firstDay === 0 ? 0 : firstDay;
    for (let i = adjustedFirstDay - 1; i >= 0; i--) {
        const dayEl = createMonthDay(daysInPrevMonth - i, true);
        container.appendChild(dayEl);
    }
    
    // Add days of current month
    for (let day = 1; day <= daysInMonth; day++) {
        const date = new Date(year, month, day);
        const dayEl = createMonthDay(day, false, date);
        
        // Add appointments for this day
        const dayAppointments = appointments.filter(apt => 
            apt.appointment_date === date.toISOString().split('T')[0]
        );
        
        if (dayAppointments.length > 0) {
            const appointmentsSummary = document.createElement('div');
            appointmentsSummary.className = 'month-event bg-purple-100 text-purple-700';
            appointmentsSummary.textContent = `${dayAppointments.length} citas`;
            dayEl.appendChild(appointmentsSummary);
            
            // Add hover popup with details
            const popup = document.createElement('div');
            popup.className = 'day-detail-popup';
            popup.innerHTML = `
                <p class="text-xs font-semibold text-gray-900 mb-1">${date.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' })}</p>
                ${dayAppointments.slice(0, 3).map(apt => `
                    <p class="text-xs text-gray-600">${apt.start_time} - ${apt.patient_name}</p>
                `).join('')}
                ${dayAppointments.length > 3 ? `<p class="text-xs text-gray-500 italic">...y ${dayAppointments.length - 3} más</p>` : ''}
            `;
            dayEl.appendChild(popup);
        }
        
        // Check for exceptions
        const exception = scheduleExceptions.find(exc => exc.date === date.toISOString().split('T')[0]);
        if (exception && !exception.is_working_day) {
            const exceptionEl = document.createElement('div');
            exceptionEl.className = 'month-event bg-red-100 text-red-700';
            exceptionEl.textContent = 'Cerrado';
            dayEl.appendChild(exceptionEl);
        }
        
        container.appendChild(dayEl);
    }
    
    // Add days from next month to complete grid
    const totalCells = container.children.length - 7; // Subtract headers
    const remainingCells = 42 - totalCells; // 6 weeks * 7 days
    
    for (let day = 1; day <= remainingCells; day++) {
        const dayEl = createMonthDay(day, true);
        container.appendChild(dayEl);
    }
}

// Create month day element
function createMonthDay(day, isOtherMonth, date = null) {
    const dayEl = document.createElement('div');
    dayEl.className = 'month-day';
    
    if (isOtherMonth) {
        dayEl.classList.add('other-month');
    }
    
    if (date && isDateToday(date)) {
        dayEl.classList.add('today');
    }
    
    const dayNumber = document.createElement('div');
    dayNumber.className = 'month-day-number';
    dayNumber.textContent = day;
    dayEl.appendChild(dayNumber);
    
    // Add click handler
    if (date && !isOtherMonth) {
        dayEl.addEventListener('click', () => {
            currentDate = new Date(date);
            currentView = 'day';
            document.querySelector('.view-btn.active').classList.remove('active');
            document.querySelector('.view-btn').classList.add('active');
            switchView('day', document.querySelector('.view-btn'));
        });
    }
    
    return dayEl;
}

// Create appointment block
function createAppointmentBlock(appointment, compact = false) {
    const block = document.createElement('div');
    block.className = compact ? 'week-appointment' : 'appointment-block';
    
    // Determine color based on status and type
    const colorClass = getAppointmentColorClass(appointment);
    block.classList.add(colorClass);
    
    // Calculate position and height for day view
    if (!compact) {
        const startMinutes = timeToMinutes(appointment.start_time);
        const endMinutes = timeToMinutes(appointment.end_time);
        const duration = endMinutes - startMinutes;
        const topOffset = (startMinutes % 60) / 60 * 60;
        const height = (duration / 60) * 60 - 4;
        
        block.style.top = `${topOffset + 4}px`;
        block.style.height = `${height}px`;
        block.style.position = 'absolute';
        block.style.left = '80px';
        block.style.right = '20px';
    }
    
    // Add content
    const isAIScheduled = appointment.auto_scheduled || appointment.source === 'whatsapp';
    
    if (compact) {
        block.innerHTML = `
            <div class="font-semibold text-xs truncate">
                ${isAIScheduled ? '🤖 ' : ''}${appointment.patient_name.split(' ')[0]}
            </div>
        `;
    } else {
        block.innerHTML = `
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="font-semibold text-xs">
                        ${isAIScheduled ? '🤖 ' : ''}${appointment.patient_name}
                    </div>
                    <div class="text-xs opacity-75">
                        ${appointment.appointment_type?.name || appointment.reason || 'Consulta'}
                    </div>
                </div>
                ${appointment.status === 'scheduled' ? '<span class="text-xs">⏰</span>' : ''}
                ${appointment.status === 'confirmed' ? '<span class="text-xs">✓</span>' : ''}
            </div>
        `;
    }
    
    // Add click handler
    block.addEventListener('click', (e) => {
        e.stopPropagation();
        showAppointmentDetails(appointment);
    });
    
    return block;
}

// Get appointment color class
function getAppointmentColorClass(appointment) {
    // If appointment has a type with color, use it
    if (appointment.appointment_type?.color) {
        const color = appointment.appointment_type.color;
        // Map hex colors to classes
        const colorMap = {
            '#9333ea': 'appointment-purple',
            '#0284c7': 'appointment-blue',
            '#16a34a': 'appointment-green',
            '#dc2626': 'appointment-urgent',
            '#f59e0b': 'appointment-amber'
        };
        return colorMap[color] || 'appointment-regular';
    }
    
    // Default by status
    switch (appointment.status) {
        case 'confirmed':
            return 'appointment-confirmed';
        case 'scheduled':
            return 'appointment-regular';
        case 'urgent':
            return 'appointment-urgent';
        default:
            return 'appointment-new';
    }
}

// Highlight available slots in day view
function highlightAvailableSlots() {
    if (currentView !== 'day' || !availableSlots.length) return;
    
    // Clear previous highlights
    document.querySelectorAll('.slot-available').forEach(el => {
        el.classList.remove('slot-available');
    });
    
    // Add click handlers to available slots
    availableSlots.forEach(slot => {
        const hour = parseInt(slot.start.split(':')[0]);
        const timeSlot = document.querySelector(`#day-view .time-slot[data-hour="${hour}"]`);
        
        if (timeSlot && !timeSlot.querySelector('.appointment-block')) {
            timeSlot.classList.add('slot-available');
            timeSlot.style.cursor = 'pointer';
            timeSlot.onclick = () => openNewAppointmentModal(currentDate, slot.start);
        }
    });
}

// Show appointment details
async function showAppointmentDetails(appointment) {
    selectedAppointment = appointment;
    
    // Create or update details modal
    let modal = document.getElementById('appointment-details-modal');
    if (!modal) {
        modal = createAppointmentDetailsModal();
        document.body.appendChild(modal);
    }
    
    // Update content
    modal.querySelector('#detail-patient-name').textContent = appointment.patient_name;
    modal.querySelector('#detail-patient-phone').innerHTML = `
        <i class="fas fa-phone mr-2"></i>${appointment.patient_phone}
    `;
    modal.querySelector('#detail-patient-email').innerHTML = `
        <i class="fas fa-envelope mr-2"></i>${appointment.patient_email || 'No registrado'}
    `;
    
    const date = new Date(appointment.appointment_date + 'T00:00:00');
    modal.querySelector('#detail-date').textContent = date.toLocaleDateString('es-MX', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });
    
    modal.querySelector('#detail-time').textContent = `${formatTime(appointment.start_time)} - ${formatTime(appointment.end_time)}`;
    modal.querySelector('#detail-type').textContent = appointment.appointment_type?.name || appointment.reason || 'Consulta general';
    
    const statusEl = modal.querySelector('#detail-status');
    statusEl.textContent = getStatusLabel(appointment.status);
    statusEl.className = `px-2 py-1 rounded-full text-xs font-medium ${getStatusClass(appointment.status)}`;
    
    modal.querySelector('#detail-notes').textContent = appointment.notes || 'Sin notas adicionales';
    
    // Show source
    if (appointment.auto_scheduled) {
        modal.querySelector('#detail-source').innerHTML = `
            <span class="text-xs bg-blue-100 text-blue-700 px-2 py-1 rounded-full">
                🤖 Agendada por IA
            </span>
        `;
    } else {
        modal.querySelector('#detail-source').innerHTML = `
            <span class="text-xs bg-gray-100 text-gray-700 px-2 py-1 rounded-full">
                Manual
            </span>
        `;
    }
    
    // Show modal
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

// Create appointment details modal
function createAppointmentDetailsModal() {
    const modal = document.createElement('div');
    modal.id = 'appointment-details-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 600px;">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-bold text-gray-900">Detalles de la Cita</h3>
                <button onclick="closeAppointmentDetails()" class="icon-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            
            <div class="space-y-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-sm font-semibold text-gray-700 mb-3">Información del Paciente</h4>
                    <div class="space-y-2">
                        <div class="text-lg font-bold text-gray-900" id="detail-patient-name"></div>
                        <div class="text-sm text-gray-600" id="detail-patient-phone"></div>
                        <div class="text-sm text-gray-600" id="detail-patient-email"></div>
                    </div>
                </div>
                
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-sm font-semibold text-gray-700 mb-3">Detalles de la Cita</h4>
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <div class="text-xs text-gray-500">Fecha</div>
                            <div class="text-sm font-medium" id="detail-date"></div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-500">Horario</div>
                            <div class="text-sm font-medium" id="detail-time"></div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-500">Tipo</div>
                            <div class="text-sm font-medium" id="detail-type"></div>
                        </div>
                        <div>
                            <div class="text-xs text-gray-500">Estado</div>
                            <div id="detail-status"></div>
                        </div>
                    </div>
                </div>
                
                <div class="bg-gray-50 rounded-lg p-4">
                    <h4 class="text-sm font-semibold text-gray-700 mb-2">Notas</h4>
                    <div class="text-sm text-gray-600" id="detail-notes"></div>
                </div>
                
                <div id="detail-source"></div>
            </div>
            
            <div class="flex gap-3 mt-6">
                <button onclick="startConsultation()" class="btn-primary flex-1 bg-green-600 hover:bg-green-700 text-white py-2 rounded-lg font-semibold">
                    <i class="fas fa-play mr-2"></i>Iniciar Consulta
                </button>
                <button onclick="rescheduleAppointment()" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg font-semibold">
                    <i class="fas fa-calendar-alt mr-2"></i>Reprogramar
                </button>
                <button onclick="cancelAppointment()" class="flex-1 bg-red-600 hover:bg-red-700 text-white py-2 rounded-lg font-semibold">
                    <i class="fas fa-times mr-2"></i>Cancelar
                </button>
            </div>
        </div>
    `;
    
    return modal;
}

// Close appointment details
function closeAppointmentDetails() {
    const modal = document.getElementById('appointment-details-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = '';
    }
    selectedAppointment = null;
}

// Start consultation
function startConsultation() {
    if (!selectedAppointment) return;
    
    // Mark appointment as in progress
    updateAppointmentStatus(selectedAppointment.id, 'in_progress');
    showToast('Consulta iniciada', 'success');
    closeAppointmentDetails();
}

// Reschedule appointment
async function rescheduleAppointment() {
    if (!selectedAppointment) return;
    
    // Open reschedule modal
    openRescheduleModal(selectedAppointment);
}

// Cancel appointment
async function cancelAppointment() {
    if (!selectedAppointment) return;
    
    if (!confirm('¿Estás seguro de cancelar esta cita? Se notificará al paciente.')) {
        return;
    }
    
    try {
        showLoading();
        
        await api.makeRequest(`/schedule/appointments/${selectedAppointment.id}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ 
                status: 'cancelled',
                reason: 'Cancelada por el doctor'
            })
        });
        
        // Update local data
        const appointment = appointments.find(apt => apt.id === selectedAppointment.id);
        if (appointment) {
            appointment.status = 'cancelled';
        }
        
        // Refresh view
        renderView();
        closeAppointmentDetails();
        updateUpcomingAppointments();
        
        hideLoading();
        showToast('Cita cancelada. Se ha notificado al paciente.', 'success');
        
    } catch (error) {
        hideLoading();
        showToast('Error al cancelar la cita', 'error');
    }
}

// Update appointment status
async function updateAppointmentStatus(appointmentId, status) {
    try {
        await api.makeRequest(`/schedule/appointments/${appointmentId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ status })
        });
        
        // Update local data
        const appointment = appointments.find(apt => apt.id === appointmentId);
        if (appointment) {
            appointment.status = status;
        }
        
        renderView();
        updateStatistics();
        
    } catch (error) {
        console.error('Error updating appointment status:', error);
        showToast('Error al actualizar el estado de la cita', 'error');
    }
}

// Open new appointment modal
function openNewAppointmentModal(date = null, time = null) {
    selectedDate = date || currentDate;
    selectedTime = time;
    
    let modal = document.getElementById('new-appointment-modal');
    if (!modal) {
        modal = createNewAppointmentModal();
        document.body.appendChild(modal);
    }
    
    // Set default values
    const dateStr = selectedDate.toISOString().split('T')[0];
    modal.querySelector('#appointment-date').value = dateStr;
    
    if (selectedTime) {
        modal.querySelector('#appointment-time').value = selectedTime;
    }
    
    // Load available times for selected date
    loadAvailableTimesForDate(selectedDate);
    
    // Populate appointment types
    const typeSelect = modal.querySelector('#appointment-type');
    typeSelect.innerHTML = '<option value="">Seleccionar tipo...</option>';
    appointmentTypes.forEach(type => {
        typeSelect.innerHTML += `
            <option value="${type.id}" data-duration="${type.duration}">
                ${type.name} (${type.duration} min)
            </option>
        `;
    });
    
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

// Create new appointment modal
function createNewAppointmentModal() {
    const modal = document.createElement('div');
    modal.id = 'new-appointment-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 600px;">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-bold text-gray-900">Nueva Cita</h3>
                <button onclick="closeNewAppointmentModal()" class="icon-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            
            <div class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="label">Nombre del Paciente *</label>
                        <input type="text" id="patient-name" class="input-field" placeholder="Nombre completo" required>
                    </div>
                    <div>
                        <label class="label">Teléfono *</label>
                        <input type="tel" id="patient-phone" class="input-field" placeholder="+52 123 456 7890" required>
                    </div>
                </div>
                
                <div>
                    <label class="label">Correo Electrónico</label>
                    <input type="email" id="patient-email" class="input-field" placeholder="correo@ejemplo.com">
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="label">Fecha *</label>
                        <input type="date" id="appointment-date" class="input-field" required onchange="loadAvailableTimesForDate(new Date(this.value))">
                    </div>
                    <div>
                        <label class="label">Hora *</label>
                        <select id="appointment-time" class="input-field" required>
                            <option value="">Seleccionar hora...</option>
                        </select>
                    </div>
                </div>
                
                <div>
                    <label class="label">Tipo de Consulta</label>
                    <select id="appointment-type" class="input-field">
                        <option value="">Seleccionar tipo...</option>
                    </select>
                </div>
                
                <div>
                    <label class="label">Motivo de Consulta</label>
                    <textarea id="appointment-reason" class="input-field" rows="2" placeholder="Describa brevemente el motivo..."></textarea>
                </div>
                
                <div>
                    <label class="label">Notas Internas</label>
                    <textarea id="appointment-notes" class="input-field" rows="2" placeholder="Notas adicionales (no visibles para el paciente)..."></textarea>
                </div>
            </div>
            
            <div class="flex gap-3 mt-6">
                <button onclick="saveNewAppointment()" class="btn-primary flex-1 bg-gradient-to-r from-purple-600 to-pink-600 text-white py-3 rounded-xl font-semibold hover:shadow-lg transition-all">
                    <i class="fas fa-check mr-2"></i>
                    Agendar Cita
                </button>
                <button onclick="closeNewAppointmentModal()" class="flex-1 px-6 py-3 border-2 border-gray-300 rounded-xl text-gray-700 font-semibold hover:bg-gray-50 transition-all">
                    Cancelar
                </button>
            </div>
        </div>
    `;
    
    return modal;
}

// Load available times for a specific date
async function loadAvailableTimesForDate(date) {
    try {
        const dateStr = date.toISOString().split('T')[0];
        const response = await api.makeRequest(`/schedule/availability/${dateStr}`);
        
        const timeSelect = document.querySelector('#appointment-time');
        if (!timeSelect) return;
        
        timeSelect.innerHTML = '<option value="">Seleccionar hora...</option>';
        
        if (response.available_slots && response.available_slots.length > 0) {
            response.available_slots.forEach(slot => {
                timeSelect.innerHTML += `
                    <option value="${slot.start}">${formatTime(slot.start)} - ${formatTime(slot.end)}</option>
                `;
            });
        } else {
            timeSelect.innerHTML = '<option value="">No hay horarios disponibles</option>';
        }
        
    } catch (error) {
        console.error('Error loading available times:', error);
    }
}

// Save new appointment
async function saveNewAppointment() {
    const modal = document.getElementById('new-appointment-modal');
    
    const appointmentData = {
        patient_name: modal.querySelector('#patient-name').value,
        patient_phone: modal.querySelector('#patient-phone').value,
        patient_email: modal.querySelector('#patient-email').value,
        appointment_date: modal.querySelector('#appointment-date').value,
        start_time: modal.querySelector('#appointment-time').value,
        appointment_type_id: modal.querySelector('#appointment-type').value || null,
        reason: modal.querySelector('#appointment-reason').value,
        notes: modal.querySelector('#appointment-notes').value,
        source: 'manual'
    };
    
    // Validate required fields
    if (!appointmentData.patient_name || !appointmentData.patient_phone || 
        !appointmentData.appointment_date || !appointmentData.start_time) {
        showToast('Por favor complete todos los campos requeridos', 'warning');
        return;
    }
    
    try {
        showLoading();
        
        const response = await api.makeRequest('/schedule/appointments', {
            method: 'POST',
            body: JSON.stringify(appointmentData)
        });
        
        if (response.appointment_id) {
            showToast('Cita agendada exitosamente', 'success');
            closeNewAppointmentModal();
            await loadCalendarData();
        }
        
    } catch (error) {
        console.error('Error creating appointment:', error);
        showToast(error.message || 'Error al agendar la cita', 'error');
    } finally {
        hideLoading();
    }
}

// Close new appointment modal
function closeNewAppointmentModal() {
    const modal = document.getElementById('new-appointment-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = '';
    }
}

// Open reschedule modal
function openRescheduleModal(appointment) {
    let modal = document.getElementById('reschedule-modal');
    if (!modal) {
        modal = createRescheduleModal();
        document.body.appendChild(modal);
    }
    
    // Store appointment ID
    modal.dataset.appointmentId = appointment.id;
    
    // Set patient info
    modal.querySelector('#reschedule-patient-name').textContent = appointment.patient_name;
    modal.querySelector('#reschedule-current-date').textContent = formatDate(appointment.appointment_date);
    modal.querySelector('#reschedule-current-time').textContent = `${formatTime(appointment.start_time)} - ${formatTime(appointment.end_time)}`;
    
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

// Create reschedule modal
function createRescheduleModal() {
    const modal = document.createElement('div');
    modal.id = 'reschedule-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-bold text-gray-900">Reprogramar Cita</h3>
                <button onclick="closeRescheduleModal()" class="icon-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            
            <div class="space-y-4">
                <div class="bg-gray-50 rounded-lg p-4">
                    <div class="text-sm text-gray-600">Paciente</div>
                    <div class="font-semibold" id="reschedule-patient-name"></div>
                    <div class="text-sm text-gray-600 mt-2">Cita actual</div>
                    <div class="text-sm" id="reschedule-current-date"></div>
                    <div class="text-sm" id="reschedule-current-time"></div>
                </div>
                
                <div>
                    <label class="label">Nueva Fecha *</label>
                    <input type="date" id="reschedule-date" class="input-field" required onchange="loadRescheduleAvailableTimes(this.value)">
                </div>
                
                <div>
                    <label class="label">Nueva Hora *</label>
                    <select id="reschedule-time" class="input-field" required>
                        <option value="">Primero seleccione una fecha</option>
                    </select>
                </div>
                
                <div>
                    <label class="label">Motivo de Reprogramación</label>
                    <textarea id="reschedule-reason" class="input-field" rows="2" placeholder="Opcional..."></textarea>
                </div>
                
                <div>
                    <label class="flex items-center gap-2">
                        <input type="checkbox" id="notify-patient" checked>
                        <span class="text-sm">Notificar al paciente del cambio</span>
                    </label>
                </div>
            </div>
            
            <div class="flex gap-3 mt-6">
                <button onclick="confirmReschedule()" class="btn-primary flex-1 bg-blue-600 hover:bg-blue-700 text-white py-3 rounded-xl font-semibold">
                    <i class="fas fa-check mr-2"></i>
                    Confirmar Cambio
                </button>
                <button onclick="closeRescheduleModal()" class="flex-1 px-6 py-3 border-2 border-gray-300 rounded-xl text-gray-700 font-semibold hover:bg-gray-50 transition-all">
                    Cancelar
                </button>
            </div>
        </div>
    `;
    
    return modal;
}

// Load available times for reschedule
async function loadRescheduleAvailableTimes(dateStr) {
    try {
        const response = await api.makeRequest(`/schedule/availability/${dateStr}`);
        
        const timeSelect = document.querySelector('#reschedule-time');
        if (!timeSelect) return;
        
        timeSelect.innerHTML = '<option value="">Seleccionar hora...</option>';
        
        if (response.available_slots && response.available_slots.length > 0) {
            response.available_slots.forEach(slot => {
                timeSelect.innerHTML += `
                    <option value="${slot.start}">${formatTime(slot.start)} - ${formatTime(slot.end)}</option>
                `;
            });
        } else {
            timeSelect.innerHTML = '<option value="">No hay horarios disponibles</option>';
        }
        
    } catch (error) {
        console.error('Error loading reschedule times:', error);
    }
}

// Confirm reschedule
async function confirmReschedule() {
    const modal = document.getElementById('reschedule-modal');
    const appointmentId = modal.dataset.appointmentId;
    
    const data = {
        appointment_date: modal.querySelector('#reschedule-date').value,
        start_time: modal.querySelector('#reschedule-time').value,
        reschedule_reason: modal.querySelector('#reschedule-reason').value,
        notify_patient: modal.querySelector('#notify-patient').checked
    };
    
    if (!data.appointment_date || !data.start_time) {
        showToast('Por favor seleccione fecha y hora', 'warning');
        return;
    }
    
    try {
        showLoading();
        
        await api.makeRequest(`/schedule/appointments/${appointmentId}/reschedule`, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
        
        showToast('Cita reprogramada exitosamente', 'success');
        closeRescheduleModal();
        closeAppointmentDetails();
        await loadCalendarData();
        
    } catch (error) {
        console.error('Error rescheduling appointment:', error);
        showToast('Error al reprogramar la cita', 'error');
    } finally {
        hideLoading();
    }
}

// Close reschedule modal
function closeRescheduleModal() {
    const modal = document.getElementById('reschedule-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = '';
    }
}

// Open emergency closure modal
function openEmergencyModal() {
    let modal = document.getElementById('emergency-modal');
    if (!modal) {
        modal = createEmergencyModal();
        document.body.appendChild(modal);
    }
    
    // Set default date to today
    modal.querySelector('#emergency-date').value = currentDate.toISOString().split('T')[0];
    
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

// Create emergency modal
function createEmergencyModal() {
    const modal = document.createElement('div');
    modal.id = 'emergency-modal';
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 500px;">
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-xl font-bold text-gray-900">
                    <i class="fas fa-exclamation-triangle text-red-500 mr-2"></i>
                    Cierre de Emergencia
                </h3>
                <button onclick="closeEmergencyModal()" class="icon-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            
            <div class="bg-red-50 border border-red-200 rounded-lg p-4 mb-4">
                <p class="text-sm text-red-800">
                    <strong>⚠️ Advertencia:</strong> Esta acción cancelará TODAS las citas del día seleccionado y notificará a los pacientes.
                </p>
            </div>
            
            <div class="space-y-4">
                <div>
                    <label class="label">Fecha a cerrar *</label>
                    <input type="date" id="emergency-date" class="input-field" required>
                </div>
                
                <div>
                    <label class="label">Motivo del cierre *</label>
                    <select id="emergency-reason" class="input-field" required>
                        <option value="">Seleccionar motivo...</option>
                        <option value="Emergencia médica">Emergencia médica</option>
                        <option value="Emergencia familiar">Emergencia familiar</option>
                        <option value="Problema en el consultorio">Problema en el consultorio</option>
                        <option value="Condiciones climáticas">Condiciones climáticas</option>
                        <option value="Otro">Otro</option>
                    </select>
                </div>
                
                <div>
                    <label class="label">Mensaje para los pacientes</label>
                    <textarea id="emergency-message" class="input-field" rows="3" 
                        placeholder="Estimado paciente, por motivos de emergencia debemos cancelar su cita. Nos pondremos en contacto para reagendar. Disculpe las molestias."></textarea>
                </div>
                
                <div>
                    <label class="flex items-center gap-2">
                        <input type="checkbox" id="reschedule-appointments" checked>
                        <span class="text-sm">Intentar reprogramar las citas automáticamente</span>
                    </label>
                </div>
            </div>
            
            <div class="flex gap-3 mt-6">
                <button onclick="confirmEmergencyClosure()" class="btn-primary flex-1 bg-red-600 hover:bg-red-700 text-white py-3 rounded-xl font-semibold">
                    <i class="fas fa-exclamation-circle mr-2"></i>
                    Confirmar Cierre
                </button>
                <button onclick="closeEmergencyModal()" class="flex-1 px-6 py-3 border-2 border-gray-300 rounded-xl text-gray-700 font-semibold hover:bg-gray-50 transition-all">
                    Cancelar
                </button>
            </div>
        </div>
    `;
    
    return modal;
}

// Close emergency modal
function closeEmergencyModal() {
    const modal = document.getElementById('emergency-modal');
    if (modal) {
        modal.classList.remove('show');
        document.body.style.overflow = '';
    }
}

// Confirm emergency closure
async function confirmEmergencyClosure() {
    const modal = document.getElementById('emergency-modal');
    
    const date = modal.querySelector('#emergency-date').value;
    const reason = modal.querySelector('#emergency-reason').value;
    const message = modal.querySelector('#emergency-message').value;
    const reschedule = modal.querySelector('#reschedule-appointments').checked;
    
    if (!date || !reason) {
        showToast('Por favor complete todos los campos requeridos', 'warning');
        return;
    }
    
    if (!confirm(`¿Confirmas el cierre de emergencia para el ${formatDate(date)}? Se cancelarán TODAS las citas de ese día.`)) {
        return;
    }
    
    try {
        showLoading();
        
        const response = await api.makeRequest('/schedule/emergency-closure', {
            method: 'POST',
            body: JSON.stringify({
                date: date,
                reason: reason,
                message: message || `Estimado paciente, por motivos de ${reason.toLowerCase()} debemos cancelar su cita. Nos pondremos en contacto para reagendar. Disculpe las molestias.`,
                reschedule_appointments: reschedule
            })
        });
        
        // Reload calendar data
        await loadCalendarData();
        
        closeEmergencyModal();
        hideLoading();
        
        showToast(`Cierre de emergencia aplicado. Se han cancelado ${response.cancelled_count || 0} citas y notificado a los pacientes.`, 'success');
        
    } catch (error) {
        hideLoading();
        showToast('Error al aplicar cierre de emergencia', 'error');
    }
}

// Update statistics
function updateStatistics() {
    const today = new Date().toISOString().split('T')[0];
    const todayAppointments = appointments.filter(apt => 
        apt.appointment_date === today
    );
    
    const confirmed = todayAppointments.filter(apt => apt.status === 'confirmed').length;
    const pending = todayAppointments.filter(apt => apt.status === 'scheduled').length;
    const completed = todayAppointments.filter(apt => apt.status === 'completed').length;
    
    // Update stats in UI
    const statsContainer = document.querySelector('.stats-summary');
    if (statsContainer) {
        statsContainer.innerHTML = `
            <h4 class="text-sm font-bold text-gray-900 mb-4">
                RESUMEN DE ${currentView === 'day' ? 'HOY' : currentView === 'week' ? 'LA SEMANA' : 'EL MES'}
            </h4>
            <div class="space-y-3">
                <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Citas totales</span>
                    <span class="text-xl font-bold text-gray-900">${todayAppointments.length}</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Confirmadas</span>
                    <span class="text-xl font-bold text-green-600">${confirmed}</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Por confirmar</span>
                    <span class="text-xl font-bold text-amber-600">${pending}</span>
                </div>
                <div class="flex justify-between items-center">
                    <span class="text-sm text-gray-600">Completadas</span>
                    <span class="text-xl font-bold text-blue-600">${completed}</span>
                </div>
            </div>
        `;
    }
}

// Update upcoming appointments list
function updateUpcomingAppointments() {
    const container = document.querySelector('.upcoming-appointments');
    if (!container) return;
    
    container.innerHTML = '';
    
    // Get next 5 appointments
    const now = new Date();
    const upcoming = appointments
        .filter(apt => {
            const aptDate = new Date(apt.appointment_date + 'T' + apt.start_time);
            return aptDate > now && apt.status !== 'cancelled';
        })
        .sort((a, b) => {
            const dateA = new Date(a.appointment_date + 'T' + a.start_time);
            const dateB = new Date(b.appointment_date + 'T' + b.start_time);
            return dateA - dateB;
        })
        .slice(0, 5);
    
    upcoming.forEach(appointment => {
        const card = document.createElement('div');
        card.className = 'cita-card';
        
        const isToday = appointment.appointment_date === now.toISOString().split('T')[0];
        const isAI = appointment.auto_scheduled || appointment.source === 'whatsapp';
        
        card.innerHTML = `
            <div class="flex-1">
                <div class="font-semibold text-gray-900">
                    ${isAI ? '🤖 ' : ''}${appointment.patient_name}
                </div>
                <p class="text-xs text-gray-500">
                    ${appointment.appointment_type?.name || 'Consulta'} • 
                    ${isToday ? 'Hoy' : formatDate(appointment.appointment_date)} 
                    ${formatTime(appointment.start_time)}
                </p>
            </div>
            ${isToday && appointment.status === 'confirmed' ? `
                <button onclick="startConsultationQuick('${appointment.id}')" class="px-4 py-1.5 bg-green-500 text-white rounded-lg font-bold text-sm hover:bg-green-600 transition-all ml-2">
                    INICIAR
                </button>
            ` : ''}
            <button onclick="toggleDropdown(this)" class="text-gray-400 hover:text-gray-600 px-2 relative">
                <i class="fas fa-ellipsis-v"></i>
                <div class="dropdown-menu">
                    <div class="dropdown-item" onclick="showAppointmentDetails(${JSON.stringify(appointment).replace(/"/g, '&quot;')})">Ver detalles</div>
                    <div class="dropdown-item" onclick="quickReschedule('${appointment.id}')">Reprogramar</div>
                    <div class="dropdown-item" onclick="quickCancel('${appointment.id}')">Cancelar</div>
                </div>
            </button>
        `;
        
        container.appendChild(card);
    });
    
    if (upcoming.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-gray-500">
                <i class="fas fa-calendar-check text-2xl mb-2 opacity-50"></i>
                <p class="text-sm">No hay citas próximas</p>
            </div>
        `;
    }
}

// Update notifications
function updateNotifications() {
    const container = document.querySelector('.notifications-container');
    if (!container) return;
    
    const notifications = [];
    
    // Check for unconfirmed appointments
    const unconfirmed = appointments.filter(apt => 
        apt.status === 'scheduled' && 
        new Date(apt.appointment_date) >= new Date()
    );
    
    if (unconfirmed.length > 0) {
        notifications.push({
            type: 'warning',
            icon: 'bell',
            title: 'Citas sin confirmar',
            message: `${unconfirmed.length} citas pendientes de confirmación`
        });
    }
    
    // Check for AI scheduled appointments needing review
    const aiScheduled = appointments.filter(apt => 
        apt.auto_scheduled && 
        apt.status === 'scheduled'
    );
    
    if (aiScheduled.length > 0) {
        notifications.push({
            type: 'info',
            icon: 'robot',
            title: 'Citas agendadas por IA',
            message: `${aiScheduled.length} citas requieren revisión`
        });
    }
    
    // Render notifications
    container.innerHTML = notifications.map(notif => `
        <div class="p-3 border-l-4 border-gray-300 rounded">
            <div class="flex items-start gap-2">
                <i class="fas fa-${notif.icon} text-gray-500 text-xs mt-1"></i>
                <div>
                    <p class="text-xs font-semibold text-gray-700">${notif.title}</p>
                    <p class="text-xs text-gray-600">${notif.message}</p>
                </div>
            </div>
        </div>
    `).join('');
    
    if (notifications.length === 0) {
        container.innerHTML = `
            <div class="text-center py-4 text-gray-400">
                <i class="fas fa-check-circle text-2xl mb-2 opacity-50"></i>
                <p class="text-xs">Sin notificaciones</p>
            </div>
        `;
    }
}

// Quick actions
function startConsultationQuick(appointmentId) {
    updateAppointmentStatus(appointmentId, 'in_progress');
    showToast('Consulta iniciada', 'success');
}

function quickReschedule(appointmentId) {
    const appointment = appointments.find(apt => apt.id === appointmentId);
    if (appointment) {
        openRescheduleModal(appointment);
    }
}

async function quickCancel(appointmentId) {
    if (!confirm('¿Estás seguro de cancelar esta cita?')) return;
    
    try {
        await api.makeRequest(`/schedule/appointments/${appointmentId}/status`, {
            method: 'PATCH',
            body: JSON.stringify({ 
                status: 'cancelled',
                reason: 'Cancelada por el doctor'
            })
        });
        
        await loadCalendarData();
        showToast('Cita cancelada', 'success');
        
    } catch (error) {
        showToast('Error al cancelar la cita', 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    // Close modals on Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeAppointmentDetails();
            closeEmergencyModal();
            closeNewAppointmentModal();
            closeRescheduleModal();
        }
    });
    
    // Click outside to close dropdowns
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.fa-ellipsis-v') && !e.target.closest('.dropdown-menu')) {
            document.querySelectorAll('.dropdown-menu').forEach(d => d.classList.remove('show'));
        }
    });
    
    // Add keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + N for new appointment
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            openNewAppointmentModal();
        }
        
        // Ctrl/Cmd + D for day view
        if ((e.ctrlKey || e.metaKey) && e.key === 'd') {
            e.preventDefault();
            switchView('day', document.querySelector('.view-btn'));
        }
        
        // Ctrl/Cmd + W for week view
        if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
            e.preventDefault();
            switchView('week', document.querySelectorAll('.view-btn')[1]);
        }
        
        // Ctrl/Cmd + M for month view
        if ((e.ctrlKey || e.metaKey) && e.key === 'm') {
            e.preventDefault();
            switchView('month', document.querySelectorAll('.view-btn')[2]);
        }
    });
}

// Auto-refresh data every 30 seconds
function startAutoRefresh() {
    setInterval(() => {
        if (!isLoading) {
            loadCalendarData();
        }
    }, 30000);
}

// Utility functions
function getMonday(date) {
    const d = new Date(date);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(d.setDate(diff));
}

function isDateToday(date) {
    const today = new Date();
    return date.getDate() === today.getDate() &&
           date.getMonth() === today.getMonth() &&
           date.getFullYear() === today.getFullYear();
}

function getDayName(date) {
    const days = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'];
    return days[date.getDay()];
}

function formatTime(timeStr) {
    if (!timeStr) return '';
    
    const [hours, minutes] = timeStr.split(':');
    const h = parseInt(hours);
    const period = h >= 12 ? 'PM' : 'AM';
    const displayHours = h > 12 ? h - 12 : (h === 0 ? 12 : h);
    
    return `${displayHours}:${minutes} ${period}`;
}

function formatHour(hour) {
    const period = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour > 12 ? hour - 12 : (hour === 0 ? 12 : hour);
    return `${displayHour} ${period}`;
}

function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('es-MX', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });
}

function timeToMinutes(timeStr) {
    const [hours, minutes] = timeStr.split(':');
    return parseInt(hours) * 60 + parseInt(minutes);
}

function findTimeSlot(timeStr) {
    const hour = parseInt(timeStr.split(':')[0]);
    return document.querySelector(`#day-view .time-slot[data-hour="${hour}"]`);
}

function getStatusLabel(status) {
    const labels = {
        'scheduled': 'Agendada',
        'confirmed': 'Confirmada',
        'completed': 'Completada',
        'cancelled': 'Cancelada',
        'no_show': 'No asistió',
        'in_progress': 'En curso',
        'rescheduled': 'Reprogramada'
    };
    
    return labels[status] || status;
}

function getStatusClass(status) {
    const classes = {
        'scheduled': 'bg-blue-100 text-blue-700',
        'confirmed': 'bg-green-100 text-green-700',
        'completed': 'bg-gray-100 text-gray-700',
        'cancelled': 'bg-red-100 text-red-700',
        'no_show': 'bg-amber-100 text-amber-700',
        'in_progress': 'bg-purple-100 text-purple-700',
        'rescheduled': 'bg-indigo-100 text-indigo-700'
    };
    
    return classes[status] || 'bg-gray-100 text-gray-700';
}

function showLoading() {
    let spinner = document.getElementById('calendar-loading');
    if (!spinner) {
        spinner = document.createElement('div');
        spinner.id = 'calendar-loading';
        spinner.className = 'fixed inset-0 bg-white bg-opacity-75 flex items-center justify-center z-50';
        spinner.innerHTML = '<div class="loading-spinner"></div>';
        document.body.appendChild(spinner);
    }
    spinner.style.display = 'flex';
}

function hideLoading() {
    const spinner = document.getElementById('calendar-loading');
    if (spinner) {
        spinner.style.display = 'none';
    }
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast') || createToast();
    const messageEl = toast.querySelector('#toast-message');
    const iconEl = toast.querySelector('i');
    
    if (!messageEl) return;
    
    messageEl.textContent = message;
    
    // Update icon and colors based on type
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

function createToast() {
    const toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    toast.innerHTML = `
        <i class="fas fa-check-circle text-emerald-400"></i>
        <span id="toast-message">Mensaje</span>
    `;
    document.body.appendChild(toast);
    return toast;
}

// Toggle dropdown menu
function toggleDropdown(btn) {
    const dropdown = btn.querySelector('.dropdown-menu');
    // Close all other dropdowns
    document.querySelectorAll('.dropdown-menu').forEach(d => {
        if (d !== dropdown) d.classList.remove('show');
    });
    dropdown.classList.toggle('show');
}

// Toggle sidebar for mobile
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) sidebar.classList.toggle('open');
}

// Export functions for global use
window.switchView = switchView;
window.previousPeriod = previousPeriod;
window.nextPeriod = nextPeriod;
window.goToToday = goToToday;
window.openNewAppointmentModal = openNewAppointmentModal;
window.openEmergencyModal = openEmergencyModal;
window.closeEmergencyModal = closeEmergencyModal;
window.confirmEmergencyClosure = confirmEmergencyClosure;
window.closeNewAppointmentModal = closeNewAppointmentModal;
window.saveNewAppointment = saveNewAppointment;
window.closeAppointmentDetails = closeAppointmentDetails;
window.cancelAppointment = cancelAppointment;
window.rescheduleAppointment = rescheduleAppointment;
window.startConsultation = startConsultation;
window.closeRescheduleModal = closeRescheduleModal;
window.confirmReschedule = confirmReschedule;
window.loadAvailableTimesForDate = loadAvailableTimesForDate;
window.loadRescheduleAvailableTimes = loadRescheduleAvailableTimes;
window.toggleDropdown = toggleDropdown;
window.toggleSidebar = toggleSidebar;
window.showAppointmentDetails = showAppointmentDetails;
window.startConsultationQuick = startConsultationQuick;
window.quickReschedule = quickReschedule;
window.quickCancel = quickCancel;