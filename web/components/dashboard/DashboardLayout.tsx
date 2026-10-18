"use client";

import { useState, useEffect, ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { PipelineStage } from "@/lib/types";

interface DashboardLayoutProps {
  children: ReactNode;
  title: string;
  pipelineStages?: PipelineStage[];
  showSearch?: boolean;
  onSearch?: (value: string) => void;
  searchPlaceholder?: string;
}

export function DashboardLayout({
  children,
  title,
  pipelineStages,
  showSearch = false,
  onSearch,
  searchPlaceholder,
}: DashboardLayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 1024);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  const toggleSidebar = () => {
    if (window.innerWidth < 1024) {
      setIsMobileMenuOpen(!isMobileMenuOpen);
    } else {
      setIsSidebarCollapsed(!isSidebarCollapsed);
    }
  };

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Sidebar Overlay for Mobile */}
      {isMobileMenuOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={closeMobileMenu}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <Sidebar
        isCollapsed={isSidebarCollapsed || isMobile}
        onToggle={toggleSidebar}
        pipelineStatus={pipelineStages}
      />

      {/* Main Content */}
      <div
        className={cn(
          "transition-all duration-300",
          "lg:ml-72",
          isSidebarCollapsed && "lg:ml-16",
          !isSidebarCollapsed && "lg:ml-72"
        )}
      >
        {/* Top Bar */}
        <TopBar
          title={title}
          onMenuClick={toggleSidebar}
          showSearch={showSearch}
          onSearch={onSearch}
          searchPlaceholder={searchPlaceholder}
        />

        {/* Page Content */}
        <main className="p-4 lg:p-6" onClick={closeMobileMenu}>
          {children}
        </main>
      </div>

      {/* Mobile Bottom Navigation */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-background">
        <div className="flex justify-around items-center h-14">
          <a href="/overview" className="flex flex-col items-center gap-1 p-2 text-muted-foreground">
            <span className="text-[10px]">Overview</span>
          </a>
          <a href="/rates" className="flex flex-col items-center gap-1 p-2 text-muted-foreground">
            <span className="text-[10px]">Rates</span>
          </a>
          <a href="/quality" className="flex flex-col items-center gap-1 p-2 text-muted-foreground">
            <span className="text-[10px]">Quality</span>
          </a>
          <a href="/address" className="flex flex-col items-center gap-1 p-2 text-muted-foreground">
            <span className="text-[10px]">Address</span>
          </a>
          <a href="/audit" className="flex flex-col items-center gap-1 p-2 text-muted-foreground">
            <span className="text-[10px]">Audit</span>
          </a>
        </div>
      </nav>
    </div>
  );
}