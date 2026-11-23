"""Canned answers for offline test runs (models.provider: mock)."""
import itertools

_fc_calls = itertools.count()
_topic_seq = itertools.count()

SCENES = [
    ("क्या आपको पता है कि आपका दिमाग हर रात खुद को साफ़ करता है?", "Kya aapko pata hai ki aapka dimaag har raat khud ko saaf karta hai?", "brain neurons glowing", "BRAIN CLEANING"),
    ("इसे glymphatic system कहते हैं, और ये गहरी नींद में सबसे ज़्यादा active होता है।", "Ise glymphatic system kehte hain, aur ye gehri neend mein sabse zyada active hota hai.", "person sleeping night", "DEEP SLEEP"),
    ("नींद के दौरान दिमाग का fluid तेज़ी से बहता है और waste बाहर निकालता है।", "Neend ke dauraan dimaag ka fluid tezi se behta hai aur waste bahar nikaalta hai.", "water flowing slow motion", ""),
    ("Scientists अभी भी study कर रहे हैं कि ये इंसानों में कितना असर करता है।", "Scientists abhi bhi study kar rahe hain ki ye insaanon mein kitna asar karta hai.", "science laboratory research", "STILL RESEARCHED"),
    ("तो अगली बार देर रात scroll करने से पहले सोचिए, आपका दिमाग सफ़ाई का इंतज़ार कर रहा है।", "Toh agli baar der raat scroll karne se pehle sochiye, aapka dimaag safaai ka intezaar kar raha hai.", "phone screen dark room", "SO SLEEP!"),
]


SKIT = [
    ("Narrator", "narrator", "जब मम्मी कहती हैं, बस पाँच मिनट में खाना तैयार है।", "Jab mummy kehti hain, bas paanch minute mein khana taiyaar hai.", "indian kitchen cooking"),
    ("Rohan", "male", "मम्मी, पाँच मिनट हो गए, खाना कहाँ है?", "Mummy, paanch minute ho gaye, khana kahan hai?", "young man hungry waiting"),
    ("Mummy", "female", "अभी तो सब्ज़ी काटनी शुरू की है बेटा, थोड़ा सब्र रखो।", "Abhi toh sabzi kaatni shuru ki hai beta, thoda sabr rakho.", "chopping vegetables"),
    ("Rohan", "male", "मम्मी, आपका पाँच मिनट और Google का पाँच मिनट अलग है क्या?", "Mummy, aapka paanch minute aur Google ka paanch minute alag hai kya?", "man looking at phone clock"),
    ("Mummy", "female", "Google खाना बनाता है क्या? चलो प्लेट लगाओ, एक घंटे में मिल जाएगा।", "Google khana banata hai kya? Chalo plate lagao, ek ghante mein mil jayega.", "family dinner table"),
]


def mock_answer(task, prompt):
    if task.startswith("panel_"):
        return {"reviews": [{"id": "W31", "name": "Hook Writer", "score": 7, "fixes": ["Make line 1 punchier"]}],
                "top_fixes": ["Make line 1 punchier", "Cut scene 4 by 3 words"], "panel_score": 7.0 if "PANEL:" not in prompt else 8.2}
    if task == "plan":
        return {"page_positioning": "Raaz aur hasi - mysteries by day, desi laughs by night", "brand_voice": "warm, curious",
                "series": [{"name": "Raaz Ki Raat", "format": "story", "premise": "true mysteries", "recurring_elements": ["cold open"], "episode_ideas": ["x"]},
                           {"name": "Ghar Ke Kisse", "format": "skit", "premise": "family humour", "recurring_elements": ["Mummy vs Rohan"], "episode_ideas": ["y"]}],
                "recurring_characters": [{"name": "Rohan", "voice": "male", "personality": "lazy but smart", "catchphrase": "Bas ho gaya!"},
                                         {"name": "Mummy", "voice": "female", "personality": "always one step ahead", "catchphrase": "Sab pata hai"}],
                "weekly_calendar": [], "community_rituals": ["Guess the ending"], "visual_identity": {}, "monetisation_path": "YPP"}
    if task == "creator_study":
        return {"hook_patterns": ["Cold open with the strangest detail"], "title_patterns": ["Question + number"],
                "ideal_length_sec": {"story": 50, "skit": 35}, "structure_patterns": [], "posting_cadence": "daily",
                "series_formats": [], "what_audiences_love": [], "by_format": {"story": [], "skit": []}, "avoid": ["copying"],
                "adapt_for_us": ["Start every story with the strangest detail"], "evidence_strength": "weak"}
    if task == "trend":
        base = next(_topic_seq) * 10
        return {"topics": [{"topic": f"Mock topic {base + i}: brain cleans itself at night", "angle": "sleep as brain maintenance",
                            "niche": "psychology", "why_now": "mock", "demand": 9 - i % 4, "originality": 7,
                            "relevance": 8, "competition_gap": 6, "evergreen": 9, "sourceability": 9} for i in range(10)]}
    if task == "research":
        return {"summary": "Mock research summary.", "sufficient": True, "uncertainties": ["Human evidence still developing"],
                "do_not_say": ["Sleep cures dementia"],
                "key_facts": [{"claim": "The glymphatic system clears waste from the brain", "source_url": "https://example.org/a",
                               "source_title": "Mock A", "published": "2013", "confidence": "high"},
                              {"claim": "Clearance increases during sleep in mice", "source_url": "https://example.org/b",
                               "source_title": "Mock B", "published": "2013", "confidence": "high"}]}
    if task == "script" and "Comedy Writers' Room" in prompt:
        return {"working_title": "Mummy ka 5 minute", "hook": SKIT[0][2],
                "characters": [{"name": "Rohan", "voice": "male", "personality": "hungry"}, {"name": "Mummy", "voice": "female", "personality": "smart"}],
                "scenes": [{"n": i + 1, "speaker": sp, "voice": v, "narration": n, "caption": c, "visual_query": q,
                            "veo_prompt": f"Cinematic vertical: {q}", "shot": "close-up, kitchen", "on_screen_text": ""}
                           for i, (sp, v, n, c, q) in enumerate(SKIT)],
                "ending": SKIT[-1][2], "est_duration_sec": 38, "claims_used": []}
    if task == "script":
        return {"working_title": "Aapka dimaag raat ko kya karta hai?", "hook": SCENES[0][0],
                "scenes": [{"n": i + 1, "narration": n, "caption": c, "visual_query": q,
                            "veo_prompt": f"Cinematic vertical shot: {q}, moody lighting", "on_screen_text": t}
                           for i, (n, c, q, t) in enumerate(SCENES)],
                "ending": SCENES[-1][0], "est_duration_sec": 42, "claims_used": ["glymphatic system clears waste"]}
    if task == "fact_check":
        k = next(_fc_calls)
        if k == 0:
            return {"verdict": "revise", "notes": "mock: first pass asks for a hedge",
                    "claims": [{"scene": 3, "claim": "fluid flows faster", "status": "misleading", "evidence_url": "",
                                "fix": "Say this was observed in mice"}]}
        return {"verdict": "pass", "notes": "mock pass", "claims": [{"scene": 2, "claim": "glymphatic", "status": "supported",
                                                                       "evidence_url": "https://example.org/a", "fix": ""}]}
    if task == "distribution":
        return {"youtube": {"title": "Aapka dimaag raat ko khud ko saaf karta hai? #shorts",
                            "description": "Neend ka asli kaam.\nSources:\nhttps://example.org/a\n#brain #sleep",
                            "tags": ["brain", "sleep", "hindi"]},
                "instagram": {"caption": "Raat ko dimaag kya karta hai? 🧠\n#brain #sleep #hindi"},
                "thumbnail_text": "BRAIN CLEANS ITSELF", "pinned_comment": "Aap raat ko kitne baje sote ho?",
                "synthetic_disclosure": False, "disclosure_reason": "stock footage only"}
    if task == "qc_editorial":
        ids = ["hook_honest", "original", "claims_supported", "metadata_accurate", "visual_fit", "disclosure", "pacing"]
        return {"checks": [{"id": i, "pass": True, "owner": "script", "correction": ""} for i in ids], "overall_notes": "mock ok"}
    if task == "analytics":
        return {"top_subjects": ["sleep science"], "what_worked": ["mock"], "what_failed": [],
                "experiments_next_week": ["test question hooks"], "guidance_for_next_topics": "Prefer body/brain science."}
    return {}
