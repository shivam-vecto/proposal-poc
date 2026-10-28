import React from 'react';

export default function ChoiceRow({ options = [], onSelect, disabled }) {
  if (!options?.length) return null;
  return (
    <div className="ml-11 mt-2 flex flex-wrap gap-2">
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onSelect(opt)}
          disabled={disabled}
          className="rounded-full border border-teal-200 bg-white px-4 py-1.5 text-sm font-medium text-teal-700 transition hover:border-teal-400 hover:bg-teal-50 disabled:opacity-50"
        >
          {opt}
        </button>
      ))}
    </div>
  );
}