document.addEventListener('click', (event) => {
  const close = event.target.closest('.toast-close');
  if (close) close.closest('.toast')?.remove();
});

document.addEventListener('submit', (event) => {
  const form = event.target;
  const button = event.submitter;
  if (!button || !form.checkValidity()) return;
  button.classList.add('loading');
  button.disabled = true;
  const label = button.querySelector('.btn-label');
  if (label) label.textContent = 'Working…';
  const spinner = document.createElement('span');
  spinner.className = 'spinner';
  spinner.setAttribute('aria-hidden', 'true');
  button.prepend(spinner);
});
