import os
import shutil

# Putanja do mape s datotekama (točka označava trenutnu mapu)
putanja = "."

# Popis svih datoteka u mapi
za_obradu = os.listdir(putanja)

for datoteka in za_obradu:
    # Obrađujemo samo .txt datoteke i preskačemo samu skriptu
    if datoteka.endswith(".txt") and os.path.isfile(os.path.join(putanja, datoteka)):
        # Odvajamo naziv datoteke od ekstenzije
        ime_mape, _ = os.path.splitext(datoteka)
        
        # Kreiramo punu putanju za novu mapu
        nova_mapa = os.path.join(putanja, ime_mape)
        
        # Kreiramo mapu ako već ne postoji
        os.makedirs(nova_mapa, exist_ok=True)
        
        # Definiramo staru i novu putanju datoteke
        stara_putanja_datoteke = os.path.join(putanja, datoteka)
        nova_putanja_datoteke = os.path.join(nova_mapa, datoteka)
        
        # Premještamo datoteku u novu mapu
        shutil.move(stara_putanja_datoteke, nova_putanja_datoteke)
        print(f"Premješteno: {datoteka} -> {ime_mape}/")
