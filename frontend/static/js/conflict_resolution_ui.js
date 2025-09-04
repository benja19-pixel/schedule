// Conflict Resolution UI Handler for Google Calendar Sync
// Handles UI for conflict detection and resolution between external events and internal breaks

class ConflictResolutionUI {
    constructor() {
        this.pendingConflicts = [];
        this.currentConflictIndex = 0;
        this.resolutions = [];
        this.modalId = 'conflict-resolution-modal-enhanced';
    }

    // Initialize the conflict resolution process
    init(conflicts) {
        this.pendingConflicts = conflicts;
        this.currentConflictIndex = 0;
        this.resolutions = [];
        this.createModal();
        this.showNextConflict();
    }

    // Create the enhanced modal for conflict resolution
    createModal() {
        // Remove existing modal if present
        const existing = document.getElementById(this.modalId);
        if (existing) existing.remove();

        const modal = document.createElement('div');
        modal.id = this.modalId;
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-[10001] flex items-center justify-center hidden';
        
        modal.innerHTML = `
            <div class="bg-white rounded-2xl shadow-2xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-hidden">
                <div class="bg-gradient-to-r from-purple-600 to-pink-600 p-6 text-white">
                    <h2 class="text-2xl font-bold flex items-center gap-3">
                        <i class="fas fa-exclamation-triangle"></i>
                        Resolver Conflictos de Calendario
                    </h2>
                    <p class="text-sm mt-2 opacity-90">
                        Se detectaron eventos que coinciden con tus descansos configurados
                    </p>
                </div>
                
                <div class="p-6 overflow-y-auto max-h-[60vh]">
                    <div id="conflict-progress" class="mb-6">
                        <div class="flex justify-between text-sm text-gray-600 mb-2">
                            <span>Conflicto <span id="conflict-current">1</span> de <span id="conflict-total">1</span></span>
                            <span id="conflict-percentage">0%</span>
                        </div>
                        <div class="w-full bg-gray-200 rounded-full h-2">
                            <div id="progress-bar" class="bg-gradient-to-r from-purple-600 to-pink-600 h-2 rounded-full transition-all duration-300" style="width: 0%"></div>
                        </div>
                    </div>
                    
                    <div id="conflict-content">
                        <!-- Conflict details will be inserted here -->
                    </div>
                    
                    <div id="resolution-options" class="mt-6">
                        <!-- Resolution options will be inserted here -->
                    </div>
                </div>
                
                <div class="border-t p-6 bg-gray-50 flex justify-between gap-4">
                    <button id="skip-conflict" class="px-6 py-3 text-gray-600 hover:text-gray-800 transition-colors">
                        Omitir este conflicto
                    </button>
                    <div class="flex gap-3">
                        <button id="cancel-resolution" class="px-6 py-3 border-2 border-gray-300 rounded-xl text-gray-700 font-semibold hover:bg-gray-100 transition-all">
                            Cancelar Todo
                        </button>
                        <button id="apply-resolution" class="px-8 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl font-semibold hover:shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed" disabled>
                            Aplicar Resolución
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        this.attachEventListeners();
    }

    // Show the next conflict in the queue
    showNextConflict() {
        if (this.currentConflictIndex >= this.pendingConflicts.length) {
            this.completeResolution();
            return;
        }

        const conflict = this.pendingConflicts[this.currentConflictIndex];
        this.updateProgress();
        this.renderConflictDetails(conflict);
        this.renderResolutionOptions(conflict);
        this.showModal();
    }

    // Render conflict details
    renderConflictDetails(conflict) {
        const contentEl = document.getElementById('conflict-content');
        const external = conflict.external_event;
        const internal = conflict.internal_break || conflict.conflict_with;
        
        contentEl.innerHTML = `
            <div class="bg-gradient-to-br from-blue-50 to-purple-50 rounded-xl p-5 mb-4">
                <h3 class="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-calendar text-blue-600"></i>
                    Evento del Calendario Externo
                </h3>
                <div class="space-y-2">
                    <p class="text-lg font-medium text-gray-900">${external.summary || 'Sin título'}</p>
                    ${external.description ? `<p class="text-sm text-gray-600">${external.description}</p>` : ''}
                    <div class="flex items-center gap-4 text-sm">
                        <span class="flex items-center gap-1">
                            <i class="fas fa-calendar-day text-gray-400"></i>
                            ${this.formatDate(external.start_date)}
                        </span>
                        <span class="flex items-center gap-1">
                            <i class="fas fa-clock text-gray-400"></i>
                            ${this.formatTime(external.start_time)} - ${this.formatTime(external.end_time)}
                        </span>
                        <span class="px-2 py-1 bg-blue-100 text-blue-700 rounded-full text-xs font-semibold">
                            ${this.calculateDuration(external.start_time, external.end_time)} min
                        </span>
                    </div>
                </div>
            </div>
            
            <div class="flex justify-center my-4">
                <div class="bg-gradient-to-r from-amber-400 to-orange-400 text-white px-4 py-2 rounded-full text-sm font-bold flex items-center gap-2">
                    <i class="fas fa-bolt"></i>
                    CONFLICTO DETECTADO
                </div>
            </div>
            
            <div class="bg-gradient-to-br from-purple-50 to-pink-50 rounded-xl p-5">
                <h3 class="font-semibold text-gray-800 mb-4 flex items-center gap-2">
                    <i class="fas fa-hospital text-purple-600"></i>
                    Descanso en MediConnect
                </h3>
                <div class="space-y-2">
                    <p class="text-lg font-medium text-gray-900">${this.getBreakTypeName(internal.type || internal.break_type)}</p>
                    <div class="flex items-center gap-4 text-sm">
                        <span class="flex items-center gap-1">
                            <i class="fas fa-clock text-gray-400"></i>
                            ${internal.break_time || `${internal.start} - ${internal.end}`}
                        </span>
                        <span class="px-2 py-1 bg-purple-100 text-purple-700 rounded-full text-xs font-semibold">
                            ${this.calculateDurationFromBreak(internal)} min
                        </span>
                    </div>
                </div>
            </div>
        `;
    }

    // Render resolution options
    renderResolutionOptions(conflict) {
        const optionsEl = document.getElementById('resolution-options');
        
        optionsEl.innerHTML = `
            <h4 class="font-semibold text-gray-700 mb-3">Selecciona cómo resolver este conflicto:</h4>
            <div class="grid grid-cols-2 gap-3">
                <button class="resolution-option" data-type="merge_sum">
                    <div class="option-icon bg-green-100 text-green-600">
                        <i class="fas fa-plus-circle"></i>
                    </div>
                    <div class="option-content">
                        <h5 class="font-semibold">Sumar tiempos</h5>
                        <p class="text-xs text-gray-500">Suma la duración de ambos eventos</p>
                    </div>
                </button>
                
                <button class="resolution-option" data-type="merge_combine">
                    <div class="option-icon bg-blue-100 text-blue-600">
                        <i class="fas fa-compress-arrows-alt"></i>
                    </div>
                    <div class="option-content">
                        <h5 class="font-semibold">Combinar</h5>
                        <p class="text-xs text-gray-500">Un bloque desde el inicio más temprano al fin más tardío</p>
                    </div>
                </button>
                
                <button class="resolution-option" data-type="keep_external">
                    <div class="option-icon bg-purple-100 text-purple-600">
                        <i class="fas fa-calendar-check"></i>
                    </div>
                    <div class="option-content">
                        <h5 class="font-semibold">Usar calendario externo</h5>
                        <p class="text-xs text-gray-500">Reemplazar con el evento de Google</p>
                    </div>
                </button>
                
                <button class="resolution-option" data-type="keep_internal">
                    <div class="option-icon bg-pink-100 text-pink-600">
                        <i class="fas fa-shield-alt"></i>
                    </div>
                    <div class="option-content">
                        <h5 class="font-semibold">Mantener actual</h5>
                        <p class="text-xs text-gray-500">Conservar el descanso de MediConnect</p>
                    </div>
                </button>
            </div>
            
            <div id="resolution-preview" class="mt-4 p-4 bg-gray-50 rounded-lg hidden">
                <h5 class="text-sm font-semibold text-gray-600 mb-2">Vista previa del resultado:</h5>
                <div id="preview-content" class="text-sm"></div>
            </div>
        `;
        
        // Add styles for resolution options
        const style = document.createElement('style');
        style.textContent = `
            .resolution-option {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 16px;
                border: 2px solid #e5e7eb;
                border-radius: 12px;
                background: white;
                transition: all 0.2s;
                text-align: left;
            }
            
            .resolution-option:hover {
                border-color: #9333ea;
                background: #faf5ff;
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(147, 51, 234, 0.15);
            }
            
            .resolution-option.selected {
                border-color: #9333ea;
                background: linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%);
            }
            
            .option-icon {
                width: 48px;
                height: 48px;
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
                flex-shrink: 0;
            }
            
            .option-content {
                flex: 1;
            }
        `;
        
        if (!document.querySelector('#conflict-resolution-styles')) {
            style.id = 'conflict-resolution-styles';
            document.head.appendChild(style);
        }
        
        this.attachOptionListeners();
    }

    // Attach event listeners to resolution options
    attachOptionListeners() {
        const options = document.querySelectorAll('.resolution-option');
        const applyBtn = document.getElementById('apply-resolution');
        
        options.forEach(option => {
            option.addEventListener('click', (e) => {
                // Remove selected class from all options
                options.forEach(opt => opt.classList.remove('selected'));
                
                // Add selected class to clicked option
                option.classList.add('selected');
                
                // Enable apply button
                applyBtn.disabled = false;
                
                // Show preview
                const type = option.dataset.type;
                this.showResolutionPreview(type);
            });
        });
    }

    // Show resolution preview
    showResolutionPreview(type) {
        const previewEl = document.getElementById('resolution-preview');
        const contentEl = document.getElementById('preview-content');
        const conflict = this.pendingConflicts[this.currentConflictIndex];
        
        let previewHtml = '';
        
        switch(type) {
            case 'merge_sum':
                const totalMinutes = this.calculateTotalDuration(conflict);
                previewHtml = `<i class="fas fa-check-circle text-green-500 mr-2"></i>Nuevo descanso de ${totalMinutes} minutos total`;
                break;
            case 'merge_combine':
                const combined = this.getCombinedTime(conflict);
                previewHtml = `<i class="fas fa-check-circle text-blue-500 mr-2"></i>Descanso combinado: ${combined.start} - ${combined.end}`;
                break;
            case 'keep_external':
                previewHtml = `<i class="fas fa-calendar text-purple-500 mr-2"></i>Se usará el evento del calendario externo`;
                break;
            case 'keep_internal':
                previewHtml = `<i class="fas fa-shield-alt text-pink-500 mr-2"></i>Se mantendrá el descanso actual de MediConnect`;
                break;
        }
        
        contentEl.innerHTML = previewHtml;
        previewEl.classList.remove('hidden');
    }

    // Calculate total duration
    calculateTotalDuration(conflict) {
        const external = conflict.external_event;
        const internal = conflict.internal_break || conflict.conflict_with;
        
        const externalDuration = this.calculateDuration(external.start_time, external.end_time);
        const internalDuration = this.calculateDurationFromBreak(internal);
        
        return externalDuration + internalDuration;
    }

    // Get combined time range
    getCombinedTime(conflict) {
        const external = conflict.external_event;
        const internal = conflict.internal_break || conflict.conflict_with;
        
        const externalStart = this.parseTime(external.start_time);
        const externalEnd = this.parseTime(external.end_time);
        const internalStart = this.parseTime(internal.start || internal.break_time.split(' - ')[0]);
        const internalEnd = this.parseTime(internal.end || internal.break_time.split(' - ')[1]);
        
        const start = externalStart < internalStart ? external.start_time : (internal.start || internal.break_time.split(' - ')[0]);
        const end = externalEnd > internalEnd ? external.end_time : (internal.end || internal.break_time.split(' - ')[1]);
        
        return { start: this.formatTime(start), end: this.formatTime(end) };
    }

    // Attach main event listeners
    attachEventListeners() {
        const applyBtn = document.getElementById('apply-resolution');
        const cancelBtn = document.getElementById('cancel-resolution');
        const skipBtn = document.getElementById('skip-conflict');
        
        applyBtn?.addEventListener('click', () => this.applyCurrentResolution());
        cancelBtn?.addEventListener('click', () => this.cancelAll());
        skipBtn?.addEventListener('click', () => this.skipCurrent());
    }

    // Apply current resolution
    applyCurrentResolution() {
        const selectedOption = document.querySelector('.resolution-option.selected');
        if (!selectedOption) return;
        
        const resolution = {
            conflict_index: this.currentConflictIndex,
            event_id: this.pendingConflicts[this.currentConflictIndex].external_event.id,
            resolution_type: selectedOption.dataset.type
        };
        
        this.resolutions.push(resolution);
        this.currentConflictIndex++;
        
        // Reset UI
        document.getElementById('apply-resolution').disabled = true;
        
        // Show next conflict or complete
        this.showNextConflict();
    }

    // Skip current conflict
    skipCurrent() {
        this.resolutions.push({
            conflict_index: this.currentConflictIndex,
            event_id: this.pendingConflicts[this.currentConflictIndex].external_event.id,
            resolution_type: 'skip'
        });
        
        this.currentConflictIndex++;
        this.showNextConflict();
    }

    // Cancel all
    cancelAll() {
        this.hideModal();
        this.cleanup();
        showToast('Resolución de conflictos cancelada', 'warning');
    }

    // Complete resolution
    async completeResolution() {
        if (this.resolutions.length === 0) {
            this.hideModal();
            this.cleanup();
            return;
        }
        
        // Filter out skipped resolutions
        const validResolutions = this.resolutions.filter(r => r.resolution_type !== 'skip');
        
        if (validResolutions.length > 0) {
            showLoading('Aplicando resoluciones...');
            
            try {
                const response = await api.makeRequest('/calendar-sync/resolve-conflicts', {
                    method: 'POST',
                    body: JSON.stringify(validResolutions)
                });
                
                if (response && response.success) {
                    showToast(`${validResolutions.length} conflictos resueltos exitosamente`, 'success');
                    
                    // Refresh schedule
                    if (typeof loadHorarioData === 'function') {
                        await loadHorarioData();
                    }
                }
            } catch (error) {
                console.error('Error applying resolutions:', error);
                showToast('Error al aplicar resoluciones', 'error');
            } finally {
                hideLoading();
            }
        }
        
        this.hideModal();
        this.cleanup();
    }

    // Update progress bar
    updateProgress() {
        const current = this.currentConflictIndex + 1;
        const total = this.pendingConflicts.length;
        const percentage = Math.round((this.currentConflictIndex / total) * 100);
        
        document.getElementById('conflict-current').textContent = current;
        document.getElementById('conflict-total').textContent = total;
        document.getElementById('conflict-percentage').textContent = `${percentage}%`;
        document.getElementById('progress-bar').style.width = `${percentage}%`;
    }

    // Helper functions
    formatDate(dateStr) {
        const date = new Date(dateStr + 'T00:00:00');
        return date.toLocaleDateString('es-MX', {
            weekday: 'long',
            day: 'numeric',
            month: 'long'
        });
    }

    formatTime(timeStr) {
        if (!timeStr) return '';
        const [hours, minutes] = timeStr.split(':');
        const h = parseInt(hours);
        const period = h >= 12 ? 'PM' : 'AM';
        const displayHours = h > 12 ? h - 12 : (h === 0 ? 12 : h);
        return `${displayHours}:${minutes} ${period}`;
    }

    parseTime(timeStr) {
        if (!timeStr) return 0;
        if (timeStr.includes(' - ')) {
            timeStr = timeStr.split(' - ')[0];
        }
        const [hours, minutes] = timeStr.split(':').map(Number);
        return hours * 60 + minutes;
    }

    calculateDuration(startTime, endTime) {
        const start = this.parseTime(startTime);
        const end = this.parseTime(endTime);
        return end - start;
    }

    calculateDurationFromBreak(breakInfo) {
        if (breakInfo.start && breakInfo.end) {
            return this.calculateDuration(breakInfo.start, breakInfo.end);
        } else if (breakInfo.break_time) {
            const [start, end] = breakInfo.break_time.split(' - ');
            return this.calculateDuration(start, end);
        }
        return 0;
    }

    getBreakTypeName(type) {
        const types = {
            'lunch': 'Comida',
            'break': 'Descanso',
            'administrative': 'Administrativo'
        };
        return types[type] || 'Descanso';
    }

    showModal() {
        const modal = document.getElementById(this.modalId);
        modal?.classList.remove('hidden');
    }

    hideModal() {
        const modal = document.getElementById(this.modalId);
        modal?.classList.add('hidden');
    }

    cleanup() {
        const modal = document.getElementById(this.modalId);
        if (modal) {
            setTimeout(() => modal.remove(), 300);
        }
        this.pendingConflicts = [];
        this.resolutions = [];
        this.currentConflictIndex = 0;
    }
}

// Export for global use
window.ConflictResolutionUI = ConflictResolutionUI;