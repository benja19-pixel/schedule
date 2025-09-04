// Consultorios.js - Complete JavaScript for managing medical offices/locations
// FIXED: Proper reset of location data and Google Maps URL handling

// Global variables
let consultorios = [];
let currentConsultorio = null;
let editingConsultorioId = null;
let map = null;
let marker = null;
let mapPreview = null;
let markerPreview = null;
let pendingDeleteId = null;
let currentLocation = null;
let fotoPrincipalFile = null;
let fotosSecundarias = [];
let carouselStates = {}; // Track carousel state for each card
let useVirtualSecretaryPhone = false;
let isFirstConsultorio = false; // Track if this is the user's first consultorio

// Mexican states list
const ESTADOS_MEXICO = [
    'Aguascalientes',
    'Baja California',
    'Baja California Sur',
    'Campeche',
    'Chiapas',
    'Chihuahua',
    'Ciudad de México',
    'Coahuila',
    'Colima',
    'Durango',
    'Estado de México',
    'Guanajuato',
    'Guerrero',
    'Hidalgo',
    'Jalisco',
    'Michoacán',
    'Morelos',
    'Nayarit',
    'Nuevo León',
    'Oaxaca',
    'Puebla',
    'Querétaro',
    'Quintana Roo',
    'San Luis Potosí',
    'Sinaloa',
    'Sonora',
    'Tabasco',
    'Tamaulipas',
    'Tlaxcala',
    'Veracruz',
    'Yucatán',
    'Zacatecas'
];

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    console.log('Initializing Consultorios...');
    
    // Check authentication
    if (typeof isAuthenticated === 'function' && !isAuthenticated()) {
        window.location.href = '/login';
        return;
    }
    
    // Initialize UI
    initializeUI();
    
    // Load consultorios
    await loadConsultorios();
});

// Initialize UI elements
function initializeUI() {
    // Add consultorio button
    const addBtn = document.getElementById('add-consultorio-btn');
    if (addBtn) {
        addBtn.addEventListener('click', () => openConsultorioModal());
    }
    
    // Form submit prevention
    const form = document.getElementById('consultorio-form');
    if (form) {
        form.addEventListener('submit', (e) => {
            e.preventDefault();
            saveConsultorio();
        });
    }
    
    // Location preview on address change
    const addressFields = ['calle', 'numero', 'colonia', 'ciudad', 'estado', 'codigo_postal', 'pais'];
    addressFields.forEach(field => {
        const element = document.getElementById(field);
        if (element) {
            element.addEventListener('change', () => {
                // FIXED: Clear map preview and reset location when address changes
                const mapContainer = document.getElementById('map-preview-container');
                if (mapContainer && !mapContainer.classList.contains('hidden')) {
                    mapContainer.classList.add('hidden');
                }
                // Reset current location when address fields change
                if (currentLocation && !currentLocation.markerAdjusted) {
                    currentLocation = null;
                }
            });
        }
    });
    
    // Handle country change for states list
    const paisSelect = document.getElementById('pais');
    if (paisSelect) {
        paisSelect.addEventListener('change', handleCountryChange);
    }
    
    // Initialize states datalist
    setupStatesDatalist();
}

// Setup states datalist
function setupStatesDatalist() {
    const datalist = document.getElementById('estados-mexico');
    if (datalist) {
        datalist.innerHTML = ESTADOS_MEXICO.map(estado => 
            `<option value="${estado}">`
        ).join('');
    }
}

// Handle country change
function handleCountryChange() {
    const paisSelect = document.getElementById('pais');
    const estadoInput = document.getElementById('estado');
    
    if (!paisSelect || !estadoInput) return;
    
    const country = paisSelect.value.toLowerCase();
    
    // Check if Mexico is selected (handle variations)
    if (country === 'méxico' || country === 'mexico' || country === 'mex' || country === 'mx') {
        // Set datalist for Mexican states
        estadoInput.setAttribute('list', 'estados-mexico');
        estadoInput.placeholder = 'Selecciona o escribe un estado';
    } else {
        // Remove datalist for other countries
        estadoInput.removeAttribute('list');
        estadoInput.placeholder = 'Ej: California';
    }
}

// Load all consultorios
async function loadConsultorios() {
    showLoading('Cargando consultorios...');
    
    try {
        const response = await api.makeRequest('/consultorios');
        
        if (response && response.consultorios) {
            consultorios = response.consultorios;
            isFirstConsultorio = consultorios.length === 0;
            renderConsultorios();
        }
    } catch (error) {
        console.error('Error loading consultorios:', error);
        showToast('Error al cargar los consultorios', 'error');
    } finally {
        hideLoading();
    }
}

// Render consultorios grid
function renderConsultorios() {
    const grid = document.getElementById('consultorios-grid');
    const emptyState = document.getElementById('empty-state');
    
    if (!grid) return;
    
    if (consultorios.length === 0) {
        grid.classList.add('hidden');
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }
    
    grid.classList.remove('hidden');
    if (emptyState) emptyState.classList.add('hidden');
    
    grid.innerHTML = '';
    
    consultorios.forEach(consultorio => {
        const card = createConsultorioCard(consultorio);
        grid.appendChild(card);
    });
}

// Create consultorio card with carousel
function createConsultorioCard(consultorio) {
    const card = document.createElement('div');
    card.className = 'consultorio-card';
    card.dataset.consultorioId = consultorio.id;
    
    // Initialize carousel state
    carouselStates[consultorio.id] = 0;
    
    // Prepare all images (main + secondary)
    const allImages = [];
    
    // Add main photo if exists
    if (consultorio.foto_principal) {
        if (consultorio.foto_principal.url) {
            allImages.push({
                type: 'image',
                url: consultorio.foto_principal.url,
                isMain: true
            });
        } else if (consultorio.foto_principal.color) {
            allImages.push({
                type: 'color',
                color: consultorio.foto_principal.color,
                isMain: true
            });
        }
    } else {
        allImages.push({
            type: 'gradient',
            isMain: true
        });
    }
    
    // Add secondary photos
    if (consultorio.fotos_secundarias && consultorio.fotos_secundarias.length > 0) {
        consultorio.fotos_secundarias.forEach(foto => {
            allImages.push({
                type: 'image',
                url: foto.url || foto.thumbnail,
                caption: foto.caption
            });
        });
    }
    
    // Create carousel HTML
    let carouselHTML = '';
    if (allImages.length > 1) {
        // Multiple images - create carousel
        carouselHTML = `
            <div class="card-carousel">
                <div class="card-carousel-images" data-consultorio-id="${consultorio.id}">
                    ${allImages.map((img, index) => {
                        if (img.type === 'image') {
                            return `<div class="card-carousel-image" style="background-image: url('${img.url}');"></div>`;
                        } else if (img.type === 'color') {
                            return `<div class="card-carousel-image" style="background-color: ${img.color};">
                                <i class="fas fa-hospital text-white text-4xl opacity-50"></i>
                            </div>`;
                        } else {
                            return `<div class="card-carousel-image" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                                <i class="fas fa-hospital text-white text-4xl opacity-50"></i>
                            </div>`;
                        }
                    }).join('')}
                </div>
                <button onclick="moveCarousel('${consultorio.id}', -1)" class="carousel-nav prev">
                    <i class="fas fa-chevron-left text-gray-600"></i>
                </button>
                <button onclick="moveCarousel('${consultorio.id}', 1)" class="carousel-nav next">
                    <i class="fas fa-chevron-right text-gray-600"></i>
                </button>
                <div class="carousel-indicators">
                    ${allImages.map((_, index) => 
                        `<div class="carousel-indicator ${index === 0 ? 'active' : ''}" 
                              onclick="goToSlide('${consultorio.id}', ${index})"></div>`
                    ).join('')}
                </div>
            </div>
        `;
    } else {
        // Single image or color
        const img = allImages[0];
        if (img.type === 'image') {
            carouselHTML = `<div class="card-carousel-image" style="background-image: url('${img.url}');"></div>`;
        } else if (img.type === 'color') {
            carouselHTML = `<div class="card-carousel-image" style="background-color: ${img.color};">
                <i class="fas fa-hospital text-white text-4xl opacity-50"></i>
            </div>`;
        } else {
            carouselHTML = `<div class="card-carousel-image" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
                <i class="fas fa-hospital text-white text-4xl opacity-50"></i>
            </div>`;
        }
    }
    
    // Principal badge
    const principalBadge = consultorio.es_principal ? 
        '<span class="principal-badge">Principal</span>' : '';
    
    // Parking icon
    const parkingIcon = consultorio.tiene_estacionamiento ? 
        '<i class="fas fa-parking text-blue-500" title="Con estacionamiento"></i>' : '';
    
    // Accessibility icon
    const accessibilityIcon = getAccessibilityIcon(consultorio.accesibilidad);
    
    // Short address
    const shortAddress = `${consultorio.calle} ${consultorio.numero}, ${consultorio.ciudad}`;
    
    card.innerHTML = `
        <div class="card-header">
            ${carouselHTML}
            ${principalBadge}
            <div class="card-actions">
                <button onclick="editConsultorio('${consultorio.id}')" class="card-action-btn">
                    <i class="fas fa-edit"></i>
                </button>
                <button onclick="deleteConsultorio('${consultorio.id}')" class="card-action-btn">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
        <div class="card-body">
            <h3 class="card-title">${consultorio.nombre}</h3>
            <p class="card-address">
                <i class="fas fa-map-marker-alt text-gray-400 mr-1"></i>
                ${shortAddress}
            </p>
            ${consultorio.notas ? `<p class="card-notes">${consultorio.notas}</p>` : ''}
            <div class="card-features">
                ${parkingIcon}
                ${accessibilityIcon}
            </div>
            ${consultorio.google_maps_url ? `
            <a href="${consultorio.google_maps_url}" target="_blank" class="card-map-link">
                <i class="fas fa-map mr-1"></i>
                Ver en Google Maps
            </a>
            ` : ''}
        </div>
    `;
    
    return card;
}

// Carousel navigation functions
window.moveCarousel = function(consultorioId, direction) {
    const carousel = document.querySelector(`.card-carousel-images[data-consultorio-id="${consultorioId}"]`);
    const indicators = carousel.parentElement.querySelectorAll('.carousel-indicator');
    const totalImages = carousel.children.length;
    
    // Update state
    carouselStates[consultorioId] = (carouselStates[consultorioId] + direction + totalImages) % totalImages;
    const currentIndex = carouselStates[consultorioId];
    
    // Move carousel
    carousel.style.transform = `translateX(-${currentIndex * 100}%)`;
    
    // Update indicators
    indicators.forEach((indicator, index) => {
        indicator.classList.toggle('active', index === currentIndex);
    });
};

window.goToSlide = function(consultorioId, slideIndex) {
    const carousel = document.querySelector(`.card-carousel-images[data-consultorio-id="${consultorioId}"]`);
    const indicators = carousel.parentElement.querySelectorAll('.carousel-indicator');
    
    // Update state
    carouselStates[consultorioId] = slideIndex;
    
    // Move carousel
    carousel.style.transform = `translateX(-${slideIndex * 100}%)`;
    
    // Update indicators
    indicators.forEach((indicator, index) => {
        indicator.classList.toggle('active', index === slideIndex);
    });
};

// Get accessibility icon
function getAccessibilityIcon(accessibility) {
    const icons = {
        'todos': '<i class="fas fa-wheelchair text-green-500" title="Accesible para todos"></i>',
        'con_discapacidad': '<i class="fas fa-wheelchair text-blue-500" title="Accesible para personas con discapacidad"></i>',
        'sin_discapacidad': '<i class="fas fa-walking text-gray-500" title="Solo personas sin discapacidad"></i>',
        'limitada': '<i class="fas fa-exclamation-triangle text-yellow-500" title="Accesibilidad limitada"></i>'
    };
    
    return icons[accessibility] || '';
}

// Open consultorio modal
function openConsultorioModal(consultorioId = null) {
    const modal = document.getElementById('consultorio-modal');
    const modalTitle = document.getElementById('modal-title');
    const saveBtn = document.getElementById('save-btn-text');
    const principalCheckbox = document.getElementById('es_principal');
    const principalContainer = principalCheckbox?.closest('.flex');
    
    if (!modal) return;
    
    // FIXED: Always reset form and state completely
    resetConsultorioForm();
    
    // FIXED: Explicitly reset location state
    currentLocation = null;
    mapPreview = null;
    markerPreview = null;
    
    // Check if this is the first consultorio
    isFirstConsultorio = consultorios.length === 0;
    
    if (consultorioId) {
        // Edit mode
        editingConsultorioId = consultorioId;
        modalTitle.textContent = 'Editar Consultorio';
        saveBtn.textContent = 'Actualizar Consultorio';
        
        // Load consultorio data
        const consultorio = consultorios.find(c => c.id === consultorioId);
        if (consultorio) {
            // FIXED: Load data AFTER resetting state
            loadConsultorioIntoForm(consultorio);
            
            // Check if this is the only consultorio
            const activeConsultorios = consultorios.filter(c => c.activo !== false);
            if (activeConsultorios.length === 1 && consultorio.es_principal) {
                // It's the only consultorio and it's principal - can't uncheck
                principalCheckbox.disabled = true;
                if (principalContainer) {
                    // Add info message
                    let infoMsg = principalContainer.querySelector('.principal-info-msg');
                    if (!infoMsg) {
                        infoMsg = document.createElement('span');
                        infoMsg.className = 'principal-info-msg text-xs text-amber-600 ml-2';
                        infoMsg.innerHTML = '<i class="fas fa-info-circle mr-1"></i>No se puede quitar (único consultorio)';
                        principalContainer.appendChild(infoMsg);
                    }
                }
            } else {
                principalCheckbox.disabled = false;
                // Remove info message if exists
                const infoMsg = principalContainer?.querySelector('.principal-info-msg');
                if (infoMsg) infoMsg.remove();
            }
        }
    } else {
        // Create mode
        editingConsultorioId = null;
        modalTitle.textContent = 'Nuevo Consultorio';
        saveBtn.textContent = 'Guardar Consultorio';
        
        // Set default color for header
        const headerPhoto = document.getElementById('modal-header-photo');
        const defaultColor = generateRandomColor();
        headerPhoto.style.background = defaultColor;
        headerPhoto.style.backgroundImage = '';
        
        // Handle first consultorio
        if (isFirstConsultorio) {
            // First consultorio MUST be principal
            principalCheckbox.checked = true;
            principalCheckbox.disabled = true;
            
            if (principalContainer) {
                // Add informative message
                let infoMsg = principalContainer.querySelector('.principal-info-msg');
                if (!infoMsg) {
                    infoMsg = document.createElement('span');
                    infoMsg.className = 'principal-info-msg text-xs text-emerald-600 ml-2';
                    infoMsg.innerHTML = '<i class="fas fa-star mr-1"></i>Tu primer consultorio será el principal';
                    principalContainer.appendChild(infoMsg);
                }
            }
            
            // Show first consultorio banner
            showFirstConsultorioBanner();
        } else {
            principalCheckbox.disabled = false;
            // Remove info message if exists
            const infoMsg = principalContainer?.querySelector('.principal-info-msg');
            if (infoMsg) infoMsg.remove();
        }
    }
    
    // Trigger country change to setup states
    handleCountryChange();
    
    modal.classList.add('show');
}

// Show banner for first consultorio
function showFirstConsultorioBanner() {
    const modalBody = document.querySelector('.modal-body');
    if (!modalBody) return;
    
    // Check if banner already exists
    if (modalBody.querySelector('.first-consultorio-banner')) return;
    
    const banner = document.createElement('div');
    banner.className = 'first-consultorio-banner bg-gradient-to-r from-emerald-50 to-teal-50 border border-emerald-200 rounded-lg p-4 mb-6';
    banner.innerHTML = `
        <div class="flex items-start gap-3">
            <div class="flex-shrink-0 w-10 h-10 bg-emerald-100 rounded-full flex items-center justify-center">
                <i class="fas fa-star text-emerald-600"></i>
            </div>
            <div>
                <h4 class="font-semibold text-emerald-800 mb-1">¡Bienvenido! Este será tu consultorio principal</h4>
                <p class="text-sm text-emerald-700">
                    Tu primer consultorio se establecerá automáticamente como principal. 
                    Aquí es donde tus pacientes te encontrarán por defecto.
                </p>
            </div>
        </div>
    `;
    
    // Insert at the beginning of modal body
    modalBody.insertBefore(banner, modalBody.firstChild);
}

// Toggle phone virtual secretary
window.toggleVirtualSecretaryPhone = function() {
    const toggle = document.getElementById('use-virtual-phone-toggle');
    const phoneField = document.getElementById('telefono_consultorio');
    const phoneContainer = document.getElementById('phone-field-container');
    
    useVirtualSecretaryPhone = !useVirtualSecretaryPhone;
    
    toggle.classList.toggle('active', useVirtualSecretaryPhone);
    
    if (useVirtualSecretaryPhone) {
        phoneContainer.style.display = 'none';
        phoneField.value = '';
        phoneField.disabled = true;
    } else {
        phoneContainer.style.display = 'block';
        phoneField.disabled = false;
    }
};

// Close consultorio modal
function closeConsultorioModal() {
    const modal = document.getElementById('consultorio-modal');
    if (modal) {
        modal.classList.remove('show');
    }
    
    // Remove first consultorio banner if exists
    const banner = document.querySelector('.first-consultorio-banner');
    if (banner) banner.remove();
    
    // FIXED: Complete reset of all state
    editingConsultorioId = null;
    currentConsultorio = null;
    fotoPrincipalFile = null;
    fotosSecundarias = [];
    useVirtualSecretaryPhone = false;
    isFirstConsultorio = false;
    currentLocation = null;  // FIXED: Reset location
    
    // FIXED: Destroy map instances
    if (mapPreview) {
        mapPreview = null;
        markerPreview = null;
        // Clear the map div content
        const mapDiv = document.getElementById('map-preview');
        if (mapDiv) {
            mapDiv.innerHTML = '';
        }
    }
}

// Reset form
function resetConsultorioForm() {
    const form = document.getElementById('consultorio-form');
    if (form) form.reset();
    
    // Reset header photo
    const headerPhoto = document.getElementById('modal-header-photo');
    headerPhoto.style.backgroundImage = '';
    headerPhoto.style.backgroundColor = generateRandomColor();
    
    // Hide map preview
    const mapContainer = document.getElementById('map-preview-container');
    if (mapContainer) mapContainer.classList.add('hidden');
    
    // FIXED: Clear map div content
    const mapDiv = document.getElementById('map-preview');
    if (mapDiv) {
        mapDiv.innerHTML = '';
    }
    
    // Clear secondary photos
    renderSecondaryPhotos([]);
    
    // Hide extras
    const extrasSection = document.getElementById('extras-section');
    if (extrasSection) extrasSection.classList.add('hidden');
    
    // Reset icon
    const extrasIcon = document.getElementById('extras-icon');
    if (extrasIcon) extrasIcon.classList.remove('fa-chevron-up');
    if (extrasIcon) extrasIcon.classList.add('fa-chevron-down');
    
    // Reset phone toggle
    useVirtualSecretaryPhone = false;
    const toggle = document.getElementById('use-virtual-phone-toggle');
    if (toggle) toggle.classList.remove('active');
    const phoneContainer = document.getElementById('phone-field-container');
    if (phoneContainer) phoneContainer.style.display = 'block';
    const phoneField = document.getElementById('telefono_consultorio');
    if (phoneField) phoneField.disabled = false;
    
    // Remove any info messages
    const infoMsgs = document.querySelectorAll('.principal-info-msg');
    infoMsgs.forEach(msg => msg.remove());
    
    // FIXED: Reset all location-related state
    currentLocation = null;
    mapPreview = null;
    markerPreview = null;
    fotoPrincipalFile = null;
    fotosSecundarias = [];
}

// Load consultorio data into form
function loadConsultorioIntoForm(consultorio) {
    // FIXED: Reset location state before loading new data
    currentLocation = null;
    
    // Basic fields
    document.getElementById('nombre').value = consultorio.nombre || '';
    document.getElementById('es_principal').checked = consultorio.es_principal || false;
    
    // Address fields
    document.getElementById('pais').value = consultorio.pais || 'México';
    document.getElementById('estado').value = consultorio.estado || '';
    document.getElementById('ciudad').value = consultorio.ciudad || '';
    document.getElementById('calle').value = consultorio.calle || '';
    document.getElementById('numero').value = consultorio.numero || '';
    document.getElementById('colonia').value = consultorio.colonia || '';
    document.getElementById('codigo_postal').value = consultorio.codigo_postal || '';
    
    // Extra fields
    document.getElementById('notas').value = consultorio.notas || '';
    document.getElementById('tiene_estacionamiento').checked = consultorio.tiene_estacionamiento || false;
    document.getElementById('accesibilidad').value = consultorio.accesibilidad || 'todos';
    
    // Phone handling
    if (consultorio.usa_telefono_virtual) {
        useVirtualSecretaryPhone = true;
        document.getElementById('use-virtual-phone-toggle').classList.add('active');
        document.getElementById('phone-field-container').style.display = 'none';
        document.getElementById('telefono_consultorio').disabled = true;
    } else {
        document.getElementById('telefono_consultorio').value = consultorio.telefono_consultorio || '';
    }
    
    document.getElementById('email_consultorio').value = consultorio.email_consultorio || '';
    
    // Header photo
    const headerPhoto = document.getElementById('modal-header-photo');
    if (consultorio.foto_principal && consultorio.foto_principal.url) {
        headerPhoto.style.backgroundImage = `url('${consultorio.foto_principal.url}')`;
        headerPhoto.style.backgroundColor = '';
    } else if (consultorio.foto_principal && consultorio.foto_principal.color) {
        headerPhoto.style.backgroundColor = consultorio.foto_principal.color;
        headerPhoto.style.backgroundImage = '';
    }
    
    // Secondary photos
    if (consultorio.fotos_secundarias && consultorio.fotos_secundarias.length > 0) {
        fotosSecundarias = consultorio.fotos_secundarias;
        renderSecondaryPhotos(fotosSecundarias);
    }
    
    // FIXED: Store current location properly for this specific consultorio
    if (consultorio.latitud && consultorio.longitud) {
        currentLocation = {
            lat: consultorio.latitud,
            lng: consultorio.longitud,
            google_maps_url: consultorio.google_maps_url,
            markerAdjusted: consultorio.marcador_ajustado || false,
            consultorioId: consultorio.id  // FIXED: Track which consultorio this location belongs to
        };
    }
}

// Save consultorio
async function saveConsultorio() {
    // Validate form
    const requiredFields = ['nombre', 'pais', 'estado', 'ciudad', 'calle', 'numero', 'codigo_postal'];
    const formData = {};
    
    for (const field of requiredFields) {
        const value = document.getElementById(field).value.trim();
        if (!value) {
            showToast(`Por favor completa el campo: ${field.replace('_', ' ')}`, 'error');
            return;
        }
        formData[field] = value;
    }
    
    // Add optional fields
    formData.colonia = document.getElementById('colonia').value.trim();
    
    // Handle principal checkbox
    if (isFirstConsultorio && !editingConsultorioId) {
        // Force first consultorio to be principal
        formData.es_principal = true;
    } else {
        // For existing consultorios or when there are already consultorios
        const principalCheckbox = document.getElementById('es_principal');
        
        // Check if trying to uncheck the only consultorio
        if (editingConsultorioId) {
            const activeConsultorios = consultorios.filter(c => c.activo !== false);
            const currentConsultorio = consultorios.find(c => c.id === editingConsultorioId);
            
            if (activeConsultorios.length === 1 && currentConsultorio?.es_principal && !principalCheckbox.checked) {
                showToast('No puedes quitar el estado principal del único consultorio activo', 'error');
                return;
            }
        }
        
        formData.es_principal = principalCheckbox.checked;
    }
    
    formData.notas = document.getElementById('notas').value.trim();
    formData.tiene_estacionamiento = document.getElementById('tiene_estacionamiento').checked;
    formData.accesibilidad = document.getElementById('accesibilidad').value;
    
    // Handle phone based on toggle - send boolean flag
    formData.usa_telefono_virtual = useVirtualSecretaryPhone;
    if (!useVirtualSecretaryPhone) {
        formData.telefono_consultorio = document.getElementById('telefono_consultorio').value.trim();
    }
    
    formData.email_consultorio = document.getElementById('email_consultorio').value.trim();
    
    // FIXED: Only add marker coordinates if they belong to THIS consultorio
    if (currentLocation && currentLocation.markerAdjusted) {
        // Only use the location if it's not from another consultorio
        if (!editingConsultorioId || currentLocation.consultorioId === editingConsultorioId || !currentLocation.consultorioId) {
            formData.marcador_latitud = currentLocation.lat;
            formData.marcador_longitud = currentLocation.lng;
        }
    }
    
    showLoading('Guardando consultorio...');
    
    try {
        let response;
        let consultorioId;
        
        if (editingConsultorioId) {
            // Update existing
            response = await api.makeRequest(`/consultorios/${editingConsultorioId}`, {
                method: 'PUT',
                body: JSON.stringify(formData)
            });
            consultorioId = editingConsultorioId;
        } else {
            // Create new
            response = await api.makeRequest('/consultorios', {
                method: 'POST',
                body: JSON.stringify(formData)
            });
            consultorioId = response.consultorio.id;
            
            // Show success message for first consultorio
            if (isFirstConsultorio) {
                showToast('¡Felicidades! Tu primer consultorio ha sido creado como principal', 'success');
            }
        }
        
        // Upload main photo if changed
        if (fotoPrincipalFile) {
            await uploadFotoPrincipal(consultorioId, fotoPrincipalFile);
        }
        
        // Upload secondary photos if any
        for (const foto of fotosSecundarias) {
            if (foto.file && !foto.uploaded) {
                await uploadFotoSecundaria(consultorioId, foto.file, foto.caption);
            }
        }
        
        if (!isFirstConsultorio || editingConsultorioId) {
            showToast(response.message || 'Consultorio guardado exitosamente', 'success');
        }
        
        // Reload consultorios
        await loadConsultorios();
        
        // Close modal
        closeConsultorioModal();
        
    } catch (error) {
        console.error('Error saving consultorio:', error);
        showToast(error.message || 'Error al guardar el consultorio', 'error');
    } finally {
        hideLoading();
    }
}

// Edit consultorio
window.editConsultorio = function(consultorioId) {
    openConsultorioModal(consultorioId);
};

// Delete consultorio
window.deleteConsultorio = function(consultorioId) {
    // Check if it's the only consultorio
    const activeConsultorios = consultorios.filter(c => c.activo !== false);
    
    if (activeConsultorios.length === 1) {
        showToast('No puedes eliminar tu único consultorio activo', 'error');
        return;
    }
    
    pendingDeleteId = consultorioId;
    const modal = document.getElementById('confirm-modal');
    if (modal) {
        modal.classList.add('show');
    }
};

// Confirm delete
window.confirmDelete = async function() {
    if (!pendingDeleteId) return;
    
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.remove('show');
    
    showLoading('Eliminando consultorio...');
    
    try {
        const response = await api.makeRequest(`/consultorios/${pendingDeleteId}`, {
            method: 'DELETE'
        });
        
        showToast(response.message || 'Consultorio eliminado', 'success');
        
        // Reload consultorios
        await loadConsultorios();
        
    } catch (error) {
        console.error('Error deleting consultorio:', error);
        showToast(error.message || error.detail || 'Error al eliminar el consultorio', 'error');
    } finally {
        hideLoading();
        pendingDeleteId = null;
    }
};

// Cancel delete
window.cancelDelete = function() {
    pendingDeleteId = null;
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.remove('show');
};

// Toggle extras section
window.toggleExtras = function() {
    const section = document.getElementById('extras-section');
    const icon = document.getElementById('extras-icon');
    
    if (section.classList.contains('hidden')) {
        section.classList.remove('hidden');
        icon.classList.remove('fa-chevron-down');
        icon.classList.add('fa-chevron-up');
    } else {
        section.classList.add('hidden');
        icon.classList.remove('fa-chevron-up');
        icon.classList.add('fa-chevron-down');
    }
};

// Handle main photo upload
window.handleFotoPrincipal = function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file type
    if (!file.type.startsWith('image/')) {
        showToast('Por favor selecciona una imagen válida', 'error');
        return;
    }
    
    // Store file for upload
    fotoPrincipalFile = file;
    
    // Preview image
    const reader = new FileReader();
    reader.onload = function(e) {
        const headerPhoto = document.getElementById('modal-header-photo');
        headerPhoto.style.backgroundImage = `url('${e.target.result}')`;
        headerPhoto.style.backgroundColor = '';
    };
    reader.readAsDataURL(file);
};

// Remove main photo
window.removeFotoPrincipal = function() {
    const headerPhoto = document.getElementById('modal-header-photo');
    headerPhoto.style.backgroundImage = '';
    headerPhoto.style.backgroundColor = generateRandomColor();
    fotoPrincipalFile = null;
    
    // Clear file input
    const input = document.getElementById('foto-principal-input');
    if (input) input.value = '';
};

// Handle secondary photo upload
window.handleFotoSecundaria = function(event) {
    const file = event.target.files[0];
    if (!file) return;
    
    // Validate file type
    if (!file.type.startsWith('image/')) {
        showToast('Por favor selecciona una imagen válida', 'error');
        return;
    }
    
    // Check limit
    if (fotosSecundarias.length >= 10) {
        showToast('Máximo 10 fotos secundarias permitidas', 'error');
        return;
    }
    
    // Read and preview
    const reader = new FileReader();
    reader.onload = function(e) {
        const foto = {
            id: generateUUID(),
            url: e.target.result,
            file: file,
            caption: '',
            uploaded: false
        };
        
        fotosSecundarias.push(foto);
        renderSecondaryPhotos(fotosSecundarias);
    };
    reader.readAsDataURL(file);
    
    // Clear input
    event.target.value = '';
};

// Render secondary photos
function renderSecondaryPhotos(photos) {
    const grid = document.getElementById('secondary-photos-grid');
    if (!grid) return;
    
    // Clear current photos
    grid.innerHTML = '';
    
    // Add photos
    photos.forEach(photo => {
        const photoDiv = document.createElement('div');
        photoDiv.className = 'secondary-photo';
        photoDiv.innerHTML = `
            <img src="${photo.url}" alt="Foto">
            <button onclick="removeSecondaryPhoto('${photo.id}')" class="remove-photo-btn">
                <i class="fas fa-times"></i>
            </button>
        `;
        grid.appendChild(photoDiv);
    });
    
    // Add the "add photo" button
    const addBtn = document.createElement('label');
    addBtn.className = 'add-photo-box';
    addBtn.htmlFor = 'foto-secundaria-input';
    addBtn.innerHTML = `
        <i class="fas fa-plus"></i>
        <span>Agregar foto</span>
    `;
    grid.appendChild(addBtn);
}

// Remove secondary photo
window.removeSecondaryPhoto = function(photoId) {
    fotosSecundarias = fotosSecundarias.filter(p => p.id !== photoId);
    renderSecondaryPhotos(fotosSecundarias);
};

// Upload main photo
async function uploadFotoPrincipal(consultorioId, file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`/api/consultorios/${consultorioId}/foto-principal`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Error uploading photo');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error uploading main photo:', error);
        throw error;
    }
}

// Upload secondary photo
async function uploadFotoSecundaria(consultorioId, file, caption = '') {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('caption', caption);
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(`/api/consultorios/${consultorioId}/fotos-secundarias`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });
        
        if (!response.ok) {
            throw new Error('Error uploading photo');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error uploading secondary photo:', error);
        throw error;
    }
}

// Preview location on map
window.previewLocation = async function() {
    // Get address components
    const address = {
        calle: document.getElementById('calle').value.trim(),
        numero: document.getElementById('numero').value.trim(),
        colonia: document.getElementById('colonia').value.trim(),
        ciudad: document.getElementById('ciudad').value.trim(),
        estado: document.getElementById('estado').value.trim(),
        codigo_postal: document.getElementById('codigo_postal').value.trim(),
        pais: document.getElementById('pais').value.trim()
    };
    
    // Validate required fields
    if (!address.calle || !address.numero || !address.ciudad || !address.estado || !address.pais) {
        showToast('Por favor completa todos los campos de dirección requeridos', 'warning');
        return;
    }
    
    // Build full address
    let fullAddress = `${address.calle} ${address.numero}, `;
    if (address.colonia) fullAddress += `${address.colonia}, `;
    fullAddress += `${address.ciudad}, ${address.estado}, ${address.codigo_postal}, ${address.pais}`;
    
    // Show map container
    const mapContainer = document.getElementById('map-preview-container');
    mapContainer.classList.remove('hidden');
    
    // FIXED: Always reinitialize map to avoid stale state
    initMapPreview();
    
    // Geocode address
    geocodeAddress(fullAddress);
};

// Initialize map preview
function initMapPreview() {
    const mapDiv = document.getElementById('map-preview');
    if (!mapDiv) return;
    
    // Check if Google Maps is loaded
    if (typeof google === 'undefined' || !google.maps) {
        console.error('Google Maps API not loaded');
        showToast('Error al cargar el mapa. Por favor recarga la página.', 'error');
        return;
    }
    
    // FIXED: Always create a new map instance
    mapPreview = new google.maps.Map(mapDiv, {
        zoom: 15,
        center: { lat: 19.4326, lng: -99.1332 }, // Mexico City default
        mapTypeId: 'roadmap'
    });
    
    markerPreview = new google.maps.Marker({
        map: mapPreview,
        draggable: true,
        animation: google.maps.Animation.DROP
    });
    
    // Update location when marker is dragged
    markerPreview.addListener('dragend', function() {
        const position = markerPreview.getPosition();
        
        // FIXED: Store location with proper identification
        currentLocation = {
            lat: position.lat(),
            lng: position.lng(),
            markerAdjusted: true,  // Flag that marker was manually adjusted
            consultorioId: editingConsultorioId  // Track which consultorio this belongs to
        };
        
        // Generate new Google Maps URL for the exact marker position
        const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${position.lat()},${position.lng()}`;
        currentLocation.google_maps_url = mapsUrl;
        
        // Just store the new position, don't update address fields
        showToast('Ubicación del marcador actualizada', 'info');
    });
}

// Geocode address
function geocodeAddress(address) {
    // Check if Google Maps is loaded
    if (typeof google === 'undefined' || !google.maps) {
        console.error('Google Maps API not loaded');
        showToast('Error al cargar el mapa. Por favor recarga la página.', 'error');
        return;
    }
    
    const geocoder = new google.maps.Geocoder();
    
    geocoder.geocode({ address: address }, (results, status) => {
        if (status === 'OK') {
            const location = results[0].geometry.location;
            
            // Update map
            mapPreview.setCenter(location);
            markerPreview.setPosition(location);
            
            // FIXED: Store location properly with consultorio ID
            currentLocation = {
                lat: location.lat(),
                lng: location.lng(),
                formatted_address: results[0].formatted_address,
                place_id: results[0].place_id,
                markerAdjusted: false,  // This is from geocoding, not manual adjustment
                consultorioId: editingConsultorioId  // Track which consultorio this belongs to
            };
            
        } else {
            console.error('Geocode failed:', status);
            showToast('No se pudo encontrar la ubicación. Verifica la dirección.', 'warning');
        }
    });
}

// Initialize Google Maps (callback function)
window.initMap = function() {
    console.log('Google Maps API loaded');
};

// Close map modal
window.closeMapModal = function() {
    const modal = document.getElementById('map-modal');
    if (modal) modal.classList.remove('show');
};

// Confirm location from map
window.confirmLocation = function() {
    if (currentLocation) {
        showToast('Ubicación confirmada', 'success');
        closeMapModal();
    }
};

// Utility functions
function generateRandomColor() {
    const colors = [
        '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
        '#f97316', '#10b981', '#3b82f6', '#06b6d4'
    ];
    return colors[Math.floor(Math.random() * colors.length)];
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
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
        iconEl.className = type === 'error' ? 
            'fas fa-times-circle text-red-400' : 
            type === 'warning' ?
            'fas fa-exclamation-triangle text-yellow-400' :
            type === 'info' ?
            'fas fa-info-circle text-blue-400' :
            'fas fa-check-circle text-green-400';
    }
    
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Export for external use
window.openConsultorioModal = openConsultorioModal;
window.closeConsultorioModal = closeConsultorioModal;
window.saveConsultorio = saveConsultorio;