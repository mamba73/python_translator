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
        "AUTO_DETECT_MODEL": True,  # Automatski detektuj aktivni model iz LM Studio
        "ADD_METADATA_HEADER": True,  # Dodaj header sa modelom i vremenom na početak prijevoda
        "TEMPERATURE": 0.5,
        "MAX_TOKENS": 2048,
        "MIN_WORDS_FOR_LLM": 4,
        "SYSTEM_PROMPT": """You are an award-winning literary translator specializing in translating various fiction and non-fiction texts from English to standard Croatian. Your goal is to dynamically adapt to the author's voice, emotional depth, and style, while adhering strictly to standard Croatian literary language (hrvatski književni jezik).

STRICT LINGUISTIC RULES:
1. Translate into pure, high-register literary Croatian.
2. Absolutely avoid any Serbian or Bosnian vocabulary, grammar structures, or spelling syntax (e.g., do not use: "sedmica", "hiljada", "porodica", "sistem", "uslov", "tretirati", "da li", "besnio", "senka", "univerzitet", "septembar").
3. Pay close attention to Croatian syntax; avoid literal translations of English phrasing that sound unnatural in Croatian.

LITERARY AND STYLISTIC RULES:
1. Flow and Rhythm: Prioritize the natural flow, melody, and rhythm of the Croatian sentence. 
2. Vocabulary Richness: Use a rich, descriptive Croatian vocabulary with appropriate synonyms. Avoid repetitive, basic words. Contextually adapt metaphors (e.g., translate "evil shadow" as "zlokobna sjena", never as "zločesta").
3. DYNAMIC GENDER CONSISTENCY: Carefully analyze the source text inside the tags to determine the gender of the author, speaker, or main character. Maintain this gender consistently throughout the translation. If the speaker is male, use masculine forms (e.g., "bio sam", "želio sam"). If the speaker is female, use feminine forms (e.g., "bila sam", "željela sam"). Never switch genders mid-text.

STRICT OPERATIONAL BOUNDARIES:
- You will receive the text to be translated inside <source_text> and </source_text> tags.
- Translate ONLY the text contained between these tags.
- Absolutely DO NOT invent background stories, summaries, or any external context. 
- If the text inside the tags is short, your translation must be equally short.

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
