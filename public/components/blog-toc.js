// Blog Table of Contents Component
// Automatically generates a sidebar TOC from h2 headers in the blog post

document.addEventListener('DOMContentLoaded', () => {
  const tocContainer = document.getElementById('blog-toc');
  const blogContent = document.querySelector('.blog-post-content');
  
  if (!tocContainer || !blogContent) return;
  
  // Get all h2 headers from the blog content
  const headers = blogContent.querySelectorAll('h2');
  
  if (headers.length === 0) {
    tocContainer.style.display = 'none';
    return;
  }
  
  // Build TOC HTML
  let tocHTML = '<nav class="toc-nav"><h3 class="toc-title">Contents</h3><ul class="toc-list">';
  
  headers.forEach((header, index) => {
    // Create an ID for the header if it doesn't have one
    if (!header.id) {
      header.id = 'section-' + (index + 1);
    }
    
    tocHTML += `<li class="toc-item">
      <a href="#${header.id}" class="toc-link" data-index="${index}">${header.textContent}</a>
    </li>`;
  });
  
  tocHTML += '</ul></nav>';
  tocContainer.innerHTML = tocHTML;
  
  const tocLinks = tocContainer.querySelectorAll('.toc-link');
  let clickedIndex = -1;
  let scrollTimeout = null;
  
  // Helper to set active link
  function setActiveLink(index) {
    tocLinks.forEach((l, i) => {
      if (i === index) {
        l.classList.add('active');
      } else {
        l.classList.remove('active');
      }
    });
  }
  
  // Add smooth scrolling behavior with immediate highlight
  tocLinks.forEach((link, index) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const targetId = link.getAttribute('href').slice(1);
      const target = document.getElementById(targetId);
      if (target) {
        // Immediately highlight the clicked section
        clickedIndex = index;
        setActiveLink(index);
        
        // Remove highlight from all headers
        headers.forEach(h => h.classList.remove('highlight'));
        
        // Add highlight class to target header for visual feedback
        target.classList.add('highlight');
        
        // Scroll to target
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
        // Update URL hash without jumping
        history.pushState(null, null, '#' + targetId);
        
        // Remove highlight class after animation completes
        setTimeout(() => {
          target.classList.remove('highlight');
        }, 2000);
        
        // After scroll completes, allow scroll-based highlighting again
        clearTimeout(scrollTimeout);
        scrollTimeout = setTimeout(() => {
          clickedIndex = -1;
        }, 1000);
      }
    });
  });
  
  // Calculate which section is currently most visible
  function updateActiveOnScroll() {
    // If user just clicked, don't override their selection
    if (clickedIndex >= 0) return;
    
    const scrollTop = window.scrollY;
    const viewportHeight = window.innerHeight;
    const documentHeight = document.documentElement.scrollHeight;
    const offset = viewportHeight * 0.3; // Consider section active when it's in top 30%
    
    // Check if we're near the bottom of the page (within 200px)
    const isNearBottom = scrollTop + viewportHeight >= documentHeight - 200;
    
    // If near bottom, always highlight the last section
    if (isNearBottom && headers.length > 0) {
      setActiveLink(headers.length - 1);
      return;
    }
    
    let activeIndex = 0;
    
    // Find the last header that has scrolled past the offset point
    headers.forEach((header, index) => {
      const rect = header.getBoundingClientRect();
      if (rect.top <= offset) {
        activeIndex = index;
      }
    });
    
    setActiveLink(activeIndex);
  }
  
  // Throttled scroll handler
  let ticking = false;
  window.addEventListener('scroll', () => {
    if (!ticking) {
      requestAnimationFrame(() => {
        updateActiveOnScroll();
        ticking = false;
      });
      ticking = true;
    }
  });
  
  // Initial highlight
  updateActiveOnScroll();
});
