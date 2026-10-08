(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Scroll-based reveal
  const reveals = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && !reduce) {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) {
            en.target.classList.add("is-visible");
            io.unobserve(en.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("is-visible"));
  }

  // Idea → Final flow lights up in sequence
  document.querySelectorAll("[data-flow]").forEach((flow) => {
    const items = [...flow.children];
    const run = () => items.forEach((li, i) => setTimeout(() => li.classList.add("on"), reduce ? 0 : i * 260));
    if ("IntersectionObserver" in window && !reduce) {
      const io = new IntersectionObserver((en) => {
        if (en[0].isIntersecting) {
          run();
          io.disconnect();
        }
      }, { threshold: 0.6 });
      io.observe(flow);
    } else {
      run();
    }
  });

  // Reading progress
  const bar = document.querySelector(".progress span");
  if (bar) {
    let ticking = false;
    const update = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bar.style.setProperty("--p", max > 0 ? Math.min(1, scrollY / max).toFixed(4) : 0);
      ticking = false;
    };
    addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }

  // Highlight the current section in the in-page navigation
  const subLinks = [...document.querySelectorAll(".subnav a")];
  if (subLinks.length && "IntersectionObserver" in window) {
    const map = new Map(subLinks.map((a) => [a.getAttribute("href").slice(1), a]));
    const spy = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) {
          subLinks.forEach((a) => a.classList.remove("is-current"));
          map.get(en.target.id)?.classList.add("is-current");
        }
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    map.forEach((_, id) => { const el = document.getElementById(id); if (el) spy.observe(el); });
  }

  // Lightbox
  const links = [...document.querySelectorAll("a[data-lightbox]")];
  if (links.length && typeof HTMLDialogElement === "function") {
    const dlg = document.createElement("dialog");
    dlg.className = "lightbox";
    dlg.setAttribute("aria-label", "Image viewer");
    dlg.innerHTML = `
      <div class="lightbox__stage"><img class="lightbox__img" alt=""></div>
      <div class="lightbox__bar"><span class="lightbox__cap"></span><span class="lightbox__count"></span></div>
      <button class="lightbox__close" aria-label="Close">&times;</button>
      <button class="lightbox__prev" aria-label="Previous image">&larr;</button>
      <button class="lightbox__next" aria-label="Next image">&rarr;</button>`;
    document.body.append(dlg);
    const stage = dlg.querySelector(".lightbox__stage");
    const img = dlg.querySelector(".lightbox__img");
    const cap = dlg.querySelector(".lightbox__cap");
    const count = dlg.querySelector(".lightbox__count");
    let index = 0;

    const show = (i) => {
      index = (i + links.length) % links.length;
      const a = links[index];
      stage.classList.remove("is-zoomed");
      img.src = a.href;
      img.alt = a.querySelector("img")?.alt || "";
      cap.textContent = a.dataset.caption || "";
      count.textContent = `${index + 1} / ${links.length}`;
      stage.scrollTo(0, 0);
    };
    links.forEach((a, i) => a.addEventListener("click", (ev) => {
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey) return;
      ev.preventDefault();
      show(i);
      dlg.showModal();
    }));
    img.addEventListener("click", () => stage.classList.toggle("is-zoomed"));
    stage.addEventListener("click", (ev) => { if (ev.target === stage) dlg.close(); });
    dlg.querySelector(".lightbox__close").addEventListener("click", () => dlg.close());
    dlg.querySelector(".lightbox__prev").addEventListener("click", () => show(index - 1));
    dlg.querySelector(".lightbox__next").addEventListener("click", () => show(index + 1));
    dlg.addEventListener("keydown", (ev) => {
      if (ev.key === "ArrowLeft") show(index - 1);
      if (ev.key === "ArrowRight") show(index + 1);
    });
    let sx = 0;
    dlg.addEventListener("touchstart", (ev) => { sx = ev.touches[0].clientX; }, { passive: true });
    dlg.addEventListener("touchend", (ev) => {
      if (stage.classList.contains("is-zoomed")) return;
      const dx = ev.changedTouches[0].clientX - sx;
      if (Math.abs(dx) > 60) show(index + (dx < 0 ? 1 : -1));
    });
  }

  // Previous / next project with the arrow keys
  const main = document.getElementById("main");
  if (main && main.dataset.next) {
    addEventListener("keydown", (ev) => {
      if (ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      if (document.querySelector("dialog[open]") || /input|textarea|select/i.test(ev.target.tagName)) return;
      if (ev.key === "ArrowRight") location.href = main.dataset.next;
      if (ev.key === "ArrowLeft") location.href = main.dataset.prev;
    });
  }
})();
