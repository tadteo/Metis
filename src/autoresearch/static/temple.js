"use strict";

// A decorative scene only: no research state, requests or progress are consumed.
// The terminal outline uses the same local timing and initial view.
const Temple = (() => {
  const faces = [
    [[0, 4, 6, 2], [-1, 0, 0]], [[1, 3, 7, 5], [1, 0, 0]],
    [[0, 1, 5, 4], [0, -1, 0]], [[2, 6, 7, 3], [0, 1, 0]],
    [[0, 2, 3, 1], [0, 0, -1]], [[4, 5, 7, 6], [0, 0, 1]],
  ];
  function placement(block, elapsed, scene) {
    const t = Math.min(1, Math.max(0, (elapsed - block[6]) / scene.fall_seconds));
    return {visible: elapsed >= block[6], falling: t < 1, lift: scene.fall_height * (1 - t)};
  }
  function project(x, y, z, yaw, pitch) {
    const side = x * Math.cos(yaw) + z * Math.sin(yaw);
    const depth = -x * Math.sin(yaw) + z * Math.cos(yaw);
    return [side, -y * Math.cos(pitch) + depth * Math.sin(pitch), y * Math.sin(pitch) + depth * Math.cos(pitch)];
  }
  function polygons(scene, elapsed, yaw, pitch) {
    const result = [];
    for (const block of scene.blocks) {
      const motion = placement(block, elapsed, scene);
      if (!motion.visible) continue;
      const [x, y, z, w, h, d] = block;
      const vertices = Array.from({length: 8}, (_, i) => project(x + (i & 1 ? w : -w) / 2, y + motion.lift + (i & 2 ? h : -h) / 2, z + (i & 4 ? d : -d) / 2, yaw, pitch));
      for (const [indices, normal] of faces) {
        if (project(...normal, yaw, pitch)[2] <= 0) continue;
        const points = indices.map(i => vertices[i]);
        result.push({points, depth: points.reduce((n, p) => n + p[2], 0) / 4, top: normal[1] > 0, side: normal[0] !== 0, falling: motion.falling});
      }
    }
    return result.sort((a, b) => a.depth - b.depth);
  }
  class View {
    constructor(root, scene) {
      this.root = root;
      this.scene = scene;
      this.canvas = root.querySelector("canvas");
      this.context = this.canvas.getContext("2d");
      this.replay = root.querySelector("[data-temple-replay]");
      this.reduced = matchMedia("(prefers-reduced-motion: reduce)");
      this.elapsed = this.reduced.matches ? scene.duration : 0;
      this.yaw = scene.yaw;
      this.pitch = scene.pitch;
      this.paused = false;
      this.visible = false;
      this.frame = null;
      this.last = null;
      this.drag = null;
      this.tick = this.tick.bind(this);
      this.replay.addEventListener("click", () => this.rebuild());
      this.canvas.addEventListener("keydown", event => {
        if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
          event.preventDefault();
          this.rotate(event.key === "ArrowLeft" ? -.12 : event.key === "ArrowRight" ? .12 : 0, event.key === "ArrowUp" ? .06 : event.key === "ArrowDown" ? -.06 : 0);
        } else if (event.key === " ") {
          event.preventDefault(); this.paused = !this.paused; this.sync();
        } else if (event.key === "Home") {
          event.preventDefault(); this.yaw = scene.yaw; this.pitch = scene.pitch; this.draw();
        }
      });
      this.canvas.addEventListener("pointerdown", event => {
        if (event.button !== 0 || !event.isPrimary) return;
        this.drag = {x: event.clientX, y: event.clientY, id: event.pointerId};
        this.canvas.setPointerCapture(event.pointerId);
        this.canvas.focus({preventScroll: true});
      });
      this.canvas.addEventListener("pointermove", event => {
        if (!this.drag || this.drag.id !== event.pointerId) return;
        this.rotate((event.clientX - this.drag.x) * .008, (event.clientY - this.drag.y) * .005);
        this.drag.x = event.clientX;
        this.drag.y = event.clientY;
      });
      for (const name of ["pointerup", "pointercancel", "lostpointercapture"]) this.canvas.addEventListener(name, () => { this.drag = null; });
      this.reduced.addEventListener("change", () => {
        if (this.reduced.matches) this.elapsed = scene.duration;
        this.sync(); this.draw();
      });
      document.addEventListener("visibilitychange", () => this.sync());
      this.observer = new IntersectionObserver(entries => {
        this.visible = entries[0].isIntersecting;
        this.sync();
      });
      this.observer.observe(this.canvas);
      this.resize = new ResizeObserver(() => this.draw());
      this.resize.observe(this.canvas);
      this.theme = new MutationObserver(() => this.draw());
      this.theme.observe(document.documentElement, {attributes: true, attributeFilter: ["data-theme"]});
      root.classList.add("temple-ready");
      this.draw(); this.sync();
    }
    rotate(yaw, pitch) {
      this.yaw = (this.yaw + yaw) % (Math.PI * 2);
      this.pitch = Math.max(.15, Math.min(.8, this.pitch + pitch));
      this.draw();
    }
    rebuild() {
      this.elapsed = this.reduced.matches ? this.scene.duration : 0;
      this.paused = false;
      this.draw(); this.sync();
    }
    sync() {
      const done = this.elapsed >= this.scene.duration;
      this.replay.disabled = this.reduced.matches;
      const running = this.visible && !document.hidden && !this.paused && !done;
      if (this.frame !== null) cancelAnimationFrame(this.frame);
      this.frame = null;
      this.last = null;
      if (running) this.frame = requestAnimationFrame(this.tick);
    }
    tick(now) {
      this.frame = null;
      if (this.last !== null) this.elapsed = Math.min(this.scene.duration, this.elapsed + Math.min((now - this.last) / 1000, .08));
      this.last = now;
      this.draw();
      if (this.elapsed < this.scene.duration) this.frame = requestAnimationFrame(this.tick);
      else this.sync();
    }
    draw() {
      const width = this.canvas.clientWidth;
      const height = this.canvas.clientHeight;
      if (!width || !height || !this.context) return;
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.round(width * ratio);
      this.canvas.height = Math.round(height * ratio);
      const ctx = this.context;
      ctx.scale(ratio, ratio);
      const css = getComputedStyle(document.documentElement);
      const color = name => css.getPropertyValue(`--${name}`).trim();
      const scale = Math.min(width / 23, height / 22);
      const point = p => [width / 2 + p[0] * scale, height * .68 + p[1] * scale];
      for (const face of polygons(this.scene, this.elapsed, this.yaw, this.pitch)) {
        const points = face.points.map(point);
        ctx.beginPath(); ctx.moveTo(...points[0]);
        for (const p of points.slice(1)) ctx.lineTo(...p);
        ctx.closePath();
        ctx.fillStyle = color(face.falling ? "accent" : face.top ? "muted" : face.side ? "raised" : "border");
        ctx.fill();
        ctx.strokeStyle = color("bg"); ctx.lineWidth = .45; ctx.stroke();
      }
    }
  }
  async function mount() {
    const root = document.querySelector(".temple-mark");
    if (!root) return;
    try {
      const response = await fetch("/temple.json", {credentials: "same-origin"});
      if (!response.ok) return;
      const scene = await response.json();
      new View(root, scene);
    } catch { /* The static architectural fallback and inquiry remain available. */ }
  }
  return {placement, project, polygons, View, mount};
})();
if (typeof document !== "undefined") Temple.mount();
