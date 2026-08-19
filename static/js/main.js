// PWA Installation
let deferredPrompt;
const installPrompt = document.createElement('div');
installPrompt.className = 'pwa-install-prompt';
installPrompt.innerHTML = `
    <div>
        <strong>Install NeuraLib</strong>
        <p>Add to your home screen for quick access</p>
    </div>
    <div>
        <button class="btn btn-light" id="install-pwa">Install</button>
        <button class="btn btn-light" id="dismiss-pwa">Not Now</button>
    </div>
`;
document.body.appendChild(installPrompt);

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    installPrompt.classList.add('show');
});

document.getElementById('install-pwa').addEventListener('click', async () => {
    if (deferredPrompt) {
        deferredPrompt.prompt();
        const { outcome } = await deferredPrompt.userChoice;
        if (outcome === 'accepted') {
            console.log('User accepted the install prompt');
        }
        deferredPrompt = null;
        installPrompt.classList.remove('show');
    }
});

document.getElementById('dismiss-pwa').addEventListener('click', () => {
    installPrompt.classList.remove('show');
});

// Mobile Navigation
// Note: the hamburger toggle (data-bs-toggle="collapse") and the "admin"
// dropdown (data-bs-toggle="dropdown") are both handled natively by
// Bootstrap's own JS bundle already loaded on the page - no custom JS
// needed here. A previous version of this file duplicated that behavior
// by hand, which conflicted with Bootstrap's dropdown handling: tapping
// the "admin" dropdown was also caught by a generic "close menu on any
// .nav-link click" listener, so the whole mobile menu closed instead of
// the Profile/Logout submenu opening. Removed entirely to let Bootstrap
// handle both correctly on its own.

// Loading Spinner
function showLoading() {
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    spinner.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
    `;
    document.body.appendChild(spinner);
    spinner.classList.add('show');
}

function hideLoading() {
    const spinner = document.querySelector('.loading-spinner');
    if (spinner) {
        spinner.classList.remove('show');
        setTimeout(() => spinner.remove(), 300);
    }
}

// Toast Notifications
function showToast(message, type = 'success') {
    const toastContainer = document.querySelector('.toast-container') || document.createElement('div');
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);

    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, {
        autohide: true,
        delay: 3000
    });
    bsToast.show();

    // Add swipe to dismiss
    let touchStartX = 0;
    let touchEndX = 0;

    toast.addEventListener('touchstart', (e) => {
        touchStartX = e.touches[0].clientX;
    });

    toast.addEventListener('touchmove', (e) => {
        touchEndX = e.touches[0].clientX;
        const swipeDistance = touchEndX - touchStartX;
        
        if (Math.abs(swipeDistance) > 50) {
            toast.style.transform = `translateX(${swipeDistance}px)`;
        }
    });

    toast.addEventListener('touchend', () => {
        const swipeDistance = touchEndX - touchStartX;
        if (Math.abs(swipeDistance) > 100) {
            bsToast.hide();
        } else {
            toast.style.transform = '';
        }
    });

    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
        if (toastContainer.children.length === 0) {
            toastContainer.remove();
        }
    });
}

// Form Validation
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
});

// Material Search
const searchInput = document.querySelector('.search-input');
if (searchInput) {
    searchInput.addEventListener('input', debounce((e) => {
        const searchTerm = e.target.value.toLowerCase();
        const materials = document.querySelectorAll('.material-card');
        
        materials.forEach(material => {
            const title = material.querySelector('.card-title').textContent.toLowerCase();
            const description = material.querySelector('.card-text').textContent.toLowerCase();
            
            if (title.includes(searchTerm) || description.includes(searchTerm)) {
                material.style.display = '';
            } else {
                material.style.display = 'none';
            }
        });
    }, 300));
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Pull to Refresh
let touchStartY = 0;
let touchEndY = 0;
let pullToRefreshIndicator = document.createElement('div');
pullToRefreshIndicator.className = 'pull-to-refresh';
document.body.appendChild(pullToRefreshIndicator);

document.addEventListener('touchstart', (e) => {
    touchStartY = e.touches[0].clientY;
});

document.addEventListener('touchmove', (e) => {
    if (window.scrollY === 0) {
        touchEndY = e.touches[0].clientY;
        const pullDistance = touchEndY - touchStartY;
        
        if (pullDistance > 0) {
            e.preventDefault();
            const pullProgress = Math.min(pullDistance / 150, 1);
            pullToRefreshIndicator.style.transform = `scaleX(${pullProgress})`;
        }
    }
});

document.addEventListener('touchend', () => {
    const pullDistance = touchEndY - touchStartY;
    if (pullDistance > 150 && window.scrollY === 0) {
        pullToRefreshIndicator.style.transform = 'scaleX(1)';
        setTimeout(() => {
            window.location.reload();
        }, 300);
    } else {
        pullToRefreshIndicator.style.transform = 'scaleX(0)';
    }
});

// Handle File Upload
const fileInput = document.querySelector('input[type="file"]');
if (fileInput) {
    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const maxSize = 16 * 1024 * 1024; // 16MB
            if (file.size > maxSize) {
                showToast('File size exceeds 16MB limit', 'danger');
                e.target.value = '';
            }
        }
    });
}

// Mobile Form Improvements
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        // Prevent zoom on focus for iOS
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('focus', () => {
                input.style.fontSize = '16px';
            });
        });

        // Add loading state to buttons
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            form.addEventListener('submit', () => {
                submitButton.disabled = true;
                submitButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Loading...';
            });
        }
    });
});

// Mobile Search Improvements
if (searchInput) {
    // Clear search on escape
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            searchInput.value = '';
            filterMaterials();
        }
    });

    // Add clear button
    const clearButton = document.createElement('button');
    clearButton.className = 'btn btn-link position-absolute end-0 top-50 translate-middle-y';
    clearButton.innerHTML = '<i class="bi bi-x"></i>';
    clearButton.style.display = 'none';
    searchInput.parentNode.appendChild(clearButton);

    searchInput.addEventListener('input', () => {
        clearButton.style.display = searchInput.value ? 'block' : 'none';
    });

    clearButton.addEventListener('click', () => {
        searchInput.value = '';
        clearButton.style.display = 'none';
        filterMaterials();
        searchInput.focus();
    });
}

// Mobile Rating Improvements
const ratingStars = document.querySelectorAll('.rating-stars .bi-star-fill');
if (ratingStars.length > 0) {
    ratingStars.forEach(star => {
        // Add touch feedback
        star.addEventListener('touchstart', () => {
            star.style.transform = 'scale(1.2)';
        });

        star.addEventListener('touchend', () => {
            star.style.transform = 'scale(1)';
        });
    });
}

// Mobile Image Optimization
document.addEventListener('DOMContentLoaded', () => {
    const images = document.querySelectorAll('img');
    images.forEach(img => {
        // Add loading="lazy" for better performance
        img.loading = 'lazy';
        
        // Add error handling
        img.onerror = function() {
            this.src = '/static/images/placeholder.png';
        };
    });
});

// Mobile Scroll Improvements
let lastScrollTop = 0;
const navbar = document.querySelector('.navbar');
const navbarCollapseEl = document.getElementById('navbarNav');

if (navbar) {
    window.addEventListener('scroll', () => {
        const scrollTop = window.pageYOffset || document.documentElement.scrollTop;

        // Never hide the navbar while the mobile menu is open, and ignore
        // tiny scroll movements (e.g. the bounce from just touching the
        // screen) so the nav doesn't jitter or disappear mid-tap.
        const menuIsOpen = navbarCollapseEl && navbarCollapseEl.classList.contains('show');
        const scrollDelta = Math.abs(scrollTop - lastScrollTop);

        if (!menuIsOpen && scrollDelta > 10) {
            if (scrollTop > lastScrollTop && scrollTop > 80) {
                // Scrolling down
                navbar.style.transform = 'translateY(-100%)';
            } else {
                // Scrolling up
                navbar.style.transform = 'translateY(0)';
            }
            lastScrollTop = scrollTop;
        }

        if (menuIsOpen) {
            navbar.style.transform = 'translateY(0)';
        }
    });
}

// Define filterMaterials function
function filterMaterials() {
    const searchTerm = searchInput.value.toLowerCase();
    const materials = document.querySelectorAll('.material-card');
    
    materials.forEach(material => {
        const title = material.querySelector('.card-title').textContent.toLowerCase();
        const description = material.querySelector('.card-text').textContent.toLowerCase();
        
        if (title.includes(searchTerm) || description.includes(searchTerm)) {
            material.style.display = '';
        } else {
            material.style.display = 'none';
        }
    });
} 
// --------------------------------------------------------------------
// Offline material caching (used by the "Read Online" / "Download"
// buttons on a material page, and by the My Downloads page).
// --------------------------------------------------------------------
const MATERIALS_CACHE = 'neuralib-materials-v1';

// Fetches a material file and stores it in the Cache Storage API so it can
// be read offline later, even if the browser tab is closed and reopened.
function cacheForOffline(url) {
    if (!('caches' in window)) return;
    caches.open(MATERIALS_CACHE).then(cache => {
        cache.add(url).catch(err => console.warn('Could not cache for offline use:', err));
    });
}

// Checks whether a URL is already cached, and calls back with true/false.
// Used by the My Downloads page to show an "Available offline" badge.
function isCachedOffline(url, callback) {
    if (!('caches' in window)) { callback(false); return; }
    caches.open(MATERIALS_CACHE).then(cache => {
        cache.match(url).then(match => callback(!!match));
    });
}

// --------------------------------------------------------------------
// Password show/hide toggle. Add class "password-toggle-wrapper" to a
// wrapper div containing a password <input> and a toggle <button
// class="password-toggle">, and this wires them all up automatically.
// --------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.password-toggle').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const wrapper = btn.closest('.password-toggle-wrapper');
            const input = wrapper ? wrapper.querySelector('input') : null;
            if (!input) return;
            const icon = btn.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                if (icon) { icon.classList.remove('fa-eye'); icon.classList.add('fa-eye-slash'); }
                btn.setAttribute('aria-label', 'Hide password');
            } else {
                input.type = 'password';
                if (icon) { icon.classList.remove('fa-eye-slash'); icon.classList.add('fa-eye'); }
                btn.setAttribute('aria-label', 'Show password');
            }
        });
    });
});
