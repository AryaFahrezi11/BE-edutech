/* ============================================
   EduTech Landing Page — Interactive JavaScript
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {

  // --- Navbar scroll effect ---
  const navbar = document.getElementById('navbar');

  const handleScroll = () => {
    if (window.scrollY > 50) {
      navbar.classList.add('scrolled');
    } else {
      navbar.classList.remove('scrolled');
    }
  };

  window.addEventListener('scroll', handleScroll, { passive: true });
  handleScroll(); // Initial check


  // --- Mobile hamburger menu ---
  const hamburger = document.getElementById('hamburger');
  const navLinks = document.getElementById('navLinks');
  const navOverlay = document.getElementById('navOverlay');

  const toggleMenu = () => {
    hamburger.classList.toggle('active');
    navLinks.classList.toggle('open');
    navOverlay.classList.toggle('active');
    document.body.style.overflow = navLinks.classList.contains('open') ? 'hidden' : '';
  };

  hamburger.addEventListener('click', toggleMenu);
  navOverlay.addEventListener('click', toggleMenu);

  // Close menu when clicking a link
  navLinks.querySelectorAll('.navbar__link, .navbar__cta').forEach(link => {
    link.addEventListener('click', () => {
      if (navLinks.classList.contains('open')) {
        toggleMenu();
      }
    });
  });


  // --- Scroll reveal animations ---
  const revealElements = document.querySelectorAll('.reveal');

  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        revealObserver.unobserve(entry.target);
      }
    });
  }, {
    threshold: 0.15,
    rootMargin: '0px 0px -50px 0px'
  });

  revealElements.forEach(el => revealObserver.observe(el));


  // --- Smooth scroll for anchor links ---
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const targetId = this.getAttribute('href');
      const targetEl = document.querySelector(targetId);

      if (targetEl) {
        const navbarHeight = navbar.offsetHeight;
        const elementPosition = targetEl.getBoundingClientRect().top + window.scrollY;
        const offsetPosition = elementPosition - navbarHeight - 20;

        window.scrollTo({
          top: offsetPosition,
          behavior: 'smooth'
        });
      }
    });
  });


  // --- Parallax effect on hero floating cards ---
  const heroVisual = document.querySelector('.hero__visual');

  if (heroVisual) {
    const floats = heroVisual.querySelectorAll('.hero__float');

    window.addEventListener('mousemove', (e) => {
      const { clientX, clientY } = e;
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;
      const moveX = (clientX - centerX) / centerX;
      const moveY = (clientY - centerY) / centerY;

      floats.forEach((float, i) => {
        const depth = (i + 1) * 8;
        float.style.transform = `translateY(${Math.sin(Date.now() / 1000 + i) * 12}px) translate(${moveX * depth}px, ${moveY * depth}px)`;
      });
    }, { passive: true });
  }


  // --- Typing effect on hero title (subtle) ---
  const heroTitle = document.querySelector('.hero__title span');
  if (heroTitle) {
    const text = heroTitle.textContent;
    heroTitle.textContent = '';
    heroTitle.style.borderRight = '3px solid var(--primary)';

    let i = 0;
    const typeInterval = setInterval(() => {
      if (i < text.length) {
        heroTitle.textContent += text.charAt(i);
        i++;
      } else {
        clearInterval(typeInterval);
        // Remove cursor after typing
        setTimeout(() => {
          heroTitle.style.borderRight = 'none';
        }, 800);
      }
    }, 80);
  }


  // --- Counter animation for hero stats ---
  const statValues = document.querySelectorAll('.hero__stat-value');

  const animateCounter = (el) => {
    const text = el.textContent.trim();

    // Only animate numeric values
    const numMatch = text.match(/^(\d+)/);
    if (!numMatch) return;

    const targetNum = parseInt(numMatch[1]);
    const suffix = text.replace(numMatch[1], '');
    let current = 0;
    const increment = Math.ceil(targetNum / 40);
    const duration = 1500;
    const stepTime = duration / (targetNum / increment);

    el.textContent = '0' + suffix;

    const counter = setInterval(() => {
      current += increment;
      if (current >= targetNum) {
        current = targetNum;
        clearInterval(counter);
      }
      el.textContent = current + suffix;
    }, stepTime);
  };

  const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        animateCounter(entry.target);
        statsObserver.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  statValues.forEach(el => statsObserver.observe(el));


  // --- Feature cards tilt effect ---
  const featureCards = document.querySelectorAll('.feature-card');

  featureCards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = (y - centerY) / centerY * -5;
      const rotateY = (x - centerX) / centerX * 5;

      card.style.transform = `translateY(-8px) perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'translateY(0) perspective(1000px) rotateX(0deg) rotateY(0deg)';
    });
  });


  // --- App preview phone hover glow ---
  const previewPhones = document.querySelectorAll('.app-preview__phone');
  previewPhones.forEach(phone => {
    phone.addEventListener('mouseenter', () => {
      phone.style.boxShadow = '0 30px 80px rgba(28, 176, 246, 0.3)';
    });
    phone.addEventListener('mouseleave', () => {
      phone.style.boxShadow = '';
    });
  });

});
