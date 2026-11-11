
document.addEventListener("DOMContentLoaded", () => {
    const loginForm = document.getElementById("loginForm");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");

    const togglePassword = document.getElementById("togglePassword");
    const loginButton = document.getElementById("loginButton");
    const formMessage = document.getElementById("formMessage");

    const emailError = document.getElementById("emailError");
    const passwordError = document.getElementById("passwordError");

    const forgotPassword = document.getElementById("forgotPassword");
    const signupLink = document.getElementById("signupLink");
    const googleButton = document.getElementById("googleButton");

    // Display a message to the user.
    function showMessage(message, type = "") {
        formMessage.textContent = message;
        formMessage.className = "form-message";

        if (type) {
            formMessage.classList.add(type);
        }
    }

    // Clear previous validation errors.
    function clearErrors() {
        emailError.textContent = "";
        passwordError.textContent = "";

        emailInput.closest(".input-wrapper").classList.remove("has-error");
        passwordInput.closest(".input-wrapper").classList.remove("has-error");
    }

    // Show or hide the password.
    togglePassword.addEventListener("click", () => {
        const isPasswordHidden = passwordInput.type === "password";

        passwordInput.type = isPasswordHidden ? "text" : "password";

        togglePassword.setAttribute(
            "aria-label",
            isPasswordHidden ? "Hide password" : "Show password"
        );

        togglePassword.setAttribute(
            "aria-pressed",
            String(isPasswordHidden)
        );
    });

    // Remove errors as the user corrects the fields.
    emailInput.addEventListener("input", () => {
        emailError.textContent = "";
        emailInput.closest(".input-wrapper").classList.remove("has-error");
        showMessage();
    });

    passwordInput.addEventListener("input", () => {
        passwordError.textContent = "";
        passwordInput.closest(".input-wrapper").classList.remove("has-error");
        showMessage();
    });

    // Validate and handle the login form.
    loginForm.addEventListener("submit", (event) => {
        event.preventDefault();

        clearErrors();
        showMessage();

        const email = emailInput.value.trim();
        const password = passwordInput.value;

        let isValid = true;

        // Validate email.
        const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

        if (!email) {
            emailError.textContent = "Please enter your email address.";
            emailInput.closest(".input-wrapper").classList.add("has-error");
            isValid = false;
        } else if (!emailPattern.test(email)) {
            emailError.textContent = "Please enter a valid email address.";
            emailInput.closest(".input-wrapper").classList.add("has-error");
            isValid = false;
        }

        // Validate password.
        if (!password) {
            passwordError.textContent = "Please enter your password.";
            passwordInput.closest(".input-wrapper").classList.add("has-error");
            isValid = false;
        }

        if (!isValid) {
            showMessage("Please correct the errors above.", "error");
            return;
        }

        // A real login requires a backend authentication endpoint.
        showMessage(
            "Your form is valid. Connect your authentication backend to log in.",
            "success"
        );
    });

    // Forgot password action.
    forgotPassword.addEventListener("click", (event) => {
        event.preventDefault();

        const email = emailInput.value.trim();

        if (!email) {
            showMessage(
                "Enter your email address first to reset your password.",
                "error"
            );
            emailInput.focus();
            return;
        }

        showMessage(
            "Password reset is not available yet. Connect a backend to enable it.",
            "error"
        );
    });

    // Sign-up action.
    signupLink.addEventListener("click", (event) => {
        event.preventDefault();

        showMessage(
            "The registration page has not been connected yet.",
            "error"
        );
    });

    // Google sign-in action.
    googleButton.addEventListener("click", () => {
        showMessage(
            "Google sign-in requires Google OAuth configuration.",
            "error"
        );
    });
});