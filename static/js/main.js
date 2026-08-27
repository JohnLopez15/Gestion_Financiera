/**
 * Formatea un número o string a formato monetario $ XXX XXX XXX,XX
 * @param {number|string} value 
 * @returns {string} Formateado como $ 1.234.567,89 o $ 1 234 567,89
 */
function formatCurrency(value) {
    if (value === null || value === undefined || value === '') return '$ 0,00';
    let num = typeof value === 'string' ? parseFloat(value.replace(/[^0-9.-]+/g,"")) : value;
    if (isNaN(num)) return '$ 0,00';
    
    // Formato con espacio/punto de miles y coma decimal
    let parts = num.toFixed(2).split('.');
    let integerPart = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
    let decimalPart = parts[1];
    return `$ ${integerPart},${decimalPart}`;
}

/**
 * Convierte un string monetario con formato "$ 1 234 567,89" a número float estándar
 * @param {string} str 
 * @returns {number}
 */
function parseCurrencyToNumber(str) {
    if (!str) return 0;
    // Remueve $, espacios y cualquier caracter no numérico excepto coma o punto
    let cleaned = str.toString().replace(/\$/g, '').trim().replace(/\s/g, '');
    // Si tiene comas como separador decimal, convertimos a punto
    cleaned = cleaned.replace(',', '.');
    let val = parseFloat(cleaned);
    return isNaN(val) ? 0 : val;
}

/**
 * Aplica máscara de entrada de moneda en tiempo real a los inputs con clase .currency-input
 */
function setupCurrencyInputs() {
    document.querySelectorAll('.currency-input').forEach(input => {
        // Al recibir foco, si es $ 0,00 limpiar o seleccionar
        input.addEventListener('focus', function() {
            if (this.value === '$ 0,00' || this.value === '$ 0') {
                this.value = '';
            }
        });

        // Formateo dinámico mientras escribe
        input.addEventListener('input', function(e) {
            let cursorPosition = this.selectionStart;
            let rawValue = this.value.replace(/[^0-9]/g, '');
            
            if (!rawValue) {
                this.value = '$ 0,00';
                this.dataset.rawValue = '0';
                return;
            }

            // Tratamos los últimos 2 dígitos como decimales (centavos)
            let floatVal = parseFloat(rawValue) / 100;
            this.dataset.rawValue = floatVal.toString();
            this.value = formatCurrency(floatVal);
        });

        // Al perder el foco asegurar que no quede vacío
        input.addEventListener('blur', function() {
            if (!this.value || this.value.trim() === '' || this.value === '$') {
                this.value = '$ 0,00';
                this.dataset.rawValue = '0';
            }
        });

        // Inicializar valor inicial si no tiene formato
        if (!input.value || input.value === '0' || input.value === '0.0') {
            input.value = '$ 0,00';
            input.dataset.rawValue = '0';
        } else {
            let parsed = parseCurrencyToNumber(input.value);
            input.value = formatCurrency(parsed);
            input.dataset.rawValue = parsed.toString();
        }
    });
}

/**
 * Resetea los campos de un formulario a sus valores por defecto y los monetarios a $ 0,00
 * @param {HTMLFormElement} form 
 */
function resetFormToZeros(form) {
    form.reset();
    form.querySelectorAll('.currency-input').forEach(input => {
        input.value = '$ 0,00';
        input.dataset.rawValue = '0';
    });
    form.querySelectorAll('input[type="number"]').forEach(input => {
        if (input.dataset.defaultVal !== undefined) {
            input.value = input.dataset.defaultVal;
        }
    });
}

// Inicialización automática al cargar el DOM
document.addEventListener('DOMContentLoaded', () => {
    setupCurrencyInputs();
});

