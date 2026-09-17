document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-expand-target]').forEach((button) => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.expandTarget);
      if (!target) return;
      const expanded = target.classList.toggle('is-expanded');
      button.textContent = expanded ? 'たたむ' : 'もっと表示';
    });
  });
});
