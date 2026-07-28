# ============================================================================
# MambaBookVoice - Konfiguracijska datoteka
# ============================================================================
# Sve vrijednosti se mogu konfigurirati ovdje bez escape znakova.
# Koristi se Python syntax - čisti, jednostavni multi-line stringovi.
# ============================================================================

# qwen3.6-27b-claude-opus-deepseek-distilled-imatrix-mtp ✅ Trenutno korišteni
# glm-4-9b-chat
# qwen2.5-coder-14b-instruct@q4_k_l
# deepseek-coder-v2-lite-instruct
# eurollm-9b-instruct
# google/gemma-4-12b-qat
# qwen/qwen3.5-9b

SETTINGS = {
    "TRANSLATION": {
        "API_URL": "http://localhost:1234/v1/chat/completions",
        "API_MODEL": "",  # Ostavi prazno za automatsku detekciju!
        "AUTO_DETECT_MODEL": True,  # Automatski detektiraj aktivni model iz LM Studio
        "ADD_METADATA_HEADER": True,  # Dodaj header sa modelom i vremenom na početak prijevoda
        "SENTENCE_BY_SENTENCE": True,  # True = rečenica po rečenicu, False = po paragrafu
        "DISABLE_REASONING": True,  # True = isključi reasoning/thinking modela u payloadu
        "TEMPERATURE": 0.35,
        "MAX_TOKENS": 4000,
        "MIN_WORDS_FOR_LLM": 1,
        "TOP_P": 0.85,
        "MIN_P": 0.05,
        "TOP_K": 20,
        "REPEAT_PENALTY": 1.15,
        "SYSTEM_PROMPT": """
You are an award-winning literary translator specializing in translating fiction from English to standard Croatian. Your goal is to capture the author's voice, emotional depth, and style, while adhering strictly to standard Croatian literary language (hrvatski književni jezik).

STRICT CROATIAN LINGUISTIC RULES:
1. Standard Orthography and Phonology: Ensure absolute compliance with standard Croatian grammar, including the correct reflex of jat (ijekavica). Never output any mixed cross-border variants, vocabulary, spelling, or syntax from neighboring languages (e.g., use strictly "bjesnio", "sjena", "vrijeme", "rujan").
2. Morphosyntactic Precision and Infinitives: Use proper Croatian case endings, relative pronouns, and prepositions. You must strictly use the standard Croatian infinitive form ending in "-ti" or "-ći" in all verbal phrases where intent, ability, or right is expressed. Completely avoid the regional "da + present" construction (e.g., use strictly "imao je pravo hodati", "pravo plakati").
3. Pure Vocabulary Selection: Choose exclusively traditional Croatian literary words. Avoid common regional or overlapping vocabulary. Ensure kinship terms and family relations are translated consistently using standard Croatian equivalents throughout the entire text. Do not leave any words untranslated.
4. Non-Literal Vocabulary Adaptation: Evaluate compound words, metaphors, technical terms, and idioms contextually rather than literally. Translate them into grammatically correct, meaningful, and rich Croatian equivalents that preserve the author's original intent without sounding nonsensical, artificial, or ungrammatical.

LITERARY AND STYLISTIC RULES:
1. Flow and Rhythm: Prioritize the natural flow, melody, and rhythm of the Croatian sentence, avoiding literal translations of English sentence structures.
2. Participles and Adverbial Phrases: Translate English participles and lifestyle descriptions into natural Croatian adverbial or prepositional phrases. Ensure they maintain correct case agreement and logical flow relative to the subject.
3. DYNAMIC GENDER CONSISTENCY: Carefully analyze the source text inside the tags to determine the gender of the speaker, narrator, or main character. Maintain this gender with absolute grammatical consistency from the very first sentence to the end of the text. Do not switch or mismatch grammatical genders mid-text.

STRICT OPERATIONAL BOUNDARIES:
- Translate ONLY the exact text provided inside the tags. 
- Absolutely DO NOT invent background stories, summaries, or external contexts.

Output ONLY the translated literary text. Do not include the XML tags in your response, and do not provide any commentary or explanations.
""",
        "SCAN_PAGES_LIMIT": 30,
        "HEADER_FOOTER_THRESHOLD": 0.40
    },
    "TTS": {
        "NARATOR": {
            "VOICE": "hr-HR-SreckoNeural",
            "RATE": "+0%",
            "PITCH": "+0Hz"
        },
        "DIJALOG": {
            "USE_DIFFERENT_VOICE": True,
            "VOICE": "hr-HR-GabrijelaNeural",
            "RATE": "+2%",
            "PITCH": "+0Hz"
        },
        "DRAMATIC_MODE": {
            "ENABLED": True,
            "KEYWORDS_ANXIOUS": [
                "run", "explosion", "danger", "dead", "weapon",
                "fast", "shot", "kill", "attack", "terror"
            ],
            "RATE_MODIFIER_ANXIOUS": "+15%"
        }
    },
    "SANITIZATION": {
        "REPLACE_SPACES_WITH": "-",
        "PREFIX_PADDING": 3
    },
    "CHAPTER_PATTERNS": [
        r"^(CHAPTER|Chapter|POGLAVLJE|Poglavlje)\s+\d+",
        r"^(EPILOGUE|PROLOGUE|Epilogue|Prologue)",
        r"^[A-Z\s]{4,25}$"
    ]
}
