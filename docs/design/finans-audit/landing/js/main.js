'use strict';

/**
 * Лендинг «Финанс» — ванильный JS без зависимостей.
 * Каждый инициализатор молча выходит, если его блока нет на странице.
 * Узлы ищем по data-атрибутам: классы БЭМ принадлежат стилям.
 */

var THEME_KEY = 'finans-theme';

function initCubes() {
  var cubes = document.querySelectorAll('[data-cube]');
  if (!cubes.length) return;

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var EDGE_KIND = ['h', 'h', 'h', 'h', 'v', 'v', 'v', 'v', 'h', 'h', 'h', 'h'];
  var SIDES = ['front', 'back', 'right', 'left', 'top', 'bottom'];
  var TEXTURED = ['front', 'back', 'right', 'left'];

  function add(parent, cls) {
    var node = document.createElement('span');
    node.className = cls;
    parent.appendChild(node);
    return node;
  }

  cubes.forEach(function (cube) {
    if (cube.dataset.cubeReady) return;
    cube.dataset.cubeReady = '1';

    add(cube, 'cube__halo');
    var stage = add(cube, 'cube__stage');

    if (cube.hasAttribute('data-cube-orbit') && !reduced) {
      var orbit = add(stage, 'cube__orbit');
      for (var o = 1; o <= 12; o++) {
        var orbitNode = add(orbit, 'cube__orbit-node cube__orbit-node--' + o);
        add(orbitNode, 'cube__orbit-dot' + (o % 2 === 0 ? ' cube__orbit-dot--alt' : ''));
      }
    }

    var rig = add(stage, 'cube__rig');
    add(rig, 'cube__shockwave');
    var tilt = add(add(rig, 'cube__bob'), 'cube__tilt');
    var spin = add(tilt, 'cube__spin');

    SIDES.forEach(function (side) {
      var face = add(spin, 'cube__face cube__face--' + side);
      if (TEXTURED.indexOf(side) === -1) return;
      add(face, 'cube__node cube__node--' + side + '-a');
      add(face, 'cube__node cube__node--' + side + '-b');
      add(face, 'cube__scan cube__scan--' + side);
    });

    for (var e = 0; e < 12; e++) add(spin, 'cube__edge cube__edge--' + EDGE_KIND[e] + ' cube__edge--' + (e + 1));
    for (var c = 1; c <= 8; c++) add(spin, 'cube__corner' + (c % 2 === 0 ? ' cube__corner--alt' : '') + ' cube__corner--' + c);

    var core = add(tilt, 'cube__core');
    SIDES.forEach(function (side) { add(core, 'cube__core-face cube__core-face--' + side); });
    for (var ce = 0; ce < 12; ce++) add(core, 'cube__core-edge cube__core-edge--' + EDGE_KIND[ce] + ' cube__core-edge--' + (ce + 1));
    add(tilt, 'cube__core-glow');

    if (reduced) return;

    // наклон вслед за курсором — как в макете
    var frame = null;
    cube.addEventListener('pointermove', function (event) {
      if (frame) return;
      frame = requestAnimationFrame(function () {
        frame = null;
        var rect = cube.getBoundingClientRect();
        var nx = (event.clientX - rect.left) / rect.width - .5;
        var ny = (event.clientY - rect.top) / rect.height - .5;
        tilt.style.transform = 'rotateX(' + (-ny * 24).toFixed(2) + 'deg) rotateY(' + (nx * 24).toFixed(2) + 'deg)';
      });
    });
    cube.addEventListener('pointerleave', function () { tilt.style.transform = ''; });
  });
}

function initTheme() {
  var buttons = document.querySelectorAll('[data-theme-set]');
  if (!buttons.length) return;

  function apply(theme) {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
    buttons.forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(btn.dataset.themeSet === theme));
    });
  }

  buttons.forEach(function (btn) {
    btn.addEventListener('click', function () { apply(btn.dataset.themeSet); });
  });

  apply(document.documentElement.dataset.theme || 'dark');
}

function initBurger() {
  var header = document.querySelector('[data-header]');
  var burger = document.querySelector('[data-burger]');
  if (!header || !burger) return;

  var nav = document.getElementById(burger.getAttribute('aria-controls'));
  var open = false;

  function setState(next) {
    open = next;
    header.classList.toggle('header--menu-open', open);
    burger.setAttribute('aria-expanded', String(open));
    burger.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
    document.body.style.overflow = open ? 'hidden' : '';
    if (open && nav) {
      var first = nav.querySelector('a');
      if (first) first.focus();
    }
  }

  burger.addEventListener('click', function () { setState(!open); });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && open) {
      setState(false);
      burger.focus();
    }
    if (event.key === 'Tab' && open && nav) {
      // ловушка фокуса: меню + сама кнопка
      var items = [].slice.call(nav.querySelectorAll('a')).concat([burger]);
      var first = items[0];
      var last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  if (nav) {
    nav.addEventListener('click', function (event) {
      if (event.target.closest('a') && open) setState(false);
    });
  }

  window.addEventListener('resize', function () {
    if (open && window.innerWidth >= 1280) setState(false);
  });
}

function initAccordion() {
  var roots = document.querySelectorAll('[data-accordion]');
  if (!roots.length) return;

  roots.forEach(function (root) {
    var items = [].slice.call(root.querySelectorAll('[data-accordion-item]'));

    function collapse(item) {
      var panel = item.querySelector('.faq__answer');
      var toggle = item.querySelector('[data-accordion-toggle]');
      item.classList.remove('faq__item--expanded');
      if (toggle) toggle.setAttribute('aria-expanded', 'false');
      if (panel) panel.style.maxHeight = '0px';
    }

    function expand(item) {
      var panel = item.querySelector('.faq__answer');
      var toggle = item.querySelector('[data-accordion-toggle]');
      item.classList.add('faq__item--expanded');
      if (toggle) toggle.setAttribute('aria-expanded', 'true');
      if (panel) panel.style.maxHeight = panel.scrollHeight + 32 + 'px';
    }

    items.forEach(function (item, index) {
      var toggle = item.querySelector('[data-accordion-toggle]');
      if (!toggle) return;
      collapse(item);
      toggle.addEventListener('click', function () {
        var isOpen = item.classList.contains('faq__item--expanded');
        items.forEach(collapse);
        if (!isOpen) expand(item);
      });
      if (index === 0) expand(item);
    });

    window.addEventListener('resize', function () {
      items.forEach(function (item) {
        if (item.classList.contains('faq__item--expanded')) expand(item);
      });
    });
  });
}

function initSmoothScroll() {
  var links = document.querySelectorAll('a[href^="#"]');
  if (!links.length) return;
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  links.forEach(function (link) {
    link.addEventListener('click', function (event) {
      var id = link.getAttribute('href');
      if (!id || id === '#') return;
      var target = document.querySelector(id);
      if (!target) return;
      event.preventDefault();
      var header = document.querySelector('[data-header]');
      var offset = header ? header.offsetHeight : 0;
      var top = target.getBoundingClientRect().top + window.pageYOffset - offset;
      window.scrollTo({ top: top, behavior: reduced ? 'auto' : 'smooth' });
      if (history.replaceState) history.replaceState(null, '', id);
    });
  });
}

function initForm() {
  var form = document.querySelector('[data-form]');
  if (!form) return;

  var status = form.querySelector('[data-status]');
  var fields = [].slice.call(form.querySelectorAll('[data-field]'));

  function validateField(field) {
    var input = field.querySelector('input, textarea');
    if (!input) return true;
    var valid = input.checkValidity();
    field.classList.toggle('form__field--invalid', !valid);
    input.classList.toggle('form__input--invalid', !valid);
    input.setAttribute('aria-invalid', String(!valid));
    return valid;
  }

  fields.forEach(function (field) {
    var input = field.querySelector('input, textarea');
    if (!input) return;
    input.addEventListener('blur', function () { validateField(field); });
    input.addEventListener('input', function () {
      if (field.classList.contains('form__field--invalid')) validateField(field);
    });
  });

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    var firstInvalid = null;
    fields.forEach(function (field) {
      if (!validateField(field) && !firstInvalid) firstInvalid = field;
    });
    if (firstInvalid) {
      var input = firstInvalid.querySelector('input, textarea');
      if (input) input.focus();
      if (status) status.classList.remove('form__status--visible');
      return;
    }
    form.reset();
    fields.forEach(function (field) {
      field.classList.remove('form__field--invalid');
    });
    if (status) status.classList.add('form__status--visible');
  });
}

function initReveal() {
  var root = document.documentElement;
  var items = [].slice.call(document.querySelectorAll('.reveal'));
  if (!items.length) return;

  // Скрытое состояние живёт под классом на <html>. Если прокрутки в этой среде
  // нет (или пользователь её не начал), класс снимается — контент виден всегда.
  function disarm() {
    root.classList.remove('reveal-armed');
    items.forEach(function (item) { item.classList.add('reveal--visible'); });
    items = [];
  }

  var watchdog = window.setTimeout(disarm, 2000);

  function sweep() {
    if (!items.length) return;
    var limit = window.innerHeight * 1.15;
    items = items.filter(function (item) {
      if (item.getBoundingClientRect().top > limit) return true;
      item.classList.add('reveal--visible');
      return false;
    });
  }

  var scheduled = false;
  function onScroll() {
    window.clearTimeout(watchdog);
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(function () {
      scheduled = false;
      sweep();
    });
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  sweep();

  if (!('IntersectionObserver' in window)) return;

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('reveal--visible');
      observer.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.05 });

  items.forEach(function (item) { observer.observe(item); });
}

initCubes();
initTheme();
initBurger();
initAccordion();
initSmoothScroll();
initForm();
initReveal();
