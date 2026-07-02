"use client";

import { useState } from "react";

export interface TabDef {
  id: string;
  label: string;
  badge?: React.ReactNode;
  content: React.ReactNode;
}

export function Tabs({ tabs, initialTabId }: { tabs: TabDef[]; initialTabId?: string }) {
  const [activeId, setActiveId] = useState(initialTabId ?? tabs[0]?.id);
  const active = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  return (
    <div>
      <div role="tablist" aria-label="Document sections" className="flex flex-wrap gap-1 border-b border-gray-200">
        {tabs.map((tab) => {
          const isActive = tab.id === active?.id;
          return (
            <button
              key={tab.id}
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActiveId(tab.id)}
              className={`flex items-center gap-2 rounded-t-md px-4 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
                isActive
                  ? "border-b-2 border-blue-600 text-blue-700"
                  : "border-b-2 border-transparent text-gray-500 hover:text-gray-700"
              }`}
            >
              {tab.label}
              {tab.badge}
            </button>
          );
        })}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`panel-${tab.id}`}
          aria-labelledby={`tab-${tab.id}`}
          hidden={tab.id !== active?.id}
          className="py-5"
        >
          {tab.id === active?.id ? tab.content : null}
        </div>
      ))}
    </div>
  );
}
