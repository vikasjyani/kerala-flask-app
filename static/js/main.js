// Global Variables
let currentStep = 1;
let totalSteps = 4;
let formData = {};

// Initialize current step based on page
function initializeCurrentStep() {
    const progressWrapper = document.querySelector('.progress-wrapper');
    if (progressWrapper) {
        const dataCurrent = parseInt(progressWrapper.dataset.currentStep, 10);
        const dataTotal = parseInt(progressWrapper.dataset.totalSteps, 10);

        if (!isNaN(dataTotal) && dataTotal > 0) {
            totalSteps = dataTotal;
        }
        if (!isNaN(dataCurrent) && dataCurrent > 0) {
            currentStep = dataCurrent;
        }
    } else {
        // Fallback to legacy width detection if wrapper not present
        const progressBar = document.querySelector('.progress-bar');
        if (progressBar && progressBar.style.width) {
            const percentage = parseInt(progressBar.style.width, 10);
            if (percentage === 25) currentStep = 1;
            else if (percentage === 50) currentStep = 2;
            else if (percentage === 75) currentStep = 3;
            else if (percentage === 100) currentStep = 4;
        }
    }
}

// Translation object (will be populated based on current language)
let translations = {
    en: {
        'validation_required': 'This field is required',
        'validation_email': 'Please enter a valid email address',
        'validation_number': 'Please enter a valid number',
        'validation_minimum': 'Enter a value of {min} or more.',
        'validation_maximum': 'Enter a value of {max} or less.',
        'validation_step': 'Use increments of {step} from {min}.',
        'calculation_progress': 'Calculating your energy consumption...',
        'analysis_progress': 'Performing comprehensive analysis...',
        'success_message': 'Data saved successfully!',
        'error_message': 'An error occurred. Please try again.',
        'confirm_navigation': 'Are you sure you want to leave? Your data will be lost.',
        'download_starting': 'Your report is being generated...',
        'share_success': 'Link copied to clipboard!',
        'share_copy_failed': 'Unable to copy link',
        'share_title': 'Keralam Cooking Energy Analysis Results',
        'share_text': 'Check out my cooking energy analysis results!',
        'loading': 'Loading...',
        'request_timeout': 'This is taking longer than expected. Your inputs are still here. Please try again.',
        'dismiss_notification': 'Dismiss notification',
        'edited_during_save': 'Your earlier inputs were saved. You made more changes while saving; select Continue again to save them.',
        'step_template': 'Step {current} of {total}',
        'chart_monthly_cost_label': 'Monthly Cost (₹)',
        'chart_monthly_cost_title': 'Monthly Cost Comparison',
        'chart_annual_co2_label': 'Annual CO₂ (kg)',
        'chart_annual_co2_title': 'Annual CO₂ Emissions Comparison',
        'chart_health_risk_label': 'Health Risk Score',
        'chart_health_risk_title': 'Health Risk Score Comparison',
        'chart_low_risk_threshold': 'Low Risk Threshold',
        'chart_radar_cost_efficiency': 'Cost Efficiency',
        'chart_radar_low_emissions': 'Low Emissions',
        'chart_radar_health_safety': 'Health Safety',
        'chart_radar_overall_rating': 'Overall Rating',
        'chart_radar_title': 'Multi-Criteria Performance Comparison'
    },
    ml: {
        'validation_required': 'ഈ ഫീൽഡ് ആവശ്യമാണ്',
        'validation_email': 'സാധുവായ ഇമെയിൽ വിലാസം നൽകുക',
        'validation_number': 'സാധുവായ നമ്പർ നൽകുക',
        'validation_minimum': '{min} അല്ലെങ്കിൽ അതിൽ കൂടുതൽ നൽകുക.',
        'validation_maximum': '{max} അല്ലെങ്കിൽ അതിൽ കുറവ് നൽകുക.',
        'validation_step': '{min} മുതൽ {step} വീതമുള്ള മൂല്യങ്ങൾ നൽകുക.',
        'calculation_progress': 'നിങ്ങളുടെ ഊർജ്ജ ഉപഭോഗം കണക്കാക്കുന്നു...',
        'analysis_progress': 'സമഗ്ര വിശകലനം നടത്തുന്നു...',
        'success_message': 'ഡാറ്റ വിജയകരമായി സേവ് ചെയ്തു!',
        'error_message': 'ഒരു പിശക് സംഭവിച്ചു. ദയവായി വീണ്ടും ശ്രമിക്കുക.',
        'confirm_navigation': 'നിങ്ങൾക്ക് ഉറപ്പാണോ? നിങ്ങളുടെ ഡാറ്റ നഷ്ടപ്പെടും.',
        'download_starting': 'നിങ്ങളുടെ റിപ്പോർട്ട് തയ്യാറാക്കുന്നു...',
        'share_success': 'ലിങ്ക് ക്ലിപ്പ്ബോർഡിലേക്ക് പകർത്തി!',
        'share_copy_failed': 'ലിങ്ക് പകർത്താൻ കഴിഞ്ഞില്ല',
        'share_title': 'കേരള പാചക ഊർജ വിശകലന ഫലങ്ങൾ',
        'share_text': 'എന്റെ പാചക ഊർജ വിശകലന ഫലങ്ങൾ കാണൂ!',
        'loading': 'ലോഡിംഗ്...',
        'request_timeout': 'പ്രതീക്ഷിച്ചതിലും കൂടുതൽ സമയമെടുക്കുന്നു. നിങ്ങളുടെ വിവരങ്ങൾ ഇവിടെയുണ്ട്. വീണ്ടും ശ്രമിക്കുക.',
        'dismiss_notification': 'അറിയിപ്പ് അടയ്ക്കുക',
        'edited_during_save': 'മുമ്പത്തെ വിവരങ്ങൾ സേവ് ചെയ്തു. സേവ് ചെയ്യുന്നതിനിടെ വരുത്തിയ മാറ്റങ്ങൾ സേവ് ചെയ്യാൻ വീണ്ടും തുടരുക തിരഞ്ഞെടുക്കുക.',
        'step_template': 'ഘട്ടം {current} / {total}',
        'chart_monthly_cost_label': 'മാസാന്ത്യ ചെലവ് (₹)',
        'chart_monthly_cost_title': 'മാസാന്ത്യ ചെലവ് താരതമ്യം',
        'chart_annual_co2_label': 'വാർഷിക CO₂ (kg)',
        'chart_annual_co2_title': 'വാർഷിക CO₂ ഉത്സർജനം താരതമ്യം',
        'chart_health_risk_label': 'ആരോഗ്യ അപകട സ്കോർ',
        'chart_health_risk_title': 'ആരോഗ്യ അപകട സ്കോർ താരതമ്യം',
        'chart_low_risk_threshold': 'കുറഞ്ഞ അപകട പരിധി',
        'chart_radar_cost_efficiency': 'ചെലവ് കാര്യക്ഷമത',
        'chart_radar_low_emissions': 'കുറഞ്ഞ ഉത്സർജനം',
        'chart_radar_health_safety': 'ആരോഗ്യ സുരക്ഷ',
        'chart_radar_overall_rating': 'മൊത്തം റേറ്റിംഗ്',
        'chart_radar_title': 'ബഹുമാനദണ്ഡ പ്രകടന താരതമ്യം'
    },
    hi: {
        'validation_required': 'यह फ़ील्ड आवश्यक है',
        'validation_email': 'कृपया एक मान्य ईमेल पता दर्ज करें',
        'validation_number': 'कृपया एक मान्य संख्या दर्ज करें',
        'validation_minimum': '{min} या उससे अधिक का मान दर्ज करें।',
        'validation_maximum': '{max} या उससे कम का मान दर्ज करें।',
        'validation_step': '{min} से {step} की वृद्धि में मान दर्ज करें।',
        'calculation_progress': 'आपकी ऊर्जा खपत की गणना की जा रही है...',
        'analysis_progress': 'व्यापक विश्लेषण किया जा रहा है...',
        'success_message': 'डेटा सफलतापूर्वक सहेजा गया!',
        'error_message': 'कोई त्रुटि हुई। कृपया पुनः प्रयास करें।',
        'confirm_navigation': 'क्या आप वाकई इस पृष्ठ को छोड़ना चाहते हैं? आपका डेटा खो जाएगा।',
        'download_starting': 'आपकी रिपोर्ट तैयार की जा रही है...',
        'share_success': 'लिंक क्लिपबोर्ड पर कॉपी हो गया!',
        'share_copy_failed': 'लिंक कॉपी नहीं हो सका',
        'share_title': 'केरलम कुकिंग ऊर्जा विश्लेषण परिणाम',
        'share_text': 'मेरे कुकिंग ऊर्जा विश्लेषण परिणाम देखें!',
        'loading': 'लोड हो रहा है...',
        'request_timeout': 'इसमें अपेक्षा से अधिक समय लग रहा है। आपकी जानकारी अभी भी सुरक्षित है। कृपया पुनः प्रयास करें।',
        'dismiss_notification': 'सूचना हटाएं',
        'edited_during_save': 'आपकी पहले की जानकारी सहेज ली गई है। सहेजे जाने के दौरान आपने और बदलाव किए हैं; उन्हें सहेजने के लिए फिर से \'जारी रखें\' चुनें।',
        'step_template': 'चरण {current} का {total}',
        'chart_monthly_cost_label': 'मासिक लागत (₹)',
        'chart_monthly_cost_title': 'मासिक लागत तुलना',
        'chart_annual_co2_label': 'वार्षिक CO₂ (kg)',
        'chart_annual_co2_title': 'वार्षिक CO₂ उत्सर्जन तुलना',
        'chart_health_risk_label': 'स्वास्थ्य जोखिम स्कोर',
        'chart_health_risk_title': 'स्वास्थ्य जोखिम स्कोर तुलना',
        'chart_low_risk_threshold': 'कम जोखिम सीमा',
        'chart_radar_cost_efficiency': 'लागत दक्षता',
        'chart_radar_low_emissions': 'कम उत्सर्जन',
        'chart_radar_health_safety': 'स्वास्थ्य सुरक्षा',
        'chart_radar_overall_rating': 'समग्र रेटिंग',
        'chart_radar_title': 'बहु-मानदंड प्रदर्शन तुलना'
    }
};

// Get current language
function getCurrentLanguage() {
    return document.documentElement.lang || 'en';
}

// Get translation
function t(key) {
    const lang = getCurrentLanguage();
    return translations[lang] && translations[lang][key] ? translations[lang][key] : key;
}

// Initialize application
document.addEventListener('DOMContentLoaded', function () {
    initializeApp();
});

function initializeApp() {
    // Initialize current step
    initializeCurrentStep();

    // Initialize tooltips
    initializeTooltips();

    // Initialize form validation
    initializeFormValidation();

    // Native selects cannot wrap their visible value. Show it below only when
    // the current font and available width would otherwise cut it off.
    initializeSelectDescriptions();

    // Initialize progress tracking
    updateProgress();

    // Initialize charts if on analysis page
    if (document.getElementById('costChart')) {
        initializeCharts();
    }

    // Add animation classes to elements
    addAnimations();

    // Initialize navigation warnings
    initializeNavigationWarnings();
}

// Tooltip initialization
function initializeTooltips() {
    if (!window.bootstrap?.Tooltip) return;
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(element => {
        bootstrap.Tooltip.getOrCreateInstance(element);
    });
}

// Form Validation
function initializeFormValidation() {
    const forms = document.querySelectorAll('.needs-validation');

    forms.forEach(function (form) {
        form.querySelectorAll('input, select, textarea').forEach(field => {
            let feedback = field.parentElement?.querySelector('.invalid-feedback')
                || field.closest('.input-group')?.parentElement?.querySelector('.invalid-feedback');
            if (!feedback && field.willValidate && field.type === 'number') {
                feedback = document.createElement('div');
                feedback.className = 'invalid-feedback';
                feedback.dataset.nativeValidation = 'true';
                (field.closest('.input-group') || field).insertAdjacentElement('afterend', feedback);
            }
            if (feedback && field.id) {
                feedback.id ||= `${field.id}-feedback`;
                const describedBy = new Set((field.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
                describedBy.add(feedback.id);
                field.setAttribute('aria-describedby', [...describedBy].join(' '));
            }
            field.addEventListener('input', () => {
                if (field.validity.valid) field.removeAttribute('aria-invalid');
                updateValidationFeedback(form);
            });
            field.addEventListener('change', () => {
                if (field.validity.valid) field.removeAttribute('aria-invalid');
                updateValidationFeedback(form);
            });
        });
        form.addEventListener('submit', function (event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                showValidationErrors(form);
            }
            form.classList.add('was-validated');
            updateValidationFeedback(form);
        }, false);
    });
}

function updateValidationFeedback(form) {
    form.querySelectorAll('.invalid-feedback[id]').forEach(feedback => {
        const controls = [...form.querySelectorAll('input, select, textarea')]
            .filter(field => (field.getAttribute('aria-describedby') || '').split(/\s+/).includes(feedback.id));
        const invalid = controls.find(field => !field.disabled && !field.validity.valid);
        // Bootstrap's sibling selector cannot reach messages outside input groups.
        feedback.classList.toggle('d-block', Boolean(invalid && (form.classList.contains('was-validated') || invalid.classList.contains('is-invalid'))));
        if (feedback.dataset.nativeValidation && invalid) feedback.textContent = getFieldValidationMessage(invalid);
    });
}

function getFieldValidationMessage(field) {
    const validity = field.validity;
    if (validity.valueMissing) return t('validation_required');
    if (validity.rangeUnderflow) return t('validation_minimum').replace('{min}', field.min);
    if (validity.rangeOverflow) return t('validation_maximum').replace('{max}', field.max);
    if (validity.stepMismatch) return t('validation_step').replace('{step}', field.step || '1').replace('{min}', field.min || '0');
    if (field.type === 'number' && !validity.valid) return t('validation_number');
    if (field.type === 'email' && validity.typeMismatch) return t('validation_email');
    return field.validationMessage;
}

function initializeSelectDescriptions() {
    const root = document.querySelector('main');
    if (!root) return;
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    if (!context) return;
    const descriptions = new Map();
    let sequence = 0;
    let frame = 0;
    const update = select => {
        const description = descriptions.get(select);
        if (!description) return;
        const selected = select.selectedOptions[0];
        const text = selected?.textContent.replace(/\s+/g, ' ').trim() || '';
        const style = getComputedStyle(select);
        context.font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
        const letterSpacing = Number.parseFloat(style.letterSpacing) || 0;
        const textWidth = context.measureText(text).width + letterSpacing * Math.max(0, text.length - 1);
        const availableWidth = select.clientWidth - Number.parseFloat(style.paddingLeft) - Number.parseFloat(style.paddingRight);
        const clipped = Boolean(select.getClientRects().length && text && textWidth > availableWidth + 1);
        description.hidden = !clipped;
        description.classList.toggle('d-none', !clipped);
        if (description.textContent !== text) description.textContent = text;
        const ids = new Set((select.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean));
        if (clipped) ids.add(description.id);
        else ids.delete(description.id);
        if (ids.size) select.setAttribute('aria-describedby', [...ids].join(' '));
        else select.removeAttribute('aria-describedby');
    };
    const refresh = () => {
        if (frame) return;
        frame = requestAnimationFrame(() => {
            frame = 0;
            descriptions.forEach((description, select) => {
                if (!select.isConnected) {
                    resizeObserver?.unobserve(select);
                    description.remove();
                    descriptions.delete(select);
                } else update(select);
            });
        });
    };
    const resizeObserver = window.ResizeObserver ? new ResizeObserver(refresh) : null;
    const register = select => {
        if (select.multiple || select.size > 1 || descriptions.has(select)) return;
        const description = document.createElement('div');
        description.id = `select-description-${++sequence}`;
        description.className = 'form-text select-value-description d-none';
        description.hidden = true;
        (select.closest('.input-group') || select).insertAdjacentElement('afterend', description);
        descriptions.set(select, description);
        resizeObserver?.observe(select);
    };
    root.querySelectorAll('select').forEach(register);
    new MutationObserver(mutations => {
        mutations.forEach(mutation => mutation.addedNodes.forEach(node => {
            if (node.nodeType !== Node.ELEMENT_NODE) return;
            if (node.matches('select')) register(node);
            node.querySelectorAll('select').forEach(register);
        }));
        refresh();
    }).observe(root, { childList: true, subtree: true });
    root.addEventListener('change', refresh);
    root.addEventListener('input', refresh);
    window.addEventListener('resize', refresh, { passive: true });
    window.addEventListener('pageshow', refresh);
    document.fonts?.ready.then(refresh);
    window.refreshSelectDescriptions = refresh;
    refresh();
}

function showValidationErrors(form) {
    const invalidFields = form.querySelectorAll('input:invalid, select:invalid, textarea:invalid');
    invalidFields.forEach(field => field.setAttribute('aria-invalid', 'true'));
    if (invalidFields.length > 0) {
        invalidFields[0].focus({ preventScroll: true });
        invalidFields[0].scrollIntoView({ block: 'center', behavior: 'auto' });
    }
}

// Progress tracking
function updateProgress() {
    const progressBar = document.querySelector('.progress-bar');
    const progressText = document.querySelector('.progress-text');

    if (progressBar) {
        const progress = (currentStep / totalSteps) * 100;
        progressBar.style.width = progress + '%';
        progressBar.setAttribute('aria-valuenow', progress);
    }

    if (progressText) {
        const template = progressText.dataset.labelTemplate || t('step_template');
        const description = progressText.dataset.labelDescription || '';
        let label = template.replace('{current}', currentStep).replace('{total}', totalSteps);
        if (description) {
            label += ` - ${description}`;
        }
        progressText.textContent = label;
    }
}

// Navigation functions
function goToNextStep(url, data = null, onSuccess = null) {
    if (data) {
        return submitFormData(url, data, onSuccess);
    } else {
        window.location.href = url;
    }
}

function goToPreviousStep() {
    // Use the custom nav-confirm modal when there are unsaved changes,
    // otherwise just go back immediately.
    if (typeof window.showNavConfirm === 'function') {
        window.showNavConfirm('__back__');
    } else {
        window.history.back();
    }
}

// Form submission
let submissionInProgress = null;

function submitFormData(url, data, onSuccess = null) {
    // Double-clicks and repeated Enter presses share the existing request.
    if (submissionInProgress) return submissionInProgress;

    showLoadingOverlay();
    const submittedValues = window.captureFormValues?.();
    const buttons = [...document.querySelectorAll('main button[type="submit"], main .btn-nav-next')]
        .filter(button => !button.disabled);
    buttons.forEach(button => {
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
    });
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 60000);

    const headers = {
        'Content-Type': 'application/json',
    };

    // Add CSRF token if available
    const csrfInput = document.querySelector('input[name="csrf_token"]');
    if (csrfInput) {
        headers['X-CSRFToken'] = csrfInput.value;
    }

    submissionInProgress = fetch(url, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(data),
        signal: controller.signal
    })
        .then(async response => {
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || t('error_message'));
            return result;
        })
        .then(data => {
            if (data.status === 'success' || data.success === true) {
                const changedDuringSave = submittedValues !== undefined && window.captureFormValues?.() !== submittedValues;
                window.markFormSubmitting?.(submittedValues);
                // Clear local drafts only after the server confirms that it saved them.
                if (!changedDuringSave && typeof onSuccess === 'function') {
                    try { onSuccess(data); } catch (error) { console.error('Draft cleanup:', error); }
                }
                if (changedDuringSave) {
                    showToast(t('edited_during_save'), 'info');
                    return data;
                }
                // Increment step on successful submission
                if (currentStep < totalSteps) {
                    currentStep++;
                    updateProgress();
                }

                if (data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    showToast(t('success_message'), 'success');
                }
            } else {
                showToast(data.message || t('error_message'), 'error');
            }
            return data;
        })
        .catch(error => {
            console.error('Error:', error);
            showToast(error.name === 'AbortError' ? t('request_timeout') : (error.message || t('error_message')), 'error');
            return null;
        })
        .finally(() => {
            window.clearTimeout(timeout);
            hideLoadingOverlay();
            buttons.forEach(button => {
                button.disabled = false;
                button.removeAttribute('aria-busy');
            });
            submissionInProgress = null;
        });
    return submissionInProgress;
}

// Loading overlay
function showLoadingOverlay(message = null) {
    let overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        if (message) overlay.querySelector('.loading-status-message').textContent = message;
        return;
    }
    overlay = document.createElement('div');
    overlay.className = 'spinner-overlay';
    overlay.id = 'loadingOverlay';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-live', 'polite');
    overlay.setAttribute('aria-atomic', 'true');

    const content = document.createElement('div');
    content.className = 'loading-status-content';
    const spinner = document.createElement('span');
    spinner.className = 'spinner-border loading-status-spinner text-success';
    spinner.setAttribute('aria-hidden', 'true');
    const label = document.createElement('span');
    label.className = 'loading-status-message';
    label.textContent = message || t('loading');
    content.append(spinner, label);
    overlay.appendChild(content);
    document.body.appendChild(overlay);
    document.querySelector('main')?.setAttribute('aria-busy', 'true');
}

function hideLoadingOverlay() {
    document.querySelectorAll('#loadingOverlay').forEach(overlay => overlay.remove());
    document.querySelector('main')?.removeAttribute('aria-busy');
}

// Browsers can restore the previous DOM, including its loading state, with Back.
window.addEventListener('pageshow', hideLoadingOverlay);

// Toast notifications
function showToast(message, type = 'info') {
    const toastContainer = getOrCreateToastContainer();
    const text = String(message ?? '');
    if ([...toastContainer.children].some(toast => toast.dataset.message === text)) return;
    const bgClass = type === 'success' ? 'bg-success' :
        type === 'error' ? 'bg-danger' :
            type === 'warning' ? 'bg-warning' : 'bg-info';
    const toastElement = document.createElement('div');
    const lightBackground = type === 'info' || type === 'warning';
    toastElement.className = `toast align-items-center ${bgClass} ${lightBackground ? 'text-dark' : 'text-white'} border-0`;
    toastElement.dataset.message = text;
    toastElement.setAttribute('role', type === 'error' ? 'alert' : 'status');
    toastElement.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
    toastElement.setAttribute('aria-atomic', 'true');
    const row = document.createElement('div');
    row.className = 'd-flex';
    const body = document.createElement('div');
    body.className = 'toast-body';
    const icon = document.createElement('i');
    icon.className = `bi bi-${getToastIcon(type)} me-2`;
    icon.setAttribute('aria-hidden', 'true');
    body.append(icon, document.createTextNode(text));
    const close = document.createElement('button');
    close.type = 'button';
    close.className = `btn-close ${lightBackground ? '' : 'btn-close-white'} me-2 m-auto`;
    close.setAttribute('aria-label', t('dismiss_notification'));
    close.setAttribute('data-bs-dismiss', 'toast');
    row.append(body, close);
    toastElement.appendChild(row);
    toastContainer.appendChild(toastElement);
    if (!window.bootstrap?.Toast) {
        toastElement.classList.add('show');
        close.addEventListener('click', () => toastElement.remove());
        return;
    }
    const toast = new bootstrap.Toast(toastElement, {
        autohide: true,
        delay: type === 'error' ? 8000 : 5000
    });

    toast.show();

    // Remove toast element after it's hidden
    toastElement.addEventListener('hidden.bs.toast', () => {
        toastElement.remove();
    });
}

function getOrCreateToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '11000';
        // Clear the sticky green strip so toasts never cover the language switcher.
        container.style.top = 'calc(63px + 1rem)';
        document.body.appendChild(container);
    }
    return container;
}

function getToastIcon(type) {
    switch (type) {
        case 'success': return 'check-circle-fill';
        case 'error': return 'exclamation-triangle-fill';
        case 'warning': return 'exclamation-circle-fill';
        default: return 'info-circle-fill';
    }
}

// Chart initialization
let chartInstances = {};

function destroyExistingCharts() {
    Object.keys(chartInstances).forEach(chartId => {
        if (chartInstances[chartId]) {
            chartInstances[chartId].$labelObserver?.disconnect();
            chartInstances[chartId].destroy();
        }
    });
    chartInstances = {};
}

function initializeCharts() {
    // Destroy existing charts before creating new ones
    destroyExistingCharts();

    // Get analysis type from DOM
    const container = document.getElementById('analysis-container');
    const type = container ? container.dataset.analysisType : null;

    Chart.defaults.color = getThemeColor('--text-muted');
    Chart.defaults.borderColor = getThemeColor('--border');
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) Chart.defaults.animation = false;

    // Get chart data from API
    const url = type ? `/api/chart_data?type=${type}` : '/api/chart_data';

    fetch(url)
        .then(response => response.json())
        .then(async data => {
            if (document.fonts?.ready) await document.fonts.ready;
            if (data.error) {
                console.error('Chart data error:', data.error);
                return;
            }

            createCostChart(data.cost_comparison);
            createEmissionsChart(data.emissions_comparison);
            createHealthChart(data.health_comparison);
            createRadarChart(data);
        })
        .catch(error => {
            console.error('Error fetching chart data:', error);
        });
}

// Wrap labels by their rendered width, preserving Malayalam grapheme clusters.
function wrapChartLabel(label, maxWidth, context) {
    const words = String(label).trim().split(/\s+/);
    const lines = [];
    let line = '';
    const segmenter = typeof Intl.Segmenter === 'function'
        ? new Intl.Segmenter(getCurrentLanguage(), { granularity: 'grapheme' })
        : null;
    words.forEach(word => {
        const candidate = line ? `${line} ${word}` : word;
        if (context.measureText(candidate).width <= maxWidth) {
            line = candidate;
            return;
        }
        if (line) lines.push(line);
        line = '';
        const clusters = segmenter
            ? Array.from(segmenter.segment(word), segment => segment.segment)
            : (word.match(/\P{Mark}\p{Mark}*|\p{Mark}+/gu) || Array.from(word));
        clusters.forEach(cluster => {
            if (line && context.measureText(line + cluster).width > maxWidth) {
                lines.push(line);
                line = cluster;
            } else {
                line += cluster;
            }
        });
    });
    if (line) lines.push(line);
    return lines.length ? lines : [''];
}

function createComparisonChart(chartId, data, metricLabel, unit) {
    const canvas = document.getElementById(chartId);
    if (!canvas || !Array.isArray(data?.labels) || !Array.isArray(data?.data)) return;
    const plot = canvas.closest('.chart-plot') || canvas.parentElement;
    const context = canvas.getContext('2d');
    const fontFamily = getComputedStyle(document.body).fontFamily;
    let chart = null;
    let lastWidth = 0;

    function fitLabels() {
        const width = plot.clientWidth;
        if (!width || Math.abs(width - lastWidth) < 1) return null;
        lastWidth = width;
        context.font = `13px ${fontFamily}`;
        const maxLabelWidth = Math.max(64, Math.min(168, width * 0.43));
        const labels = data.labels.map(label => wrapChartLabel(label, maxLabelWidth, context));
        const longestLabel = Math.max(1, ...labels.map(lines => lines.length));
        // Category rows are evenly spaced; reserve enough room for the longest
        // translated label so no line overlaps the next fuel.
        const height = Math.max(300, data.labels.length * (longestLabel * 19 + 14) + 52);
        plot.style.setProperty('--chart-height', `${height}px`);
        if (chart) {
            chart.data.labels = labels;
            chart.options.scales.x.ticks.maxTicksLimit = width < 360 ? 3 : 5;
            chart.update('none');
        }
        return labels;
    }

    const formatValue = value => unit === 'currency'
        ? `₹${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
        : `${Number(value).toLocaleString('en-IN', { maximumFractionDigits: 0 })} kg`;
    const labels = fitLabels() || data.labels;
    chart = new Chart(canvas, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: metricLabel,
                data: data.data,
                backgroundColor: data.labels.map((_, index) => getColorForIndex(index)),
                // Two palette entries fall below 3:1 on white; the outline carries
                // the mark boundary so every bar stays distinguishable.
                borderColor: getThemeColor('--text'),
                borderWidth: 1,
                borderRadius: 5,
                borderSkipped: false,
                maxBarThickness: 26
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            resizeDelay: 100,
            animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                ? false : { duration: 250 },
            plugins: {
                legend: { display: false },
                title: { display: false },
                tooltip: {
                    callbacks: {
                        title(items) {
                            if (!items.length) return '';
                            context.font = `13px ${fontFamily}`;
                            return wrapChartLabel(data.labels[items[0].dataIndex], Math.max(96, plot.clientWidth - 40), context);
                        },
                        label(item) { return formatValue(item.parsed.x); }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: {
                        maxTicksLimit: plot.clientWidth < 360 ? 3 : 5,
                        maxRotation: 0,
                        font: { size: 12 },
                        callback(value) {
                            // Full values are available on tap and in the table.
                            const compact = Number(value).toLocaleString('en-IN', {
                                notation: 'compact', maximumFractionDigits: 1
                            });
                            return unit === 'currency' ? `₹${compact}` : compact;
                        }
                    }
                },
                y: {
                    grid: { display: false },
                    ticks: {
                        autoSkip: false,
                        padding: 8,
                        font: { size: 13, lineHeight: 1.45 }
                    }
                }
            }
        }
    });
    chartInstances[chartId] = chart;
    if (typeof ResizeObserver === 'function') {
        chart.$labelObserver = new ResizeObserver(fitLabels);
        chart.$labelObserver.observe(plot);
    }
}

function createCostChart(data) {
    createComparisonChart('costChart', data, t('chart_monthly_cost_label'), 'currency');
}

function createEmissionsChart(data) {
    createComparisonChart('emissionsChart', data, t('chart_annual_co2_label'), 'emissions');
}

function createHealthChart(data) {
    const ctx = document.getElementById('healthChart');
    if (!ctx) return;

    chartInstances['healthChart'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: t('chart_health_risk_label'),
                data: data.data,
                backgroundColor: data.data.map(value => {
                    if (value < 30) return getThemeColor('--success');
                    if (value < 50) return getThemeColor('--warning-fill');
                    if (value < 70) return getThemeColor('--warning');
                    return getThemeColor('--danger');
                }),
                borderColor: getThemeColor('--text'),
                borderWidth: 1,
                borderRadius: 8,
                borderSkipped: false,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: t('chart_health_risk_title'),
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    color: getThemeColor('--brand-strong')
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: function (value) {
                            return value + '/100';
                        }
                    }
                }
            },
            annotation: {
                annotations: {
                    line1: {
                        type: 'line',
                        yMin: 30,
                        yMax: 30,
                        borderColor: getThemeColor('--success'),
                        borderWidth: 2,
                        borderDash: [5, 5],
                        label: {
                            content: t('chart_low_risk_threshold'),
                            enabled: true,
                            position: 'end'
                        }
                    }
                }
            },
            animation: {
                duration: 250
            }
        }
    });
}

function createRadarChart(data) {
    const ctx = document.getElementById('radarChart');
    if (!ctx) return;

    // Simplified radar chart with top 3 alternatives
    const topAlternatives = data.cost_comparison.labels.slice(0, 4); // Current + top 3

    chartInstances['radarChart'] = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: [
                t('chart_radar_cost_efficiency'),
                t('chart_radar_low_emissions'),
                t('chart_radar_health_safety'),
                t('chart_radar_overall_rating')
            ],
            datasets: topAlternatives.map((label, index) => {
                const costScore = Math.max(0, 100 - (data.cost_comparison.data[index] / (Math.max(...data.cost_comparison.data) || 1) * 100));
                const emissionScore = Math.max(0, 100 - (data.emissions_comparison.data[index] / (Math.max(...data.emissions_comparison.data) || 1) * 100));
                const healthScore = Math.max(0, 100 - data.health_comparison.data[index]);
                const overallScore = (costScore + emissionScore + healthScore) / 3;

                return {
                    label: label,
                    data: [costScore, emissionScore, healthScore, overallScore],
                    borderColor: getColorForIndex(index),
                    backgroundColor: getColorForIndex(index, 0.1),
                    pointBackgroundColor: getColorForIndex(index),
                    pointBorderColor: getThemeColor('--surface'),
                    pointHoverBackgroundColor: getThemeColor('--surface'),
                    pointHoverBorderColor: getColorForIndex(index)
                };
            })
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: {
                    display: true,
                    text: t('chart_radar_title'),
                    font: {
                        size: 16,
                        weight: 'bold'
                    },
                    color: getThemeColor('--brand-strong')
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        stepSize: 20
                    }
                }
            },
            animation: {
                duration: 250,
                animateRotate: true,
                animateScale: true
            }
        }
    });
}

function getThemeColor(token) {
    return getComputedStyle(document.documentElement).getPropertyValue(token).trim();
}

function getColorForIndex(index, alpha = 1) {
    const color = getThemeColor('--chart-color-' + ((index % 8) + 1));
    if (alpha === 1) return color;
    const channels = color.slice(1).match(/.{2}/g).map(channel => parseInt(channel, 16));
    return 'rgba(' + channels.join(', ') + ', ' + alpha + ')';
}

// Animation helpers
function addAnimations() {
    // Add fade-in animation to cards
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => {
        card.classList.add('fade-in-up');
    });

    // Add slide-in animation to metrics
    const metrics = document.querySelectorAll('.metric-card');
    metrics.forEach(metric => {
        metric.classList.add('slide-in-right');
    });
}

// Saved values, rather than any input event, determine whether Back discards work.
// Browser-controlled unload prompts are deliberately not registered.
function initializeNavigationWarnings() {
    const forms = [...document.querySelectorAll('main form')];
    const snapshot = () => JSON.stringify(forms.map(form =>
        [...form.querySelectorAll('input, select, textarea')]
            .filter(field => !['hidden', 'submit', 'button', 'reset'].includes(field.type))
            .map(field => [field.name || field.id,
                field.type === 'checkbox' || field.type === 'radio' ? field.checked :
                    field.multiple ? [...field.selectedOptions].map(option => option.value) : field.value])
    ));
    let savedValues = snapshot();
    let hasEdited = false;
    let pendingNavTarget = null;
    let navigationTrigger = null;
    const modalElement = document.getElementById('navConfirmModal');
    const cancelButton = modalElement?.querySelector('[data-bs-dismiss="modal"]');
    const navigate = target => {
        if (typeof target === 'function') target();
        else if (target === '__back__') window.history.back();
        else if (target) window.location.href = target;
    };

    // Called after successful AJAX saves and immediately before native form.submit().
    window.captureFormValues = snapshot;
    window.markFormSubmitting = (values = snapshot()) => {
        savedValues = values;
        hasEdited = snapshot() !== savedValues;
    };

    // Pages restore server data and populate controls asynchronously. Capture that
    // settled state before the first edit, so loading controls is never a change.
    ['focusin', 'pointerdown', 'keydown'].forEach(eventName => {
        document.addEventListener(eventName, () => {
            if (!hasEdited) savedValues = snapshot();
        }, true);
    });
    forms.forEach(form => {
        form.addEventListener('input', () => { hasEdited = true; });
        form.addEventListener('change', () => { hasEdited = true; });
        form.addEventListener('click', event => {
            if (event.target.closest('.method-card')) hasEdited = true;
        });
    });
    const hasChanges = () => hasEdited && snapshot() !== savedValues;

    // A callback also supports actions such as changing language before reloading.
    window.showNavConfirm = function (target) {
        if (!hasChanges() || !modalElement || !window.bootstrap?.Modal) {
            navigate(target);
            return;
        }
        pendingNavTarget = target;
        navigationTrigger = document.activeElement;
        bootstrap.Modal.getOrCreateInstance(modalElement, { keyboard: true }).show();
    };

    document.addEventListener('click', function (e) {
        const backLink = e.target.closest('a.btn-nav-back, a[data-nav-confirm]');
        if (!backLink || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        if (backLink.target === '_blank' || backLink.hasAttribute('download')) return;
        if (!hasChanges()) return;
        e.preventDefault();
        window.showNavConfirm(backLink.href);
    });

    // Initialization already runs at DOMContentLoaded; bind now, not in a second
    // DOMContentLoaded listener that would never run.
    document.getElementById('navConfirmLeaveBtn')?.addEventListener('click', function () {
        const target = pendingNavTarget;
        pendingNavTarget = null;
        bootstrap.Modal.getInstance(modalElement)?.hide();
        navigate(target);
    });
    modalElement?.addEventListener('shown.bs.modal', () => cancelButton?.focus());
    modalElement?.addEventListener('hidden.bs.modal', () => {
        pendingNavTarget = null;
        if (navigationTrigger?.isConnected) navigationTrigger.focus();
        navigationTrigger = null;
    });
}

// Download and share functions
function downloadReport(type) {
    showToast(t('download_starting'), 'info');
    const url = type ? `/download_report?type=${type}` : '/download_report';
    window.location.href = url;
}

function shareResults() {
    if (navigator.share) {
        navigator.share({
            title: t('share_title'),
            text: t('share_text'),
            url: window.location.href
        }).catch(console.error);
    } else if (navigator.clipboard) {
        navigator.clipboard.writeText(window.location.href).then(() => {
            showToast(t('share_success'), 'success');
        }).catch(() => {
            showToast(t('share_copy_failed'), 'error');
        });
    }
}

// Export functions for global use
window.goToNextStep = goToNextStep;
window.goToPreviousStep = goToPreviousStep;
window.downloadReport = downloadReport;
window.shareResults = shareResults;
window.showToast = showToast;
