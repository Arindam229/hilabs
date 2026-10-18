"use client";

import { useState, useEffect } from "react";
import { useTheme } from "next-themes";
import { Menu, Sun, Moon, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface TopBarProps {
  title: string;
  onMenuClick: () => void;
  showSearch?: boolean;
  onSearch?: (value: string) => void;
  searchPlaceholder?: string;
}

export function TopBar({
  title,
  onMenuClick,
  showSearch = false,
  onSearch,
  searchPlaceholder = "Search...",
}: TopBarProps) {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const currentTheme = theme === "system" ? resolvedTheme : theme;
  const isDark = currentTheme === "dark";

  const toggleTheme = () => {
    setTheme(isDark ? "light" : "dark");
  };

  return (
    <header className="sticky top-0 z-30 h-16 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b border-border">
      <div className="flex h-full items-center justify-between px-4 sm:px-6 gap-4">
        {/* Left: Menu button + Title */}
        <div className="flex items-center gap-3 min-w-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={onMenuClick}
            className="lg:hidden h-9 w-9 text-muted-foreground hover:text-foreground"
            aria-label="Toggle menu"
          >
            <Menu className="h-5 w-5" />
          </Button>
          <h1 className="text-lg font-semibold tracking-tight text-foreground truncate">{title}</h1>
        </div>

        {/* Center: Search (optional) */}
        {showSearch && (
          <div className="flex-1 max-w-md hidden md:block">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                type="search"
                placeholder={searchPlaceholder}
                onChange={(e) => onSearch?.(e.target.value)}
                className="pl-9 pr-4 h-9 bg-card border-border/80 focus-visible:ring-primary/20"
                aria-label="Search"
              />
            </div>
          </div>
        )}

        {/* Right: Refined Dark/Light Mode Toggle */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={toggleTheme}
            className="h-9 px-3 rounded-lg border-border/80 bg-card hover:bg-muted/80 text-foreground flex items-center gap-2 shadow-xs transition-colors cursor-pointer select-none"
            aria-label="Toggle color theme"
          >
            {mounted ? (
              isDark ? (
                <>
                  <Moon className="h-4 w-4 text-sky-400" />
                  <span className="text-xs font-medium">Dark Mode</span>
                </>
              ) : (
                <>
                  <Sun className="h-4 w-4 text-amber-500" />
                  <span className="text-xs font-medium">Light Mode</span>
                </>
              )
            ) : (
              <span className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </header>
  );
}