// Home Button Component - Reusable navigation home button
// Styled to match social links

const homeButtonHTML = `
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z"/>
  </svg>
`;

// Initialize home button when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('home-button');
  if (container) {
    container.href = '/';
    container.setAttribute('aria-label', 'Home');
    container.innerHTML = homeButtonHTML;
  }
});
