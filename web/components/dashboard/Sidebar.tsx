"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Table,
  FileCheck,
  MapPin,
  GitBranch,
  ChevronLeft,
  ChevronRight,
  Activity,
} from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";

const navigation = [
  { name: "Overview", href: "/overview", icon: LayoutDashboard },
  { name: "Rates Explorer", href: "/rates", icon: Table },
  { name: "File Quality", href: "/quality", icon: FileCheck },
  { name: "Address Coverage", href: "/address", icon: MapPin },
  { name: "Audit Trail", href: "/audit", icon: GitBranch },
];

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 h-screen bg-card border-r border-border transition-all duration-300",
        "flex flex-col",
        isCollapsed ? "w-16" : "w-72"
      )}
      aria-label="Main navigation"
    >
      {/* Logo / Brand */}
      <div className="flex items-center justify-between h-16 px-4 border-b border-border">
        {!isCollapsed && (
          <Link href="/overview" className="flex items-center gap-2.5 font-bold text-lg text-primary tracking-tight">
            <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
              <Activity className="h-5 w-5" />
            </div>
            <div className="flex flex-col">
              <span className="leading-none text-foreground font-extrabold text-base">HiLabs</span>
              <span className="text-[10px] text-muted-foreground font-medium">Provider Rates PTD</span>
            </div>
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggle}
          aria-label={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
        >
          {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      <ScrollArea className="flex-1 py-3">
        <nav className="px-3 space-y-1.5" aria-label="Main navigation">
          {!isCollapsed && (
            <div className="px-2 py-1 text-[11px] font-semibold text-muted-foreground/80 uppercase tracking-wider">
              Navigation
            </div>
          )}
          {navigation.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150",
                  isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  isCollapsed && "justify-center px-0"
                )}
                aria-current={isActive ? "page" : undefined}
                title={isCollapsed ? item.name : undefined}
              >
                <item.icon className={cn("h-4 w-4 flex-shrink-0", isActive ? "text-primary-foreground" : "text-primary")} />
                {!isCollapsed && <span className="truncate">{item.name}</span>}
              </Link>
            );
          })}
        </nav>
      </ScrollArea>

      {/* Footer */}
      <div className="border-t border-border p-3.5 bg-muted/20">
        {!isCollapsed ? (
          <div className="text-[11px] text-muted-foreground text-center font-medium">
            Centene California PPO Curation
          </div>
        ) : (
          <div className="flex justify-center">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="System Active" />
          </div>
        )}
      </div>
    </aside>
  );
}