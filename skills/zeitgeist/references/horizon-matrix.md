# Temporal Horizon Matrix Reference

This reference defines how Zeitgeist categorizes temporal queries, which data source it queries, and which reliability label it mandates in assistant responses.

| Horizon | Relative Window | Resolution | Data Strategy | Reliability Label | Mandatory Output Phrasing |
|---|---|---|---|---|---|
| **1. Micro** | 0 – 36 uur | Uur-tot-uur (Hourly) | Open-Meteo Forecast API `hourly` | `forecast` | "Verwachting voor [uur/tijdstip]: ..." |
| **2. Meso** | 36 uur – 7 dagen | Dagdelen + Min/Max | Open-Meteo Forecast API `daily` | `forecast` (dag 1-4) / `trend` (dag 5-7) | "Verwachting / Trend voor [dag]: ..." |
| **3. Macro** | 8 – 30 dagen | Wekelijkse trends | Open-Meteo 16-day Ensemble / Historical Trend | `trend` / `climatology` | "Meerdaagse trend voor [periode]: ..." |
| **4. Clima** | > 30 dagen (tot jaren) | Maand-/seizoensnormalen | Open-Meteo Climate Normals & Archive | `climatology` | "Klimatologische verwachting voor [maand/seizoen]: ..." |

### Anti-Hallucination Rules:
1. **Never invent a daily forecast for dates > 16 days out.** Always use `climatology` averages and state it explicitly.
2. **Always include the reliability tag:** `[forecast]`, `[trend]`, or `[climatology]`.
3. **Multi-horizon queries:** Split into sequential segments and label each segment individually.
