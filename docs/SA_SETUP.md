# Service Account + Public Key Upload — Ohjeet

Google Cloud Console hyväksyy X.509-sertifikaatin (ei raakaa julkista avainta).
Oikea tiedosto: **public_x509.pem** (luotu valmiiksi koneellasi).

## Vaihe A: Service Accountin luonti

1. Avaa: **https://console.cloud.google.com/iam-admin/serviceaccounts**
2. Varmista että crossfit-agentin projekti on valittuna (yläpalkista)
3. **Create Service Account**
   - Nimi: `crossfit-agent-calendar`
   - ID: `crossfit-agent-calendar` (täyttyy automaattisesti)
   - Klikkaa **Create and Continue**
4. Älä lisää rooleja — klikkaa **Done**
5. Klikkaa juuri luotua Service Accountia listasta (sähköpostilinkki)

## Vaihe B: Public key upload

6. Valitse **Keys**-välilehti
7. **Add Key → Upload public key**
8. Valitse tiedosto: **`/Users/petekaik/projects/crossfit-agent/public_x509.pem`**
9. Klikkaa **Upload**
10. Kopioi näkyviin tulevat tiedot talteen:
    - **SA-sähköposti**: `crossfit-agent-calendar@<projekti-id>.iam.gserviceaccount.com`
    - **Key ID**: (esim. `abc123def456...` — 40-merkkinen hex-string)

## Vaihe C: Kalenterin jakaminen SA:lle

11. Avaa **Google Calendar** (calendar.google.com)
12. Etsi **Urheilutapahtumat**-kalenteri vasemmalta listalta
13. Vie hiiri kalenterin nimen päälle → **⋮ (kolme pistettä)** → **Settings and sharing**
14. Vieritä kohtaan **Share with specific people or groups**
15. Klikkaa **Add people and groups**
16. Liitä SA:n sähköpostiosoite (Vaihe B, kohta 10)
17. Oikeus: **Make changes to events**
18. Klikkaa **Send**

    ⚠️ SA ei vastaanota sähköpostia, mutta jako rekisteröityy. Varmista että
    Service Account näkyy listalla "Share with specific people or groups" -
   osiossa.

## Toimitus minulle

Palauta nämä kolme arvoa:
- **SA-sähköposti**: `crossfit-agent-calendar@<projekti-id>.iam.gserviceaccount.com`
- **Key ID**: 40-merkkinen hex (Cloud Consolesta kopioituna)
- **Projekti-ID**: näkyy console-etusivulla tai URL:ssa
