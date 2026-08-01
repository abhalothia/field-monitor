const form = document.querySelector('#login-form');
const status = document.querySelector('#status');
const button = form.querySelector('button');
const nextPath = new URLSearchParams(window.location.search).get('next') || '/manager';

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  status.textContent = '';
  button.disabled = true;
  try {
    const response = await fetch('/api/v1/launch/login', {
      method: 'POST',
      headers: {'content-type': 'application/json'},
      body: JSON.stringify({password: form.password.value, next_path: nextPath}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Unable to sign in');
    window.location.assign(result.next_path);
  } catch (error) {
    status.textContent = error.message || 'Unable to sign in';
  } finally {
    button.disabled = false;
  }
});
