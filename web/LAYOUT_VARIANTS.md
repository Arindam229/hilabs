# HiLabs Provider Rates Dashboard - Layout Variants

## Shared Constraints
- **Stack**: Next.js 14 (App Router) + Tailwind CSS + shadcn/ui + Tremor + TanStack Table + Recharts + Framer Motion
- **Data**: Real pipeline outputs (data/out/final_provider_rates.xlsx, data/stage/c4/c4_summary.json, data/stage/c3/file_metrics.parquet, _manifest.json files)
- **Pages**: Overview, Rates Explorer, File Quality, Address Coverage, Audit Trail
- **Colors**: Professional blue/gray with status colors (green=corroborated, amber=single, red=conflicting, gray=unresolved)
- **Responsive**: Sidebar collapse, dark mode, loading skeletons, empty states, error boundaries
- **Accessibility**: Keyboard navigation, ARIA labels, focus rings

---

## Variant 1: "Command Center" - High Density, Side Navigation
**Core Idea**: Maximum information density for power users who monitor pipeline health daily

### Layout Structure
```
┌─────────────────────────────────────────────────────────────────┐
│ Top Bar: HiLabs Logo | Search | Theme Toggle | User Menu       │
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                        │
│  SIDE    │  MAIN CONTENT AREA                                     │
│  BAR     │  ┌────────────────────────────────────────────────┐   │
│  (280px) │  │ KPI Row (4 cards): Rates | NPIs | TINs | % Addr │   │
│          │  ├────────────────────────────────────────────────┤   │
│  Nav:    │  │ Trend Sparklines (4 mini charts)               │   │
│  - Overview    ├────────────────────────────────────────────────┤   │
│  - Rates       │  │ Pipeline Status: C1→C2→C3→C4→C5→C6       │   │
│  - Quality     │  │ [●][●][●][●][●][●] with timing + counts  │   │
│  - Address     │  └────────────────────────────────────────────────┘   │
│  - Audit       │                                                        │
│          │                                                        │
│  Collapse│                                                        │
│  to 64px │                                                        │
└──────────┴──────────────────────────────────────────────────────┘
```

### Key Differences from Others
1. **Persistent side navigation** - Always visible, collapses to icons only
2. **Single-page density** - All Overview content fits without scrolling on 1440p
3. **Pipeline as horizontal timeline** - Visual stage progression with live status

### References
- 21st: "tremor-dashboard" (high-density admin panels)
- 21st: "vercel-style-sidebar" (collapsible icon-only mode)

### Tradeoffs
- **Pros**: Fast navigation, everything visible, familiar admin pattern
- **Cons**: Less breathing room, sidebar takes horizontal space

---

## Variant 2: "Focus Flow" - Card-Based, Top Navigation
**Core Idea**: Guided workflow with progressive disclosure, better for exploratory analysis

### Layout Structure
```
┌─────────────────────────────────────────────────────────────────┐
│ Top Bar: HiLabs Logo | Page Tabs [Overview][Rates][Quality]... │
│         Theme Toggle | User Menu                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  MAIN CONTENT (full width, centered max 1400px)                │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ KPI Cards Grid (auto-fit: 4 on desktop, 2 tablet, 1 mobile)│ │
│  │ [Rates][NPIs][TINs][% Verified]                           │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Section: Pipeline Health                                  │  │
│  │ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐   │  │
│  │ │  C1  │→│  C2  │→│  C3  │→│  C4  │→│  C5  │→│  C6  │   │  │
│  │ │ ✓ 0.1s│ │ ✓ 18s│ │ ✓ 15s│ │ ✓ 50s│ │ ✓ 203s│ │ ✓ 2s│   │  │
│  │ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘   │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Section: Quick Insights (3 cards: Trend, Coverage, Grade) │ │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Differences from Others
1. **Top tab navigation** - Page switching via tabs, no persistent sidebar
2. **Card-based sections** - Each major metric group in its own card with clear hierarchy
3. **Full-width content** - Maximum width for tables/charts on Rates/Quality pages

### References
- 21st: "linear-app-layout" (clean tab navigation)
- 21st: "stripe-dashboard-cards" (breathing room, card hierarchy)

### Tradeoffs
- **Pros**: More space for data tables, cleaner mobile experience, modern feel
- **Cons**: Tab switching overhead, pipeline status less prominent

---

## Variant 3: "Hybrid Workspace" - Responsive Sidebar + Tab Bar
**Core Idea**: Best of both - sidebar on desktop, bottom tabs on mobile, contextual tools

### Layout Structure
```
┌─────────────────────────────────────────────────────────────────┐
│ Top Bar: HiLabs Logo | Page Title | Actions | Theme | User     │
├──────────┬──────────────────────────────────────────────────────┤
│          │                                                        │
│  SIDE    │  MAIN CONTENT                                         │
│  BAR     │  ┌────────────────────────────────────────────────┐   │
│  (280px) │  │ KPI Bar: 4 compact metrics (icon + value + Δ)  │   │
│          │  ├────────────────────────────────────────────────┤   │
│  Sections:│  │ Content Area (varies by page)                  │   │
│  ▼ Overview │  │ Overview: Pipeline timeline + mini charts    │   │
│  ▼ Rates    │  │ Rates: TanStack Table (full height)          │   │
│  ▼ Quality  │  │ Quality: Grade card + metric table           │   │
│  ▼ Address  │  │ Address: Donut + bar + unresolved list       │   │
│  ▼ Audit    │  │ Audit: Timeline list with expandable details │   │
│          │  │                                                │   │
│  Quick    │  └────────────────────────────────────────────────┘   │
│  Filters  │                                                        │
│  (context)│                                                        │
│          │                                                        │
└──────────┴──────────────────────────────────────────────────────┘

Mobile: Sidebar → Bottom tab bar (5 tabs), Top bar → Hamburger menu
```

### Key Differences from Others
1. **Sectioned sidebar** - Expandable sections with contextual quick filters per page
2. **Compact KPI bar** - Single row of 4 metrics with trend indicators
3. **Adaptive navigation** - Sidebar on desktop, bottom tabs on mobile

### References
- 21st: "notion-sidebar" (sectioned, collapsible sections)
- 21st: "github-responsive-nav" (desktop sidebar → mobile bottom tabs)

### Tradeoffs
- **Pros**: Best responsive behavior, contextual filters, balanced density
- **Cons**: Most complex implementation, sidebar state management

---

## Comparison Matrix

| Aspect | Command Center | Focus Flow | Hybrid Workspace |
|--------|---------------|------------|------------------|
| Navigation | Persistent sidebar | Top tabs | Sidebar + sections |
| Density | High | Medium | Medium-High |
| Pipeline visibility | Always (timeline) | On Overview only | Always (sidebar) |
| Table space | Constrained | Full width | Full width |
| Mobile UX | Sidebar drawer | Native tabs | Bottom tabs |
| Implementation | Simple | Simple | Complex |
| Power user fit | ★★★★★ | ★★★☆☆ | ★★★★☆ |
| Explorer fit | ★★★☆☆ | ★★★★★ | ★★★★☆ |

---

## Recommendation: **Variant 3 - Hybrid Workspace**

**Why**:
1. **Best responsive behavior** - Critical for a dashboard that may be viewed on tablets
2. **Contextual filters in sidebar** - Rates page gets NPI/TIN search; Quality gets grade filter; Address gets status filter
3. **Pipeline always visible** - Sidebar shows stage status without navigating away
4. **Balanced density** - Compact KPI bar + full-width content area
5. **Progressive enhancement** - Can start simple, add sidebar sections incrementally

**Risks to mitigate**:
- Sidebar state persistence (localStorage)
- Mobile bottom tab bar implementation
- Section expand/collapse animation performance

---

## Next Steps
1. Initialize Next.js 14 project with all dependencies
2. Set up shadcn/ui with custom theme (blue/gray + status colors)
3. Implement Hybrid Workspace layout with:
   - Responsive sidebar (desktop) / bottom tabs (mobile)
   - Top bar with page title, actions, theme toggle
   - KPI bar component
   - Page content areas
4. Build API routes for data loading
5. Implement each page with real data
6. Add Framer Motion transitions
7. Add loading skeletons, error boundaries, empty states