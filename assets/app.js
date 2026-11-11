(function () {
  var dataEl = document.getElementById("paper-data");
  var DAYS = [], TOPICS = [], PAPERS = [];
  if (dataEl) {
    var data = JSON.parse(dataEl.textContent);
    DAYS = data.days || [];
    TOPICS = data.topics || [];
    PAPERS = data.papers || [];
  }

  var state = { topic: "all", q: "", onlyPick: false, sort: "score" };
  var $list = document.getElementById("list");
  var $count = document.getElementById("shown-count");
  var $nav = document.getElementById("topic-nav");
  var $q = document.getElementById("q");
  var $onlyPick = document.getElementById("only-pick");
  var $sort = document.getElementById("sort");
  var $daySelect = document.getElementById("day-select");
  var $briefSelect = document.getElementById("brief-select");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function topicMap() {
    var m = {};
    TOPICS.forEach(function (t) { m[t.id] = t; });
    return m;
  }
  var TM = topicMap();

  function counts() {
    var c = { all: PAPERS.length };
    TOPICS.forEach(function (t) { c[t.id] = 0; });
    PAPERS.forEach(function (p) {
      (p.topics || []).forEach(function (t) { if (c[t] != null) c[t]++; });
    });
    return c;
  }

  function renderNav() {
    var c = counts();
    var html = '<button class="topic-item' + (state.topic === "all" ? " active" : "") +
      '" data-topic="all"><span class="dot" style="background:#9aa0ae"></span>全部方向<span class="n">' + c.all + "</span></button>";
    TOPICS.forEach(function (t) {
      html += '<button class="topic-item' + (state.topic === t.id ? " active" : "") + '" data-topic="' + esc(t.id) + '">' +
        '<span class="dot" style="background:' + esc(t.color) + '"></span>' + esc(t.name) +
        '<span class="n">' + (c[t.id] || 0) + "</span></button>";
    });
    $nav.innerHTML = html;
    Array.prototype.forEach.call($nav.querySelectorAll(".topic-item"), function (btn) {
      btn.addEventListener("click", function () {
        state.topic = btn.getAttribute("data-topic");
        render();
      });
    });
  }

  function filtered() {
    var q = state.q.trim().toLowerCase();
    return PAPERS.filter(function (p) {
      if (state.onlyPick && !p.pick) return false;
      if (state.topic !== "all" && (p.topics || []).indexOf(state.topic) === -1) return false;
      if (!q) return true;
      var hay = [p.title, p.title_zh, p.abstract, p.abstract_zh, (p.authors || []).join(" "), p.comment, p.id]
        .join(" ").toLowerCase();
      return q.split(/\s+/).every(function (w) { return hay.indexOf(w) !== -1; });
    }).sort(function (a, b) {
      if (state.sort === "date") {
        if (a.published_date !== b.published_date) return a.published_date < b.published_date ? 1 : -1;
        return b.score - a.score;
      }
      return b.score - a.score;
    });
  }

  function card(p, idx) {
    var chips = (p.topics || []).map(function (t) {
      var tp = TM[t] || { name: t, color: "#999" };
      return '<span class="chip" style="color:' + esc(tp.color) + ';border-color:' + esc(tp.color) + '33">' + esc(tp.name) + "</span>";
    }).join("");

    var authors = (p.authors || []).slice(0, 4).map(esc).join(", ");
    if ((p.authors || []).length > 4) authors += ' <span class="more">等 ' + p.authors.length + " 人</span>";

    var sourceLabel = (p.sources && p.sources.length ? p.sources.join(" · ") : (p.source || ""));
    var sourceChip = sourceLabel ? '<span class="chip source">' + esc(sourceLabel) + "</span>" : "";
    var hasZh = !!(p.title_zh || p.abstract_zh);
    var body = p.abstract_zh || "（中文摘要待生成）";
    var bodyEn = p.abstract ? '<div class="abstract-en" hidden>' + esc(p.abstract) + "</div>" : "";

    return '<article class="card' + (p.pick ? " pick" : "") + '" data-i="' + idx + '">' +
      '<div class="card-top">' +
        (p.pick ? '<span class="chip pick">★ 精选</span>' : "") +
        sourceChip + chips +
        '<span class="score"><span class="meter"><i style="width:' + Math.max(4, Math.min(100, p.score)) + '%"></i></span>' + p.score + "</span>" +
      "</div>" +
      '<h2 class="title"><a href="' + esc(p.abs_url) + '" target="_blank" rel="noopener">' + esc(p.title_zh || p.title) + "</a></h2>" +
      (p.title_zh ? '<p class="title-en">' + esc(p.title) + "</p>" : "") +
      '<div class="authors">' + authors + " · " + esc(p.published_date) + (p.comment ? " · " + esc(p.comment.slice(0, 90)) : "") + "</div>" +
      '<div class="abstract clamp">' + esc(body) + "</div>" + bodyEn +
      '<div class="foot">' +
        '<a href="' + esc(p.abs_url) + '" target="_blank" rel="noopener">arXiv:' + esc(p.id) + "</a>" +
        '<a href="' + esc(p.pdf_url) + '" target="_blank" rel="noopener">PDF</a>' +
        (p.reader_url ? '<a class="reader-link" href="' + esc(p.reader_url) + '">中文精读 →</a>' : '') +
        (p.code ? '<a href="' + esc(p.code) + '" target="_blank" rel="noopener">💻 Code</a>' : "") +
        '<button class="expand-btn">展开摘要</button>' +
      "</div></article>";
  }

  function render() {
    var rows = filtered();
    $count.textContent = rows.length + " 篇";
    renderNav();
    if (!rows.length) {
      $list.innerHTML = '<div class="empty">没有匹配的论文，换个关键词或方向试试 🌱</div>';
      return;
    }
    $list.innerHTML = rows.map(card).join("");
    Array.prototype.forEach.call($list.querySelectorAll(".expand-btn"), function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".card");
        var abs = card.querySelector(".abstract");
        var en = card.querySelector(".abstract-en");
        var open = abs.classList.toggle("clamp") === false;
        if (en) en.hidden = !open;
        btn.textContent = open ? "收起摘要" : "展开摘要";
      });
    });
  }

  $q.addEventListener("input", function () { state.q = $q.value; render(); });
  $onlyPick.addEventListener("change", function () { state.onlyPick = $onlyPick.checked; render(); });
  $sort.addEventListener("change", function () { state.sort = $sort.value; render(); });
  if ($daySelect) $daySelect.addEventListener("change", function () { if ($daySelect.value) location.href = $daySelect.value; });
  if ($briefSelect) $briefSelect.addEventListener("change", function () { if ($briefSelect.value) location.href = $briefSelect.value; });
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== $q) { e.preventDefault(); $q.focus(); }
    if (e.key === "Escape" && document.activeElement === $q) { $q.value = ""; state.q = ""; $q.blur(); render(); }
  });

  /* 主题切换 */
  var root = document.documentElement;
  var saved = localStorage.getItem("pr-theme");
  if (saved) root.setAttribute("data-theme", saved);
  document.getElementById("theme-toggle").addEventListener("click", function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("pr-theme", next);
  });

  render();
})();
