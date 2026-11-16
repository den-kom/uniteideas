/* Interactive tour for /onboarding: spotlights the real buttons on the page, never navigates. */
(function () {
  var STEPS = [
    { sel: '[data-tour="submit"]', title: 'Submit', text: 'This is where you post an idea. Write a public one-pager, seal the private detail, and get a timestamp from an independent third party the moment you submit.' },
    { sel: '[data-tour="ideas"]', title: 'Ideas', text: 'Browse what others have posted. Back the ones you like: backing lifts an idea up the list and makes its glow brighter.' },
    { sel: '[data-tour="verify"]', title: 'Verify', text: 'Anyone can check a proof here without seeing the sealed text. It shows when an idea was first recorded.' },
    { sel: '[data-tour="profile"]', title: 'Your profile', text: 'List what you can help with, so teams can find you. You can also set an optional password here.' },
    { sel: '[data-tour="theme"]', title: 'Light or dark', text: 'Switch the look of the site any time.' },
    { sel: '[data-tour="finish"]', title: 'All done', text: 'Press this when you are ready and we will stop showing the welcome page.' }
  ];
  var startRow = document.getElementById('tour-start-row');
  var startBtn = document.getElementById('tour-start');
  if (!startBtn) return;
  startRow.hidden = false;

  var steps = [], index = 0, shade, card, lastFocus;

  function visible(el) { return el && el.getClientRects().length > 0; }

  function place() {
    var s = steps[index], r = s.el.getBoundingClientRect(), pad = 6;
    shade.style.left = (r.left - pad) + 'px';
    shade.style.top = (r.top - pad) + 'px';
    shade.style.width = (r.width + pad * 2) + 'px';
    shade.style.height = (r.height + pad * 2) + 'px';
    var w = Math.min(320, window.innerWidth - 24);
    card.style.width = w + 'px';
    var left = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
    var below = r.bottom + 16;
    var top = below + card.offsetHeight > window.innerHeight ? Math.max(12, r.top - card.offsetHeight - 16) : below;
    card.style.left = left + 'px';
    card.style.top = top + 'px';
  }

  function show() {
    var s = steps[index];
    s.el.scrollIntoView({ block: 'center', inline: 'nearest' });
    card.querySelector('.tour-step').textContent = 'Step ' + (index + 1) + ' of ' + steps.length;
    card.querySelector('.tour-title').textContent = s.title;
    card.querySelector('.tour-text').textContent = s.text;
    card.querySelector('.tour-back').hidden = index === 0;
    var next = card.querySelector('.tour-next');
    next.textContent = index === steps.length - 1 ? 'Finish' : 'Next';
    place();
    next.focus();
  }

  function stop() {
    window.removeEventListener('resize', place);
    window.removeEventListener('keydown', onKey, true);
    shade.remove(); card.remove(); blocker.remove();
    try { sessionStorage.setItem('tourSeen', '1'); } catch (e) {}
    if (lastFocus) lastFocus.focus();
  }

  function onKey(e) {
    if (e.key === 'Escape') { e.preventDefault(); stop(); }
    if (e.key === 'ArrowRight') { go(1); }
    if (e.key === 'ArrowLeft') { go(-1); }
  }

  function go(d) {
    var n = index + d;
    if (n < 0) return;
    if (n >= steps.length) { stop(); return; }
    index = n; show();
  }

  var blocker;
  function start() {
    steps = STEPS.map(function (s) { return { el: document.querySelector(s.sel), title: s.title, text: s.text }; })
      .filter(function (s) { return visible(s.el); });
    if (!steps.length) return;
    lastFocus = document.activeElement;
    index = 0;
    blocker = document.createElement('div');
    blocker.className = 'tour-blocker';
    blocker.addEventListener('click', stop);
    shade = document.createElement('div');
    shade.className = 'tour-spot';
    card = document.createElement('div');
    card.className = 'tour-card';
    card.setAttribute('role', 'dialog');
    card.setAttribute('aria-live', 'polite');
    card.setAttribute('aria-label', 'Site tour');
    card.innerHTML = '<p class="tour-step fine"></p><h2 class="tour-title"></h2><p class="tour-text"></p>' +
      '<div class="row"><button type="button" class="btn small ghost tour-back">Back</button>' +
      '<button type="button" class="btn small tour-next">Next</button>' +
      '<button type="button" class="btn small ghost tour-skip">Skip</button></div>';
    document.body.appendChild(blocker);
    document.body.appendChild(shade);
    document.body.appendChild(card);
    card.querySelector('.tour-back').addEventListener('click', function () { go(-1); });
    card.querySelector('.tour-next').addEventListener('click', function () { go(1); });
    card.querySelector('.tour-skip').addEventListener('click', stop);
    window.addEventListener('resize', place);
    window.addEventListener('keydown', onKey, true);
    show();
  }

  startBtn.addEventListener('click', start);
  var seen = false;
  try { seen = sessionStorage.getItem('tourSeen') === '1'; } catch (e) {}
  if (!seen && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setTimeout(start, 400); }
})();
