# Design System

## Theme

Arc-reactor command interface: a near-black blue-tinted environment designed for a desktop operator in a dim room. Cyan identifies active energy and primary actions; amber, green, and red are reserved for semantic states.

## Color Palette

- Workspace: `#000306`
- Primary surface: `#00080F`
- Raised surface: `#000C18`
- Structural border: `#0A2535`
- Bright border: `#1A5C7A`
- Primary reactor cyan: `#00C8FF`
- Energy cyan: `#00E5FF`
- Primary text: `#E8F8FF`
- Secondary text: `#3A9AB0`
- Dim telemetry: `#1E5A6A`
- Success: `#00FF88`
- Warning: `#FFB300`
- Error: `#FF2244`

## Typography

- **Primary UI:** Space Grotesk, weight 400 for body copy and 500/600 for headings, navigation, buttons, settings, dialogue, and popup titles.
- **Technical data:** JetBrains Mono, weight 400/500 for timestamps, metrics, coordinates, identifiers, terminal output, and status readouts.
- Avoid novelty sci-fi fonts and excessive bold weights. The reactor, motion, spacing, and lighting carry the cinematic identity.
- Letter spacing is reserved for short system labels and must not reduce body-copy legibility.

## Components

- Structural panels use thin cyan-tinted borders and near-black fills.
- Interactive controls retain compact radii and clear active, hover, focus, and disabled states.
- The reactor visualization is the primary identity motif.
- Overlays are opaque enough for legibility and avoid decorative blur.
- Progress represents actual sequence position, not fictional hardware health.

## Layout

The current application uses its three-panel console and centered reactor HUD. Earlier first-run introduction and guided-tour concepts were never implemented in `ui.py`; they remain historical design material and are not part of the executable product contract.

## Motion

Use restrained opacity, scale, and position changes with exponential easing. Avoid bounce, strobing, or continuous decorative movement. Routine launches enter the current console directly.
