# TODO.md - Kehitysjono

**Päivitetty:** 2026-03-22

---

## 🔄 Jatkokehitys - Tulevat ominaisuudet

### Korkea prioriteetti
- [ ] **World Fitness Project** - Lähde ja parseri WFP:n osakilpailuille
- [ ] **Roque Invitational** - Lähde ja parseri Roque invitational crossfit- ja vahvin-kilpailuille
- [ ] **Muut ulkomaiset eliittitason kisat** - Muista lähteistä löytyvät eliittitason toiminnallisen urheilun kisat
- [ ] **API-endpointtien tutkiminen** - Reppi.fi API:n reverse engineering
- [ ] **Playwright-optimointi** - Oikea odotusaika Angular-latautumiselle
- [ ] **Error recovery parannukset** - Automaattinen retry virhetilanteissa

### Keskiprioriteetti
- [x] ~~**Uusia suomalaisia kisoja**~~ - Lisää fallback-listaan tunnettuja kisoja
- [x] ~~**Wodapalooza & Rogue Invitational**~~ - Lisätty 2026 kisat
- [x] ~~**World Fitness Project (WFP)**~~ - Tour Stopit ja Finals lisätty
- [ ] **Kalenterimerkintöjen päivitys** - Päivitä olemassa olevat tapahtumat

### Matala prioriteetti
- [ ] **Web-UI** - Yksinkertainen web-käyttöliittymä
- [ ] **Tilastot** - Kilpailuiden analytiikka
- [ ] **Mobile app** - React Native app

---

## 🐛 Tunnetut bugit

### Aktiiviset
- [ ] **Timeout-ongelma** - Search-job joskus timeout (ratkaisu: nostettu 600s)

### Korjatut
- [x] **Import-virhe** - Python path korjattu cron_runner.py:ssä
- [x] **ModuleNotFoundError** - PYTHONPATH lisätty subprocess-kutsuihin
- [x] **Duplikaattibugi** - Parempi deduplikointi calendar_sync.py:ssä ja scraper.py:ssä (2026-03-22)

---

## 💡 Ideat

- Integraatio muihin kalenteripalveluihin (Outlook, Apple Calendar)
- Discord-bot kilpailuilmoituksiin
- SMS-notifikaatiot tärkeistä kisoista
- Kilpailuiden vertailu ja ranking

---

**Viimeisin valmis:** Katso [DONE.md](DONE.md)
