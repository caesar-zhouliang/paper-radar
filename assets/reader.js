(() => {
  const root = document.documentElement;
  const themeButton = document.getElementById('themeToggle');
  const progress = document.getElementById('progress');
  const toTop = document.getElementById('toTop');
  const filter = document.getElementById('tocFilter');
  const links = [...document.querySelectorAll('.sidebar .toc-link')];
  const syncTheme = () => {
    const dark = root.dataset.theme === 'dark';
    themeButton.textContent = dark ? '切换浅色' : '切换深色';
    themeButton.setAttribute('aria-label', dark ? '切换到浅色主题' : '切换到深色主题');
  };
  syncTheme();
  themeButton.addEventListener('click', () => {
    root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('vp-dissociation-theme', root.dataset.theme);
    syncTheme();
  });
  document.getElementById('printBtn').addEventListener('click', () => window.print());

  const update = () => {
    const max = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = `${max > 0 ? Math.min(100, scrollY / max * 100) : 0}%`;
    toTop.classList.toggle('visible', scrollY > 700);
  };
  addEventListener('scroll', update, {passive: true});
  update();
  toTop.addEventListener('click', () => scrollTo({top: 0, behavior: 'smooth'}));

  filter.addEventListener('input', () => {
    const q = filter.value.trim().toLowerCase();
    links.forEach(link => link.classList.toggle('hidden', q && !link.textContent.toLowerCase().includes(q)));
  });

  const headings = [...document.querySelectorAll('.content h2,.content h3,.content h4')];
  const byId = new Map(links.map(link => [link.getAttribute('href').slice(1), link]));
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      links.forEach(link => link.classList.remove('active'));
      byId.get(entry.target.id)?.classList.add('active');
    }
  }, {rootMargin: '-8% 0px -76% 0px', threshold: 0});
  headings.forEach(h => observer.observe(h));

  const lightbox = document.getElementById('lightbox');
  const image = document.getElementById('lightboxImage');
  const caption = document.getElementById('lightboxCaption');
  const close = document.getElementById('lightboxClose');
  let lastTrigger = null;
  document.querySelectorAll('.figure-zoom').forEach(button => button.addEventListener('click', () => {
    const sourceImage = button.querySelector('img');
    lastTrigger = button;
    image.src = sourceImage.src;
    image.alt = sourceImage.alt;
    image.width = sourceImage.naturalWidth || sourceImage.width;
    image.height = sourceImage.naturalHeight || sourceImage.height;
    caption.textContent = button.closest('.paper-figure')?.querySelector('figcaption')?.textContent.trim() || sourceImage.alt;
    lightbox.hidden = false;
    document.body.classList.add('no-scroll');
    close.focus();
  }));
  const closeLightbox = () => {
    lightbox.hidden = true;
    image.removeAttribute('src');
    image.removeAttribute('width');
    image.removeAttribute('height');
    document.body.classList.remove('no-scroll');
    lastTrigger?.focus();
  };
  close.addEventListener('click', closeLightbox);
  lightbox.addEventListener('click', event => { if (event.target === lightbox) closeLightbox(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !lightbox.hidden) closeLightbox();
  });
})();
