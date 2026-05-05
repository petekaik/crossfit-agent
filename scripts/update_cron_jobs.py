#!/usr/bin/env python3
"""
CrossFit Cron Job Update Script
Päivittää OpenClaw cron jobit enhanced-versiolle
"""

print("""
Päivitettävät cron jobit:

1. crossfit-reppi-search
   - Timeout: 300s → 600s (10 min)
   - Syy: Aikaisemmat timeout-virheet
   - Lisätty: Retry logic cron_runner.py:ssä

2. crossfit-reppi-sync  
   - Toimii OK (viimeisin success)
   - Ei muutoksia

3. UUSI: crossfit-status-check
   - Ajoitus: 0 8 * * * (klo 8:00)
   - Tulostaa statuksen Discordiin

Hyväksy päivitys Web UI:ssa tai terminaalissa.
""")
