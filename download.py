import os
import subprocess
import sys
from huggingface_hub import HfApi

# ==============================================================================
# KONFIGURACIJSKI DIO (Zadane / Fallback vrijednosti ako samo stisneš Enter)
# ==============================================================================
DEFAULT_MODEL_ID = "bartowski/gemma-4-12B-it-GGUF"
DEFAULT_QUANT = "Q4_K_M"
BASE_DIR = "g:\\LLMs\\LMStudio\\models"  # Tvoj osnovni direktorij za LM Studio
# ==============================================================================


def dohvati_korisnicki_unos():
    print("-" * 60)
    print("      HUGGING FACE GGUF AUTOMATSKI DOWNLOADER ZA LM STUDIO")
    print("-" * 60)

    # 1. Unos za Model ID
    model_id_input = input(
        f"1. Upisite/Zalijepite MODEL ID\n   [Pritisnite Enter za zadano: {DEFAULT_MODEL_ID}]: "
    ).strip()
    model_id = model_id_input if model_id_input else DEFAULT_MODEL_ID

    # 2. Unos za Kvantizaciju
    quant_input = input(
        f"\n2. Upisite zeljenu kvantizaciju (npr. Q4_K_M, Q6_K, Q8_0, IQ4_XS)\n   [Pritisnite Enter za zadano: {DEFAULT_QUANT}]: "
    ).strip()
    quant = quant_input if quant_input else DEFAULT_QUANT

    return model_id, quant


def pokreni_automatsko_preuzimanje():
    # Dohvaćanje interaktivnog unosa od korisnika
    model_id, quant = dohvati_korisnicki_unos()

    # Priprema i čišćenje putanja
    clean_model_id = model_id.strip("/")
    if "/" not in clean_model_id:
        print(
            "\n[GREŠKA] Neispravan Model ID format. Mora sadržavati autora i repozitorij (npr. autor/ime-modela)."
        )
        return

    autor, ime_repozitorija = clean_model_id.split("/")
    odredisni_dir = os.path.join(BASE_DIR, autor, ime_repozitorija)

    print(
        f"\n[1/3] Povezivanje s Hugging Face repozitorijem: {clean_model_id}..."
    )

    # Pretraživanje repozitorija za točan naziv datoteke (ignorirajući velika/mala slova)
    api = HfApi()
    try:
        datoteke_u_repu = api.list_repo_files(repo_id=clean_model_id)
    except Exception as e:
        print(f"\n[GREŠKA] Nemoguće pristupiti repozitoriju '{clean_model_id}'.")
        print(f"Detalji: {e}")
        return

    točan_naziv_datoteke = None
    trazena_kvantizacija = quant.lower().strip()

    # Tražimo datoteku koja završava na .gguf i sadrži našu kvantizaciju
    for datoteka in datoteke_u_repu:
        if datoteka.endswith(".gguf") and trazena_kvantizacija in datoteka.lower():
            točan_naziv_datoteke = datoteka
            break

    if not točan_naziv_datoteke:
        print(
            f"\n[GREŠKA] U repozitoriju nije pronađena GGUF datoteka s oznakom '{quant}'."
        )
        print("Dostupne GGUF datoteke u ovom repozitoriju su:")
        for f in datoteke_u_repu:
            if f.endswith(".gguf"):
                print(f" - {f}")
        return

    print(f"[2/3] Pronađena točna datoteka na poslužitelju: {točan_naziv_datoteke}")
    print(f"      Lokacija na G: disku: {odredisni_dir}")

    # Sastavljanje i pokretanje nove 'hf' naredbe kroz sustav
    naredba = [
        "hf",
        "download",
        clean_model_id,
        točan_naziv_datoteke,
        "--local-dir",
        odredisni_dir,
    ]

    print("\n[3/3] Pokretanje preuzimanja preko 'hf' alata...\n")
    print("-" * 60)

    try:
        # Pokrećemo proces i preusmjeravamo ispis izravno u tvoj terminal da vidiš postotke
        rezultat = subprocess.run(naredba, check=True)
        if resultado := rezultat.returncode == 0:
            print("-" * 60)
            print("[USPJEH] Preuzimanje završeno bez grešaka!")
            print(
                f"Model je spreman za rad u LM Studiju unutar mape: {autor}"
            )
            print("-" * 60)
    except FileNotFoundError:
        print(
            "\n[GREŠKA] Naredba 'hf' nije pronađena u sustavu. Provjeri je li ispravno instalirana."
        )
    except subprocess.CalledProcessError as e:
        print(f"\n[GREŠKA] Preuzimanje je prekinuto ili je došlo do mrežne pogreške.")
        print(f"Izlazni kod greške: {e.returncode}")


if __name__ == "__main__":
    # Automatska provjera i instalacija 'huggingface_hub' paketa ako nedostaje u Pythonu
    try:
        import huggingface_hub
    except ImportError:
        print("Instaliranje potrebnih Python paketa za API komunikaciju...")
        subprocess.run([sys.executable, "-m", "pip", "install", "huggingface_hub"])

    pokreni_automatsko_preuzimanje()
