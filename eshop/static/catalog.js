/* Spreadshop E-shop — Catalog interactions (filter, search, cart) */
(function () {
  "use strict";

  /* ── Cart (localStorage) ─────────────────────────────────── */
  var CART_KEY = "spreadshop_cart";

  function getCart() {
    try { return JSON.parse(localStorage.getItem(CART_KEY) || "[]"); }
    catch (_) { return []; }
  }

  function saveCart(cart) {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
  }

  function addToCart(id, name, price) {
    var cart = getCart();
    var existing = cart.find(function (i) { return i.id === id; });
    if (existing) {
      existing.qty += 1;
    } else {
      cart.push({ id: id, name: name, price: price, qty: 1 });
    }
    saveCart(cart);
    updateCartCount();
    showToast(name);
  }

  function updateCartCount() {
    var cart = getCart();
    var total = cart.reduce(function (s, i) { return s + i.qty; }, 0);
    var el = document.getElementById("cart-count");
    if (el) el.textContent = total;
  }

  function showToast(name) {
    var toast = document.getElementById("cart-toast");
    var text = document.getElementById("cart-toast-text");
    if (!toast) return;
    if (text) text.textContent = "\u201c" + name.slice(0, 40) + "\u201d \u03c0\u03c1\u03bf\u03c3\u03c4\u03ad\u03b8\u03b7\u03ba\u03b5"; // «name» προστέθηκε
    toast.classList.add("show");
    clearTimeout(toast._hideTimer);
    toast._hideTimer = setTimeout(function () {
      toast.classList.remove("show");
    }, 2800);
  }

  function toggleCart() {
    var cart = getCart();
    if (cart.length === 0) {
      alert("Το καλάθι σας είναι άδειο.");
      return;
    }
    var lines = cart.map(function (i) {
      return i.qty + "x " + i.name + " — €" + (i.price * i.qty).toFixed(2);
    });
    var total = cart.reduce(function (s, i) { return s + i.price * i.qty; }, 0);
    lines.push("\nΣύνολο: €" + total.toFixed(2));
    alert("Καλάθι αγορών:\n\n" + lines.join("\n"));
  }

  /* Expose to global for onclick= handlers */
  window.addToCart = addToCart;
  window.toggleCart = toggleCart;

  /* ── Category filter ─────────────────────────────────────── */
  var activeCategory = "all";

  function filterProducts() {
    var query = (document.getElementById("search-input") || {}).value || "";
    query = query.toLowerCase().trim();

    var cards = document.querySelectorAll(".product-card[data-name]");
    var shown = 0;

    cards.forEach(function (card) {
      var cat = (card.dataset.category || "").toLowerCase();
      var name = (card.dataset.name || "").toLowerCase();

      var catMatch = activeCategory === "all" || cat === activeCategory.toLowerCase();
      var nameMatch = !query || name.indexOf(query) !== -1;

      if (catMatch && nameMatch) {
        card.style.display = "";
        shown++;
      } else {
        card.style.display = "none";
      }
    });

    var countEl = document.getElementById("results-count");
    if (countEl) {
      countEl.textContent = shown + " προϊόντα";
    }

    /* Show/hide empty state */
    var emptyEl = document.getElementById("empty-state");
    if (emptyEl) emptyEl.style.display = shown === 0 ? "" : "none";
  }

  function initCategoryPills() {
    var pills = document.querySelectorAll(".filter-pill");
    pills.forEach(function (pill) {
      pill.addEventListener("click", function () {
        pills.forEach(function (p) { p.classList.remove("active"); });
        pill.classList.add("active");
        activeCategory = pill.dataset.category || "all";
        filterProducts();
      });
    });
  }

  function initSearch() {
    var input = document.getElementById("search-input");
    if (!input) return;
    input.addEventListener("input", filterProducts);
    input.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { input.value = ""; filterProducts(); }
    });
  }

  /* ── Init ────────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", function () {
    updateCartCount();
    initCategoryPills();
    initSearch();
  });

}());
