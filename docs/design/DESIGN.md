---
name: Vibrant Friendly Ledger
colors:
  surface: '#f9f9ff'
  surface-dim: '#cfdaf2'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f3ff'
  surface-container: '#e7eeff'
  surface-container-high: '#dee8ff'
  surface-container-highest: '#d8e3fb'
  on-surface: '#111c2d'
  on-surface-variant: '#3d4a43'
  inverse-surface: '#263143'
  inverse-on-surface: '#ecf1ff'
  outline: '#6d7a73'
  outline-variant: '#bccac1'
  surface-tint: '#006c4f'
  primary: '#00694d'
  on-primary: '#ffffff'
  primary-container: '#008562'
  on-primary-container: '#f5fff7'
  inverse-primary: '#61dcae'
  secondary: '#b02c35'
  on-secondary: '#ffffff'
  secondary-container: '#ff6569'
  on-secondary-container: '#690011'
  tertiary: '#0051d5'
  on-tertiary: '#ffffff'
  tertiary-container: '#316bf3'
  on-tertiary-container: '#fefcff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#7ff9c9'
  primary-fixed-dim: '#61dcae'
  on-primary-fixed: '#002116'
  on-primary-fixed-variant: '#00513b'
  secondary-fixed: '#ffdad8'
  secondary-fixed-dim: '#ffb3b1'
  on-secondary-fixed: '#410007'
  on-secondary-fixed-variant: '#8e1020'
  tertiary-fixed: '#dbe1ff'
  tertiary-fixed-dim: '#b4c5ff'
  on-tertiary-fixed: '#00174b'
  on-tertiary-fixed-variant: '#003ea8'
  background: '#f9f9ff'
  on-background: '#111c2d'
  surface-variant: '#d8e3fb'
typography:
  display-currency:
    fontFamily: Lexend
    fontSize: 44px
    fontWeight: '700'
    lineHeight: 52px
    letterSpacing: -0.02em
  display-currency-mobile:
    fontFamily: Lexend
    fontSize: 34px
    fontWeight: '700'
    lineHeight: 42px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Lexend
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Lexend
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Lexend
    fontSize: 22px
    fontWeight: '600'
    lineHeight: 30px
    letterSpacing: 0em
  headline-sm:
    fontFamily: Lexend
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: 0em
  body-lg:
    fontFamily: Lexend
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
    letterSpacing: 0em
  body-md:
    fontFamily: Lexend
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-bold:
    fontFamily: Lexend
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: 0em
  label-lg:
    fontFamily: Lexend
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Lexend
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Lexend
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.5rem
  DEFAULT: 1rem
  md: 1.5rem
  lg: 2rem
  xl: 3rem
  full: 9999px
spacing:
  space-xxs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 2.5rem
  space-3xl: 3.5rem
  touch-target-min: 3rem
---

## Brand & Style

This design system establishes a welcoming, optimistic, and radically accessible financial sanctuary. Personal finance is conventionally associated with anxiety, sterile spreadsheets, or aggressive gamification; this system rejects those archetypes in favor of joyful clarity, tactile reassurance, and cross-generational legibility.

### Target Audience & Emotional Intent
- **Cross-Generational Inclusivity:** Engineered with equal devotion to young adults establishing baseline financial hygiene and seniors requiring hyper-legible typography, generous touch targets, and unmistakable affordances.
- **Emotional Tone:** Encouraging, unhurried, celebratory, and safe. Financial awareness feels rewarding rather than punitive.
- **Design Movement:** Modern Tactile Soft-Pop. It blends the clean discipline of modern accessibility standards with soft pill-shaped containers, cheerful color accents, tactile elevations, and expressive typographic scaling.

## Colors

The color system delivers high visual joy without compromising strict WCAG 2.1 AA and AAA legibility. The canvas is balanced with purposeful color coding for instant cognitive orientation across demographics.

### Palette Architecture
- **Primary (`#009E75` - Forest Mint):** Grounded teal-green tuned to pass WCAG AAA contrast against light surfaces. Used for primary CTAs, active tab accents, and financial inflow/savings milestones.
- **Secondary (`#E04F54` - Warm Coral Red):** A non-punitive, warm coral tuned for clear outflow and critical notifications while maintaining high contrast.
- **Tertiary (`#2563EB` - Clear Sky Cobalt):** Provides informational clarity, interactive secondary elements, and structural balance against warm accents.
- **Neutral Core (`#1E293B` - Deep Ink Slate):** Replaces harsh pure black for all foundational typography and structural boundaries, guaranteeing comfortable reading.
- **Canvas Base (`#F8FAFC` - Soft Daylight):** Ultra-crisp background surface with minimal glare, paired with elevated white (`#FFFFFF`) card surfaces.
- **Joy Accents:** Accent fills including Sunny Amber (`#D97706`), Lively Mint Light (`#E6FBF5`), and Warm Sky Light (`#EBF5FF`) provide friendly, non-distracting badge backgrounds and category identifiers.

### Semantic Status & Cashflow Logic
- **Income / Inflow:** Emerald Teal tones paired with an upward directional indicator.
- **Expense / Outflow:** Gentle Coral tones paired with a downward directional indicator.
- **Neutral / Pending:** Warm Sunny Amber tones for holding states or transfers between self-owned accounts.

## Typography

Lexend was explicitly engineered to reduce visual crowding and increase character recognition speed, making it exceptionally suited for cross-generational financial software.

### Typographic Principles
- **Tabular Figures:** All numeric displays (balances, transactions, ledger lines) enforce tabular lining numerals (`tnum`) to ensure aligned decimal points and rapid visual parsing.
- **Generous Line Height:** Generous line heights are maintained across all scale tiers to prevent lines from clumping together for visually impaired or elderly users.
- **Hierarchy Distinction:** Weight steps are kept crisp (Normal 400, Semi-Bold 600, Bold 700). We avoid thin/hairline weights to ensure legibility on low-brightness screens.

## Layout & Spacing

The layout is built around comfortable touch interactions, thumb-driven single-hand navigation, and immediate structural clarity.

### Layout Model
- **Grid Structure:** Single-column mobile stack spanning 4 to 8 columns on mobile viewports with a 16px to 20px screen margin. On wider viewports (tablets/foldables), content limits to a maximum reading container of 640px to prevent excessive horizontal eye travel.
- **Touch Targets:** The base touch target standard enforces a strict minimum boundary of 48px (`3rem`) for every interactive area, avoiding mistaps for seniors or users on the move.
- **Spacing Rhythm:** Built on an 8pt base grid (`0.5rem`). Micro-details utilize 4px half-steps. Screen padding dynamically transitions between `space-md` (16px) on compact phones and `space-lg` (24px) on standard devices.

## Elevation & Depth

Visual depth combines warm layered planes with soft, colored ambient drop shadows. This creates a tactile, approachable interface rather than an intimidating, hyper-flat grid.

### Elevation Levels
- **Level 0 (Floor):** Canvas background `#F8FAFC`. Completely flat.
- **Level 1 (Card & Content Blocks):** Pure white `#FFFFFF` surface resting on the floor with a dual shadow: `0 2px 4px rgba(30, 41, 59, 0.04)` combined with an ambient diffuse `0 8px 16px -4px rgba(100, 116, 139, 0.08)`.
- **Level 2 (Interactive Elements & Floating CTAs):** Elevated buttons and active status cards use an intentional tinted ambient cast: `0 10px 20px -6px rgba(0, 158, 117, 0.25)` for primary actions and `0 8px 18px -4px rgba(30, 41, 59, 0.12)` for standard surface components.
- **Level 3 (Modals & Bottom Drawers):** Bottom action sheets and contextual breakdowns sit on a high-blur diffuse shadow: `0 -12px 32px rgba(30, 41, 59, 0.12)`, grounding focus securely over a 40% opacity ink backdrop.

## Shapes

The design system embraces a friendly, pill-forward shape hierarchy (Level 3). Soft, curvilinear geometry reduces cognitive tension, invites exploration, and signals safety.

### Geometry Guidelines
- **Buttons and Badges:** Fully pill-shaped (`border-radius: 9999px`) to immediately communicate clickability and warmth.
- **Cards and Containers:** Rounded corners (`1.5rem` to `2rem`) define all transaction clusters, account cards, and budget graphs.
- **Form Controls:** Text inputs and selectors use rounded corners of `1rem`, complementing buttons while retaining structural definition.

## Components

### Buttons
- **Primary Action:** Pill-shaped, minimum height 52px (touch accessible). Filled with Forest Mint (`#009E75`), label in white `label-lg`, with active micro-scale press feedback (`scale: 0.98`).
- **Secondary Action:** Pill-shaped, 52px height, tinted background (`#E6FBF5`), crisp `#009E75` text, and zero sharp borders.
- **Destructive Action:** Soft coral tint background (`#FEE2E2`) with `#E04F54` text.

### Badges & Pill Chips
- **Category & Status Chips:** Capsule pills (`rounded-full`) with a vertical padding of 6px and horizontal padding of 14px.
- **Visual Cues:** Backgrounds use low-saturation, cheerful tints (e.g., `#FEF3C7` Amber light for discretionary spending, `#E0F2FE` Sky light for utilities) with high-contrast text. Accompanied by simple iconography.

### Cards
- **Account & Budget Containers:** White background, Level 1 shadow, 24px internal padding, 24px outer corner radius. Dividers inside cards use 1px soft hairline dividers (`#F1F5F9`) rather than heavy borders.
- **Spending Alert Cards:** Feature an integrated 4px left-hand color spine and a light thematic tint across the surface to immediately flag status without aggressive error styling.

### Input Fields
- **Design:** Minimum height 56px. Clear 16px baseline font size to prevent mobile browser auto-zooming.
- **States:** Inactive border in `#E2E8F0` (1.5px width). Active focus state shifts to a 2px `#009E75` ring with an ambient soft glow. Error states replace the ring with `#E04F54` alongside plain-language helper messages.

### Selection Controls (Checkboxes & Radios)
- **Geometry:** Checkboxes have 8px rounded corners; radio buttons are circular.
- **Sizing:** Large 24px x 24px visual mark surrounded by a minimum 48px touch-activation container. High-contrast checkmarks ensure effortless scanning.

### Lists & Transaction Feeds
- **Item Row:** Generous 64px row height. Left icon pill (44px) on a tinted category base, vertical stack containing transaction title (`headline-sm`) and metadata (`body-md`), with right-aligned tabular currency displays.
- **Inflow Numbers:** Prefixed with a clear `+` sign and colored `#009E75`.
- **Outflow Numbers:** Prefixed with a `-` sign and colored `#1E293B` (or `#E04F54` for budget limit exceeded).

### Data Visualizations & Charts
- **Bar & Donut Graphs:** Thick, rounded-cap strokes (12px to 16px minimum thickness) avoid thin wireframes.
- **Direct Labeling:** Data values display directly on or adjacent to segments with explicit text tags; never rely exclusively on separate color-only legends.