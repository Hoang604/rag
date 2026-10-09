import colors from 'tailwindcss/colors.js';
import { writeFileSync } from 'node:fs';
const steps = [50,100,200,300,400,500,600,700,800,900,950];
const rgb = (hex) => { const n = parseInt(hex.slice(1), 16); return `${n>>16&255} ${n>>8&255} ${n&255}`; };
const mirror = (scale) => Object.fromEntries(steps.map((s, i) => [s, scale[steps[steps.length-1-i]]]));
const slateDark = {50:'#f8fafc',100:'#eef1f6',200:'#dde2ea',300:'#bcc4d2',400:'#8e99ad',500:'#667286',600:'#485366',700:'#323b4c',800:'#232a38',900:'#171c27',950:'#0d1118'};
const slateLight = {50:'#0b1220',100:'#121a2b',200:'#1f2a40',300:'#374359',400:'#5b677d',500:'#8793a8',600:'#b3bccb',700:'#d3d9e3',800:'#e4e8ef',900:'#eef1f6',950:'#f8f9fb'};
const o = colors.teal;
const brandDark = {...o, 400: '#2dd4bf', 500: '#14b8a6', 600: '#0f766e', 700: '#115e59'};
const brandLight = {50:o[950],100:o[900],200:o[800],300:o[700],400:'#0f766e',500:'#0d9488',600:'#0f766e',700:'#115e59',800:o[200],900:o[100],950:o[50]};
const families = { slate: [slateDark, slateLight], brand: [brandDark, brandLight] };
for (const f of ['emerald','amber','rose','indigo','cyan','sky','purple','orange','teal','violet','green','red','blue','yellow','lime','fuchsia','pink','stone','zinc','gray','neutral']) {
  const base = Object.fromEntries(steps.map(s => [s, colors[f][s]]));
  families[f] = [base, mirror(base)];
}
const block = (idx) => Object.entries(families).map(([f, pair]) => steps.map(s => `  --c-${f}-${s}: ${rgb(pair[idx][s])};`).join('\n')).join('\n');
const css = `:root {\n  color-scheme: light;\n${block(1)}\n}\n:root:not([data-theme="light"]) {\n}\n@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n    color-scheme: dark;\n${block(0).replace(/^/gm,'  ')}\n  }\n}\n:root[data-theme="dark"] {\n  color-scheme: dark;\n${block(0)}\n}\n`;
writeFileSync('src/theme.css', css.replace(':root:not([data-theme="light"]) {\n}\n',''));
const twColors = Object.fromEntries(Object.keys(families).map(f => [f, Object.fromEntries(steps.map(s => [s, `rgb(var(--c-${f}-${s}) / <alpha-value>)`]))]));
writeFileSync('src/theme-colors.json', JSON.stringify(twColors, null, 1));
