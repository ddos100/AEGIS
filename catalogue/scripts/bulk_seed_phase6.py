"""
Phase 6 catalogue expansion — bulk-generates additional AI service YAML entries.

Run once: `python catalogue/scripts/bulk_seed_phase6.py` (idempotent, only writes
files that do not already exist). This script is excluded from runtime; it is a
one-shot generator kept in the repo for reproducibility.
"""
from __future__ import annotations
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1] / "services"
TODAY = "2026-05-15"
VER = "1.0.0"


def write(provider: str, slug: str, body: dict) -> None:
    pdir = ROOT / provider
    pdir.mkdir(parents=True, exist_ok=True)
    target = pdir / f"{slug}.yaml"
    if target.exists():
        return
    lines = []
    for k, v in body.items():
        if isinstance(v, bool):
            lines.append(f"{k}: {'true' if v else 'false'}")
        elif isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            elif isinstance(v[0], str) and all(" " not in x and ":" not in x for x in v):
                lines.append(f"{k}: [{', '.join(v)}]")
            else:
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for kk, vv in v.items():
                lines.append(f"  {kk}: {vv}")
        elif isinstance(v, int):
            lines.append(f"{k}: {v}")
        else:
            sv = str(v)
            if any(c in sv for c in [":", "#", "'", '"']) or sv.startswith(" "):
                sv = '"' + sv.replace('"', '\\"') + '"'
            lines.append(f"{k}: {sv}")
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def entry(eid, name, provider, category, *, subcategory=None, desc=None, website=None,
          api=None, domains=None, hq="US", gdpr=True, eu="limited_risk",
          caps=None, ins=None, outs=None, sens="medium", cap_lvl="medium", trust=70,
          tags=None) -> dict:
    body = {
        "id": eid,
        "name": name,
        "provider_slug": provider,
        "category": category,
    }
    if subcategory: body["subcategory"] = subcategory
    if desc: body["description"] = desc
    if website: body["website"] = website
    if api: body["api_endpoint_patterns"] = api
    if domains: body["browser_domains"] = domains
    body["hq_country"] = hq
    body["gdpr_applicable"] = gdpr
    body["eu_ai_act_category"] = eu
    if caps: body["capabilities"] = caps
    if ins: body["input_data_types"] = ins
    if outs: body["output_data_types"] = outs
    body["default_risk_indicators"] = {
        "data_sensitivity_hint": sens,
        "capability_level": cap_lvl,
        "provider_trust_score": trust,
    }
    if tags: body["tags"] = tags
    body["catalogue_version"] = VER
    body["last_updated"] = TODAY
    return body


ENTRIES = [
    # --- Writing / productivity / browser AI assistants ---
    ("grammarly", "grammarly-go", entry(
        "grammarly-go", "Grammarly Go", "grammarly", "llm",
        subcategory="writing_assistant",
        desc="AI writing assistant integrated into desktop apps, browser, and Office.",
        website="https://www.grammarly.com/business",
        api=["api.grammarly.com/v1", "capi.grammarly.com"],
        domains=["app.grammarly.com", "grammarly.com"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=74,
        tags=["writing_assistant", "browser_extension", "saas_embedded"])),
    ("grammarly", "grammarly-extension", entry(
        "grammarly-extension", "Grammarly Browser Extension", "grammarly", "browser_extension",
        desc="Browser extension that injects AI writing assistance into any web text field.",
        domains=["grammarly.com"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=74,
        tags=["browser_extension", "writing_assistant", "grammarly"])),
    ("monica", "monica-ai", entry(
        "monica-ai", "Monica AI", "monica", "browser_extension",
        desc="All-in-one AI copilot browser extension proxying GPT/Claude/Gemini.",
        domains=["monica.im"],
        caps=["text_generation", "summarization", "code_generation"],
        ins=["text", "image"], outs=["text"],
        sens="high", cap_lvl="high", trust=45,
        tags=["browser_extension", "ai_copilot", "shadow_ai_risk"])),
    ("merlin", "merlin-ai", entry(
        "merlin-ai", "Merlin AI", "merlin", "browser_extension",
        desc="Chrome extension giving GPT-4/Claude access on any webpage.",
        domains=["getmerlin.in"], hq="IN",
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="high", trust=42,
        tags=["browser_extension", "indian_vendor", "shadow_ai_risk"])),
    ("sider", "sider-ai", entry(
        "sider-ai", "Sider AI", "sider", "browser_extension",
        desc="Sidebar AI assistant browser extension; multi-model.",
        domains=["sider.ai"],
        caps=["text_generation", "summarization"], ins=["text", "image"], outs=["text"],
        sens="high", cap_lvl="high", trust=40,
        tags=["browser_extension", "shadow_ai_risk"])),
    ("maxai", "maxai-extension", entry(
        "maxai-extension", "MaxAI.me", "maxai", "browser_extension",
        desc="Multi-model browser AI extension with quick reply and rewrite.",
        domains=["maxai.me"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=38,
        tags=["browser_extension", "shadow_ai_risk"])),
    ("harpa", "harpa-ai", entry(
        "harpa-ai", "HARPA AI", "harpa", "browser_extension",
        desc="AI automation + web monitoring browser extension.",
        domains=["harpa.ai"],
        caps=["text_generation", "browser_automation", "summarization"],
        ins=["text"], outs=["text"],
        sens="high", cap_lvl="high", trust=35,
        tags=["browser_extension", "automation", "shadow_ai_risk"])),
    ("wiseone", "wiseone-extension", entry(
        "wiseone-extension", "Wiseone", "wiseone", "browser_extension",
        desc="Reading-companion AI extension that summarises and cross-references articles.",
        domains=["wiseone.io"], hq="FR",
        caps=["summarization", "text_generation"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=58,
        tags=["browser_extension", "research"])),
    ("glasp", "glasp-ai", entry(
        "glasp-ai", "Glasp AI", "glasp", "browser_extension",
        desc="Social web highlighter with AI summarisation extension.",
        domains=["glasp.co"], hq="JP",
        caps=["summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=55,
        tags=["browser_extension", "summarization"])),

    # --- Search / research engines ---
    ("you-com", "you-search", entry(
        "you-search", "You.com", "you-com", "search",
        desc="AI-first search engine with generative answers.",
        domains=["you.com"],
        api=["chat-api.you.com"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=60,
        tags=["search", "ai_search"])),
    ("phind", "phind-search", entry(
        "phind-search", "Phind", "phind", "search",
        subcategory="developer_search",
        desc="AI search engine for developers.",
        domains=["phind.com"],
        caps=["text_generation", "code_generation"], ins=["text"], outs=["text", "code"],
        sens="medium", cap_lvl="medium", trust=62,
        tags=["search", "developer"])),
    ("kagi", "kagi-search", entry(
        "kagi-search", "Kagi Search", "kagi", "search",
        desc="Paid premium search engine with AI Universal Summarizer + The Assistant.",
        domains=["kagi.com"],
        api=["kagi.com/api/v0"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=72,
        tags=["search", "premium_search"])),
    ("brave-leo", "brave-leo", entry(
        "brave-leo", "Brave Leo", "brave-leo", "browser_extension",
        desc="Built-in AI assistant inside the Brave browser.",
        domains=["brave.com"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=68,
        tags=["browser_assistant", "brave"])),
    ("duckduckgo-ai", "duckduckgo-ai-chat", entry(
        "duckduckgo-ai-chat", "DuckDuckGo AI Chat", "duckduckgo-ai", "llm",
        desc="Anonymous proxy chat against multiple model providers.",
        domains=["duck.ai", "duckduckgo.com"],
        caps=["text_generation"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=70,
        tags=["chat", "proxy_chat"])),
    ("opera-aria", "opera-aria", entry(
        "opera-aria", "Opera Aria", "opera-aria", "browser_extension",
        desc="Aria AI assistant built into Opera browser.",
        domains=["opera.com"], hq="NO",
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=64,
        tags=["browser_assistant", "opera"])),
    ("arc-browser", "arc-max", entry(
        "arc-max", "Arc Max", "arc-browser", "browser_extension",
        desc="AI features (Ask on Page, Tidy Tabs, 5-second Previews) bundled with Arc browser.",
        domains=["arc.net"],
        caps=["summarization", "text_generation"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=66,
        tags=["browser_assistant", "arc"])),

    # --- Research-paper AI ---
    ("scite", "scite-assistant", entry(
        "scite-assistant", "Scite Assistant", "scite", "search",
        desc="AI research assistant grounded in 1.2B+ citation statements.",
        domains=["scite.ai"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=70,
        tags=["research", "academic"])),
    ("consensus", "consensus-ai", entry(
        "consensus-ai", "Consensus AI", "consensus", "search",
        desc="Search engine extracting findings from peer-reviewed papers.",
        domains=["consensus.app"],
        caps=["summarization"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=72,
        tags=["research", "academic"])),
    ("elicit", "elicit-ai", entry(
        "elicit-ai", "Elicit", "elicit", "search",
        desc="AI research assistant for systematic literature reviews.",
        domains=["elicit.com"],
        caps=["summarization", "text_generation"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="medium", trust=70,
        tags=["research", "academic"])),

    # --- Meetings / transcription ---
    ("otter", "otter-ai", entry(
        "otter-ai", "Otter.ai", "otter", "speech",
        desc="AI meeting note-taker; joins Zoom/Meet/Teams.",
        domains=["otter.ai"],
        api=["api.otter.ai"],
        caps=["speech_to_text", "summarization"], ins=["audio"], outs=["text"],
        sens="high", cap_lvl="medium", trust=68,
        tags=["meeting_notes", "transcription"])),
    ("fathom", "fathom-ai", entry(
        "fathom-ai", "Fathom", "fathom", "speech",
        desc="Free AI meeting note-taker; auto-summaries.",
        domains=["fathom.video"],
        caps=["speech_to_text", "summarization"], ins=["audio"], outs=["text"],
        sens="high", cap_lvl="medium", trust=64,
        tags=["meeting_notes"])),
    ("fireflies", "fireflies-ai", entry(
        "fireflies-ai", "Fireflies.ai", "fireflies", "speech",
        desc="AI meeting assistant for Zoom/Meet/Teams with conversation analytics.",
        domains=["fireflies.ai"],
        api=["api.fireflies.ai"],
        caps=["speech_to_text", "summarization", "classification"], ins=["audio"], outs=["text"],
        sens="high", cap_lvl="medium", trust=66,
        tags=["meeting_notes"])),
    ("gong", "gong-revenue-ai", entry(
        "gong-revenue-ai", "Gong Revenue AI", "gong", "speech",
        desc="Revenue intelligence platform; captures and analyses customer calls.",
        domains=["gong.io"],
        api=["api.gong.io"],
        caps=["speech_to_text", "classification", "summarization"], ins=["audio"], outs=["text"],
        sens="critical", cap_lvl="high", trust=74,
        tags=["sales_intelligence", "call_recording"])),
    ("descript", "descript-ai", entry(
        "descript-ai", "Descript", "descript", "speech",
        desc="AI-powered audio/video editor with voice cloning (Overdub).",
        domains=["descript.com"],
        caps=["speech_to_text", "text_to_speech"], ins=["audio", "video"], outs=["audio", "video"],
        sens="high", cap_lvl="high", trust=66,
        tags=["audio_editing", "voice_cloning"])),
    ("assemblyai", "assemblyai", entry(
        "assemblyai", "AssemblyAI", "assemblyai", "speech",
        desc="Speech-to-text and audio-intelligence API.",
        api=["api.assemblyai.com"],
        caps=["speech_to_text", "classification", "summarization"], ins=["audio"], outs=["text"],
        sens="high", cap_lvl="medium", trust=70,
        tags=["speech_api"])),
    ("deepgram", "deepgram", entry(
        "deepgram", "Deepgram", "deepgram", "speech",
        desc="Real-time speech-to-text + text-to-speech API.",
        api=["api.deepgram.com"],
        caps=["speech_to_text", "text_to_speech"], ins=["audio"], outs=["text", "audio"],
        sens="high", cap_lvl="medium", trust=72,
        tags=["speech_api"])),
    ("rev", "rev-ai", entry(
        "rev-ai", "Rev AI", "rev", "speech",
        desc="Speech-to-text API (Rev).",
        api=["api.rev.ai"],
        caps=["speech_to_text"], ins=["audio"], outs=["text"],
        sens="high", cap_lvl="low", trust=68,
        tags=["speech_api"])),

    # --- Voice / TTS ---
    ("elevenlabs-voices", "elevenlabs-voicelab", entry(
        "elevenlabs-voicelab", "ElevenLabs Voice Lab", "elevenlabs-voices", "speech",
        desc="Voice cloning / TTS platform; supports instant + professional voice cloning.",
        domains=["elevenlabs.io"],
        api=["api.elevenlabs.io"],
        caps=["text_to_speech"], ins=["text", "audio"], outs=["audio"],
        sens="high", cap_lvl="high", trust=58,
        tags=["voice_cloning", "tts"])),
    ("d-id", "d-id-studio", entry(
        "d-id-studio", "D-ID Studio", "d-id", "video_gen",
        desc="AI avatar / talking-head video generation.",
        domains=["d-id.com", "studio.d-id.com"],
        api=["api.d-id.com"],
        caps=["video_generation", "text_to_speech"], ins=["text", "image"], outs=["video"],
        sens="high", cap_lvl="high", trust=52,
        tags=["avatar", "video_gen", "deepfake_risk"])),
    ("synthesia", "synthesia-studio", entry(
        "synthesia-studio", "Synthesia", "synthesia", "video_gen",
        desc="AI video creation platform with realistic AI avatars.",
        domains=["synthesia.io"], hq="GB",
        caps=["video_generation", "text_to_speech"], ins=["text"], outs=["video"],
        sens="high", cap_lvl="high", trust=68,
        tags=["video_gen", "avatar"])),
    ("heygen", "heygen-studio", entry(
        "heygen-studio", "HeyGen", "heygen", "video_gen",
        desc="AI spokesperson video generator with translation features.",
        domains=["heygen.com"],
        api=["api.heygen.com"],
        caps=["video_generation", "text_to_speech"], ins=["text", "image"], outs=["video"],
        sens="high", cap_lvl="high", trust=58,
        tags=["video_gen", "avatar"])),

    # --- Music / video / image gen ---
    ("suno", "suno-music", entry(
        "suno-music", "Suno", "suno", "other",
        subcategory="music_generation",
        desc="Generative music / song AI.",
        domains=["suno.com"],
        caps=[], ins=["text"], outs=["audio"],
        sens="low", cap_lvl="medium", trust=50,
        tags=["music_gen"])),
    ("udio", "udio-music", entry(
        "udio-music", "Udio", "udio", "other",
        subcategory="music_generation",
        desc="AI music generation platform.",
        domains=["udio.com"],
        caps=[], ins=["text"], outs=["audio"],
        sens="low", cap_lvl="medium", trust=48,
        tags=["music_gen"])),
    ("clipdrop", "clipdrop", entry(
        "clipdrop", "Clipdrop", "clipdrop", "image_gen",
        desc="Stability-owned image editing + generation suite.",
        domains=["clipdrop.co"],
        api=["clipdrop-api.co"],
        caps=["image_generation", "vision"], ins=["image", "text"], outs=["image"],
        sens="medium", cap_lvl="medium", trust=64,
        tags=["image_gen", "stability"])),
    ("leonardo", "leonardo-ai", entry(
        "leonardo-ai", "Leonardo.Ai", "leonardo", "image_gen",
        desc="Generative image platform for game assets and concept art.",
        domains=["leonardo.ai"],
        api=["cloud.leonardo.ai/api"],
        caps=["image_generation"], ins=["text", "image"], outs=["image"],
        sens="low", cap_lvl="medium", trust=58,
        tags=["image_gen", "creative"])),
    ("ideogram", "ideogram-ai", entry(
        "ideogram-ai", "Ideogram", "ideogram", "image_gen",
        desc="Image generation model strong at typography in images.",
        domains=["ideogram.ai"],
        caps=["image_generation"], ins=["text"], outs=["image"],
        sens="low", cap_lvl="medium", trust=58,
        tags=["image_gen"])),
    ("recraft", "recraft-ai", entry(
        "recraft-ai", "Recraft", "recraft", "image_gen",
        desc="Vector + raster generative image platform.",
        domains=["recraft.ai"],
        caps=["image_generation"], ins=["text"], outs=["image"],
        sens="low", cap_lvl="medium", trust=56,
        tags=["image_gen", "vector"])),
    ("krea", "krea-ai", entry(
        "krea-ai", "Krea AI", "krea", "image_gen",
        desc="Real-time generative image / video platform.",
        domains=["krea.ai"],
        caps=["image_generation", "video_generation"], ins=["text", "image"], outs=["image", "video"],
        sens="low", cap_lvl="medium", trust=56,
        tags=["image_gen", "real_time"])),
    ("playground-ai", "playground-ai-image", entry(
        "playground-ai-image", "Playground AI", "playground-ai", "image_gen",
        desc="Generative image platform.",
        domains=["playground.com"],
        caps=["image_generation"], ins=["text"], outs=["image"],
        sens="low", cap_lvl="medium", trust=54,
        tags=["image_gen"])),

    # --- Productivity SaaS embedded AI ---
    ("monday", "monday-ai", entry(
        "monday-ai", "monday.com AI", "monday", "agent",
        desc="Embedded AI assistant inside monday.com work-OS.",
        domains=["monday.com"],
        api=["api.monday.com/v2"],
        caps=["text_generation", "summarization", "classification"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=66,
        tags=["saas_embedded", "productivity"])),
    ("zendesk", "zendesk-ai", entry(
        "zendesk-ai", "Zendesk AI", "zendesk", "agent",
        desc="Zendesk Advanced AI for ticket triage, autoresponders, and agent copilots.",
        domains=["zendesk.com"],
        api=["api.zendesk.com"],
        caps=["text_generation", "classification", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=72,
        tags=["customer_support", "saas_embedded"])),
    ("intercom", "intercom-fin", entry(
        "intercom-fin", "Intercom Fin", "intercom", "agent",
        desc="GPT-powered customer-support AI bot from Intercom.",
        domains=["intercom.com"],
        api=["api.intercom.io"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=70,
        tags=["customer_support", "saas_embedded"])),
    ("figma", "figma-ai", entry(
        "figma-ai", "Figma AI", "figma", "agent",
        desc="Generative design features inside Figma (Make Designs, Visual Search).",
        domains=["figma.com"],
        api=["api.figma.com"],
        caps=["image_generation", "text_generation"], ins=["text", "image"], outs=["image"],
        sens="medium", cap_lvl="medium", trust=70,
        tags=["design", "saas_embedded"])),
    ("airtable", "airtable-ai", entry(
        "airtable-ai", "Airtable AI", "airtable", "agent",
        desc="Embedded AI fields, formulas, and agents in Airtable.",
        domains=["airtable.com"],
        api=["api.airtable.com"],
        caps=["text_generation", "summarization", "classification"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=68,
        tags=["saas_embedded", "no_code"])),
    ("clickup", "clickup-brain", entry(
        "clickup-brain", "ClickUp Brain", "clickup", "agent",
        desc="AI assistant embedded in ClickUp project management.",
        domains=["clickup.com"],
        api=["api.clickup.com/api/v2"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=64,
        tags=["saas_embedded", "productivity"])),
    ("asana", "asana-ai", entry(
        "asana-ai", "Asana AI", "asana", "agent",
        desc="AI smart fields, goals, and status updates inside Asana.",
        domains=["asana.com"],
        api=["app.asana.com/api/1.0"],
        caps=["text_generation", "summarization", "classification"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=68,
        tags=["saas_embedded", "productivity"])),
    ("linear", "linear-ai", entry(
        "linear-ai", "Linear AI", "linear", "agent",
        desc="AI summarisation and triage inside Linear issue tracker.",
        domains=["linear.app"],
        api=["api.linear.app"],
        caps=["summarization", "classification"], ins=["text"], outs=["text"],
        sens="medium", cap_lvl="low", trust=70,
        tags=["saas_embedded", "engineering"])),
    ("loom", "loom-ai", entry(
        "loom-ai", "Loom AI", "loom", "agent",
        desc="Auto-transcription + summarisation of Loom video recordings.",
        domains=["loom.com"],
        caps=["speech_to_text", "summarization"], ins=["video"], outs=["text"],
        sens="high", cap_lvl="medium", trust=70,
        tags=["saas_embedded", "video"])),

    # --- Note-taking AI ---
    ("mem", "mem-ai", entry(
        "mem-ai", "Mem", "mem", "agent",
        desc="AI-powered note-taking application.",
        domains=["mem.ai"],
        caps=["text_generation", "summarization", "embedding"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=58,
        tags=["note_taking"])),
    ("reflect", "reflect-ai", entry(
        "reflect-ai", "Reflect", "reflect", "agent",
        desc="Networked notes app with GPT-4 AI assistant.",
        domains=["reflect.app"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=58,
        tags=["note_taking"])),
    ("tana", "tana-ai", entry(
        "tana-ai", "Tana", "tana", "agent",
        desc="AI-powered knowledge-graph note app.",
        domains=["tana.inc"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=56,
        tags=["note_taking"])),
    ("saner", "saner-ai", entry(
        "saner-ai", "Saner.AI", "saner", "agent",
        desc="AI personal assistant for ADHD support.",
        domains=["saner.ai"],
        caps=["text_generation", "summarization"], ins=["text"], outs=["text"],
        sens="high", cap_lvl="medium", trust=42,
        tags=["personal_assistant"])),
]


def main() -> None:
    written = 0
    for provider_slug_for_dir, _slug, body in ENTRIES:
        # provider directory = the first element
        pdir = ROOT / provider_slug_for_dir
        pdir.mkdir(parents=True, exist_ok=True)
        target = pdir / f"{body['id']}.yaml"
        if target.exists():
            continue
        lines = []
        for k, v in body.items():
            if isinstance(v, bool):
                lines.append(f"{k}: {'true' if v else 'false'}")
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{k}: []")
                else:
                    if all(isinstance(x, str) and " " not in x and ":" not in x and "/" not in x and "-" not in x[0:1] for x in v) and len(v) <= 8:
                        # short flat list — but '-' in identifier is fine; use block style for safety
                        lines.append(f"{k}:")
                        for item in v:
                            lines.append(f"  - {item}")
                    else:
                        lines.append(f"{k}:")
                        for item in v:
                            lines.append(f"  - {item}")
            elif isinstance(v, dict):
                lines.append(f"{k}:")
                for kk, vv in v.items():
                    lines.append(f"  {kk}: {vv}")
            elif isinstance(v, int):
                lines.append(f"{k}: {v}")
            else:
                sv = str(v)
                if ":" in sv or "#" in sv or sv.startswith(" ") or "'" in sv:
                    sv = '"' + sv.replace('"', '\\"') + '"'
                lines.append(f"{k}: {sv}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
    print(f"wrote {written} new catalogue entries (skipped existing)")


if __name__ == "__main__":
    main()
