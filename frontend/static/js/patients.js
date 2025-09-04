// Patients Management JavaScript - Versión Corregida
let currentPage = 1;
const itemsPerPage = 10;
let allPatients = [];
let filteredPatients = [];
let currentPatientId = null;
let currentPaymentIndex = 0;
let patientToDelete = null; // Para almacenar el paciente a eliminar

// Payment selection state
window.currentPendingDebts = [];
window.selectedDebtId = null;
window.selectedDebtAmount = null;

// Color mapping for patient initials (FIXED colors per patient)
const colorMap = {};
const availableColors = ['purple', 'blue', 'green', 'amber', 'pink', 'indigo'];

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Cargar pacientes primero, luego estadísticas y calendario
    await loadPatients();
    await loadStats();
    await loadPaymentCalendar();
    setupEventListeners();
});

// Setup event listeners
function setupEventListeners() {
    // Search input with debounce
    const searchInput = document.getElementById('search-patients');
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                applyFilters();
            }, 300);
        });
    }
    
    // Form submission handlers
    const patientForm = document.getElementById('patient-form');
    if (patientForm) {
        patientForm.addEventListener('submit', savePatient);
    }
    
    // Setup real-time formatting for money inputs
    setupMoneyInputFormatting();
}

// Setup money input formatting
function setupMoneyInputFormatting() {
    const moneyInputs = [
        'debt-amount',
        'payment-amount',
        'credit-amount'
    ];
    
    moneyInputs.forEach(id => {
        const input = document.getElementById(id);
        if (input) {
            // Format on input
            input.addEventListener('input', function(e) {
                let value = e.target.value.replace(/[^\d.]/g, '');
                let cursorPos = e.target.selectionStart;
                let oldLength = e.target.value.length;
                
                // Format the value
                if (value) {
                    const parts = value.split('.');
                    // Add commas to integer part
                    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
                    // Limit decimal places to 2
                    if (parts[1] && parts[1].length > 2) {
                        parts[1] = parts[1].substring(0, 2);
                    }
                    value = parts.join('.');
                }
                
                e.target.value = value;
                
                // Adjust cursor position after formatting
                let newLength = value.length;
                let diff = newLength - oldLength;
                e.target.setSelectionRange(cursorPos + diff, cursorPos + diff);
            });
            
            // Format on blur for final cleanup
            input.addEventListener('blur', function(e) {
                let value = e.target.value.replace(/[^\d.]/g, '');
                if (value && !isNaN(parseFloat(value))) {
                    const num = parseFloat(value);
                    e.target.value = num.toLocaleString('es-MX', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    });
                }
            });
        }
    });
}

// Format money with proper accounting format
function formatMoney(amount) {
    return new Intl.NumberFormat('es-MX', {
        style: 'currency',
        currency: 'MXN',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

// Get fixed color for patient
function getPatientColor(patientId) {
    if (!colorMap[patientId]) {
        // Assign a color based on patient ID hash
        const hash = patientId.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
        colorMap[patientId] = availableColors[hash % availableColors.length];
    }
    return colorMap[patientId];
}

// Load all patients from backend
async function loadPatients() {
    try {
        const response = await fetch('/api/patients', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            allPatients = await response.json();
            filteredPatients = [...allPatients];
            renderPatients();
            updateFilterBadges();
        } else {
            console.error('Error loading patients');
            showToast('Error al cargar pacientes', 'error');
        }
    } catch (error) {
        console.error('Error loading patients:', error);
        showToast('Error de conexión', 'error');
    }
}

// Render patients as cards - UPDATED WITH OPTIONS MENU
function renderPatients() {
    const container = document.querySelector('.space-y-4');
    if (!container) return;
    
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    const paginatedPatients = filteredPatients.slice(start, end);
    
    if (paginatedPatients.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500">
                <i class="fas fa-users text-4xl mb-3 text-gray-300"></i>
                <p>No se encontraron pacientes</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = paginatedPatients.map(patient => {
        // Determine balance status with proper formatting
        let balanceStatus = '';
        if (patient.balance < 0) {
            balanceStatus = `<span class="px-2 py-0.5 bg-red-50 text-red-700 rounded text-xs font-medium">Debe ${formatMoney(Math.abs(patient.balance))}</span>`;
        } else if (patient.balance > 0) {
            balanceStatus = `<span class="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium">Saldo ${formatMoney(patient.balance)}</span>`;
        } else {
            balanceStatus = `<span class="px-2 py-0.5 bg-green-50 text-green-700 rounded text-xs font-medium">Sin adeudos</span>`;
        }
        
        // Generate initials and FIXED color
        const initials = patient.first_name.charAt(0) + patient.last_name.charAt(0);
        const color = getPatientColor(patient.id);
        
        // Format contact info
        const contactInfo = [];
        if (patient.phone) contactInfo.push(`Tel: ${patient.phone}`);
        if (patient.email) contactInfo.push(`Email: ${patient.email}`);
        const contactString = contactInfo.join(' | ');
        
        return `
            <div class="patient-card" style="position: relative;">
                <div class="flex items-start justify-between">
                    <div class="flex gap-3 w-full">
                        <div class="w-10 h-10 bg-gradient-to-br from-${color}-400 to-${color}-500 rounded-full flex items-center justify-center text-white font-semibold text-xs flex-shrink-0">
                            ${initials}
                        </div>
                        <div class="flex-1 pr-8">
                            <div class="flex items-start justify-between mb-2">
                                <h3 class="font-semibold text-gray-900 text-base">${patient.full_name}</h3>
                                <div class="flex gap-2">
                                    ${balanceStatus}
                                </div>
                            </div>
                            
                            <div class="text-xs text-gray-600 space-y-0.5 mb-3">
                                <p>${patient.age} años | ${contactString || 'Sin contacto'}</p>
                                <p>Última visita: ${patient.last_visit ? formatDate(patient.last_visit) : 'Primera vez'}</p>
                                ${patient.notes ? `<p class="text-amber-600"><i class="fas fa-sticky-note mr-1"></i>${patient.notes}</p>` : ''}
                            </div>
                            
                            <div class="flex gap-2 flex-wrap">
                                <button type="button" onclick="openHistorialCitas('${patient.id}')" class="px-3 py-2 bg-gradient-to-b from-white to-blue-50 border-2 border-blue-300 text-blue-700 rounded-lg text-xs font-bold hover:from-blue-50 hover:to-blue-100 hover:border-blue-400 shadow-sm hover:shadow-md transition-all cursor-pointer">
                                    <i class="fas fa-calendar-alt mr-1.5"></i>
                                    Citas
                                </button>
                                <button type="button" onclick="openGestionPagosModal('${patient.id}')" class="px-3 py-2 bg-gradient-to-b from-white to-emerald-50 border-2 border-emerald-300 text-emerald-700 rounded-lg text-xs font-bold hover:from-emerald-50 hover:to-emerald-100 hover:border-emerald-400 shadow-sm hover:shadow-md transition-all cursor-pointer">
                                    <i class="fas fa-dollar-sign mr-1.5"></i>
                                    Pagos y Deudas
                                </button>
                                <button type="button" onclick="openNotasModal('${patient.id}')" class="px-3 py-2 bg-gradient-to-b from-white to-amber-50 border-2 border-amber-300 text-amber-700 rounded-lg text-xs font-bold hover:from-amber-50 hover:to-amber-100 hover:border-amber-400 shadow-sm hover:shadow-md transition-all cursor-pointer">
                                    <i class="fas fa-sticky-note mr-1.5"></i>
                                    Notas
                                </button>
                                <button type="button" onclick="openEditarDatosModal('${patient.id}')" class="px-3 py-2 bg-gradient-to-b from-white to-gray-50 border-2 border-gray-300 text-gray-700 rounded-lg text-xs font-bold hover:from-gray-50 hover:to-gray-100 hover:border-gray-400 shadow-sm hover:shadow-md transition-all cursor-pointer">
                                    <i class="fas fa-edit mr-1.5"></i>
                                    Editar
                                </button>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Three dots menu button - MEJOR POSICIONADO -->
                    <button class="patient-options-btn" onclick="togglePatientOptions(event, '${patient.id}')" style="position: absolute; top: 12px; right: 12px;">
                        <i class="fas fa-ellipsis-v"></i>
                    </button>
                </div>
                
                <!-- Dropdown menu -->
                <div class="patient-options-dropdown" id="dropdown-${patient.id}" style="top: 40px; right: 12px;">
                    <button onclick="deletePatient('${patient.id}')" class="danger">
                        <i class="fas fa-trash-alt"></i>
                        <span>Eliminar paciente</span>
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Toggle patient options dropdown
function togglePatientOptions(event, patientId) {
    event.stopPropagation();
    
    const dropdown = document.getElementById(`dropdown-${patientId}`);
    const button = event.currentTarget;
    
    // Close all other dropdowns
    document.querySelectorAll('.patient-options-dropdown').forEach(d => {
        if (d !== dropdown) {
            d.classList.remove('show');
        }
    });
    
    document.querySelectorAll('.patient-options-btn').forEach(b => {
        if (b !== button) {
            b.classList.remove('active');
        }
    });
    
    // Toggle current dropdown
    dropdown.classList.toggle('show');
    button.classList.toggle('active');
}

// Delete patient - show confirmation modal
function deletePatient(patientId) {
    const patient = allPatients.find(p => p.id === patientId);
    if (!patient) return;
    
    patientToDelete = patient;
    
    // Update modal with patient name
    document.getElementById('delete-patient-name').textContent = patient.full_name;
    
    // Show confirmation modal
    document.getElementById('delete-patient-modal').classList.add('show');
    
    // Hide dropdown
    document.querySelectorAll('.patient-options-dropdown').forEach(d => {
        d.classList.remove('show');
    });
    document.querySelectorAll('.patient-options-btn').forEach(b => {
        b.classList.remove('active');
    });
}

// Confirm delete patient
async function confirmDeletePatient() {
    if (!patientToDelete) return;
    
    try {
        const response = await fetch(`/api/patients/${patientToDelete.id}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            showToast(`Paciente ${patientToDelete.full_name} eliminado exitosamente`, 'success');
            
            // Close modal
            closeDeletePatientModal();
            
            // Reload all data
            await loadPatients();
            await loadStats();
            await loadPaymentCalendar();
            
            patientToDelete = null;
        } else {
            const error = await response.json();
            showToast(error.detail || 'Error al eliminar paciente', 'error');
        }
    } catch (error) {
        console.error('Error deleting patient:', error);
        showToast('Error de conexión al eliminar paciente', 'error');
    }
}

// Apply filters (FIXED)
function applyFilters() {
    const searchTerm = document.getElementById('search-patients')?.value.toLowerCase() || '';
    
    if (!searchTerm) {
        // If no search term, use the current filter
        const activeFilter = document.querySelector('.filter-pill.active');
        if (activeFilter) {
            const filterType = activeFilter.getAttribute('data-filter-type') || 'all';
            filterPatients(filterType, activeFilter);
        } else {
            filteredPatients = [...allPatients];
        }
    } else {
        // Apply search across all patients
        filteredPatients = allPatients.filter(patient => {
            return patient.first_name.toLowerCase().includes(searchTerm) ||
                   patient.last_name.toLowerCase().includes(searchTerm) ||
                   (patient.phone && patient.phone.includes(searchTerm)) ||
                   (patient.email && patient.email.toLowerCase().includes(searchTerm)) ||
                   (patient.whatsapp && patient.whatsapp.includes(searchTerm));
        });
    }
    
    currentPage = 1;
    renderPatients();
}

// Filter by type (FIXED)
window.filterPatients = function(type, btn) {
    // Update button states
    document.querySelectorAll('.filter-pill').forEach(b => {
        b.classList.remove('active');
        b.removeAttribute('data-filter-type');
    });
    btn.classList.add('active');
    btn.setAttribute('data-filter-type', type);
    
    // Clear search when filter is clicked
    const searchInput = document.getElementById('search-patients');
    if (searchInput) {
        searchInput.value = '';
    }
    
    // Apply filter
    if (type === 'all') {
        filteredPatients = [...allPatients];
    } else if (type === 'debt') {
        filteredPatients = allPatients.filter(p => p.balance < 0);
    } else if (type === 'today') {
        // Filter patients with appointments today
        const today = new Date().toDateString();
        // This would need appointments data to work properly
        // For now, we'll just show all patients (would need to load appointments)
        filteredPatients = [...allPatients];
        showToast('Función en desarrollo', 'info');
    } else if (type === 'new') {
        const thisMonth = new Date();
        thisMonth.setDate(1);
        thisMonth.setHours(0, 0, 0, 0);
        filteredPatients = allPatients.filter(p => {
            if (!p.created_at) return false;
            return new Date(p.created_at) >= thisMonth;
        });
    }
    
    currentPage = 1;
    renderPatients();
    updateFilterBadges();
}

// Update filter badges
function updateFilterBadges() {
    const totalBadge = document.getElementById('total-patients-badge');
    if (totalBadge) {
        totalBadge.textContent = allPatients.length;
    }
    
    // Update debt count
    const debtCount = allPatients.filter(p => p.balance < 0).length;
    const debtButton = Array.from(document.querySelectorAll('.filter-pill')).find(b => b.textContent.includes('Con deuda'));
    if (debtButton) {
        const badge = debtButton.querySelector('span') || document.createElement('span');
        badge.className = 'ml-2 text-xs opacity-70';
        badge.textContent = debtCount;
        if (!debtButton.contains(badge)) {
            debtButton.appendChild(badge);
        }
    }
    
    // Update new patients count
    const thisMonth = new Date();
    thisMonth.setDate(1);
    thisMonth.setHours(0, 0, 0, 0);
    const newCount = allPatients.filter(p => p.created_at && new Date(p.created_at) >= thisMonth).length;
    const newButton = Array.from(document.querySelectorAll('.filter-pill')).find(b => b.textContent.includes('Nuevos'));
    if (newButton) {
        const badge = newButton.querySelector('span') || document.createElement('span');
        badge.className = 'ml-2 text-xs opacity-70';
        badge.textContent = newCount;
        if (!newButton.contains(badge)) {
            newButton.appendChild(badge);
        }
    }
}

// Load statistics (FIXED)
async function loadStats() {
    try {
        const response = await fetch('/api/patients/stats/summary', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const stats = await response.json();
            updateStatsDisplay(stats);
        }
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

// Update statistics display (FIXED)
function updateStatsDisplay(stats) {
    // Update stat cards with proper selectors
    const statCards = document.querySelectorAll('.stat-card');
    
    statCards.forEach(card => {
        const statType = card.querySelector('[data-stat]')?.getAttribute('data-stat');
        const valueElement = card.querySelector('p.text-2xl');
        
        if (valueElement && statType) {
            switch(statType) {
                case 'total-patients':
                    valueElement.textContent = stats.total_patients || 0;
                    break;
                case 'patients-debt':
                    valueElement.textContent = stats.patients_with_debt || 0;
                    break;
                case 'active-today':
                    valueElement.textContent = stats.appointments_today || 0;
                    break;
                case 'new-this-month':
                    valueElement.textContent = stats.new_this_month || 0;
                    break;
            }
        }
    });
}

// Load payment calendar (FIXED)
async function loadPaymentCalendar() {
    try {
        const response = await fetch('/api/patients/payment-calendar', {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            displayPaymentCalendar(data.patients, data.total_amount);
        } else {
            console.error('Payment calendar failed with status:', response.status);
            displayPaymentCalendar([], 0);
        }
    } catch (error) {
        console.error('Error loading payment calendar:', error);
        displayPaymentCalendar([], 0);
    }
}

// Display payment calendar - SIN BADGE "CON ABONOS"
function displayPaymentCalendar(patients, totalAmount) {
    const slider = document.getElementById('payment-slider');
    const totalDebtElement = document.getElementById('total-debt-amount');
    
    if (totalDebtElement) {
        totalDebtElement.textContent = formatMoney(totalAmount || 0);
    }
    
    if (!slider) return;
    
    if (!patients || patients.length === 0) {
        slider.innerHTML = `
            <div class="min-w-full flex items-center justify-center px-2">
                <p class="text-gray-500 text-sm">No hay adeudos pendientes</p>
            </div>
        `;
        updatePaymentDots(0);
        return;
    }
    
    slider.innerHTML = patients.map((patient, index) => {
        // Procesar la primera deuda (más urgente)
        let mainDebtDisplay = '';
        let additionalDebtsDisplay = '';
        
        if (patient.debts && patient.debts.length > 0) {
            const firstDebt = patient.debts[0];
            
            // Formato para la primera deuda con información de pago parcial
            let statusText = '';
            let statusColor = '';
            let debtAmountDisplay = '';
            
            // Mostrar monto restante y original si hay pago parcial o crédito aplicado
            if (firstDebt.has_partial_payment) {
                if (firstDebt.credit_applied && firstDebt.credit_applied > 0) {
                    // Si se aplicó crédito del saldo a favor
                    const totalApplied = firstDebt.total_paid + firstDebt.credit_applied;
                    debtAmountDisplay = `
                        <div>
                            <span class="text-xs font-bold text-purple-600">DEBE</span>
                            <span class="text-lg font-black text-purple-700 ml-1">${formatMoney(firstDebt.amount)}</span>
                            <span class="text-xs text-gray-500 ml-1">de ${formatMoney(firstDebt.original_amount)}</span>
                        </div>
                    `;
                } else if (firstDebt.total_paid > 0) {
                    // Solo pagos parciales sin crédito
                    debtAmountDisplay = `
                        <div>
                            <span class="text-xs font-bold text-purple-600">DEBE</span>
                            <span class="text-lg font-black text-purple-700 ml-1">${formatMoney(firstDebt.amount)}</span>
                            <span class="text-xs text-gray-500 ml-1">de ${formatMoney(firstDebt.original_amount)}</span>
                        </div>
                    `;
                }
            } else {
                debtAmountDisplay = `
                    <div>
                        <span class="text-xs font-bold text-purple-600">DEBE</span>
                        <span class="text-lg font-black text-purple-700 ml-1">${formatMoney(firstDebt.amount)}</span>
                    </div>
                `;
            }
            
            // Determinar estado de pago
            if (firstDebt.is_overdue) {
                statusText = 'VENCIDO';
                statusColor = 'red';
            } else if (firstDebt.days_until_due === 0) {
                statusText = 'PAGA HOY';
                statusColor = 'amber';
            } else if (firstDebt.days_until_due === 1) {
                statusText = 'PAGA MAÑANA';
                statusColor = 'amber';
            } else if (firstDebt.days_until_due > 1 && firstDebt.days_until_due <= 7) {
                statusText = `PAGA en ${firstDebt.days_until_due} días`;
                statusColor = 'blue';
            } else if (firstDebt.due_date) {
                statusText = `PAGA el ${formatDate(firstDebt.due_date)}`;
                statusColor = 'gray';
            } else {
                statusText = 'Sin fecha de pago';
                statusColor = 'gray';
            }
            
            mainDebtDisplay = `
                <div class="flex items-center justify-between">
                    ${debtAmountDisplay}
                    <span class="text-xs font-bold text-${statusColor}-600">
                        ${statusText}
                    </span>
                </div>
            `;
            
            // Si hay más deudas, mostrarlas en formato compacto
            if (patient.debts.length > 1) {
                additionalDebtsDisplay = patient.debts.slice(1).map(debt => {
                    let debtStatus = '';
                    let amountText = '';
                    
                    // Mostrar monto restante y original si hay pago parcial o crédito aplicado
                    if (debt.has_partial_payment) {
                        if (debt.credit_applied && debt.credit_applied > 0) {
                            amountText = `${formatMoney(debt.amount)} de ${formatMoney(debt.original_amount)}`;
                        } else if (debt.total_paid > 0) {
                            amountText = `${formatMoney(debt.amount)} de ${formatMoney(debt.original_amount)}`;
                        } else {
                            amountText = formatMoney(debt.amount);
                        }
                    } else {
                        amountText = formatMoney(debt.amount);
                    }
                    
                    if (debt.due_date) {
                        if (debt.is_overdue) {
                            debtStatus = 'Vencido';
                        } else if (debt.days_until_due === 0) {
                            debtStatus = 'Vence HOY';
                        } else if (debt.days_until_due === 1) {
                            debtStatus = 'Mañana';
                        } else if (debt.days_until_due <= 7) {
                            debtStatus = `${debt.days_until_due} días`;
                        } else {
                            debtStatus = formatDate(debt.due_date);
                        }
                    } else {
                        debtStatus = 'Sin fecha';
                    }
                    
                    return `
                        <div class="flex justify-between text-xs mt-1 pt-1 border-t border-purple-100">
                            <span class="text-gray-600">${amountText}</span>
                            <span class="text-gray-500">${debtStatus}</span>
                        </div>
                    `;
                }).join('');
            }
        }
        
        return `
            <div class="min-w-full flex items-center px-2">
                <div class="w-full cursor-pointer hover:bg-white/50 rounded-lg p-2 transition-all" onclick="openGestionPagosModal('${patient.patient_id}')">
                    <div class="mb-2">
                        <p class="font-semibold text-gray-900 text-sm">
                            ${patient.patient_name}
                        </p>
                    </div>
                    
                    ${mainDebtDisplay}
                    ${additionalDebtsDisplay}
                    
                    ${patient.whatsapp ? `
                        <button onclick="event.stopPropagation(); sendWhatsAppReminder('${patient.whatsapp}', '${patient.patient_name}', ${patient.total_debt})" 
                                class="mt-2 text-green-600 hover:text-green-700 text-xs w-full text-center">
                            <i class="fab fa-whatsapp"></i> Enviar recordatorio
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }).join('');
    
    updatePaymentDots(patients.length);
    currentPaymentIndex = 0;
}

// Update payment dots
function updatePaymentDots(count) {
    const dotsContainer = document.getElementById('payment-dots');
    if (!dotsContainer) return;
    
    dotsContainer.innerHTML = '';
    for (let i = 0; i < Math.min(count, 5); i++) {
        const dot = document.createElement('span');
        dot.className = `w-1 h-1 rounded-full transition-all ${i === 0 ? 'bg-purple-600' : 'bg-purple-300'}`;
        dot.id = `dot-${i}`;
        dotsContainer.appendChild(dot);
    }
}

// Scroll payment carousel
window.scrollPaymentNext = function() {
    const slider = document.getElementById('payment-slider');
    const slides = slider.querySelectorAll('.min-w-full').length;
    if (slides <= 1) return;
    
    currentPaymentIndex = (currentPaymentIndex + 1) % slides;
    slider.style.transform = `translateX(-${currentPaymentIndex * 100}%)`;
    updateActiveDot(currentPaymentIndex);
}

window.scrollPaymentPrev = function() {
    const slider = document.getElementById('payment-slider');
    const slides = slider.querySelectorAll('.min-w-full').length;
    if (slides <= 1) return;
    
    currentPaymentIndex = (currentPaymentIndex - 1 + slides) % slides;
    slider.style.transform = `translateX(-${currentPaymentIndex * 100}%)`;
    updateActiveDot(currentPaymentIndex);
}

function updateActiveDot(index) {
    document.querySelectorAll('[id^="dot-"]').forEach((dot, i) => {
        if (i === index) {
            dot.classList.remove('bg-purple-300');
            dot.classList.add('bg-purple-600');
        } else {
            dot.classList.remove('bg-purple-600');
            dot.classList.add('bg-purple-300');
        }
    });
}

// Save patient (from modal)
async function savePatient(event) {
    event.preventDefault();
    
    // Get form values
    const patientData = {
        first_name: document.getElementById('patient-first-name').value,
        last_name: document.getElementById('patient-last-name').value,
        age: parseInt(document.getElementById('patient-age').value),
        sex: document.getElementById('patient-sex').value,
        notes: document.getElementById('patient-notes').value || null
    };
    
    // Add contact methods if checked
    if (document.getElementById('check-telefono')?.checked) {
        const phoneInput = document.getElementById('patient-phone');
        if (phoneInput?.value) {
            patientData.phone = phoneInput.value.replace(/\D/g, '');
        }
    }
    
    if (document.getElementById('check-email')?.checked) {
        const emailInput = document.getElementById('patient-email');
        if (emailInput?.value) {
            patientData.email = emailInput.value;
        }
    }
    
    if (document.getElementById('check-whatsapp')?.checked) {
        const whatsappInput = document.getElementById('patient-whatsapp');
        if (whatsappInput?.value) {
            patientData.whatsapp = whatsappInput.value.replace(/\D/g, '');
        }
    }
    
    // Add birth date if provided
    const birthDateInput = document.getElementById('patient-birth-date');
    if (birthDateInput?.value) {
        patientData.birth_date = birthDateInput.value;
    }
    
    try {
        const response = await fetch('/api/patients', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(patientData)
        });
        
        if (response.ok) {
            showToast('Paciente registrado exitosamente');
            closePatientModal();
            await loadPatients();
            await loadStats();
            await loadPaymentCalendar();
        } else {
            const error = await response.json();
            showToast(error.detail || 'Error al registrar paciente', 'error');
        }
    } catch (error) {
        console.error('Error saving patient:', error);
        showToast('Error de conexión', 'error');
    }
}

// Edit patient - Load data
function openEditarDatosModal(patientId) {
    const patient = allPatients.find(p => p.id === patientId);
    if (!patient) return;
    
    currentPatientId = patientId;
    
    // Fill form with patient data
    document.getElementById('edit-first-name').value = patient.first_name;
    document.getElementById('edit-last-name').value = patient.last_name;
    document.getElementById('edit-age').value = patient.age;
    document.getElementById('edit-sex').value = patient.sex;
    document.getElementById('edit-phone').value = patient.phone || '';
    document.getElementById('edit-email').value = patient.email || '';
    document.getElementById('edit-whatsapp').value = patient.whatsapp || '';
    document.getElementById('edit-notes').value = patient.notes || '';
    
    document.getElementById('editar-datos-modal').classList.add('show');
}

// Save edited patient data
async function saveEditarDatos() {
    if (!currentPatientId) return;
    
    const updateData = {
        first_name: document.getElementById('edit-first-name').value,
        last_name: document.getElementById('edit-last-name').value,
        age: parseInt(document.getElementById('edit-age').value),
        sex: document.getElementById('edit-sex').value,
        phone: document.getElementById('edit-phone').value || null,
        email: document.getElementById('edit-email').value || null,
        whatsapp: document.getElementById('edit-whatsapp').value || null,
        notes: document.getElementById('edit-notes').value || null
    };
    
    try {
        const response = await fetch(`/api/patients/${currentPatientId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(updateData)
        });
        
        if (response.ok) {
            showToast('Datos actualizados correctamente');
            closeEditarDatosModal();
            await loadPatients();
        } else {
            showToast('Error al actualizar datos', 'error');
        }
    } catch (error) {
        console.error('Error updating patient:', error);
        showToast('Error de conexión', 'error');
    }
}

// Payment management (FIXED with proper debt loading)
async function openGestionPagosModal(patientId) {
    currentPatientId = patientId;
    const patient = allPatients.find(p => p.id === patientId);
    if (!patient) return;
    
    // Update patient name in modal
    document.getElementById('payment-modal-title').textContent = `Gestión de Pagos - ${patient.full_name}`;
    
    // Update balance display with proper formatting
    const debtAmount = patient.balance < 0 ? Math.abs(patient.balance) : 0;
    const creditAmount = patient.balance > 0 ? patient.balance : 0;
    
    document.getElementById('patient-debt').textContent = formatMoney(debtAmount);
    document.getElementById('patient-credit').textContent = formatMoney(creditAmount);
    
    // Show/hide saldo a favor button based on debt
    const saldoFavorBtn = document.querySelector('[onclick="agregarSaldoFavor()"]');
    if (saldoFavorBtn) {
        if (debtAmount > 0) {
            saldoFavorBtn.style.display = 'none';
        } else {
            saldoFavorBtn.style.display = 'inline-block';
        }
    }
    
    // Load payment history AND pending debts in parallel
    await Promise.all([
        loadPaymentHistory(patientId),
        loadPendingDebts(patientId)
    ]);
    
    document.getElementById('gestion-pagos-modal').classList.add('show');
}

// Load pending debts for payment selection (FIXED)
async function loadPendingDebts(patientId) {
    try {
        const response = await fetch(`/api/patients/${patientId}/pending-debts`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            window.currentPendingDebts = data.pending_debts || [];
            console.log('Loaded pending debts:', window.currentPendingDebts);
            return window.currentPendingDebts;
        } else {
            console.error('Failed to load pending debts:', response.status);
            window.currentPendingDebts = [];
        }
    } catch (error) {
        console.error('Error loading pending debts:', error);
        window.currentPendingDebts = [];
    }
    return [];
}

// Load payment history (FIXED with proper formatting)
async function loadPaymentHistory(patientId) {
    try {
        const response = await fetch(`/api/patients/${patientId}/payments`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const payments = await response.json();
            displayPaymentHistory(payments);
        }
    } catch (error) {
        console.error('Error loading payment history:', error);
    }
}

// Display payment history (IMPROVED with better status display)
function displayPaymentHistory(payments) {
    const container = document.getElementById('payment-history');
    if (!container) return;
    
    if (payments.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-500 py-4">No hay movimientos registrados</p>';
        return;
    }
    
    // Payments are already sorted by most recent from backend
    container.innerHTML = payments.map(payment => {
        let icon, iconColor, statusText, conceptText;
        
        if (payment.payment_type === 'debt') {
            icon = 'fa-minus';
            iconColor = 'red';
            statusText = payment.status === 'paid' ? '✓ Liquidado' : 'Pendiente';
            conceptText = payment.concept || 'Servicio médico';
            if (payment.due_date && payment.status === 'pending') {
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                const dueDate = new Date(payment.due_date + 'T00:00:00');  // Asegurar que es medianoche en zona local
                dueDate.setHours(0, 0, 0, 0);
                const timeDiff = dueDate.getTime() - today.getTime();
                const daysUntil = Math.ceil(timeDiff / (1000 * 60 * 60 * 24));
                
                if (daysUntil < 0) {
                    statusText += ' - VENCIDO';
                } else if (daysUntil === 0) {
                    statusText += ' - Vence HOY';
                } else if (daysUntil === 1) {
                    statusText += ' - Vence MAÑANA';
                } else if (daysUntil <= 7) {
                    statusText += ` - Vence en ${daysUntil} días`;
                }
            }
        } else if (payment.payment_type === 'payment') {
            icon = 'fa-check';
            iconColor = 'green';
            // Check if it's a partial or total payment based on concept
            if (payment.concept && payment.concept.includes('Liquidación')) {
                statusText = 'Liquidación completa';
                conceptText = payment.concept;
            } else if (payment.concept && payment.concept.includes('Abono')) {
                statusText = 'Abono parcial';
                conceptText = payment.concept;
            } else {
                statusText = 'Pago realizado';
                conceptText = payment.concept || 'Pago de adeudos';
            }
        } else {
            icon = 'fa-wallet';
            iconColor = 'purple';
            statusText = 'Saldo a favor';
            conceptText = payment.concept || 'Crédito';
        }
        
        // Add "NUEVO" badge for recent movements (last 24 hours)
        const isRecent = (new Date() - new Date(payment.payment_date)) < 24 * 60 * 60 * 1000;
        const recentBadge = isRecent ? '<span class="ml-2 px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs font-medium">NUEVO</span>' : '';
        
        return `
            <div class="flex items-center justify-between p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-all">
                <div class="flex items-center gap-3">
                    <div class="w-8 h-8 bg-${iconColor}-100 rounded-full flex items-center justify-center">
                        <i class="fas ${icon} text-${iconColor}-600 text-xs"></i>
                    </div>
                    <div>
                        <p class="text-sm font-medium text-gray-900">
                            ${conceptText}
                            ${recentBadge}
                        </p>
                        <p class="text-xs text-gray-500">${formatDateTime(payment.payment_date)}</p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="text-sm font-bold text-${iconColor}-600">${formatMoney(payment.amount)}</p>
                    <span class="text-xs text-${iconColor}-500">${statusText}</span>
                </div>
            </div>
        `;
    }).join('');
}

// Register debt (FIXED with proper datetime handling)
async function guardarDeuda() {
    const concept = document.getElementById('debt-concept').value;
    // Remove formatting to get the actual number
    const amountValue = document.getElementById('debt-amount').value.replace(/[^\d.]/g, '');
    const amount = parseFloat(amountValue);
    const dueDate = document.getElementById('debt-due-date').value;
    
    if (!amount || amount <= 0) {
        showToast('Ingrese un monto válido', 'error');
        return;
    }
    
    // Siempre usar la fecha y hora actual
    const paymentData = {
        amount: amount,
        payment_type: 'debt',
        concept: concept || 'Servicio médico',
        payment_date: null,  // El backend usará datetime.utcnow()
        due_date: dueDate || null
    };
    
    console.log('Registering debt:', paymentData);
    
    try {
        const response = await fetch(`/api/patients/${currentPatientId}/payments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(paymentData)
        });
        
        if (response.ok) {
            showToast('Deuda registrada correctamente');
            closeRegistrarDeudaModal();
            
            // Form se limpia en closeRegistrarDeudaModal
            
            // Reload everything - IMPORTANTE: Recargar historial
            await Promise.all([
                loadPatients(),
                loadPaymentHistory(currentPatientId),  // Esto debe mostrar la nueva deuda arriba
                loadPendingDebts(currentPatientId),
                loadStats(),
                loadPaymentCalendar()
            ]);
            
            // Update the balance in the modal
            const patient = allPatients.find(p => p.id === currentPatientId);
            if (patient) {
                const debtAmount = patient.balance < 0 ? Math.abs(patient.balance) : 0;
                const creditAmount = patient.balance > 0 ? patient.balance : 0;
                document.getElementById('patient-debt').textContent = formatMoney(debtAmount);
                document.getElementById('patient-credit').textContent = formatMoney(creditAmount);
                
                // Update saldo a favor button visibility
                const saldoFavorBtn = document.querySelector('[onclick="agregarSaldoFavor()"]');
                if (saldoFavorBtn) {
                    if (debtAmount > 0) {
                        saldoFavorBtn.style.display = 'none';
                    } else {
                        saldoFavorBtn.style.display = 'inline-block';
                    }
                }
            }
        } else {
            const error = await response.json();
            console.error('Error response:', error);
            showToast(error.detail || 'Error al registrar deuda', 'error');
        }
    } catch (error) {
        console.error('Error registering debt:', error);
        showToast('Error de conexión', 'error');
    }
}

// Register payment - FIXED VERSION with better error handling
async function registrarPago() {
    // First check if we have the current patient ID
    if (!currentPatientId) {
        showToast('Error: No se ha seleccionado un paciente', 'error');
        return;
    }
    
    // Load pending debts if not already loaded
    if (!window.currentPendingDebts || window.currentPendingDebts.length === 0) {
        console.log('Loading pending debts...');
        await loadPendingDebts(currentPatientId);
    }
    
    // Check again after loading
    if (!window.currentPendingDebts || window.currentPendingDebts.length === 0) {
        showToast('No hay deudas pendientes para pagar', 'info');
        return;
    }
    
    console.log('Showing payment modal with debts:', window.currentPendingDebts);
    
    // Populate debt selector in modal
    const debtSelector = document.getElementById('debt-selector');
    if (debtSelector) {
        debtSelector.innerHTML = window.currentPendingDebts.map(debt => {
            const overdueClass = debt.is_overdue ? 'border-red-200 bg-red-50' : '';
            
            // Mostrar información de crédito aplicado si existe
            let amountDisplay = '';
            if (debt.credit_applied && debt.credit_applied > 0) {
                // Si se aplicó crédito, mostrar el monto original y el restante
                amountDisplay = `
                    <p class="text-lg font-bold text-red-600">${formatMoney(debt.remaining)}</p>
                    <p class="text-xs text-gray-500">de ${formatMoney(debt.amount)}</p>
                    <p class="text-xs text-green-600">Crédito aplicado: ${formatMoney(debt.credit_applied)}</p>
                `;
            } else if (debt.total_paid > 0) {
                // Si hay pagos parciales
                amountDisplay = `
                    <p class="text-lg font-bold text-red-600">${formatMoney(debt.remaining)}</p>
                    <p class="text-xs text-gray-500">Pagado: ${formatMoney(debt.total_paid)}</p>
                `;
            } else {
                // Deuda completa sin pagos ni créditos
                amountDisplay = `
                    <p class="text-lg font-bold text-red-600">${formatMoney(debt.remaining)}</p>
                `;
            }
            
            return `
                <div class="debt-option p-3 border-2 ${overdueClass || 'border-gray-200'} rounded-lg hover:border-green-500 cursor-pointer transition-all" 
                     data-debt-id="${debt.id}" 
                     data-debt-amount="${debt.remaining}"
                     onclick="selectDebtToPay('${debt.id}', ${debt.remaining})">
                    <div class="flex justify-between items-start">
                        <div class="flex-1">
                            <p class="font-medium text-gray-900">${debt.concept}</p>
                            <p class="text-xs text-gray-500">Fecha: ${formatDate(debt.payment_date)}</p>
                            ${debt.due_date ? `<p class="text-xs text-${debt.is_overdue ? 'red' : 'gray'}-500">Vence: ${formatDate(debt.due_date)}</p>` : ''}
                        </div>
                        <div class="text-right">
                            ${amountDisplay}
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    }
    
    // Reset payment amount field
    document.getElementById('payment-amount').value = '';
    document.getElementById('payment-amount').disabled = true;
    document.getElementById('payment-amount').placeholder = 'Seleccione una deuda primero';
    
    // Hide payment options initially
    const paymentOptions = document.getElementById('payment-options');
    if (paymentOptions) {
        paymentOptions.style.display = 'none';
    }
    
    // Clear any previous selection
    window.selectedDebtId = null;
    window.selectedDebtAmount = null;
    
    // Show the modal
    document.getElementById('registrar-pago-modal').classList.add('show');
}

// Select debt to pay (IMPROVED)
window.selectDebtToPay = function(debtId, debtAmount) {
    console.log('Selecting debt:', debtId, 'Amount:', debtAmount);
    
    // Remove previous selections
    document.querySelectorAll('.debt-option').forEach(opt => {
        opt.classList.remove('border-green-500', 'bg-green-50');
        opt.classList.add('border-gray-200');
    });
    
    // Mark selected
    const selectedOption = document.querySelector(`[data-debt-id="${debtId}"]`);
    if (selectedOption) {
        selectedOption.classList.remove('border-gray-200');
        selectedOption.classList.add('border-green-500', 'bg-green-50');
    }
    
    // Store selected debt
    window.selectedDebtId = debtId;
    window.selectedDebtAmount = debtAmount;
    
    // Enable amount field
    const amountField = document.getElementById('payment-amount');
    amountField.disabled = false;
    amountField.placeholder = `Máximo: ${formatMoney(debtAmount)}`;
    amountField.focus();
    
    // Show payment options
    const paymentOptions = document.getElementById('payment-options');
    if (paymentOptions) {
        paymentOptions.style.display = 'block';
        paymentOptions.innerHTML = `
            <div class="grid grid-cols-2 gap-3 mt-3">
                <button type="button" onclick="setPaymentAmount(${debtAmount})" 
                        class="px-3 py-2 bg-green-100 text-green-700 rounded-lg text-sm font-medium hover:bg-green-200">
                    <i class="fas fa-check-circle mr-1"></i>
                    Liquidar Total<br>
                    <span class="text-xs font-bold">${formatMoney(debtAmount)}</span>
                </button>
                <button type="button" onclick="setPaymentAmount(${debtAmount * 0.5})" 
                        class="px-3 py-2 bg-blue-100 text-blue-700 rounded-lg text-sm font-medium hover:bg-blue-200">
                    <i class="fas fa-percent mr-1"></i>
                    Abonar 50%<br>
                    <span class="text-xs font-bold">${formatMoney(debtAmount * 0.5)}</span>
                </button>
            </div>
            <div class="mt-2 text-xs text-gray-500 text-center">
                O ingrese un monto personalizado en el campo de arriba
            </div>
        `;
    }
}

// Set payment amount helper
window.setPaymentAmount = function(amount) {
    const amountField = document.getElementById('payment-amount');
    amountField.value = amount.toLocaleString('es-MX', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Register payment (IMPROVED with proper datetime)
async function guardarPago() {
    if (!window.selectedDebtId) {
        showToast('Seleccione la deuda a pagar', 'error');
        return;
    }
    
    // Remove formatting to get the actual number
    const amountValue = document.getElementById('payment-amount').value.replace(/[^\d.]/g, '');
    const amount = parseFloat(amountValue);
    const method = document.getElementById('payment-method').value;
    
    if (!amount || amount <= 0) {
        showToast('Ingrese un monto válido', 'error');
        return;
    }
    
    if (amount > window.selectedDebtAmount) {
        showToast(`El monto no puede ser mayor a ${formatMoney(window.selectedDebtAmount)}`, 'error');
        return;
    }
    
    // Siempre usar la fecha y hora actual
    const paymentData = {
        amount: amount,
        payment_type: 'payment',
        concept: amount >= window.selectedDebtAmount ? 'Liquidación total' : 'Abono parcial',
        payment_method: method,
        payment_date: null,  // El backend usará datetime.utcnow()
        reference: window.selectedDebtId  // Link to specific debt
    };
    
    console.log('Saving payment:', paymentData);
    
    try {
        const response = await fetch(`/api/patients/${currentPatientId}/payments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(paymentData)
        });
        
        if (response.ok) {
            const isFullPayment = amount >= window.selectedDebtAmount;
            showToast(isFullPayment ? '✅ Deuda liquidada completamente' : '✅ Abono registrado correctamente', 'success');
            closeRegistrarPagoModal();
            
            // Form se limpia en closeRegistrarPagoModal
            
            // Reload everything to reflect changes - Use Promise.all for parallel loading
            await Promise.all([
                loadPatients(),
                loadPaymentHistory(currentPatientId),  // Esto debe mostrar el nuevo pago arriba
                loadPendingDebts(currentPatientId),
                loadStats(),
                loadPaymentCalendar()
            ]);
            
            // Update the balance in the modal
            const patient = allPatients.find(p => p.id === currentPatientId);
            if (patient) {
                const debtAmount = patient.balance < 0 ? Math.abs(patient.balance) : 0;
                const creditAmount = patient.balance > 0 ? patient.balance : 0;
                document.getElementById('patient-debt').textContent = formatMoney(debtAmount);
                document.getElementById('patient-credit').textContent = formatMoney(creditAmount);
                
                // Update saldo a favor button visibility
                const saldoFavorBtn = document.querySelector('[onclick="agregarSaldoFavor()"]');
                if (saldoFavorBtn) {
                    if (debtAmount > 0) {
                        saldoFavorBtn.style.display = 'none';
                    } else {
                        saldoFavorBtn.style.display = 'inline-block';
                        
                        // If all debts are paid, show a celebration
                        if (debtAmount === 0 && window.currentPendingDebts.length > 0) {
                            setTimeout(() => {
                                showToast('🎉 ¡Todas las deudas han sido liquidadas!', 'success');
                            }, 1500);
                        }
                    }
                }
            }
        } else {
            const error = await response.json();
            console.error('Error response:', error);
            showToast(error.detail || 'Error al registrar pago', 'error');
        }
    } catch (error) {
        console.error('Error registering payment:', error);
        showToast('Error de conexión', 'error');
    }
}

// Register credit (FIXED)
async function guardarSaldoFavor() {
    // Remove formatting to get the actual number
    const amountValue = document.getElementById('credit-amount').value.replace(/[^\d.]/g, '');
    const amount = parseFloat(amountValue);
    const concept = document.getElementById('credit-concept').value;
    
    if (!amount || amount <= 0) {
        showToast('Ingrese un monto válido', 'error');
        return;
    }
    
    // Check if patient has debt
    const patient = allPatients.find(p => p.id === currentPatientId);
    if (patient && patient.balance < 0) {
        showToast('No puede tener saldo a favor si tiene deudas pendientes', 'error');
        return;
    }
    
    // Siempre usar la fecha y hora actual
    const paymentData = {
        amount: amount,
        payment_type: 'credit',
        concept: concept || 'Saldo a favor',
        payment_date: null  // El backend usará datetime.utcnow()
    };
    
    try {
        const response = await fetch(`/api/patients/${currentPatientId}/payments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(paymentData)
        });
        
        if (response.ok) {
            showToast('Saldo a favor registrado');
            closeSaldoFavorModal();
            
            // Form se limpia en closeSaldoFavorModal
            
            await loadPatients();
            await loadPaymentHistory(currentPatientId);
            await loadStats();
            
            // Update the balance in the modal
            if (patient) {
                patient.balance += amount;
                document.getElementById('patient-credit').textContent = formatMoney(patient.balance);
            }
        } else {
            showToast('Error al registrar saldo', 'error');
        }
    } catch (error) {
        console.error('Error registering credit:', error);
        showToast('Error de conexión', 'error');
    }
}

// Notes management
async function openNotasModal(patientId) {
    currentPatientId = patientId;
    const patient = allPatients.find(p => p.id === patientId);
    if (!patient) return;
    
    // Load notes
    try {
        const response = await fetch(`/api/patients/${patientId}/notes`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const notes = await response.json();
            displayNotes(notes);
        }
    } catch (error) {
        console.error('Error loading notes:', error);
    }
    
    document.getElementById('notas-modal').classList.add('show');
}

// Display notes
function displayNotes(notes) {
    const container = document.getElementById('notes-list');
    if (!container) return;
    
    if (notes.length === 0) {
        container.innerHTML = '<p class="text-center text-gray-500">No hay notas registradas</p>';
        return;
    }
    
    container.innerHTML = notes.map(note => `
        <div class="note-item">
            <div class="flex justify-between items-start mb-2">
                <p class="text-sm font-medium text-gray-900">${note.note_type === 'important' ? 'Importante' : 'Recordatorio'}</p>
                <p class="text-xs text-gray-500">${formatDate(note.note_date)}</p>
            </div>
            <p class="text-sm text-gray-600">${note.content}</p>
        </div>
    `).join('');
}

// Add note
async function agregarNota() {
    const noteModal = document.getElementById('add-note-modal');
    if (noteModal) {
        noteModal.classList.add('show');
    }
}

// Save note from modal
async function saveNoteFromModal() {
    const content = document.getElementById('new-note-content').value;
    const type = document.getElementById('new-note-type').value;
    
    if (!content) {
        showToast('Ingrese el contenido de la nota', 'error');
        return;
    }
    
    const noteData = {
        note_type: type,
        content: content
    };
    
    try {
        const response = await fetch(`/api/patients/${currentPatientId}/notes`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            },
            body: JSON.stringify(noteData)
        });
        
        if (response.ok) {
            showToast('Nota agregada');
            document.getElementById('add-note-modal').classList.remove('show');
            document.getElementById('new-note-content').value = '';
            openNotasModal(currentPatientId);
        } else {
            showToast('Error al agregar nota', 'error');
        }
    } catch (error) {
        console.error('Error adding note:', error);
        showToast('Error de conexión', 'error');
    }
}

// Appointments management
async function openHistorialCitas(patientId) {
    currentPatientId = patientId;
    
    try {
        const response = await fetch(`/api/patients/${patientId}/appointments`, {
            headers: {
                'Authorization': `Bearer ${localStorage.getItem('access_token')}`
            }
        });
        
        if (response.ok) {
            const appointments = await response.json();
            displayAppointments(appointments);
        }
    } catch (error) {
        console.error('Error loading appointments:', error);
    }
    
    document.getElementById('historial-citas-modal').classList.add('show');
}

// Display appointments
function displayAppointments(appointments) {
    const now = new Date();
    
    const upcoming = appointments.filter(a => new Date(a.appointment_date) > now);
    const past = appointments.filter(a => new Date(a.appointment_date) <= now);
    
    // Display upcoming appointments
    const upcomingContainer = document.getElementById('upcoming-appointments');
    if (upcomingContainer) {
        if (upcoming.length === 0) {
            upcomingContainer.innerHTML = '<p class="text-gray-500 text-sm">No hay citas próximas</p>';
        } else {
            upcomingContainer.innerHTML = upcoming.map(apt => `
                <div class="bg-blue-50 border border-blue-200 rounded-lg p-3">
                    <div class="flex justify-between items-center">
                        <div>
                            <p class="font-medium text-gray-900 text-sm">${apt.appointment_type}</p>
                            <p class="text-xs text-gray-600 mt-1">
                                <i class="fas fa-calendar mr-1"></i> ${formatDateTime(apt.appointment_date)}
                            </p>
                        </div>
                        <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                            Próxima
                        </span>
                    </div>
                </div>
            `).join('');
        }
    }
    
    // Display past appointments
    const pastContainer = document.getElementById('past-appointments');
    if (pastContainer) {
        if (past.length === 0) {
            pastContainer.innerHTML = '<p class="text-gray-500 text-sm">No hay citas pasadas</p>';
        } else {
            pastContainer.innerHTML = past.map(apt => `
                <div class="bg-white border border-gray-200 rounded-lg p-3">
                    <div class="flex justify-between items-center">
                        <div>
                            <p class="font-medium text-gray-900 text-sm">${apt.appointment_type}</p>
                            <p class="text-xs text-gray-600 mt-1">
                                <i class="fas fa-calendar mr-1"></i> ${formatDateTime(apt.appointment_date)}
                            </p>
                        </div>
                        <span class="px-2 py-1 bg-green-100 text-green-700 rounded text-xs font-medium">
                            ${apt.status === 'completed' ? 'Asistió' : 'Programada'}
                        </span>
                    </div>
                </div>
            `).join('');
        }
    }
}

// WhatsApp reminder
function sendWhatsAppReminder(phone, name, amount) {
    const message = encodeURIComponent(
        `Hola ${name}, le recordamos que tiene un adeudo pendiente de ${formatMoney(amount)}. Por favor comuníquese con nosotros para acordar su pago. Gracias.`
    );
    
    window.open(`https://wa.me/52${phone}?text=${message}`, '_blank');
}

// Utility functions
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleDateString('es-MX', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function formatDateTime(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    
    // Ajustar para zona horaria local (México Central Time)
    const localDate = new Date(date.getTime());
    
    let datePrefix = '';
    if (localDate.toDateString() === today.toDateString()) {
        datePrefix = 'Hoy, ';
    } else if (localDate.toDateString() === yesterday.toDateString()) {
        datePrefix = 'Ayer, ';
    }
    
    return datePrefix + localDate.toLocaleString('es-MX', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true  // Formato 12 horas con AM/PM
    });
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toast-message');
    
    toastMessage.textContent = message;
    
    // Change icon based on type
    const icon = toast.querySelector('i');
    if (type === 'error') {
        icon.className = 'fas fa-exclamation-circle text-red-400';
    } else if (type === 'info') {
        icon.className = 'fas fa-info-circle text-blue-400';
    } else if (type === 'warning') {
        icon.className = 'fas fa-exclamation-triangle text-amber-400';
    } else {
        icon.className = 'fas fa-check-circle text-emerald-400';
    }
    
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Close modal functions
window.closePatientModal = () => document.getElementById('patient-modal').classList.remove('show');
window.closeEditarDatosModal = () => document.getElementById('editar-datos-modal').classList.remove('show');
window.closeGestionPagosModal = () => document.getElementById('gestion-pagos-modal').classList.remove('show');
window.closeRegistrarDeudaModal = () => {
    document.getElementById('registrar-deuda-modal').classList.remove('show');
    // Clear form
    document.getElementById('debt-concept').value = '';
    document.getElementById('debt-amount').value = '';
    document.getElementById('debt-due-date').value = '';
};
window.closeRegistrarPagoModal = () => {
    document.getElementById('registrar-pago-modal').classList.remove('show');
    // Clear selection state
    window.selectedDebtId = null;
    window.selectedDebtAmount = null;
    // Clear form
    document.getElementById('payment-amount').value = '';
    document.getElementById('payment-amount').disabled = true;
    document.getElementById('payment-amount').placeholder = 'Seleccione una deuda primero';
    document.getElementById('payment-method').value = 'cash';
    // Hide payment options
    const paymentOptions = document.getElementById('payment-options');
    if (paymentOptions) {
        paymentOptions.style.display = 'none';
    }
    // Clear debt selector selections
    document.querySelectorAll('.debt-option').forEach(opt => {
        opt.classList.remove('border-green-500', 'bg-green-50');
        opt.classList.add('border-gray-200');
    });
};
window.closeSaldoFavorModal = () => {
    document.getElementById('saldo-favor-modal').classList.remove('show');
    // Clear form
    document.getElementById('credit-amount').value = '';
    document.getElementById('credit-concept').value = '';
};
window.closeNotasModal = () => document.getElementById('notas-modal').classList.remove('show');
window.closeHistorialCitas = () => document.getElementById('historial-citas-modal').classList.remove('show');
window.closeDeletePatientModal = () => {
    document.getElementById('delete-patient-modal').classList.remove('show');
    patientToDelete = null;
};

// Export functions to window
window.openNewPatientModal = () => document.getElementById('patient-modal').classList.add('show');
window.openEditarDatosModal = openEditarDatosModal;
window.openGestionPagosModal = openGestionPagosModal;
window.openNotasModal = openNotasModal;
window.openHistorialCitas = openHistorialCitas;
window.saveEditarDatos = saveEditarDatos;
window.registrarDeuda = () => document.getElementById('registrar-deuda-modal').classList.add('show');
window.registrarPago = registrarPago;  // Updated to use new function
window.agregarSaldoFavor = () => document.getElementById('saldo-favor-modal').classList.add('show');
window.guardarDeuda = guardarDeuda;
window.guardarPago = guardarPago;
window.guardarSaldoFavor = guardarSaldoFavor;
window.agregarNota = agregarNota;
window.saveNoteFromModal = saveNoteFromModal;
window.showToast = showToast;
window.sendWhatsAppReminder = sendWhatsAppReminder;
window.togglePatientOptions = togglePatientOptions;
window.deletePatient = deletePatient;
window.confirmDeletePatient = confirmDeletePatient;