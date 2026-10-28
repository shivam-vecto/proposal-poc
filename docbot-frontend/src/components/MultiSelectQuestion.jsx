import React, { useState } from 'react';
import { CheckCircle } from 'lucide-react';

export default function MultiSelectQuestion({ options = [], onSubmit, disabled }) {
  const [selected, setSelected] = useState({});

  const toggle = (val) => {
    setSelected((prev) => {
      const next = { ...prev };
      if (val in next) delete next[val];
      else next[val] = '';
      return next;
    });
  };

  const updateDetail = (val, detail) => {
    setSelected((prev) => ({ ...prev, [val]: detail }));
  };

  const any = Object.keys(selected).length > 0;

  return (
    <div className="mt-3 space-y-2">
      {options.map((opt) => {
        const isChecked = opt.value in selected;
        return (
          <div
            key={opt.value}
            className={`rounded-xl border bg-white p-3 transition ${
              isChecked ? 'border-teal-300 bg-teal-50' : 'border-slate-200'
            }`}
          >
            <label className="flex cursor-pointer items-center gap-3">
              <input
                type="checkbox"
                checked={isChecked}
                onChange={() => toggle(opt.value)}
                disabled={disabled}
              />
              <span className="font-medium text-slate-700">{opt.label}</span>
              {opt.example && (
                <span className="ml-auto text-xs text-slate-400">
                  e.g., {opt.example}
                </span>
              )}
            </label>
            {isChecked && (
              <input
                type="text"
                className="mt-2 w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-teal-400 focus:ring-2 focus:ring-teal-100"
                placeholder="Since when / frequency (e.g., 3 years / 2 daily)"
                value={selected[opt.value] || ''}
                onChange={(e) => updateDetail(opt.value, e.target.value)}
                disabled={disabled}
              />
            )}
          </div>
        );
      })}
      <div className="mt-4 flex gap-2">
        <button
          onClick={() => onSubmit(selected)}
          disabled={disabled}
          className="inline-flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-teal-700 disabled:opacity-50"
        >
          <CheckCircle size={16} />
          {any ? `Confirm ${Object.keys(selected).length} selection(s)` : 'Confirm (none)'}
        </button>
        <button
          onClick={() => onSubmit('skip')}
          disabled={disabled}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
        >
          Skip
        </button>
      </div>
    </div>
  );
}