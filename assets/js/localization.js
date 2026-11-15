/* Compatibility for shared multilingual legal documents.
 * Marketing pages use static EN/RU links and do not load this script.
 * No runtime translation, storage access or automatic navigation.
 */
(() => {
  function initializeDocumentLinks() {
    document.querySelectorAll('.languages').forEach(container => {
      container.querySelectorAll('button[data-lang]').forEach(button => {
        const link = document.createElement('a');
        link.href = '#' + button.dataset.lang;
        link.lang = button.dataset.lang;
        link.textContent = button.textContent;
        container.replaceChild(link, button);
      });
      container.hidden = false;
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeDocumentLinks, { once: true });
  } else initializeDocumentLinks();
})();
