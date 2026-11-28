---
version: 1
slug: "app-templates-index-html"
primary_target: "app/templates/index.html"
related_targets: ["app/templates/_public_header.html","app/templates/citizen/portal.html","app/templates/sms/inbox.html","app/templates/dashboard/index.html","app/templates/planting/index.html","app/templates/government/index.html","app/templates/government/simulator.html","app/templates/government/reports.html","app/templates/government/scenarios.html","app/templates/mensajes/index.html","app/templates/voice/index.html"]
---

# Surface brief — Protocolo Lupita home

## Scope and mode
Public home (`/`) and the shared visual system for the citizen pages and private government console. The home is **Persuade**: help a resident choose a safe next step. Government screens remain **Operate**: help staff scan a simulated call, report, or scenario.

## Audience, task, and content
Residents who receive a suspicious message or call need to review it, report it, or consult public guidance. Government staff need to follow the local demonstration and inspect indicators. Use the existing citizen question, report and SMS-analysis flows, public advice, and credentialed console. Evidence shown in the prototype is synthetic.

## Constraints
Keep Spanish content, routes, roles, endpoints, security boundaries, and existing interactions. The shield logo supplied by the user is the exact brand asset. Use deep navy, warm off-white, and gold. Never imply real phone activity, confirmed fraud, official live alerts, or a report sent to authorities. The browser frame visible in the selected comp is a presentation artifact, not product UI.

## Chosen direction
**Wayfinding de servicio** — civic wayfinding signs and public-service directories express each next step as a clear route. The citizen home leads with the existing question and a split hero; an integrated gold route diagram points to SMS review, citizen reporting, and public alerts. Government access remains a separate, secondary route. The private console carries the same palette and destination-label grammar while prioritizing operational status and scanability. Memorable moment: one gold origin marker branches to three plainly labeled destinations.

## Open decisions
Adapt the route diagram for narrow screens; choose route icons and copy details from existing labels. Preserve the public and government distinction across all routes.

## Direction contract
THESIS: A suspicious message should lead to a clearly marked next step, not a generic threat dashboard.

OWN-WORLD: Civic wayfinding signs and service directories in deep navy, warm off-white, and gold; directional plaques, fine route rails, compact labels, and the supplied fox shield. Gold marks the primary route and active destination. No fabricated activity numbers or decorative map.

STORY: The resident recognizes their situation, sees the SMS review, report, and public-advice routes, then chooses one. Government access reads as a separate route. In the console, the same labels help staff locate live-demo, simulator, reports, and events.

FIRST VIEWPORT: A short navy header places the exact shield and Protocolo Lupita wordmark at left, navigation at right. On the off-white field, the question and explanatory sentence occupy the left half. A dominant gold “Revisar un SMS” route and outlined “Hacer un reporte” route sit below. On the right, one origin node branches to labeled SMS, report, and alert destinations. Government access and a “Demostración local · datos ficticios” note sit below the hero.

FORM: The chosen comp is `.impeccable/mocks/wayfinding-1.png`; the byte-identical direction card remains at `.impeccable/mocks/decision/model-pick.png`. The comp’s browser frame is not literalized. Build a real responsive page; controls remain links/buttons with existing behavior. Other routes inherit the wayfinding system without turning dense console tasks into promotional signage.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
