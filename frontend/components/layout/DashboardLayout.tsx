"use client";

import React from "react";
import Sidebar from "@/components/layout/Sidebar";
import TopBar  from "@/components/layout/TopBar";

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  return (
    <div className="min-h-screen" style={{ backgroundColor: "var(--bg)" }}>
      <Sidebar />
      <div className="ml-[220px] flex flex-col min-h-screen">
        <TopBar />
        <main className="flex-1 p-6 overflow-x-hidden">
          {children}
        </main>
      </div>
    </div>
  );
}