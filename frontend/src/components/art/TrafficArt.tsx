import React from 'react';

const LINE = 'fill-none stroke-slate-400 [stroke-linecap:round] [stroke-linejoin:round]';

export const RoadBanner: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg
    viewBox="0 0 760 150"
    role="img"
    aria-hidden="true"
    className={`w-full text-slate-400 ${className}`}
  >
    <circle cx="640" cy="38" r="22" className="fill-brand-600/15" />
    <path d="M0 128 H760" className="stroke-slate-700" strokeWidth="2" fill="none" />
    <path d="M0 140 H760" className="stroke-slate-800" strokeWidth="2" fill="none" strokeDasharray="26 22" />

    <g transform="translate(18 12)">
      <path d="M40 8 V104" className={LINE} strokeWidth="2" />
      <path d="M14 104 H66" className={LINE} strokeWidth="2" />
      <path d="M8 26 H72" className={LINE} strokeWidth="2" />
      <path d="M12 26 L2 58 H22 Z" className="fill-brand-600/15 stroke-brand-400" strokeWidth="1.8" strokeLinejoin="round" />
      <path d="M68 26 L58 58 H78 Z" className="fill-brand-600/15 stroke-brand-400" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="40" cy="8" r="4" className="fill-brand-400" />
    </g>

    <g transform="translate(150 44)">
      <path
        d="M6 66 C6 52 14 48 26 46 L42 24 C46 19 50 18 56 18 H108 C116 18 120 21 125 27 L140 46 C152 47 160 52 160 64 V68 H6 Z"
        className="fill-brand-600/15 stroke-brand-400"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M48 28 H70 V44 H34 Z M78 28 H108 L122 44 H78 Z" className={LINE} strokeWidth="1.6" />
      <circle cx="40" cy="70" r="13" className="fill-slate-950 stroke-slate-300" strokeWidth="2.4" />
      <circle cx="40" cy="70" r="4" className="fill-slate-400" />
      <circle cx="124" cy="70" r="13" className="fill-slate-950 stroke-slate-300" strokeWidth="2.4" />
      <circle cx="124" cy="70" r="4" className="fill-slate-400" />
    </g>

    <g transform="translate(360 54)">
      <circle cx="22" cy="62" r="15" className="fill-slate-950 stroke-slate-300" strokeWidth="2.4" />
      <circle cx="96" cy="62" r="15" className="fill-slate-950 stroke-slate-300" strokeWidth="2.4" />
      <path d="M22 62 L46 44 H76 L96 62 M46 44 L40 30 H54 M76 44 L84 22 H96" className="stroke-brand-400" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M44 44 C56 36 70 36 78 44 Z" className="fill-brand-600/20 stroke-brand-400" strokeWidth="1.8" strokeLinejoin="round" />
      <circle cx="66" cy="22" r="7" className={LINE} strokeWidth="1.8" />
      <path d="M62 30 L56 44 M70 30 L82 36" className={LINE} strokeWidth="1.8" />
    </g>

    <g transform="translate(540 10)">
      <path d="M26 14 V118" className="stroke-slate-500" strokeWidth="3" fill="none" strokeLinecap="round" />
      <rect x="10" y="0" width="32" height="76" rx="9" className="fill-slate-900 stroke-slate-500" strokeWidth="2" />
      <circle cx="26" cy="16" r="7" className="fill-rose-500" />
      <circle cx="26" cy="38" r="7" className="fill-amber-400/40" />
      <circle cx="26" cy="60" r="7" className="fill-emerald-400/40" />
    </g>

    <g transform="translate(630 22)">
      <path d="M22 44 V106" className="stroke-slate-500" strokeWidth="3" fill="none" strokeLinecap="round" />
      <circle cx="22" cy="22" r="20" className="fill-slate-950 stroke-rose-500" strokeWidth="4" />
      <text x="22" y="28" textAnchor="middle" fontSize="17" fontWeight="700" className="fill-slate-200">
        50
      </text>
    </g>
  </svg>
);

export const SignRow: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg viewBox="0 0 300 56" role="img" aria-hidden="true" className={`w-full max-w-xs ${className}`}>
    <g strokeWidth="3">
      <circle cx="28" cy="28" r="22" className="fill-slate-950 stroke-rose-500" />
      <rect x="14" y="24" width="28" height="8" rx="2" className="fill-rose-500" stroke="none" />
    </g>
    <g strokeWidth="3" strokeLinejoin="round">
      <path d="M92 8 L116 48 H68 Z" className="fill-slate-950 stroke-rose-500" />
      <path d="M92 20 V34" className="stroke-slate-300" strokeLinecap="round" />
      <circle cx="92" cy="41" r="1.6" className="fill-slate-300" stroke="none" />
    </g>
    <g strokeWidth="3">
      <circle cx="156" cy="28" r="22" className="fill-brand-600/80 stroke-brand-500" />
      <path d="M149 40 V16 H159 C166 16 166 30 159 30 H149" className="stroke-white" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </g>
    <g strokeWidth="3">
      <circle cx="220" cy="28" r="22" className="fill-slate-950 stroke-rose-500" />
      <path d="M205 43 L235 13" className="stroke-rose-500" />
    </g>
    <g strokeWidth="3">
      <rect x="258" y="6" width="38" height="44" rx="6" className="fill-slate-950 stroke-slate-500" />
      <circle cx="277" cy="20" r="5" className="fill-rose-500" stroke="none" />
      <circle cx="277" cy="36" r="5" className="fill-emerald-400" stroke="none" />
    </g>
  </svg>
);

export const ScalesMark: React.FC<{ className?: string }> = ({ className = '' }) => (
  <svg viewBox="0 0 80 80" role="img" aria-hidden="true" className={className}>
    <g fill="none" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
      <path d="M40 10 V66" className="stroke-slate-300" />
      <path d="M22 70 H58" className="stroke-slate-300" />
      <path d="M14 24 H66" className="stroke-slate-300" />
      <path d="M18 24 L8 46 H28 Z" className="stroke-brand-400 fill-brand-600/20" />
      <path d="M62 24 L52 46 H72 Z" className="stroke-brand-400 fill-brand-600/20" />
    </g>
    <circle cx="40" cy="10" r="3.5" className="fill-brand-400" />
  </svg>
);
