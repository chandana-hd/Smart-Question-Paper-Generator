// frontend/src/js/views/login.js

export function setupLoginView() {
    console.log("Login view setup initiated.");

    const loginForm = document.getElementById('login-form');
    const registerLink = document.getElementById('register-link');
    const forgotPasswordLink = document.getElementById('forgot-password-link');

    if (loginForm) {
        loginForm.addEventListener('submit', async (event) => {
            event.preventDefault(); // Prevent default form submission

            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;

            console.log('Attempting login with:', { email, password });

            // --- IMPORTANT: This is where you'll make your API call to the backend ---
            try {
                // Example API call (replace with your actual backend endpoint)
                // We'll put actual API call functions in src/js/utils/api.js later
                const response = await fetch('YOUR_BACKEND_LOGIN_ENDPOINT', { // Replace this placeholder!
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ email, password }),
                });

                const data = await response.json();

                if (response.ok) {
                    console.log('Login successful:', data);
                    // --- New idea: Store token and user data ---
                    // You'll want to save the authentication token (e.g., localStorage, sessionStorage)
                    // and potentially some user details from 'data' here.
                    // Example: localStorage.setItem('authToken', data.token);
                    // Example: redirectTo('/dashboard'); // We'll implement this routing next
                    alert('Login successful!');
                } else {
                    console.error('Login failed:', data.message || 'Unknown error');
                    alert(`Login failed: ${data.message || 'Please check your credentials.'}`);
                }
            } catch (error) {
                console.error('Network or server error during login:', error);
                alert('An error occurred during login. Please try again.');
            }
        });
    } else {
        console.error("Login form not found in the DOM.");
    }

    if (registerLink) {
        registerLink.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('Navigating to register page...');
            // We'll integrate our client-side router here later
            // For now, you can just see this log
        });
    }

    if (forgotPasswordLink) {
        forgotPasswordLink.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('Navigating to forgot password page...');
            // We'll integrate our client-side router here later
        });
    }
}