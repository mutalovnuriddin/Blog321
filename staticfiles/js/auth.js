document.querySelectorAll('[data-password-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
        const input = button.parentElement.querySelector('input');
        const reveal = input.type === 'password';

        input.type = reveal ? 'text' : 'password';
        button.textContent = reveal ? 'Yashirish' : 'Ko‘rsatish';
        button.setAttribute('aria-label', reveal ? 'Parolni yashirish' : 'Parolni ko‘rsatish');
    });
});
