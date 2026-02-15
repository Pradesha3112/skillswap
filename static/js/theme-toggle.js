// Theme Toggle Functionality
(function() {
    'use strict';

    // Get theme from localStorage or default to 'light'
    const getStoredTheme = () => localStorage.getItem('theme') || 'light';
    
    // Set theme
    const setTheme = (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        updateThemeIcon(theme);
    };

    // Update theme icon based on current theme
    const updateThemeIcon = (theme) => {
        const themeIcon = document.getElementById('themeIcon');
        if (themeIcon) {
            themeIcon.textContent = theme === 'dark' ? '☀️' : '🌙';
        }
    };

    // Initialize theme on page load
    const initTheme = () => {
        const currentTheme = getStoredTheme();
        setTheme(currentTheme);
    };

    // Toggle theme
    const toggleTheme = () => {
        const currentTheme = getStoredTheme();
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        setTheme(newTheme);
    };

    // Event listener for theme toggle button
    document.addEventListener('DOMContentLoaded', () => {
        initTheme();
        
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', toggleTheme);
        }
    });

    // Also listen for theme changes from other tabs/windows
    window.addEventListener('storage', (e) => {
        if (e.key === 'theme') {
            setTheme(e.newValue || 'light');
        }
    });
})();


