"use strict";

// The order preserves existing ?rd= links.
var f_names = ["sin", "cos", "tan", "cot", "circle", "linear", "spiral", "exponential",
  "quadratic", "toposine", "invProportional", "nike", "sign", "lemniscate", "logarithm", "power"];
var x = [], y = [];
var T = 4, B = -4, L = -4, R = 4;
var f_display;

const definitions = {
  sin: { label: "正弦函数~y = sin x", value: Math.sin },
  cos: { label: "余弦函数~y = cos x", value: Math.cos },
  tan: { label: "正切函数~y = tan x", value: Math.tan },
  cot: { label: "余切函数~y = cot x", value: t => Math.abs(Math.sin(t)) < 1e-10 ? null : 1 / Math.tan(t) },
  circle: { label: "圆方程~x² + y² = 1", parametric: t => [Math.cos(t), Math.sin(t)] },
  linear: { label: "线性函数~y = x", value: t => t },
  spiral: { label: "阿基米德螺线~x = θ cos θ，y = θ sin θ", parametric: t => [t * Math.cos(t), t * Math.sin(t)], end: 8 },
  exponential: { label: "指数函数~y = eˣ", value: Math.exp },
  quadratic: { label: "二次函数~y = x²", value: t => t * t },
  toposine: { label: "拓扑学家正弦曲线~y = sin(1/x)", value: t => t === 0 ? null : Math.sin(1 / t), step: 0.01 },
  invProportional: { label: "反比例函数~y = 1/x", value: t => t === 0 ? null : 1 / t },
  nike: { label: "耐克函数~y = x + 1/x", value: t => t === 0 ? null : t + 1 / t },
  sign: { label: "符号函数~y = sgn x", value: Math.sign },
  lemniscate: { label: "双纽线~(x² + y²)² = 2(x² − y²)", parametric: t => {
    const radiusSquared = 2 * Math.cos(2 * t);
    return radiusSquared < 0 ? [null, null] : [Math.sqrt(radiusSquared) * Math.cos(t), Math.sqrt(radiusSquared) * Math.sin(t)];
  }, step: 0.01 },
  logarithm: { label: "对数函数~y = ln x", value: t => t > 0 ? Math.log(t) : null },
  power: { label: "开方函数~y = √x", value: t => t >= 0 ? Math.sqrt(t) : null }
};

function plot_parac_conf(name) {
  const definition = Object.hasOwn(definitions, name) ? definitions[name] : definitions.linear;
  const start = definition.parametric ? 0 : L;
  const end = definition.parametric ? (definition.end || 2 * Math.PI) : R;
  const steps = Math.ceil((end - start) / (definition.step || 0.025));
  x = [];
  y = [];
  f_display = definition.label;
  for (let i = 0; i <= steps; i++) {
    const t = start + (end - start) * i / steps;
    const [px, py] = definition.parametric ? definition.parametric(t) : [t, definition.value(t)];
    // The isolated origin of sgn(x) must not join its two branches.
    if (name === "sign" && t === 0) { x.push(null); y.push(null); }
    x.push(Number.isFinite(px) ? px : null);
    y.push(Number.isFinite(py) && py <= T + 1 && py >= B - 1 ? py : null);
    if (name === "sign" && t === 0) { x.push(null); y.push(null); }
  }
}
