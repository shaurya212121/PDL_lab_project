/**
 * Used on every page.
 * Any form with data-confirm="question" asks the user before submitting.
 */
document.addEventListener('submit', event => {
  const question = event.target.dataset ? event.target.dataset.confirm : null;
  if (question && !window.confirm(question)) {
    event.preventDefault();
  }
});
