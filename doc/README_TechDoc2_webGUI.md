# TEHNIČKA DOKUMENTACIJA: RAZVOJ WEB GUI MODULA (FAZA 1)
Ovaj dokument sadrži arhitekturni plan i specifikaciju za uvođenje prezentacijskog web sloja u projekt, uz zadržavanje postojeće CLI pozadinske logike kao neovisnog modula. 
---## 1. HITNA NADOGRADNJA GLAVNOG CLI IZBORNIKAPrije podizanja web poslužitelja, struktura Glavnog izbornika u terminalu mora se modificirati kako bi omogućila ručno pokretanje Web sučelja. Opcija `5` se prenamjenjuje, a Izlaz se seli na unificiranu tipku `X`.
### Novi izgled Glavnog izbornika:

╔════════════════════════════════════════════════════════════════╗
║ GLAVNI IZBORNIK — MAMBABOOKVOICE v4.5 ║
╠════════════════════════════════════════════════════════════════╣
║ [1] Konverzija dokumenata (PDF/DOCX/EPUB/MOBI → TXT/MD) ║
║ [2] Obrada i čišćenje tekstualnih datoteka ([fixed] priprema) ║
║ [3] Prevođenje obrađenog teksta preko lokalnog LLM-a ║
║ [4] Pretvaranje prevedenih datoteka u MP3 audio knjigu ║
║ [5] Pokreni web GUI poslužitelj (FastAPI) ║
╠════════════════════════════════════════════════════════════════╣
║ [X] Izlaz iz aplikacije (uz dvostruku provjeru Y/N) ║
╚════════════════════════════════════════════════════════════════╝


*Logika opcije 5:* Odabirom broja 5, skripta u pozadini inicijalizira FastAPI server na portu `http://localhost:8000`, automatski otvara zadani web preglednik na toj adresi i drži terminal otvorenim za ispis serverskih logova u realnom vremenu.

---

## 2. ARHITEKTURA DIREKTORIJA (STRUKTURA MAPA)
U korijenu projekta kreira se novi direktorij `public/` koji preuzima ulogu statičkog i prezentacijskog sloja (Multi-page arhitektura).


MambaBookVoice/
├── app/ # Postojeća Python logika (Obrada, LLM, TTS)
├── config/ # Postojeći konfiguracijski profili (.json)
├── work/ # Radni direktoriji (ulaz, izlaz, output)
│
├── web_server.py # NOVO: FastAPI server (rute i API endpointi)
└── public/ # NOVO: Web GUI prezentacijski direktorij
├── css/
│ └── tailwind.css # Konfigurirani Tailwind CSS izlaz
├── js/
│ ├── main.js # Globalna JS logika, WebSocket klijent i logovi
│ ├── konverzija.js # Izolirana logika za Korak 1
│ ├── ciscenje.js # Izolirana logika za Korak 2
│ ├── prevod.js # Izolirana logika za Korak 3
│ └── mp3.js # Izolirana logika za Korak 4
│
├── index.html # Glavni Dashboard (Izbornik i status sustava)
├── konverzija.html # Stranica za Korak 1
├── ciscenje.html # Stranica za Korak 2
├── prevod.html # Stranica za Korak 3
└── mp3.html # Stranica za Korak 4


---

## 3. SPECIFIKACIJA WEB STRANICA (MULTI-PAGE VIEW)

Sve HTML stranice uvoze **Tailwind CSS** lokalno te imaju unificiranu tamnu SF estetiku (Dark Mode).

### index.html (Glavna nadzorna ploča)
*   **Sadržaj:** Centralni navigacijski panel s velikim, responzivnim karticama (Cards) za svaku od 4 akcije.
*   **Statusni widgeti:** Prikaz trenutnog opterećenja sustava, status veze s LM Studiom (Zeleno/Crveno) i popis aktivnih checkpointa za prevođenje s postotkom napretka (npr. *Asimov - 26.29%*).

### konverzija.html (Korak 1)
*   **Sadržaj:** Tablica s popisom sirovih datoteka iz ulazne mape. Tablica ima ugrađeno JS sortiranje klikom na stupce (Ime, Datum izmjene, Veličina).
*   **Kontrole:** Kvačice (Checkboxes) za višestruki odabir datoteka, radio gumbi za odabir formata (`.txt` ili `.md`) i gumb "Pokreni konverziju".

### ciscenje.html (Korak 2)
*   **Sadržaj:** Popis datoteka iz izlazne mape spremnih za uklanjanje tehničkog šuma. **Rigorozno pravilo:** JavaScript mora ispisati sve datoteke, uključujući i one s inkrementalnim sufiksima (`_001.txt`, `_002.txt`).
*   **Kontrole:** Gumb "Očisti i fiksiraj" koji nakon klika poziva pozadinski Python regex filter i u tablici odmah osvježava status, stvarajući `[fixed]` datoteku.

### prevod.html (Korak 3)
*   **Sadržaj:** Dropdown izbornik s popisom isključivo `[fixed]` datoteka.
*   **Forma s opcijama:** Prekrasne visualne kontrole umjesto terminalskih podizbornika:
    *   *Slajder (Slider):* Broj odlomaka za test (1 - 100).
    *   *Prekidač (Toggle):* Payload Header (ON/OFF).
    *   *Dropdown:* Granularnost (Odlomak, Paragraf, Rečenica) i Izbor konfiguracijskog profila knjige.
*   Sve promjene na ovim kontrolama JavaScript odmah asinkrono šalje na backend koji ih zapisuje u `config.json`.

### mp3.html (Korak 4)
*   **Sadržaj:** Popis gotovih prijevoda iz output mape. Klikom na gumb pokreće se TTS sinteza. Backend na ovoj ruti automatski izvršava provjeru postojanja direktorija i duplicira mapu s oznakom `_001` ako je raniji audio već generiran.

---

## 4. ASINKRONI LIVE LOG PROZOR (WEBSOCKET INTEGRACIJA)
Na dnu svake od 5 HTML stranica (ili unutar unificiranog layout podnožja) nalazi se fiksni, crni terminalski prozor (`<div id="live-console">`).

*   **Tehnologija:** JavaScript otvara stalnu WebSocket vezu prema FastAPI poslužitelju (`ws://localhost:8000/stream-logs`).
*   **Funkcionalnost:** Kada god pozadinska Python klasa odradi neku radnju (prevede odlomak, spoji rečenicu, generira MP3 dio), ta se linija u istoj sekundi "gura" kroz WebSocket i ispisuje unutar web konzole zelenim tekstom. Korisnik ima potpuni uvid u rad Qwena 3.6 uživo na web stranici bez potrebe za gledanjem u terminal.

---

## 5. PLAN IMPLEMENTACIJE ZA CLINE-A
Prilikom prosljeđivanja ovog zadatka, od Clinea će se zahtijevati da:
1.  Ažurira glavni CLI izbornik u postojećoj Python datoteci i doda opciju 5.
2.  Inicijalizira `web_server.py` koristeći FastAPI framework i postavi statičke rute prema `public/` mapi.
3.  Stvori čiste HTML stranice s ugrađenim Tailwind klasama i izoliranim JS datotekama za asinkrone `fetch` zahtjeve.

