---
name: RAWRS Pro Dark
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#c0c7d4'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#8b919d'
  outline-variant: '#414752'
  surface-tint: '#a2c9ff'
  primary: '#a2c9ff'
  on-primary: '#00315c'
  primary-container: '#58a6ff'
  on-primary-container: '#003a6b'
  inverse-primary: '#0060aa'
  secondary: '#c1c7d0'
  on-secondary: '#2b3138'
  secondary-container: '#41474f'
  on-secondary-container: '#b0b5be'
  tertiary: '#ffba42'
  on-tertiary: '#432c00'
  tertiary-container: '#da9600'
  on-tertiary-container: '#4f3400'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#d3e4ff'
  primary-fixed-dim: '#a2c9ff'
  on-primary-fixed: '#001c38'
  on-primary-fixed-variant: '#004882'
  secondary-fixed: '#dde3ec'
  secondary-fixed-dim: '#c1c7d0'
  on-secondary-fixed: '#161c23'
  on-secondary-fixed-variant: '#41474f'
  tertiary-fixed: '#ffddaf'
  tertiary-fixed-dim: '#ffba42'
  on-tertiary-fixed: '#281800'
  on-tertiary-fixed-variant: '#614000'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
typography:
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  code-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-xs: 4px
  space-sm: 8px
  space-md: 12px
  space-lg: 16px
  panel-gutter: 1px
  sidebar-width: 240px
---

## Brand & Style
The design system is a high-density, utility-first framework optimized for professional engineering environments and data-intensive workflows. It prioritizes functional clarity over decorative flair, drawing inspiration from modern IDEs and high-performance productivity tools.

The brand personality is precise, technical, and dependable. It avoids visual noise like gradients, shadows, or glassmorphism to ensure the user's cognitive load is reserved entirely for the task at hand. The aesthetic is "Technical Minimalist"—utilizing flat surfaces, crisp borders, and a strict monochromatic-leaning palette to create a stable environment for long-duration focused work.

## Colors
This design system operates exclusively in a high-contrast dark mode to reduce eye strain and emphasize syntax and data states.

- **Backgrounds:** The foundation is a deep navy (#0d1117). Secondary surfaces (sidebars, panels) use #161b22 to create subtle structural differentiation without relying on shadows.
- **Accents:** The primary action color is #58a6ff, specifically chosen for its WCAG AA compliance against dark backgrounds.
- **Borders:** A consistent slate gray (#30363d) is used for all structural containment.
- **Typography:** Text levels use a tiered white-to-gray scale (#f0f6fc for primary content, #8b949e for metadata and labels) to establish a clear information hierarchy.

## Typography
The typography system is split between functional UI navigation and data density.

- **Inter:** Used for all interface elements, menus, and prose. It provides excellent legibility at small scales.
- **JetBrains Mono:** Used for tabular data, logs, code snippets, and technical labels. The monospaced nature ensures vertical alignment in data-heavy views.
- **Sizing:** To maintain high density, the base body size is set to 14px, with 12px used for secondary labels and metadata. Headlines are kept conservative in size, using font weight rather than scale to denote importance.

## Layout & Spacing
This design system utilizes a high-density "Panel-Based" layout. Instead of fluid whitespace, it relies on strict containment and 1px borders to maximize usable screen real estate.

- **The 4px Grid:** All internal padding and margins follow a 4px stepping scale. Use 8px (space-sm) for standard element spacing and 12px (space-md) for container padding.
- **Panel Borders:** Adjacent panels should be separated by a 1px border (#30363d) rather than margins. This emulates the "tiled" look of professional IDEs.
- **Responsive Behavior:** On desktop, the layout is fixed-sidebar with fluid main content. On mobile, panels collapse into a stacked vertical view, though the primary target for this system is large-format desktop displays.

## Elevation & Depth
In alignment with the flat, utility-focused aesthetic, this design system does not use ambient shadows. Depth is communicated through color and borders.

- **Level 0 (Background):** #0d1117 - The primary canvas.
- **Level 1 (Panels):** #161b22 - Used for sidebars, bottom panels, and status bars.
- **Level 2 (Modals/Popovers):** #1c2128 - Used for floating menus or dialogs. These are the only elements allowed to have a subtle 1px border of a slightly lighter gray (#444c56) to ensure separation from the background.
- **Focus States:** High-visibility 2px solid outlines in #58a6ff are required for all keyboard navigation and active input states.

## Shapes
The shape language is rigid and structural.

- **Standard Elements:** Buttons, inputs, and tags use a "Soft" 4px (0.25rem) radius. This provides just enough visual comfort to distinguish elements from the layout grid without sacrificing the professional, "engineered" feel.
- **Container Elements:** Main panels and window segments should remain sharp (0px) to maximize the feeling of being part of a single, integrated workbench.

## Components
- **Buttons:** Primary buttons use a solid #58a6ff fill with black text for maximum contrast. Secondary buttons are ghost-style with a #30363d border and #f0f6fc text.
- **Inputs:** Dark background (#0d1117) with a 1px #30363d border. Active states must switch the border color to #58a6ff.
- **Chips/Tags:** Compact, using #161b22 background and JetBrains Mono for the label. Used for status indicators and metadata.
- **Lists/Trees:** High-density rows (28-32px height) with a hover state of #21262d. Active/Selected items use a left-edge 2px accent line in #58a6ff.
- **Data Tables:** Bordered cells using #30363d. Headers use JetBrains Mono in uppercase with #8b949e color for a technical look.
- **Status Bar:** A dedicated 24px tall strip at the bottom of the interface using #051d3b (dark blue) or #161b22, containing technical metadata and global application states.