// Servicios.js - JavaScript específico para configuración de servicios médicos

// Global state
let serviciosMedicos = [];
let consultorios = [];
let selectedDoctors = [];
let hasUnsavedChanges = false;
let saveTimeout = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Servicios Médicos...');
    
    // Check authentication
    if (typeof isAuthenticated === 'function' && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    // Load initial data
    await loadServiciosData();
    await loadConsultorios();
    
    // Initialize UI
    initializeUI();
    
    // Set up event listeners
    setupEventListeners();
});

// Load servicios data from API
async function loadServiciosData() {
    console.log('Loading servicios data...');
    showLoading();
    
    try {
        // Load servicios
        const serviciosResponse = await api.makeRequest('/servicios/list');
        if (serviciosResponse && serviciosResponse.servicios) {
            serviciosMedicos = serviciosResponse.servicios;
            console.log('Servicios loaded:', serviciosMedicos);
        }
        
        // Load statistics
        await loadStatistics();
        
    } catch (error) {
        console.error('Error loading servicios data:', error);
        showToast('Error al cargar los servicios', 'error');
    } finally {
        hideLoading();
    }
}

// Load consultorios for selection
async function loadConsultorios() {
    try {
        const response = await api.makeRequest('/servicios/consultorios');
        if (response && response.consultorios) {
            consultorios = response.consultorios;
            console.log('Consultorios loaded:', consultorios);
        }
    } catch (error) {
        console.error('Error loading consultorios:', error);
        consultorios = [];
    }
}

// Load statistics
async function loadStatistics() {
    try {
        const statsResponse = await api.makeRequest('/servicios/stats');
        if (statsResponse) {
            updateStatisticsDisplay(statsResponse);
        }
    } catch (error) {
        console.error('Error loading statistics:', error);
    }
}

// Update statistics display
function updateStatisticsDisplay(stats) {
    // Update price breakdown if exists
    const priceBreakdownEl = document.getElementById('price-breakdown');
    if (priceBreakdownEl && stats.tipos_precio) {
        let breakdownHtml = '<div class="space-y-2">';
        
        if (stats.tipos_precio.precio_fijo > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm">
                <span>Precio fijo:</span>
                <span class="font-medium">${stats.tipos_precio.precio_fijo} servicios</span>
            </div>`;
        }
        
        if (stats.tipos_precio.precio_por_evaluar > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm">
                <span>Por evaluar:</span>
                <span class="font-medium">${stats.tipos_precio.precio_por_evaluar} servicios</span>
            </div>`;
        }
        
        if (stats.tipos_precio.gratis > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm">
                <span>Gratuitos:</span>
                <span class="font-medium">${stats.tipos_precio.gratis} servicios</span>
            </div>`;
        }
        
        if (stats.tipos_precio.precio_variable > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm">
                <span>Precio variable:</span>
                <span class="font-medium">${stats.tipos_precio.precio_variable} servicios</span>
            </div>`;
        }
        
        // Add consultorios and doctors stats
        if (stats.consultorios_usados > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm mt-3 pt-3 border-t">
                <span>Consultorios:</span>
                <span class="font-medium">${stats.consultorios_usados}</span>
            </div>`;
        }
        
        if (stats.total_doctores > 0) {
            breakdownHtml += `<div class="flex justify-between text-sm">
                <span>Doctores:</span>
                <span class="font-medium">${stats.total_doctores}</span>
            </div>`;
        }
        
        breakdownHtml += '</div>';
        priceBreakdownEl.innerHTML = breakdownHtml;
    }
    
    // Update services active count
    const servicesEl = document.querySelector('[data-stat="services"]');
    if (servicesEl) {
        servicesEl.textContent = serviciosMedicos.length;
    }
}

// Initialize UI
function initializeUI() {
    displayServicios();
    updateUI();
}

// Display servicios
function displayServicios() {
    const container = document.getElementById('servicios-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (serviciosMedicos.length === 0) {
        container.innerHTML = `
            <div class="text-center py-12 text-gray-500">
                <i class="fas fa-clipboard-list text-6xl mb-4 opacity-30"></i>
                <p class="text-lg font-medium mb-2">No tienes servicios configurados</p>
                <p class="text-sm">Haz clic en el botón de abajo para agregar tu primer servicio</p>
            </div>
        `;
        return;
    }
    
    // Sort by display_order
    const sortedServicios = [...serviciosMedicos].sort((a, b) => {
        const orderA = a.display_order !== undefined ? a.display_order : 999;
        const orderB = b.display_order !== undefined ? b.display_order : 999;
        return orderA - orderB;
    });
    
    sortedServicios.forEach((servicio, index) => {
        const servicioCard = createServicioCard(servicio, index);
        container.appendChild(servicioCard);
    });
}

// Create servicio card
function createServicioCard(servicio, index) {
    const card = document.createElement('div');
    card.className = 'servicio-card';
    card.dataset.servicioId = servicio.id;
    
    // Price display logic
    let priceDisplay = '';
    if (servicio.tipo_precio === 'gratis') {
        priceDisplay = '<span class="text-emerald-600 font-medium">Gratis</span>';
    } else if (servicio.tipo_precio === 'precio_por_evaluar') {
        priceDisplay = '<span class="text-amber-600 font-medium">A evaluar en consulta</span>';
    } else if (servicio.tipo_precio === 'precio_variable') {
        priceDisplay = `<span class="text-blue-600 font-medium">${servicio.precio_display}</span>`;
    } else if (servicio.precio) {
        priceDisplay = `<span class="text-gray-900 font-bold">${servicio.precio_display}</span>`;
    }
    
    // AI instructions indicator
    const hasAIInstructions = servicio.instrucciones_ia && servicio.instrucciones_ia.length > 0;
    
    // Consultorio display
    let consultorioInfo = '';
    if (servicio.consultorio) {
        const consultorioLabel = servicio.consultorio.es_principal ? 
            `${servicio.consultorio.nombre} <span class="text-xs text-amber-600">(Principal)</span>` : 
            servicio.consultorio.nombre;
        
        consultorioInfo = `
        <div class="servicio-location">
            <div class="text-xs font-semibold text-emerald-700 mb-1">
                <i class="fas fa-hospital mr-1"></i>
                Consultorio:
            </div>
            <div class="text-xs text-emerald-600">
                ${consultorioLabel}
            </div>
        </div>
        `;
    }
    
    // Doctors display
    let doctorsInfo = '';
    if (servicio.doctores_atienden && servicio.doctores_atienden.length > 0) {
        doctorsInfo = `
        <div class="servicio-doctors">
            <div class="text-xs font-semibold text-amber-700 mb-1">
                <i class="fas fa-user-md mr-1"></i>
                Doctores que atienden:
            </div>
            <div class="text-xs text-amber-600">
                ${servicio.doctores_display}
            </div>
        </div>
        `;
    }
    
    card.innerHTML = `
        <div class="servicio-header">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <h3 class="servicio-title" style="border-left: 4px solid ${servicio.color}; padding-left: 12px;">
                        ${servicio.nombre}
                    </h3>
                    <div class="servicio-meta">
                        <span class="meta-item">
                            <i class="fas fa-clock"></i>
                            ${servicio.duracion_display}
                        </span>
                        ${servicio.cantidad_consultas > 1 ? `
                        <span class="meta-item">
                            <i class="fas fa-calendar-check"></i>
                            ${servicio.consultas_display}
                        </span>
                        ` : ''}
                        <span class="meta-item">
                            ${priceDisplay}
                        </span>
                        ${hasAIInstructions ? `
                        <span class="meta-item text-purple-600" title="Tiene instrucciones para IA">
                            <i class="fas fa-robot"></i>
                        </span>
                        ` : ''}
                    </div>
                </div>
                <div class="flex gap-2">
                    <button class="icon-btn" onclick="editServicio('${servicio.id}')" title="Editar">
                        <i class="fas fa-edit"></i>
                    </button>
                    ${serviciosMedicos.length > 1 ? `
                    <button class="icon-btn delete-btn" onclick="deleteServicio('${servicio.id}')" title="Eliminar">
                        <i class="fas fa-trash"></i>
                    </button>
                    ` : ''}
                </div>
            </div>
        </div>
        
        <div class="servicio-description">
            ${servicio.descripcion}
        </div>
        
        ${consultorioInfo}
        ${doctorsInfo}
        
        ${servicio.instrucciones_ia ? `
        <div class="servicio-ai-instructions">
            <div class="text-xs font-semibold text-purple-700 mb-1">
                <i class="fas fa-robot mr-1"></i>
                Instrucciones para IA Secretaria:
            </div>
            <div class="text-xs text-purple-600 italic">
                "${servicio.instrucciones_ia}"
            </div>
        </div>
        ` : ''}
        
        ${servicio.instrucciones_paciente ? `
        <div class="servicio-patient-instructions">
            <div class="text-xs font-semibold text-blue-700 mb-1">
                <i class="fas fa-user mr-1"></i>
                Instrucciones para el paciente:
            </div>
            <div class="text-xs text-blue-600">
                ${servicio.instrucciones_paciente}
            </div>
        </div>
        ` : ''}
    `;
    
    return card;
}

// Add new servicio
async function addServicio() {
    openServicioModal();
}

// Edit servicio
async function editServicio(servicioId) {
    const servicio = serviciosMedicos.find(s => s.id === servicioId);
    if (!servicio) return;
    
    openServicioModal(servicio);
}

// Open servicio modal
function openServicioModal(servicio = null) {
    const modal = document.getElementById('servicio-modal');
    if (!modal) return;
    
    const isEdit = servicio !== null;
    const modalTitle = modal.querySelector('h3');
    modalTitle.textContent = isEdit ? 'Editar Servicio Médico' : 'Nuevo Servicio Médico';
    
    // Reset doctors list
    selectedDoctors = servicio?.doctores_atienden || [];
    
    // Set form values
    modal.querySelector('[name="nombre"]').value = servicio?.nombre || '';
    modal.querySelector('[name="descripcion"]').value = servicio?.descripcion || '';
    modal.querySelector('[name="duracion_minutos"]').value = servicio?.duracion_minutos || 30;
    modal.querySelector('[name="cantidad_consultas"]').value = servicio?.cantidad_consultas || 1;
    
    // Set tipo precio
    const tipoPrecio = servicio?.tipo_precio || 'precio_fijo';
    modal.querySelector('[name="tipo_precio"]').value = tipoPrecio;
    
    // Set precio values based on type
    if (tipoPrecio === 'precio_fijo') {
        modal.querySelector('[name="precio"]').value = servicio?.precio ? (servicio.precio / 100) : '';
    } else if (tipoPrecio === 'precio_variable') {
        modal.querySelector('[name="precio_minimo"]').value = servicio?.precio_minimo ? (servicio.precio_minimo / 100) : '';
        modal.querySelector('[name="precio_maximo"]').value = servicio?.precio_maximo ? (servicio.precio_maximo / 100) : '';
    }
    
    modal.querySelector('[name="instrucciones_ia"]').value = servicio?.instrucciones_ia || '';
    modal.querySelector('[name="instrucciones_paciente"]').value = servicio?.instrucciones_paciente || '';
    
    // Store servicio ID for editing
    modal.dataset.servicioId = servicio?.id || '';
    
    // Load consultorios selector
    loadConsultoriosSelector(servicio?.consultorio_id);
    
    // Display doctor tags
    displayDoctorTags();
    
    // Update price fields visibility
    updatePriceFields();
    
    // Show modal
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
}

// Load consultorios selector
function loadConsultoriosSelector(selectedConsultorioId = null) {
    const selector = document.getElementById('consultorio-selector');
    const alertDiv = document.getElementById('no-consultorio-alert');
    
    if (!selector) return;
    
    // Clear existing content
    selector.innerHTML = '';
    
    // Check if there are consultorios
    if (!consultorios || consultorios.length === 0) {
        // Show alert
        if (alertDiv) {
            alertDiv.classList.remove('hidden');
        }
        selector.style.display = 'none';
        return;
    }
    
    // Hide alert
    if (alertDiv) {
        alertDiv.classList.add('hidden');
    }
    selector.style.display = '';
    
    // Find the principal consultorio
    const principalConsultorio = consultorios.find(c => c.es_principal);
    
    // If no consultorio is selected and there's a principal, select it
    if (!selectedConsultorioId && principalConsultorio) {
        selectedConsultorioId = principalConsultorio.id;
    }
    
    // Create consultorio options
    consultorios.forEach(consultorio => {
        const option = document.createElement('div');
        option.className = 'consultorio-option';
        
        // Determine if this should be selected
        const isSelected = consultorio.id === selectedConsultorioId;
        
        // Create the photo/icon display
        let photoHtml = '';
        if (consultorio.foto && consultorio.foto.url) {
            photoHtml = `<img src="${consultorio.foto.url}" alt="${consultorio.nombre}" class="consultorio-option-image">`;
        } else if (consultorio.foto && consultorio.foto.color) {
            photoHtml = `<div class="consultorio-option-image" style="background: ${consultorio.foto.color};">
                <i class="fas fa-hospital text-white"></i>
            </div>`;
        } else {
            photoHtml = `<div class="consultorio-option-image" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <i class="fas fa-hospital text-white"></i>
            </div>`;
        }
        
        option.innerHTML = `
            <input type="radio" 
                   name="consultorio_id" 
                   value="${consultorio.id}" 
                   id="consultorio-${consultorio.id}"
                   ${isSelected ? 'checked' : ''}>
            <label for="consultorio-${consultorio.id}" class="consultorio-option-label">
                ${photoHtml}
                <div class="consultorio-option-name">${consultorio.nombre}</div>
            </label>
            ${consultorio.es_principal ? '<span class="consultorio-option-badge">Principal</span>' : ''}
        `;
        
        selector.appendChild(option);
    });
}

// Handle doctor input keypress
window.handleDoctorInputKeypress = function(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        addDoctor();
    }
};

// Add doctor to list
window.addDoctor = function() {
    const input = document.getElementById('doctor-input');
    if (!input) return;
    
    const doctorName = input.value.trim();
    if (!doctorName) {
        showToast('Por favor ingresa el nombre del doctor', 'warning');
        return;
    }
    
    // Check if already exists
    if (selectedDoctors.includes(doctorName)) {
        showToast('Este doctor ya está en la lista', 'warning');
        return;
    }
    
    // Add to list
    selectedDoctors.push(doctorName);
    
    // Clear input
    input.value = '';
    
    // Update display
    displayDoctorTags();
};

// Remove doctor from list
window.removeDoctor = function(index) {
    selectedDoctors.splice(index, 1);
    displayDoctorTags();
};

// Display doctor tags
function displayDoctorTags() {
    const container = document.getElementById('doctor-tags');
    if (!container) return;
    
    container.innerHTML = '';
    
    selectedDoctors.forEach((doctor, index) => {
        const tag = document.createElement('div');
        tag.className = 'doctor-tag';
        tag.innerHTML = `
            <span>${doctor}</span>
            <i class="fas fa-times remove-tag" onclick="removeDoctor(${index})"></i>
        `;
        container.appendChild(tag);
    });
}

// Update price fields based on type
function updatePriceFields() {
    const modal = document.getElementById('servicio-modal');
    const tipoPrecio = modal.querySelector('[name="tipo_precio"]').value;
    
    // Hide all price fields first
    document.getElementById('precio-fijo-field').classList.add('hidden');
    document.getElementById('precio-variable-fields').classList.add('hidden');
    
    // Show relevant fields
    if (tipoPrecio === 'precio_fijo') {
        document.getElementById('precio-fijo-field').classList.remove('hidden');
    } else if (tipoPrecio === 'precio_variable') {
        document.getElementById('precio-variable-fields').classList.remove('hidden');
    }
}

// Save servicio
async function saveServicio() {
    const modal = document.getElementById('servicio-modal');
    const servicioId = modal.dataset.servicioId;
    const isEdit = servicioId && servicioId !== '';
    
    // Get selected consultorio
    const selectedConsultorioRadio = modal.querySelector('[name="consultorio_id"]:checked');
    const consultorioId = selectedConsultorioRadio ? selectedConsultorioRadio.value : null;
    
    // Get form values
    const formData = {
        nombre: modal.querySelector('[name="nombre"]').value.trim(),
        descripcion: modal.querySelector('[name="descripcion"]').value.trim(),
        duracion_minutos: parseInt(modal.querySelector('[name="duracion_minutos"]').value),
        cantidad_consultas: parseInt(modal.querySelector('[name="cantidad_consultas"]').value),
        tipo_precio: modal.querySelector('[name="tipo_precio"]').value,
        instrucciones_ia: modal.querySelector('[name="instrucciones_ia"]').value.trim(),
        instrucciones_paciente: modal.querySelector('[name="instrucciones_paciente"]').value.trim(),
        consultorio_id: consultorioId,
        doctores_atienden: selectedDoctors
    };
    
    // Validate required fields
    if (!formData.nombre) {
        showToast('El nombre del servicio es obligatorio', 'error');
        return;
    }
    
    if (!formData.descripcion || formData.descripcion.length < 10) {
        showToast('La descripción debe tener al menos 10 caracteres', 'error');
        return;
    }
    
    // Set price based on type
    if (formData.tipo_precio === 'precio_fijo') {
        const precio = parseFloat(modal.querySelector('[name="precio"]').value);
        if (isNaN(precio) || precio < 0) {
            showToast('Por favor ingresa un precio válido', 'error');
            return;
        }
        formData.precio = Math.round(precio * 100); // Convert to cents
    } else if (formData.tipo_precio === 'precio_variable') {
        const precioMin = parseFloat(modal.querySelector('[name="precio_minimo"]').value);
        const precioMax = parseFloat(modal.querySelector('[name="precio_maximo"]').value);
        
        if (isNaN(precioMin) || isNaN(precioMax) || precioMin < 0 || precioMax < 0) {
            showToast('Por favor ingresa precios válidos', 'error');
            return;
        }
        
        if (precioMin >= precioMax) {
            showToast('El precio máximo debe ser mayor al mínimo', 'error');
            return;
        }
        
        formData.precio_minimo = Math.round(precioMin * 100);
        formData.precio_maximo = Math.round(precioMax * 100);
    }
    
    showLoading();
    
    try {
        let response;
        if (isEdit) {
            response = await api.makeRequest(`/servicios/${servicioId}`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
        } else {
            response = await api.makeRequest('/servicios/create', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
        }
        
        // Reload servicios and consultorios
        await loadServiciosData();
        await loadConsultorios();
        
        closeModal();
        showToast(isEdit ? 'Servicio actualizado' : 'Servicio creado', 'success');
        
    } catch (error) {
        console.error('Error saving servicio:', error);
        showToast('Error al guardar el servicio', 'error');
    } finally {
        hideLoading();
    }
}

// Delete servicio
async function deleteServicio(servicioId) {
    const servicio = serviciosMedicos.find(s => s.id === servicioId);
    if (!servicio) return;
    
    if (!confirm(`¿Estás seguro de eliminar el servicio "${servicio.nombre}"?`)) {
        return;
    }
    
    showLoading();
    
    try {
        await api.makeRequest(`/servicios/${servicioId}`, {
            method: 'DELETE'
        });
        
        // Reload servicios
        await loadServiciosData();
        
        showToast('Servicio eliminado', 'success');
        
    } catch (error) {
        console.error('Error deleting servicio:', error);
        showToast('Error al eliminar el servicio', 'error');
    } finally {
        hideLoading();
    }
}

// Update UI elements
function updateUI() {
    // Update service count
    const countEl = document.getElementById('service-count');
    if (countEl) {
        countEl.textContent = `${serviciosMedicos.length} servicio${serviciosMedicos.length !== 1 ? 's' : ''} configurado${serviciosMedicos.length !== 1 ? 's' : ''}`;
    }
    
    // Update services active stat
    const servicesStatEl = document.querySelector('[data-stat="services"]');
    if (servicesStatEl) {
        servicesStatEl.textContent = serviciosMedicos.length;
    }
}

// Setup event listeners
function setupEventListeners() {
    // Tipo precio change
    const tipoPrecioSelect = document.querySelector('[name="tipo_precio"]');
    if (tipoPrecioSelect) {
        tipoPrecioSelect.addEventListener('change', updatePriceFields);
    }
}

// Utility functions
function closeModal() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
    document.body.style.overflow = '';
    
    // Reset selected doctors
    selectedDoctors = [];
    
    // Clear doctor input
    const doctorInput = document.getElementById('doctor-input');
    if (doctorInput) {
        doctorInput.value = '';
    }
}

function showLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.classList.remove('hidden');
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
window.addServicio = addServicio;
window.editServicio = editServicio;
window.deleteServicio = deleteServicio;
window.saveServicio = saveServicio;
window.updatePriceFields = updatePriceFields;
window.closeModal = closeModal;
window.toggleSidebar = toggleSidebar;