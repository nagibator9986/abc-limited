/* ТОО «АВС-Лимитед» — клиентская логика сайта */
(function () {
  "use strict";

  /* ---------- Шапка: тень при прокрутке ---------- */
  const header = document.getElementById("siteHeader");
  const onScroll = () => {
    if (!header) return;
    header.classList.toggle("scrolled", window.scrollY > 20);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ---------- Мобильное меню ---------- */
  const burger = document.getElementById("burger");
  const menu = document.getElementById("menu");
  if (burger && menu) {
    burger.addEventListener("click", () => {
      const open = menu.classList.toggle("open");
      burger.classList.toggle("open", open);
      burger.setAttribute("aria-expanded", open ? "true" : "false");
    });
    menu.querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", () => {
        menu.classList.remove("open");
        burger.classList.remove("open");
        burger.setAttribute("aria-expanded", "false");
      })
    );
  }

  /* ---------- Появление блоков при прокрутке ---------- */
  const reveals = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && reveals.length) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  /* ---------- Анимация счётчиков ---------- */
  const counters = document.querySelectorAll("[data-count]");
  const animateCount = (el) => {
    const target = parseFloat(el.getAttribute("data-count"));
    if (isNaN(target)) {
      return;
    }
    const dur = 1500;
    const start = performance.now();
    const decimals = (el.getAttribute("data-count").split(".")[1] || "").length;
    const step = (now) => {
      const t = Math.min((now - start) / dur, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      const val = target * eased;
      // годы и небольшие числа — без разделителя разрядов (чтобы «1999», а не «1 999»)
      el.textContent = decimals
        ? val.toFixed(decimals)
        : target >= 10000
          ? Math.round(val).toLocaleString("ru-RU")
          : String(Math.round(val));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  if ("IntersectionObserver" in window && counters.length) {
    const co = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            animateCount(e.target);
            co.unobserve(e.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach((el) => co.observe(el));
  }

  /* ---------- Фильтр проектов ---------- */
  const filters = document.querySelectorAll(".proj-filters button");
  const cards = document.querySelectorAll("[data-cat]");
  if (filters.length) {
    filters.forEach((btn) =>
      btn.addEventListener("click", () => {
        filters.forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        const cat = btn.getAttribute("data-filter");
        cards.forEach((card) => {
          const show = cat === "all" || card.getAttribute("data-cat") === cat;
          card.style.display = show ? "" : "none";
        });
      })
    );
  }

  /* ---------- Лайтбокс для галерей ---------- */
  const lbItems = Array.from(document.querySelectorAll("[data-lightbox]"));
  if (lbItems.length) {
    const lb = document.createElement("div");
    lb.className = "lightbox";
    lb.innerHTML =
      '<button class="lightbox__close" aria-label="Закрыть"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>' +
      '<button class="lightbox__nav prev" aria-label="Назад"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="15 18 9 12 15 6"/></svg></button>' +
      '<img src="" alt="">' +
      '<button class="lightbox__nav next" aria-label="Вперёд"><svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg></button>';
    document.body.appendChild(lb);
    const lbImg = lb.querySelector("img");
    let idx = 0;
    const show = (i) => {
      idx = (i + lbItems.length) % lbItems.length;
      const src = lbItems[idx].getAttribute("data-lightbox");
      lbImg.src = src;
      lbImg.alt = lbItems[idx].getAttribute("data-caption") || "";
    };
    const open = (i) => {
      show(i);
      lb.classList.add("open");
      document.body.style.overflow = "hidden";
    };
    const close = () => {
      lb.classList.remove("open");
      document.body.style.overflow = "";
    };
    lbItems.forEach((it, i) =>
      it.addEventListener("click", (e) => {
        e.preventDefault();
        open(i);
      })
    );
    lb.querySelector(".lightbox__close").addEventListener("click", close);
    lb.querySelector(".prev").addEventListener("click", (e) => {
      e.stopPropagation();
      show(idx - 1);
    });
    lb.querySelector(".next").addEventListener("click", (e) => {
      e.stopPropagation();
      show(idx + 1);
    });
    lb.addEventListener("click", (e) => {
      if (e.target === lb) close();
    });
    document.addEventListener("keydown", (e) => {
      if (!lb.classList.contains("open")) return;
      if (e.key === "Escape") close();
      if (e.key === "ArrowLeft") show(idx - 1);
      if (e.key === "ArrowRight") show(idx + 1);
    });
  }

  /* ---------- Автоскрытие уведомлений ---------- */
  const flashStack = document.getElementById("flashStack");
  if (flashStack) {
    setTimeout(() => {
      flashStack.querySelectorAll(".flash").forEach((f) => {
        f.style.transition = "opacity .4s, transform .4s";
        f.style.opacity = "0";
        f.style.transform = "translateX(40px)";
        setTimeout(() => f.remove(), 400);
      });
    }, 5000);
  }
})();
