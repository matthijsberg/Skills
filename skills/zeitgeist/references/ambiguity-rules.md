# Relative Time Normalization & Ambiguity Rules

### Ambiguity Standards (Deterministisch vastgelegd):

1. **"volgende week [dag]" (bv. "volgende week vrijdag"):**
   - Resolves to: the specified weekday in the *next ISO calendar week* (Monday..Sunday), NOT the first upcoming occurrence.
   - Example: On Wednesday Aug 12, "volgende week vrijdag" is Friday Aug 21, while "aanstaande vrijdag" is Friday Aug 14.
   - Confidence: 0.85 (explicitly mention interpretation in response).

2. **"dit weekend":**
   - On Monday–Friday: The upcoming Saturday 00:00 to Sunday 23:59:59.
   - On Saturday–Sunday: The current weekend remainder.
   - Confidence: 0.95.

3. **"eerste weekend van [maand]":**
   - The first Saturday–Sunday pair where Saturday falls in the target month.
   - Confidence: 0.90.

4. **"over [N] dagen / morgen / overmorgen":**
   - Relative offsets from reference date in the target timezone.
   - If daypart specified (bv. "morgenochtend"): start 06:00, end 12:00.
   - If no daypart specified: full day 00:00 to 23:59:59.

5. **Confidence Drempel:**
   - $\ge 0.80$: Proceed immediately and briefly state assumption.
   - $< 0.80$: Ask 1 targeted clarification question via `clarify`.
